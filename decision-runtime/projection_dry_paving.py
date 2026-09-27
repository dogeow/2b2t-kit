"""Exact-cell, dry Y63 paving for the verified full courtyard projection.

This module is deliberately not wired into a job. A caller must explicitly name
one to four cells and own a live MaterialClient lease. No pond, buried fill,
farmland, torch, ore, protected column, or broad region is an excavation target.
The stable per-cell journal prevents replay after an uncertain native action.
"""
from collections import Counter
from contextlib import contextmanager
import fcntl
import hashlib
import math
from pathlib import Path
import time
from types import MappingProxyType

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projection_completion import block_state
from drop_collection import collect_drop
from work_access import approach_faces, ApproachUnavailable


class PavingBlocked(RuntimeError):
    """A current observation does not authorize this cell."""


class PavingPending(PavingBlocked):
    """An earlier uncertain action needs inspection, never replay."""


# These are the 79 occupied paving cells in the 1706/3701 full audit from
# material-job-1d24a5d0-94dc-457a-9c42-b28f3852232f. The two rear rows
# are spelled out as exact X sets; no box/range is authorized for clearing.
_REAR_BRICKS_X = (
    760984, 760985, 760986, 760988, 760989, 760990, 760991,
    760993, 760994, 760995, 760996, 760998, 760999, 761000, 761001,
    761003, 761004, 761005, 761006, 761008, 761009, 761010, 761011,
    761013, 761014, 761015, 761016, 761018, 761019, 761020, 761021,
)
_REAR_ANDESITE_X = (760987, 760992, 760997, 761002, 761007, 761012, 761017)
_GRASS = 'Block{minecraft:grass_block}[snowy=false]'
PINNED_CONFLICTS = MappingProxyType({
    **{(x, 63, z): ('Block{minecraft:stone_bricks}',
                       'Block{minecraft:dirt}' if (x, z) == (761011, 797829) else _GRASS)
       for z in (797828, 797829) for x in _REAR_BRICKS_X},
    **{(x, 63, z): ('Block{minecraft:polished_andesite}', _GRASS)
       for z in (797828, 797829) for x in _REAR_ANDESITE_X},
    (760996, 63, 797861): ('Block{minecraft:stone_bricks}', _GRASS),
    (760997, 63, 797862): ('Block{minecraft:stone_bricks}', _GRASS),
    (760995, 63, 797863): ('Block{minecraft:stone_bricks}', _GRASS),
})
assert len(PINNED_CONFLICTS) == 79

SITE = MappingProxyType({
    'server': 'simpcraft.com',
    'dimension': 'minecraft:overworld',
    'name': '晴庭-完整前后庭院',
    'bounds': MappingProxyType({'min': (760982, 61, 797819), 'max': (761023, 70, 797865)}),
    'total': 3701,
    # SHA256 of current-task.json/current_projection/placement_key. This pins
    # the eight selected subregions, not just their much larger outer box.
    'placement_key_sha256': '40462f3f2f219165150ea4105abca3812fc2669806365bc3e9b18c2486762fdd',
    'protected_xz': (
        (760986, 761019, 797831, 797847),  # house, all heights
        (761008, 761023, 797848, 797854),  # warehouse and work aisle
        (761012, 761018, 797858, 797864),  # birch tree and canopy padding
    ),
    'pinned_conflicts': PINNED_CONFLICTS,
})
PAVING = {'minecraft:stone_bricks', 'minecraft:polished_andesite'}
NATURAL_SURFACE = {'minecraft:stone', 'minecraft:andesite', 'minecraft:grass_block', 'minecraft:dirt'}
NATURAL_SUPPORT = NATURAL_SURFACE
DROPS = {
    'minecraft:stone': {'minecraft:cobblestone', 'minecraft:stone'},
    'minecraft:andesite': {'minecraft:andesite'},
    'minecraft:grass_block': {'minecraft:dirt', 'minecraft:grass_block'},
    'minecraft:dirt': {'minecraft:dirt'},
}
AIR = {'Block{minecraft:air}', 'Block{minecraft:cave_air}', 'Block{minecraft:void_air}'}


