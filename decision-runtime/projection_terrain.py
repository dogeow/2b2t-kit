"""Bounded terrain clearance for a freshly audited, selected projection.

Only natural terrain in design-conflicting cells is removed. Navigation, mining,
server confirmation and manual/safety takeover remain owned by the native Kit.
"""
from collections import Counter
import json
import math
import time

from material_plan import inventory_counts
from projection_completion import block_state, repair_plan
from safety_interlock import require_unlocked
from ground_pickup import collect_nearby_ground
from drop_collection import collect_drop
from work_access import approach_faces,ApproachUnavailable

FACES = {'up': (0, 1, 0), 'west': (-1, 0, 0), 'east': (1, 0, 0),
         'north': (0, 0, -1), 'south': (0, 0, 1), 'down': (0, -1, 0)}
NO_ACCESS = {'No visible collision-free depot approach',
             'No loaded collision-free route to this depot; no ceiling is broken'}


def candidates(audit, state, reserved=None):
    selection = state['projection_selection']
    plan = repair_plan(audit, selection)
    if not plan['interior_air_checked'] or abs(state['time'] - audit.get('observed_at', 0)) > 5000:
        raise RuntimeError('Terrain removal requires a fresh loaded enclosure audit')
    if audit.get('server') != state.get('server') or audit.get('dimension') != state.get('dimension'):
        raise RuntimeError('Terrain audit belongs to another world')
    stock = inventory_counts(state)
    reserved = reserved or {}
    result = []
    for row in plan['groups'].get('terrain_clear_candidate', []):
        if row.get('block_entity') or row.get('fluid') or row.get('adjacent_fluid') is not False or not row.get('neighbors_loaded'):
            continue
        expected, _ = block_state(row['expected'])
        if expected != 'minecraft:air' and stock[expected] - reserved.get(expected, 0) <= 0:
            continue
        if state.get('on_ground') and row['pos'] == [math.floor(state['pos'][0]), math.floor(state['pos'][1])-1, math.floor(state['pos'][2])]:
            continue
        result.append(row)
    return sorted(result, key=lambda row: (-row['pos'][1], sum((a-b)**2 for a,b in zip(row['pos'], state['pos']))))


def exposed_faces(pos, detailed_rows):
    observed = {tuple(r['pos']): r for r in detailed_rows}
    return [face for face, delta in FACES.items()
            if (r := observed.get(tuple(a+b for a,b in zip(pos, delta)))) is None
            or (r.get('passable') is True or r.get('solid') is False) and r.get('fluid') is False]


def accessible_room_order(rows, observed, player):
    """Complete adjacent vertical air pairs before cutting another one-block-high pocket."""
    cells={tuple(r['pos']):r for r in observed}
    def key(row):
        expected,_=block_state(row['expected'])
        pair=False
        if expected in ('minecraft:air','minecraft:ladder'):
            x,y,z=row['pos']
            for dy in (-1,1):
                cell=cells.get((x,y+dy,z))
                pair|=cell is None or cell.get('passable') is True and not cell.get('fluid')
        return (not pair,sum((a-b)**2 for a,b in zip(row['pos'],player)))
    return sorted(rows,key=key)

def footer_headroom(pos,cells):
    x,y,z=pos
    for dy in (1,2):
        header=cells.get((x,y+dy,z))
        if header and (header.get('fluid') or not header.get('passable') and not header['state'].startswith('Block{minecraft:ladder}')):
            return False
    return True


