"""Repair only newly observed wrong placements, checking live state and recovering drops."""
from collections import Counter
import math
import time

from material_plan import inventory_counts
from safety_interlock import require_unlocked
from work_access import approach_faces,ApproachUnavailable
from drop_collection import collect_drop


AIR = {'Block{minecraft:air}', 'Block{minecraft:cave_air}', 'Block{minecraft:void_air}'}


def observed_errors(before, after, wrong_state):
    if before['placement_key'] != after['placement_key']:
        raise ValueError('Projection changed between placement observations')
    old = {tuple(row['pos']): row for row in before['mismatches']}
    result = []
    for row in after['mismatches']:
        previous = old.get(tuple(row['pos']))
        if previous and previous['expected'] == row['expected'] and previous['actual'] in AIR and row['actual'] == wrong_state:
            result.append({'pos': row['pos'], 'expected': row['expected'], 'wrong_state': wrong_state})
    if len(result) > 16:
        raise ValueError('Repair batch exceeds the bounded incident size')
    return result


def recover_drops(client, item, before_count, count, sites):
    for _ in range(12):
        state = client.status()
        drops = [e for e in state.get('entities', []) if e.get('type') == 'minecraft:item'
                 and e.get('stack', {}).get('item') == item
                 and any(sum((a-b)**2 for a,b in zip(e['pos'], site)) < 100 for site in sites)]
        if not drops:
            return inventory_counts(state)[item] >= before_count + count
        drop = min(drops, key=lambda e: sum((a-b)**2 for a,b in zip(e['pos'],state['pos'])))
        if not collect_drop(client,drop,observation=state,seconds=120):
            return False
        time.sleep(.4)
    return False


def repair(client, placement_key, errors, item='minecraft:oak_planks'):
    state = client.status();require_unlocked(client.root,state)
    before_count = inventory_counts(state)[item]
    removed = [];deferred=[]
    for error in errors:
        state = client.status();require_unlocked(client.root,state)
        current = client.request('projection_audit')['projection_audit']
        if current['placement_key'] != placement_key:
            raise RuntimeError('Placement changed; repair stopped')
        row = next((r for r in current['mismatches'] if r['pos']==error['pos']),None)
        if row is None or row['actual'] in AIR:
            continue
        if row['expected'] != error['expected'] or row['actual'] != error['wrong_state']:
            raise RuntimeError('Incident block changed; do not remove new player work')
        if row.get('block_entity') or row.get('fluid') or not row.get('neighbors_loaded') or row.get('adjacent_fluid') is not False:
            raise RuntimeError('Repair requires fresh dry non-container surroundings')
        client.checked('select_item',item='minecraft:diamond_axe')
        try:face=approach_faces(client,error['pos'],row['actual'],('down','west','east','north','south','up'),seconds=120)
        except ApproachUnavailable:
            deferred.append(error['pos']);continue
        client.checked('mine_block',pos=error['pos'],face=face,expected_state=row['actual'],seconds=20)
        time.sleep(.4)
        if client.request('scan',min=error['pos'],max=error['pos']).get('blocks'):
            raise RuntimeError('Block removal not observed; do not repeat blindly')
        removed.append(error['pos'])
    recovered = recover_drops(client,item,before_count,len(removed),[e['pos'] for e in errors])
    # Tool selection may have borrowed the bow's hotbar slot. Restore the best bow explicitly.
    state = client.status()
    bows = [v for v in state['inventory'] if v['item']=='minecraft:bow' and v.get('durability',0)>=64]
    if bows:
        bow=max(bows,key=lambda v:v['durability'])
        if bow['slot']!=5:
            slot=bow['slot'] if bow['slot']>=9 else bow['slot']+36
            client.checked('slot_click',menu_id=0,slot=slot,expected_item='minecraft:bow',expected_count=1,kind='swap',button=5)
    if not recovered:
        raise RuntimeError('Removed blocks still have uncollected drops; inspect before leaving')
    return {'removed':removed,'items_recovered':inventory_counts(client.status())[item]-before_count,
            'expected_drops':len(removed),'recovered':recovered,'deferred':deferred}