def _position(pos):
    if not isinstance(pos, (list, tuple)) or len(pos) != 3 or any(type(v) is not int for v in pos):
        raise PavingBlocked('Paving requires one exact integer XYZ cell')
    return tuple(pos)


def _block(value):
    try:
        return block_state(value)[0]
    except (KeyError, TypeError, ValueError) as error:
        raise PavingBlocked('Unrecognized block state') from error


def _server(value):
    return value.removesuffix(':25565') if isinstance(value, str) else ''


def _protected(pos, site):
    x, _, z = pos
    # A one-column buffer protects adjacent attachments and foundation edges.
    return any(x1 - 1 <= x <= x2 + 1 and z1 - 1 <= z <= z2 + 1
               for x1, x2, z1, z2 in site['protected_xz'])


def _counts(state):
    return inventory_counts(state)


def _safe_state(client, state, site):
    if type(state.get('dry_paving_protocol')) is not int or state['dry_paving_protocol'] != 1:
        raise PavingBlocked('The active Kit mod does not support guarded dry paving')
    if (not state.get('connected') or state.get('world_session') != client.world
            or _server(state.get('server')) != site['server']
            or state.get('dimension') != site['dimension']
            or state.get('screen') != '' or state.get('manual_movement')
            or state.get('health', 0) < 19 or state.get('food', 0) < 10
            or not state.get('guard_armed') or not state.get('guard_pve_only')
            or state.get('guard_busy') or not state.get('flight')
            or state.get('under_water') or state.get('air_return_active')
            or state.get('safety_hold', {}).get('active')
            or state.get('build_job', {}).get('active')
            or state.get('professional_printer', {}).get('waiting_for_server')):
        raise PavingBlocked('World, control, flight, or safety state is not ready')
    lease = state.get('supervision_lease') or {}
    if not getattr(client, 'task', None) or lease.get('kind') != 'materials' or lease.get('job_session') != client.task:
        raise PavingBlocked('An owned material session is required')
    selection = state.get('projection_selection') or {}
    key = selection.get('key', '')
    if (tuple(selection.get('min') or ()) != tuple(site['bounds']['min'])
            or tuple(selection.get('max') or ()) != tuple(site['bounds']['max'])
            or hashlib.sha256(key.encode()).hexdigest() != site['placement_key_sha256']):
        raise PavingBlocked('The selected eight-region courtyard projection changed')
    return key


def _fresh_context(client, site):
    state = client.status()
    key = _safe_state(client, state, site)
    model_reply = client.request('projection_model')
    audit_reply = client.request('projection_audit')
    state = client.status()
    if _safe_state(client, state, site) != key:
        raise PavingBlocked('Projection changed during full audit')
    if (model_reply.get('world_session') != client.world or audit_reply.get('world_session') != client.world
            or model_reply.get('phase') not in (None, 'done')
            or audit_reply.get('phase') not in (None, 'done')):
        raise PavingBlocked('Full projection observations are not from this world session')
    model = model_reply.get('projection_model') or {}
    audit = audit_reply.get('projection_audit') or {}
    bounds = model.get('bounds') or {}
    if (model.get('placement_key') != key
            or tuple(bounds.get('min') or ()) != tuple(site['bounds']['min'])
            or tuple(bounds.get('max') or ()) != tuple(site['bounds']['max'])
            or model.get('loaded_chunks_verified') is not True
            or model.get('total') != site['total'] or not model.get('content_hash')
            or not isinstance(model.get('expected'), list) or len(model['expected']) != site['total']
            or audit.get('placement_key') != key or audit.get('name') != site['name']
            or _server(audit.get('server')) != site['server'] or audit.get('dimension') != site['dimension']
            or audit.get('audit_schema', 0) < 2 or audit.get('loaded_chunks_verified') is not True
            or audit.get('total') != site['total'] or not isinstance(audit.get('mismatches'), list)
            or audit.get('matched', -1) + len(audit['mismatches']) != site['total']
            or audit.get('enclosed_air_conflicts') != []):
        raise PavingBlocked('Current complete courtyard model or audit is unverified')
    for observed in (model.get('observed_at'), audit.get('observed_at')):
        if type(observed) is not int or abs(state.get('time', 0) - observed) > 5000:
            raise PavingBlocked('Current projection evidence is stale')
    return state, model, audit