def clear_batch(client, limit=8):
    if not 1 <= limit <= 16:
        raise ValueError('Terrain batch must contain 1 to 16 blocks')
    removed, deferred = [], set()
    uncertain=set(getattr(client,'uncertain_terrain_positions',set()))
    reserved = Counter()
    while len(removed) < limit:
        state = client.status(); require_unlocked(client.root, state)
        if state.get('screen') or not state.get('flight'):
            raise RuntimeError('Terrain clearance requires a clear screen and verified flight')
        if not any(v.get('slot', 99) < 36 and not v['count'] for v in state['inventory']):
            break
        audit = client.request('projection_audit')['projection_audit']
        state = client.status()
        rows = [r for r in candidates(audit, state, reserved) if tuple(r['pos']) not in deferred|uncertain]
        if not rows:
            break
        low=[min(r['pos'][i] for r in rows)-(1 if i==1 else 0) for i in range(3)]
        high=[max(r['pos'][i] for r in rows)+(2 if i==1 else 0) for i in range(3)]
        observed=client.request('scan',min=low,max=high,details=True)['blocks']
        cells={tuple(r['pos']):r for r in observed}
        # Do not create a one-block-deep loot trap below an uncleared header.
        # The room above the lowest foundation layer must admit a standing player.
        lowest=state['projection_selection']['min'][1]
        for r in rows:
            x,y,z=r['pos']
            if y!=lowest:continue
            if not footer_headroom(r['pos'],cells):deferred.add(tuple(r['pos']))
        rows=[r for r in rows if tuple(r['pos']) not in deferred]
        if not rows:continue
        rows=accessible_room_order(rows,observed,state['pos'])
        row = rows[0]; pos = row['pos']
        region = client.request('scan', min=[v-1 for v in pos], max=[v+1 for v in pos], details=True)['blocks']
        actual = next((r for r in region if r['pos'] == pos), None)
        if not actual or actual['state'] != row['actual'] or actual.get('block_entity') or actual.get('fluid'):
            raise RuntimeError('Terrain changed after audit; do not replace player edits')
        block, _ = block_state(row['actual'])
        tool = 'minecraft:diamond_shovel' if block in ('minecraft:dirt', 'minecraft:grass_block') else 'minecraft:diamond_pickaxe'
        if client.status().get('hand',{}).get('item')!=tool:
            client.checked('select_item',item=tool)
        try:face=approach_faces(client,pos,row['actual'],exposed_faces(pos,region))
        except ApproachUnavailable:
            deferred.add(tuple(pos)); continue
        reply = client.request('mine_block', pos=pos, face=face, expected_state=row['actual'], seconds=20)
        if reply.get('phase') != 'done':
            if reply.get('phase')=='waiting' and reply.get('detail')=='mining target is occluded':
                uncertain.add(tuple(pos));client.uncertain_terrain_positions=uncertain
                observed=client.request('scan',min=pos,max=pos)['blocks']
                with (client.out/'terrain-unconfirmed.jsonl').open('a') as stream:
                    stream.write(json.dumps({'pos':pos,'expected':row['expected'],'observed_after_stop':observed,'reason':reply['detail'],'policy':'skip this position for the rest of this session; do not replay mutation'})+'\n')
                continue
            raise RuntimeError(reply.get('detail', 'Mining not confirmed; do not replay'))
        # Re-observe after the server has had time to correct optimistic client air.
        time.sleep(.8)
        if client.request('scan', min=pos, max=pos)['blocks']:
            raise RuntimeError('Server still reports the terrain block; no movement into predicted air')
        removed.append({'pos': pos, 'old_state': row['actual'], 'expected': row['expected']})
        expected, _ = block_state(row['expected'])
        if expected != 'minecraft:air':
            reserved[expected] += 1
        with (client.out/'terrain-removals.jsonl').open('a') as stream:
            stream.write(json.dumps(removed[-1])+'\n')
    # Collect only observed local drops, and stop before starting another excavation batch.
    pickups = []
    for _ in range(20):
        state = client.status()
        drops = [e for e in state.get('entities', []) if e.get('type') == 'minecraft:item'
                 and any(sum((a-b)**2 for a,b in zip(e['pos'], r['pos'])) < 16 for r in removed)]
        if not drops: break
        drop = min(drops, key=lambda e: sum((a-b)**2 for a,b in zip(e['pos'], state['pos'])))
        if not collect_drop(client,drop,observation=state):
            raise RuntimeError('Excavation drop is not recovered; inspect before continuing')
        pickups.append(drop['uuid'])
    result = {'removed': removed, 'deferred': [list(p) for p in deferred], 'picked_up_entities': pickups,
              'replacement_reservations': dict(reserved), 'requires_reaudit_and_build': True}
    (client.out/'terrain-batch-latest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result