def _target(model, audit, pos, site, *, air=False):
    pinned = site['pinned_conflicts'].get(pos)
    if pinned is None:
        raise PavingBlocked('Cell was not a verified conflict in the saved full-yard audit')
    expected = [row for row in model['expected'] if row.get('pos') == list(pos)]
    if (len(expected) != 1 or expected[0].get('state') != pinned[0]
            or _block(expected[0].get('state')) not in PAVING or pos[1] != 63):
        raise PavingBlocked('Cell is not an exact Y63 dry paving model target')
    wanted = expected[0]['state']
    mismatches = [row for row in audit['mismatches'] if row.get('pos') == list(pos)]
    if len(mismatches) != 1 or mismatches[0].get('expected') != wanted:
        raise PavingBlocked('Audit does not contain this exact unfinished model cell')
    row = mismatches[0]
    if air:
        if row.get('kind') != 'missing' or row.get('actual') not in AIR:
            raise PavingBlocked('Excavated cell is no longer verified air')
    elif (row.get('kind') != 'occupied' or row.get('actual') != pinned[1]
          or _block(row.get('actual')) not in NATURAL_SURFACE
          or row.get('block_entity') is not False or row.get('fluid') is not False
          or row.get('adjacent_fluid') is not False or row.get('neighbors_loaded') is not True):
        raise PavingBlocked('Occupied cell is not verified dry ordinary terrain')
    return row


def _scan(client, pos):
    low = [pos[0] - 1, 62, pos[2] - 1]
    high = [pos[0] + 1, 65, pos[2] + 1]
    reply = client.request('scan', min=low, max=high, details=True)
    if (reply.get('phase') not in (None, 'done') or reply.get('world_session') != client.world
            or not isinstance(reply.get('blocks'), list)):
        raise PavingBlocked('Detailed support and neighbor scan is incomplete')
    cells = {}
    for row in reply['blocks']:
        p = _position(row.get('pos'))
        if p in cells or any(p[i] < low[i] or p[i] > high[i] for i in range(3)):
            raise PavingBlocked('Detailed scan contains duplicate or outside cells')
        cells[p] = row
    return cells


def _geometry(cells, pos, actual):
    target = cells.get(pos)
    if actual in AIR:
        if target is not None:
            raise PavingBlocked('Target is not confirmed air')
    elif (target is None or target.get('state') != actual or target.get('solid') is not True
          or target.get('fluid') is not False or target.get('block_entity') is not False):
        raise PavingBlocked('Natural target changed or has unsafe block properties')
    support_pos = (pos[0], 62, pos[2])
    support = cells.get(support_pos)
    if (support is None or _block(support.get('state')) not in NATURAL_SUPPORT
            or support.get('solid') is not True or support.get('fluid') is not False
            or support.get('block_entity') is not False):
        raise PavingBlocked('Dry natural support below the paving cell is unverified')
    if any(cells.get((pos[0], y, pos[2])) is not None for y in (64, 65)):
        raise PavingBlocked('Paving body column is occupied')
    if any(row.get('fluid') is not False or row.get('block_entity') is not False
           for row in cells.values()):
        raise PavingBlocked('Fluid or block entity lies in the neighbor scan')
    for dx, dz in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        for y in (63, 64):
            neighbor = cells.get((pos[0] + dx, y, pos[2] + dz))
            if neighbor is not None and neighbor.get('solid') is not True:
                raise PavingBlocked('Nearby non-solid feature may depend on this surface')
    return support


def _entities(state, pos):
    player = state.get('pos')
    if (not isinstance(player, list) or len(player) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in player)
            or math.dist(player, [pos[0] + .5, pos[1] + .5, pos[2] + .5]) > 12
            or not isinstance(state.get('entities'), list)):
        # Native status covers only rendered entities within 16 blocks of the
        # actor. The 12-block bound leaves room for our four-block work ring.
        raise PavingBlocked('Passive-entity coverage near this cell is unverified')
    for entity in state['entities']:
        p = entity.get('pos')
        if not isinstance(p, list) or len(p) != 3 or entity.get('type') is None:
            raise PavingBlocked('Nearby entity observation is malformed')
        if math.dist(p, [pos[0] + .5, pos[1] + .5, pos[2] + .5]) <= 4:
            raise PavingBlocked('An animal, player, or unowned drop is near this cell')


def _stock_and_tool(state, actual, expected):
    wanted = _block(expected)
    if _counts(state)[wanted] < 1:
        raise PavingBlocked('Replacement block is not held in the inventory')
    if not any(row.get('slot', 99) < 36 and row.get('count') == 0 for row in state.get('inventory', [])):
        raise PavingBlocked('One empty inventory slot is required for the drop')
    kind = 'shovel' if _block(actual) in ('minecraft:dirt', 'minecraft:grass_block') else 'pickaxe'
    tools = [row for row in state.get('inventory', []) if 0 <= row.get('slot', 99) < 36
             and row.get('item') in ('minecraft:diamond_' + kind, 'minecraft:netherite_' + kind)
             and row.get('count', 0) == 1 and row.get('durability', 0) >= 64]
    if not tools:
        raise PavingBlocked('A durable matching shovel or pickaxe is required')
    return max(tools, key=lambda row: row['durability'])


def _cell_check(client, site, pos, *, air=False, source=None, require_tool=False):
    state, model, audit = _fresh_context(client, site)
    if _protected(pos, site):
        raise PavingBlocked('Protected house, warehouse, or birch-tree buffer')
    if (not air and state.get('on_ground')
            and (math.floor(state['pos'][0]), math.floor(state['pos'][1]) - 1,
                 math.floor(state['pos'][2])) == pos):
        raise PavingBlocked('The player is standing on this paving cell')
    row = _target(model, audit, pos, site, air=air)
    if source is not None and (row['expected'] != source['expected']
                               or not air and row['actual'] != source['actual']):
        raise PavingBlocked('Target changed since the recorded intent')
    cells = _scan(client, pos)
    support = _geometry(cells, pos, row['actual'])
    if require_tool:
        tool = _stock_and_tool(state, row['actual'], row['expected'])
    else:
        tool = None
        if _counts(state)[_block(row['expected'])] < 1:
            raise PavingBlocked('Replacement block is no longer held')
    _entities(state, pos)
    return state, model, row, support, tool


def _journal_path(client, site, pos):
    world = hashlib.sha256((site['server'] + '\0' + site['dimension']).encode()).hexdigest()[:20]
    return Path(client.root) / 'dry-paving-v1' / world / ('%d_%d_%d.json' % pos)


@contextmanager
def _batch_lock(client):
    directory = Path(client.root) / 'dry-paving-v1'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.batch.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _load_journal(path, site, pos, key, model_hash):
    if not path.exists():
        return None
    import json
    record = json.loads(path.read_text(encoding='utf-8'))
    if (record.get('schema') != 1 or record.get('pos') != list(pos)
            or record.get('server') != site['server'] or record.get('dimension') != site['dimension']
            or record.get('placement_key') != key or record.get('model_hash') != model_hash
            or (record.get('expected'), record.get('actual')) != site['pinned_conflicts'].get(pos)
            or record.get('phase') not in ('mine_intent', 'mined', 'pickup_intent',
                                           'recovered', 'place_intent', 'complete')):
        raise PavingPending('Existing cell journal belongs to another projection; inspect it')
    return record


def _record(path, record, phase, **evidence):
    record = {**record, 'phase': phase, 'updated_at_ns': time.time_ns(),
              'receipts': [*record.get('receipts', []), {'phase': phase, **evidence}]}
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, record)
    return record


def _drop(client, pos, source, before, path, record):
    state = client.status()
    player = state.get('pos')
    center = [pos[0]+.5, pos[1]+.5, pos[2]+.5]
    if (not isinstance(player, list) or len(player) != 3
            or math.dist(player, center) > 12 or not isinstance(state.get('entities'), list)):
        raise PavingPending('Drop and passive-entity coverage was lost after mining')
    nearby = [e for e in state['entities'] if isinstance(e.get('pos'), list)
              and len(e['pos']) == 3 and math.dist(e['pos'], center) <= 4]
    if any(e.get('type') != 'minecraft:item' for e in nearby):
        raise PavingPending('An animal or player approached the excavated cell')
    allowed = DROPS[_block(source['actual'])]
    gained = {item: _counts(state)[item] - before[item] for item in allowed}
    if any(amount > 1 or amount < 0 for amount in gained.values()):
        raise PavingPending('Drop inventory changed by an unexpected amount')
    if any(e.get('uuid') in record['nearby_before'] or e.get('stack', {}).get('item') not in allowed
           or e.get('stack', {}).get('count') != 1 for e in nearby):
        raise PavingPending('Unexpected or unowned local item drop after mining')
    new_drops = [e for e in nearby if e.get('type') == 'minecraft:item'
                 and e.get('uuid') not in record['nearby_before']
                 and e.get('stack', {}).get('item') in allowed
                 and e.get('stack', {}).get('count') == 1]
    if len(new_drops) + sum(gained.values()) != 1:
        raise PavingPending('Excavation drop ownership is not uniquely confirmed')
    if new_drops:
        drop = new_drops[0]
        record = _record(path, record, 'pickup_intent', drop_uuid=drop['uuid'], item=drop['stack']['item'])
        if not collect_drop(client, drop, observation=state):
            raise PavingPending('Excavation drop pickup was not confirmed')
        after = client.status()
        if _counts(after)[drop['stack']['item']] != before[drop['stack']['item']] + 1:
            raise PavingPending('Collected drop inventory did not match the original cell')
        item = drop['stack']['item']
    else:
        item = next(item for item, amount in gained.items() if amount == 1)
    return _record(path, record, 'recovered', item=item, inventory_after=_counts(client.status())[item])


def _place(client, site, pos, path, record, *, settle):
    state, model, row, support, _ = _cell_check(client, site, pos, air=True)
    if (record['world_session'] != client.world or record['expected'] != row['expected']
            or record['model_hash'] != model['content_hash']):
        raise PavingPending('Recovered cell belongs to another world session or model')
    support_pos = [pos[0], 62, pos[2]]
    item = _block(row['expected'])
    client.checked('select_item', item=item)
    try:
        approach_faces(client, support_pos, support['state'], ('up',), stand_distance=2.4)
    except ApproachUnavailable as error:
        raise PavingBlocked('No verified dry support-face approach; recovered cell stays pending') from error
    state, _, row, support, _ = _cell_check(client, site, pos, air=True)
    if state.get('hand', {}).get('item') != item:
        raise PavingBlocked('Replacement is not in the selected hand')
    before = _counts(state)[item]
    record = _record(path, record, 'place_intent', support_state=support['state'], material_before=before)
    reply = client.request('interact', pos=support_pos, face='up',
                           expected_state=support['state'], expected_hand=item,
                           dry_paving_guard=True)
    if reply.get('phase') != 'done':
        raise PavingPending('Placement reply is uncertain; do not send another click')
    settle(.8)
    observed = _scan(client, pos).get(pos)
    after = client.status()
    if (observed is None or observed.get('state') != row['expected']
            or _counts(after)[item] != before - 1):
        raise PavingPending('Server block or inventory did not confirm the placement')
    _, _, audit = _fresh_context(client, site)
    if any(r.get('pos') == list(pos) for r in audit['mismatches']):
        raise PavingPending('Full projection audit still disagrees after placement')
    _record(path, record, 'complete', actual=row['expected'], material_after=_counts(after)[item])
    return {'pos': list(pos), 'result': 'placed', 'expected': row['expected']}


def _one(client, site, pos, *, settle):
    state, model, audit = _fresh_context(client, site)
    if _protected(pos, site):
        raise PavingBlocked('Protected house, warehouse, or birch-tree buffer')
    path = _journal_path(client, site, pos)
    record = _load_journal(path, site, pos, state['projection_selection']['key'], model['content_hash'])
    if record is not None:
        if record['phase'] == 'complete':
            if (any(r.get('pos') == list(pos) for r in audit['mismatches'])
                    or len([r for r in model['expected'] if r.get('pos') == list(pos)
                            and r.get('state') == record['expected']]) != 1):
                raise PavingPending('Previously completed paving was changed; preserve the player edit')
            return {'pos': list(pos), 'result': 'already_complete', 'expected': record['expected']}
        if record['phase'] == 'recovered':
            return _place(client, site, pos, path, record, settle=settle)
        raise PavingPending('Existing uncertain paving intent must be inspected; no action repeated')
    model_hash = model['content_hash']
    row = _target(model, audit, pos, site)
    _geometry(_scan(client, pos), pos, row['actual'])
    tool = _stock_and_tool(state, row['actual'], row['expected'])
    client.checked('select_item', item=tool['item'], slot=tool['slot'])
    approach_faces(client, list(pos), row['actual'], ('up',), stand_distance=2.4)
    state, model, row, support, tool = _cell_check(client, site, pos, source=row, require_tool=True)
    if model['content_hash'] != model_hash:
        raise PavingBlocked('Projection model changed during approach')
    if (state.get('hand', {}).get('item') != tool['item']
            or state.get('hand', {}).get('durability', 0) < 64):
        raise PavingBlocked('Mining tool is not in the selected hand')
    before = Counter(_counts(state))
    record = _record(path, {'schema': 1, 'server': site['server'], 'dimension': site['dimension'],
                            'placement_key': state['projection_selection']['key'],
                            'model_hash': model['content_hash'], 'world_session': client.world,
                            'pos': list(pos), 'actual': row['actual'], 'expected': row['expected'],
                            'nearby_before': [e['uuid'] for e in state['entities']], 'receipts': []},
                     'mine_intent', support_state=support['state'], tool=tool['item'],
                     replacement_before=before[_block(row['expected'])])
    reply = client.request('mine_block', pos=list(pos), face='up',
                           expected_state=row['actual'], seconds=20,
                           dry_paving_guard=True)
    if reply.get('phase') != 'done':
        raise PavingPending('Mining reply is uncertain; do not repeat the excavation')
    settle(.8)
    if _scan(client, pos).get(pos) is not None:
        raise PavingPending('Server did not confirm air after the one mining request')
    record = _record(path, record, 'mined', old_state=row['actual'], server_air=True)
    record = _drop(client, pos, row, before, path, record)
    return _place(client, site, pos, path, record, settle=settle)


def pave_batch(client, positions, *, settle=time.sleep, on_cell_complete=None):
    """Run only explicitly named cells; never discover or expand a clearing area.

    This function is intentionally unused by the current material backend.
    A recovered cell may resume placement; uncertain mining/pickup/placement
    stages remain held for review. A completed cell is read-only verified.
    """
    if not isinstance(positions, (list, tuple)) or not 1 <= len(positions) <= 4:
        raise PavingBlocked('A paving batch must name one to four exact cells')
    points = [_position(pos) for pos in positions]
    if len(set(points)) != len(points):
        raise PavingBlocked('Repeated cell in a paving batch')
    with _batch_lock(client):
        results = []
        for pos in points:
            result = _one(client, SITE, pos, settle=settle)
            if on_cell_complete is not None:
                # The caller can durably publish this one confirmed cell before
                # a later cell in the same batch encounters a handoff or hold.
                on_cell_complete(result)
            results.append(result)
        return results
