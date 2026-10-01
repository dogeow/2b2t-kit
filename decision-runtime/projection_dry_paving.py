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
import json
import math
import os
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
    if type(state.get('dry_paving_protocol')) is not int or state['dry_paving_protocol'] != 2:
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


def _player_body_clear(state, pos):
    """Conservative standing-player envelope; the native guard checks the real AABB."""
    player = state.get('pos')
    if (not isinstance(player, list) or len(player) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in player)):
        return False
    # Normal native body is 0.6 blocks wide; retain clearance beyond its
    # half-width without rejecting a visible pose with a real 0.2-block gap.
    # The vertical 0.1 total margin still keeps a settled Y64.14 foot clear
    # above a Y63 destination while the native guard checks the exact AABB.
    body = ((player[0] - .35, player[0] + .35),
            (player[1] - .05, player[1] + 2),
            (player[2] - .35, player[2] + .35))
    destination = ((pos[0] - .1, pos[0] + 1.1),
                   (pos[1] - .05, pos[1] + 1.05),
                   (pos[2] - .1, pos[2] + 1.1))
    return any(own[1] <= target[0] or own[0] >= target[1]
               for own, target in zip(body, destination))


def _log_blocker(client, pos, phase, kind, state, nearby=()):
    # Keep identities and absolute entity/player positions out of advisor logs.
    event = {'at_ns': time.time_ns(), 'cell': list(pos), 'journal_phase': phase,
             'kind': kind, 'player_body_clear': _player_body_clear(state, pos),
             'nearby': list(nearby)}
    path = Path(client.out) / 'paving-blockers.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def _entities(state, pos, *, client=None, phase=None):
    player = state.get('pos')
    if (not isinstance(player, list) or len(player) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in player)
            or math.dist(player, [pos[0] + .5, pos[1] + .5, pos[2] + .5]) > 12
            or not isinstance(state.get('entities'), list)):
        # Native status covers only rendered entities within 16 blocks of the
        # actor. The 12-block bound leaves room for our four-block work ring.
        raise PavingBlocked('Passive-entity coverage near this cell is unverified')
    nearby = []
    for entity in state['entities']:
        p = entity.get('pos')
        if (not isinstance(p, list) or len(p) != 3 or not isinstance(entity.get('type'), str)
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in p)):
            raise PavingBlocked('Nearby entity observation is malformed')
        distance = math.dist(p, [pos[0] + .5, pos[1] + .5, pos[2] + .5])
        if distance <= 4:
            nearby.append({'type': entity['type'], 'distance_blocks': round(distance, 2)})
    if nearby:
        if client is not None:
            _log_blocker(client, pos, phase, 'nearby_entity', state, nearby)
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


def _cell_check(client, site, pos, *, air=False, source=None, require_tool=False,
                journal_phase=None):
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
    _entities(state, pos, client=client, phase=journal_phase)
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
                                           'recovered', 'drop_lost', 'place_intent', 'complete')):
        raise PavingPending('Existing cell journal belongs to another projection; inspect it')
    return record


def _record(path, record, phase, **evidence):
    record = {**record, 'phase': phase, 'updated_at_ns': time.time_ns(),
              'receipts': [*record.get('receipts', []), {'phase': phase, **evidence}]}
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, record)
    return record


def _record_transitions(path, record, transitions):
    """Durably publish a reconciled history without an intermediate phase."""
    receipts = list(record.get('receipts', []))
    for phase, evidence in transitions:
        receipts.append({'phase': phase, **evidence})
    updated = {**record, 'phase': transitions[-1][0],
               'updated_at_ns': time.time_ns(), 'receipts': receipts}
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, updated)
    return updated


def _confirmed_native_paving_reply(reply, *, stage, pos, state):
    """Require an exact post-send server block update, not a local action result."""
    if (reply.get('phase') != 'done'
            or reply.get('server_confirmed') is not True
            or reply.get('confirmation_scope') != 'matched_server_block_update_after_native_send'
            or reply.get('server_update_seen') is not True
            or reply.get('dry_paving_stage') != stage
            or reply.get('dry_paving_pos') != list(pos)
            or reply.get('server_observed_state') != state):
        raise PavingPending('Guarded paving lacks an exact server block confirmation')


def _paving_reply_receipt(reply):
    """Retain the exact native fields needed after a client scan lags the server."""
    return {key: reply.get(key) for key in (
        'id', 'world_session', 'control_revision', 'phase', 'server_confirmed',
        'confirmation_scope', 'server_update_seen', 'server_observed_state',
        'dry_paving_stage', 'dry_paving_pos')}


def _native_request_settled(client, state):
    """A stale or unacknowledged bridge request must not precede a rebind."""
    request_path = Path(client.root) / 'request.json'
    if not request_path.exists():
        return None
    try:
        request = json.loads(request_path.read_text(encoding='utf-8'))
        request_id = request['id']
        reply = json.loads((Path(client.root) / ('reply-' + request_id + '.json'))
                           .read_text(encoding='utf-8'))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise PavingPending('Native request completion is unverified') from error
    if (not isinstance(request_id, str) or not request_id
            or request_id != state.get('last_request')
            or request.get('world_session') != client.world
            or reply.get('id') != request_id
            or reply.get('world_session') != client.world
            or reply.get('control_revision') != state.get('control_revision')):
        raise PavingPending('A native request is pending or belongs to another session')
    return request_id


def _confirmed_recovered_journal(record):
    old_session = record.get('world_session')
    receipts = record.get('receipts')
    if (not isinstance(old_session, str) or not old_session
            or not isinstance(receipts, list)
            or not any(isinstance(r, dict) and r.get('phase') == 'mined'
                       and r.get('server_air') is True for r in receipts)
            or not any(isinstance(r, dict) and r.get('phase') == 'recovered'
                       and r.get('item') in DROPS[_block(record['actual'])]
                       and type(r.get('inventory_after')) is int
                       for r in receipts)
            or any(not isinstance(r, dict) or r.get('phase') in ('place_intent', 'complete')
                   for r in receipts)):
        raise PavingPending('Recovered journal lacks a confirmed excavation and pickup receipt')


def _confirmed_drop_lost_journal(record):
    receipts = record.get('receipts')
    if not isinstance(receipts, list) or any(not isinstance(row, dict) for row in receipts):
        raise PavingPending('Loss journal lacks a confirmed air hole and one-item loss receipt')
    mined = [(index, row) for index, row in enumerate(receipts)
             if row.get('phase') == 'mined']
    lost = [(index, row) for index, row in enumerate(receipts)
            if row.get('phase') == 'drop_lost'
            and row.get('event') != 'world_session_rebind']
    if (len(mined) != 1 or len(lost) != 1 or mined[0][0] >= lost[0][0]
            or mined[0][1].get('server_air') is not True
            or lost[0][1].get('item') != 'minecraft:grass_block'
            or lost[0][1].get('amount') != 1
            or not isinstance(lost[0][1].get('original_drop_uuid'), str)
            or not lost[0][1]['original_drop_uuid']
            or type(lost[0][1].get('inventory_unchanged')) is not int
            or lost[0][1]['inventory_unchanged'] < 0
            or any(row.get('phase') in ('pickup_intent', 'recovered', 'place_intent', 'complete')
                   for row in receipts)):
        raise PavingPending('Loss journal lacks a confirmed air hole and one-item loss receipt')


def _exact_item_drop(state, pos, allowed, previous):
    center = [pos[0] + .5, pos[1] + .5, pos[2] + .5]
    entities = state.get('entities')
    if not isinstance(entities, list):
        raise PavingPending('Drop entity evidence is unavailable')
    nearby = [entity for entity in entities
              if isinstance(entity, dict) and isinstance(entity.get('pos'), list)
              and len(entity['pos']) == 3
              and all(type(value) in (int, float) and math.isfinite(value)
                      for value in entity['pos'])
              and math.dist(entity['pos'], center) <= 4]
    if (len(nearby) != 1 or nearby[0].get('type') != 'minecraft:item'
            or nearby[0].get('uuid') in previous
            or not isinstance(nearby[0].get('uuid'), str)
            or nearby[0].get('stack', {}).get('item') not in allowed
            or nearby[0]['stack'].get('count') != 1):
        raise PavingPending('Original paving drop is not uniquely identified')
    return nearby[0]


def reconcile_mine_intent(client, pos, evidence, *, settle=time.sleep):
    """Promote one old mining intent from durable evidence, without mining again.

    This opt-in operation only changes the per-cell journal. The ordinary
    recovered-cell path must still rebind and verify the hole before placement.
    Legacy v1 mining requires a new world session, which reloads the chunk;
    a v2 native reply may instead prove the matching server block packet.
    """
    pos = _position(pos)
    if not isinstance(evidence, dict):
        raise PavingPending('Mining reconciliation evidence is missing')
    with _batch_lock(client):
        state, model, audit = _fresh_context(client, SITE)
        path = _journal_path(client, SITE, pos)
        record = _load_journal(path, SITE, pos, state['projection_selection']['key'],
                               model['content_hash'])
        if record is None or record['phase'] != 'mine_intent':
            raise PavingPending('Exact mining intent is unavailable for reconciliation')
        receipts = record.get('receipts')
        if (not isinstance(receipts, list) or not receipts
                or not isinstance(receipts[0], dict)
                or receipts[0].get('phase') != 'mine_intent'
                or type(receipts[0].get('replacement_before')) is not int
                or receipts[0]['replacement_before'] < 1
                or not isinstance(record.get('nearby_before'), list)):
            raise PavingPending('Original mining intent lacks stock or entity evidence')
        if _protected(pos, SITE):
            raise PavingPending('Protected paving cell cannot be reconciled')
        events = evidence.get('events')
        if not isinstance(events, list):
            raise PavingPending('Original mining event log is missing')
        matching = [event for event in events if isinstance(event, dict)
                    and event.get('op') == 'mine_block'
                    and (event.get('params') or {}).get('pos') == list(pos)]
        if len(matching) != 1:
            raise PavingPending('Original single mining request is not proven')
        event = matching[0]
        params = event.get('params') or {}
        if (event.get('world_session') != record['world_session']
                or event.get('phase') != 'done'
                or event.get('detail') != 'target removed'
                or event.get('evidence_scope') != 'native_operation_reply_not_goal_completion'
                or not isinstance(event.get('request_id'), str)
                or not event['request_id']
                or params.get('expected_state') != record['actual']
                or params.get('face') != 'up'
                or params.get('dry_paving_guard') is not True
                or type(event.get('revision_before')) is not int
                or event.get('revision_after') != event['revision_before'] + 1
                or any(other.get('op') == 'interact'
                       and (other.get('params') or {}).get('pos') ==
                       [pos[0], pos[1] - 1, pos[2]] for other in events
                       if isinstance(other, dict))):
            raise PavingPending('Original mining event does not match the cell intent')
        before = evidence.get('before_reply')
        after = evidence.get('after_reply')
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise PavingPending('Original pre/post mining observations are missing')
        before_blocks = [row for row in before.get('blocks', [])
                         if row.get('pos') == list(pos)]
        support_pos = [pos[0], pos[1] - 1, pos[2]]
        before_support = [row for row in before.get('blocks', [])
                          if row.get('pos') == support_pos]
        after_drops = _exact_item_drop(after, pos, DROPS[_block(record['actual'])],
                                       record['nearby_before'])
        drop_uuid = after_drops['uuid']
        if (before.get('world_session') != record['world_session']
                or after.get('world_session') != record['world_session']
                or type(before.get('time')) is not int
                or type(after.get('time')) is not int
                or type(event.get('time')) not in (int, float)
                or not before['time'] < event['time'] * 1000 < after['time']
                or len(before_blocks) != 1
                or before_blocks[0].get('state') != record['actual']
                or len(before_support) != 1
                or before_support[0].get('state') != receipts[0].get('support_state')
                or (before.get('supervision_lease') or {}).get('job_session') !=
                   params.get('task_session')
                or _counts(before)[_block(record['expected'])] !=
                   record['receipts'][0].get('replacement_before')
                or _counts(after)[_block(record['expected'])] !=
                   record['receipts'][0].get('replacement_before')):
            raise PavingPending('Original mining observations do not match the intent')
        drop_item = after_drops['stack']['item']
        original_count = _counts(before)[drop_item]
        if _counts(after)[drop_item] != original_count:
            raise PavingPending('Original drop inventory changed before pickup')
        native_reply = evidence.get('native_reply')
        if native_reply is None:
            if client.world == record['world_session']:
                raise PavingPending('Legacy mining requires a fresh world session and chunk reload')
            confirmation = 'legacy_rejoined_loaded_audit_and_exact_drop'
        else:
            stored_replies = [receipt.get('native_reply') for receipt in receipts
                              if isinstance(receipt, dict)
                              and receipt.get('phase') == 'mine_intent'
                              and isinstance(receipt.get('native_reply'), dict)]
            if (not isinstance(native_reply, dict)
                    or _paving_reply_receipt(native_reply) not in stored_replies
                    or native_reply.get('id') != event['request_id']
                    or native_reply.get('world_session') != record['world_session']
                    or native_reply.get('control_revision') != event['revision_after']):
                raise PavingPending('Original native mining reply does not match its request')
            _confirmed_native_paving_reply(native_reply, stage='mine', pos=pos,
                                           state='Block{minecraft:air}')
            confirmation = native_reply['confirmation_scope']
        pickup = evidence.get('pickup')
        loss = pickup is None and evidence.get('accept_one_original_drop_loss') is True
        pickup_event = None
        if isinstance(pickup, dict):
            pickup_before, pickup_event, pickup_after = (pickup.get('before'),
                                                         pickup.get('event'), pickup.get('after'))
            if not all(isinstance(value, dict) for value in
                       (pickup_before, pickup_event, pickup_after)):
                raise PavingPending('Exact original drop pickup receipt is incomplete')
            observed_drop = _exact_item_drop(pickup_before, pos, {drop_item},
                                             record['nearby_before'])
            if (observed_drop['uuid'] != drop_uuid
                    or pickup_event.get('op') != 'collect_item'
                    or pickup_event.get('phase') != 'done'
                    or pickup_event.get('world_session') != pickup_before.get('world_session')
                    or pickup_after.get('world_session') != pickup_before.get('world_session')
                    or (pickup_event.get('params') or {}).get('expected_uuid') != drop_uuid
                    or (pickup_event.get('params') or {}).get('expected_item') != drop_item
                    or pickup_event.get('inventory_delta') != {drop_item: 1}
                    or not isinstance(pickup_event.get('request_id'), str)
                    or not pickup_event['request_id']
                    or _counts(pickup_before)[drop_item] != original_count
                    or _counts(pickup_after)[drop_item] != original_count + 1
                    or any(entity.get('uuid') == drop_uuid
                           for entity in pickup_after.get('entities', [])
                           if isinstance(entity, dict))
                    or _counts(state)[drop_item] != original_count + 1):
                raise PavingPending('Exact original drop pickup or current inventory is unverified')
        elif loss:
            if (client.world == record['world_session']
                    or drop_item != 'minecraft:grass_block'
                    or _counts(state)[drop_item] != original_count):
                raise PavingPending('One-item loss requires a new session and unchanged grass stock')
        else:
            raise PavingPending('Exact original drop pickup or explicit one-item loss is required')
        if (_counts(state)[_block(record['expected'])] !=
                receipts[0]['replacement_before']):
            raise PavingPending('Replacement inventory changed before reconciliation')
        first = _target(model, audit, pos, SITE, air=True)
        _geometry(_scan(client, pos), pos, first['actual'])
        if loss:
            player = state.get('pos')
            if (not isinstance(player, list) or len(player) != 3
                    or math.dist(player, [pos[0]+.5, pos[1]+.5, pos[2]+.5]) > 12):
                _recovered_pre_approach(client, SITE, pos, record,
                                        allow_session_rebind=True)
        settle(.8)
        fresh, fresh_model, fresh_audit = _fresh_context(client, SITE)
        second = _target(fresh_model, fresh_audit, pos, SITE, air=True)
        support = _geometry(_scan(client, pos), pos, second['actual'])
        if loss:
            _entities(fresh, pos, client=client, phase='mine_intent')
        expected_drop_count = original_count if loss else original_count + 1
        if (fresh_model['content_hash'] != model['content_hash']
                or fresh_audit['observed_at'] <= audit['observed_at']
                or _counts(fresh)[drop_item] != expected_drop_count
                or _counts(fresh)[_block(record['expected'])] !=
                   receipts[0]['replacement_before']):
            raise PavingPending('Current loaded audit or recovered inventory changed')
        settled = _native_request_settled(client, client.status())
        mined = {'old_state': record['actual'], 'server_air': True,
                 'confirmation_scope': confirmation,
                 'native_request_id': event['request_id'],
                 'observed_world_session': client.world,
                 'audit_observed_at': fresh_audit['observed_at'],
                 'support_state': support['state'], 'settled_request_id': settled}
        if loss:
            _record_transitions(path, record, [
                ('mined', mined),
                ('drop_lost', {'item': drop_item, 'amount': 1,
                               'original_drop_uuid': drop_uuid,
                               'inventory_unchanged': original_count,
                               'observed_world_session': client.world,
                               'reason': 'Original drop not recovered after server chunk reload'})])
            return {'pos': list(pos), 'result': 'drop_lost', 'drop_uuid': drop_uuid,
                    'loss_count': 1, 'confirmation_scope': confirmation}
        _record_transitions(path, record, [
            ('mined', mined),
            ('recovered', {'item': drop_item, 'inventory_after': original_count + 1,
                           'drop_uuid': drop_uuid,
                           'pickup_request_id': pickup_event['request_id'],
                           'pickup_world_session': pickup_event['world_session']})])
        return {'pos': list(pos), 'result': 'recovered', 'drop_uuid': drop_uuid,
                'confirmation_scope': confirmation}


def _rebind_recovered(client, site, pos, path, record):
    """Revalidate one confirmed air hole after reconnect; never replay mining."""
    phase = record['phase']
    if phase == 'drop_lost':
        _confirmed_drop_lost_journal(record)
    else:
        _confirmed_recovered_journal(record)
    old_session = record['world_session']
    try:
        state, model, row, support, _ = _cell_check(
            client, site, pos, air=True, journal_phase=phase)
        fresh = client.status()
        if (_safe_state(client, fresh, site) != state['projection_selection']['key']
                or model['content_hash'] != record['model_hash']
                or row['expected'] != record['expected']
                or _counts(fresh)[_block(row['expected'])] < 1):
            raise PavingPending('Recovered cell or replacement changed across reconnect')
        _entities(fresh, pos, client=client, phase=phase)
        request_id = _native_request_settled(client, fresh)
    except PavingBlocked as error:
        raise PavingPending('Recovered cell cannot be safely rebound: ' + str(error)) from error
    return _record(path, {**record, 'world_session': client.world}, phase,
                   event='world_session_rebind', previous_world_session=old_session,
                   current_world_session=client.world, model_hash=model['content_hash'],
                   observed_air=True, support_state=support['state'],
                   replacement_count=_counts(fresh)[_block(row['expected'])],
                   settled_request_id=request_id)


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


def _clear_pose_columns(client, pos):
    """Observe the small air corridor used to leave an excavated paving cell."""
    low = [pos[0] - 2, pos[1] + 1, pos[2] - 2]
    high = [pos[0] + 2, pos[1] + 4, pos[2] + 2]
    reply = client.request('scan', min=low, max=high, details=True)
    if (reply.get('phase') not in (None, 'done') or reply.get('world_session') != client.world
            or not isinstance(reply.get('blocks'), list)):
        raise PavingBlocked('Safe paving approach corridor was not freshly scanned')
    occupied = set()
    for row in reply['blocks']:
        point = _position(row.get('pos'))
        if (point in occupied or any(point[i] < low[i] or point[i] > high[i]
                                     for i in range(3))):
            raise PavingBlocked('Safe paving approach scan is malformed')
        occupied.add(point)
    return occupied


def _clear_axis_route(occupied, site, pos, start, middle, finish, top_y):
    """Check every scanned column crossed by the conservative player envelope."""
    origin = (math.floor(start[0]), math.floor(start[1]))
    for before, after in ((start, start), (start, middle), (middle, finish)):
        if before[0] != after[0] and before[1] != after[1]:
            return False
        x1 = math.floor(min(before[0], after[0]) - .5)
        x2 = math.ceil(max(before[0], after[0]) + .5) - 1
        z1 = math.floor(min(before[1], after[1]) - .5)
        z2 = math.ceil(max(before[1], after[1]) + .5) - 1
        if (x1 < pos[0] - 2 or x2 > pos[0] + 2
                or z1 < pos[2] - 2 or z2 > pos[2] + 2):
            return False
        if any((x, y, z) in occupied for x in range(x1, x2 + 1)
               for z in range(z1, z2 + 1)
               for y in range(pos[1] + 1, top_y + 1)):
            return False
        # The actor may already be in a protected buffer; do not route deeper
        # through it while leaving this one excavated cell.
        for x in range(math.floor(min(before[0], after[0])),
                       math.floor(max(before[0], after[0])) + 1):
            for z in range(math.floor(min(before[1], after[1])),
                           math.floor(max(before[1], after[1])) + 1):
                if (x, z) != origin and _protected((x, pos[1], z), site):
                    return False
    return True


def _vertical_column_blocks(client, pos):
    low = [pos[0], pos[1] + 1, pos[2]]
    high = [pos[0], pos[1] + 3, pos[2]]
    reply = client.request('scan', min=low, max=high, details=True)
    if (reply.get('phase') not in (None, 'done') or reply.get('world_session') != client.world
            or not isinstance(reply.get('blocks'), list)):
        raise PavingBlocked('Vertical paving clearance was not freshly scanned')
    observed = {}
    for row in reply['blocks']:
        point = _position(row.get('pos'))
        if (point in observed or any(point[i] < low[i] or point[i] > high[i]
                                     for i in range(3))):
            raise PavingBlocked('Vertical paving clearance scan is malformed')
        observed[point] = row
    return observed


def _safe_canopy(occupied, pos):
    """The Y66 cap may only be an ordinary dry leaf block, never a fluid or BE."""
    for (_, y, _), row in occupied.items():
        if y <= pos[1] + 2:
            return False
        try:
            block = _block(row.get('state'))
        except PavingBlocked:
            return False
        if (not block.endswith('_leaves') or row.get('solid') is not True
                or row.get('fluid') is not False
                or row.get('block_entity') is not False):
            return False
    return True


def _stable_canopy_pose(before, after):
    """Two distinct observations must show an unmoving, unharmed player."""
    old, new = before.get('pos'), after.get('pos')
    velocity = after.get('velocity')
    return (type(before.get('time')) is int and type(after.get('time')) is int
            and after['time'] > before['time']
            and isinstance(old, list) and isinstance(new, list)
            and len(old) == len(new) == 3
            and all(type(v) in (int, float) and math.isfinite(v) for v in old + new)
            and math.dist(old, new) <= .005
            and type(before.get('health')) in (int, float)
            and type(after.get('health')) in (int, float)
            and after['health'] >= 19 and after['health'] >= before['health']
            and isinstance(velocity, list) and len(velocity) == 3
            and all(type(v) in (int, float) and math.isfinite(v) for v in velocity)
            and -.1 <= velocity[1] <= .02)


def _vertical_column_clear(client, pos):
    return not _vertical_column_blocks(client, pos)


def _ready_vertical_pose(client, pos, state):
    """Keep a centered, clear pose below foliage instead of seeking another face."""
    player = state.get('pos')
    if (not isinstance(player, list) or len(player) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in player)
            or abs(player[0] - pos[0] - .5) > .1
            or abs(player[2] - pos[2] - .5) > .1
            or not pos[1] + 1.1 <= player[1] <= pos[1] + 1.55
            or not _player_body_clear(state, pos)):
        return False
    occupied = _vertical_column_blocks(client, pos)
    if not _safe_canopy(occupied, pos):
        raise PavingBlocked('Low paving canopy is not verified dry ordinary leaves')
    # A Y66 canopy leaves only two blocks of headroom. Make one bounded,
    # collision-checked downward adjustment; never ascend through that canopy.
    if occupied and player[1] > pos[1] + 1.2 + 1e-6:
        reply = client.request('navigate', target=[player[0], pos[1] + 1.11, player[2]],
                               arrival=.1, air_only=True, seconds=15)
        if reply.get('phase') != 'done':
            raise PavingBlocked('Native low-canopy paving adjustment was not confirmed')
        settled = client.status().get('pos')
        if (not isinstance(settled, list) or len(settled) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in settled)
                or math.dist(settled, [player[0], pos[1] + 1.11, player[2]]) > .1
                or settled[1] > pos[1] + 1.18
                or not _player_body_clear({'pos': settled}, pos)):
            raise PavingBlocked('Native low-canopy reply did not prove a lower clear pose')
    return True


def _vertical_placement_pose(client, site, pos, record, state):
    """Try the open target column before traversing a crowded yard edge."""
    player = state['pos']
    if (abs(player[0] - pos[0] - .5) > .1
            or abs(player[2] - pos[2] - .5) > .1
            or not _vertical_column_clear(client, pos)):
        return False
    waypoint = [player[0], pos[1] + 1.45, player[2]]
    moved = client.request('navigate', target=waypoint, arrival=.2,
                           air_only=True, seconds=15)
    if moved.get('phase') != 'done':
        raise PavingBlocked('Native collision-checked vertical paving reposition did not finish')
    observed, model, row, _, _ = _cell_check(client, site, pos, air=True,
                                             journal_phase='recovered')
    if (record['world_session'] != client.world or record['expected'] != row['expected']
            or record['model_hash'] != model['content_hash']):
        raise PavingPending('Recovered cell changed during vertical reposition')
    if (math.dist(observed['pos'], waypoint) > .35
            or not _player_body_clear(observed, pos)):
        _log_blocker(client, pos, 'recovered', 'vertical_pose_unconfirmed', observed)
        raise PavingBlocked('Vertical paving pose or body clearance was not confirmed')
    return True


def _direct_vertical_support_face(client, site, pos, state, support, item):
    """Prove a short unobstructed ray to the natural support's upper face."""
    def pose_ready(observed):
        player = observed.get('pos')
        return (isinstance(player, list) and len(player) == 3
                and all(type(v) in (int, float) and math.isfinite(v) for v in player)
                and observed.get('game_mode') == 'survival'
                and abs(player[0] - pos[0] - .5) <= .1
                and abs(player[2] - pos[2] - .5) <= .1
                and pos[1] + 1.1 <= player[1] <= pos[1] + 1.55
                and math.dist([player[0], player[1] + 2, player[2]],
                              [pos[0] + .5, pos[1], pos[2] + .5]) <= 3.6
                and _player_body_clear(observed, pos))

    occupied = _vertical_column_blocks(client, pos)
    if (_block(support['state']) not in NATURAL_SUPPORT
            or support.get('solid') is not True or not pose_ready(state)
            or not _safe_canopy(occupied, pos)
            or occupied and state['pos'][1] > pos[1] + 1.2 + 1e-6):
        raise PavingBlocked('Direct vertical support face or body clearance is unverified')
    if occupied:
        time.sleep(.08)
    fresh = client.status()
    if (_safe_state(client, fresh, site) != state['projection_selection']['key']
            or fresh.get('hand', {}).get('item') != item):
        raise PavingBlocked('Direct vertical placement control or hand changed')
    _entities(fresh, pos, client=client, phase='recovered')
    if occupied and not _stable_canopy_pose(state, fresh):
        raise PavingBlocked('Low-canopy paving pose was not stable across fresh observations')
    if not pose_ready(fresh):
        _log_blocker(client, pos, 'recovered', 'direct_vertical_pose_lost', fresh)
        raise PavingBlocked('Direct vertical support face or body clearance is unverified')
    return fresh


def _reposition_for_placement(client, site, pos, record, state):
    """Use native collision-checked air movement; stop if no exact clear pose is proven."""
    player = state['pos']
    start = (player[0], player[2])
    if (abs(math.floor(start[0]) - pos[0]) > 1
            or abs(math.floor(start[1]) - pos[2]) > 1):
        raise PavingBlocked('Player overlaps paving from outside the bounded local corridor')
    if _vertical_placement_pose(client, site, pos, record, state):
        return 'vertical'
    occupied = _clear_pose_columns(client, pos)
    selected = middle = rise = None
    # The low route stays below a Y66 cap. Native air-only navigation checks
    # the actual swept player AABB before and throughout each move.
    for top_y, route_y in ((pos[1] + 4, pos[1] + 2.02),
                           (pos[1] + 2, pos[1] + 1.2)):
        for dx, dz in ((0, -2), (-2, 0), (2, 0), (0, 2)):
            if _protected((pos[0] + dx, pos[1], pos[2] + dz), site):
                continue
            candidate = (pos[0] + dx + .5, pos[2] + dz + .5)
            for turn in ((start[0], candidate[1]), (candidate[0], start[1])):
                if _clear_axis_route(occupied, site, pos, start, turn, candidate, top_y):
                    selected, middle, rise = candidate, turn, route_y
                    break
            if selected is not None:
                break
        if selected is not None:
            break
    if selected is None:
        raise PavingBlocked('No freshly scanned dry axis route to a clear paving pose')
    waypoints = [(start[0], rise, start[1])]
    if middle != start:
        waypoints.append((middle[0], rise, middle[1]))
    if selected != middle:
        waypoints.append((selected[0], rise, selected[1]))
    if rise > pos[1] + 1.2:
        waypoints.append((selected[0], pos[1] + 1.02, selected[1]))
    for waypoint in waypoints:
        reply = client.request('navigate', target=list(waypoint), arrival=.2,
                               air_only=True, seconds=15)
        if reply.get('phase') != 'done':
            raise PavingBlocked('Native collision-checked paving reposition did not finish')
        observed, model, row, _, _ = _cell_check(client, site, pos, air=True,
                                                 journal_phase='recovered')
        if (record['world_session'] != client.world or record['expected'] != row['expected']
                or record['model_hash'] != model['content_hash']):
            raise PavingPending('Recovered cell changed during safe reposition')
        if math.dist(observed['pos'], waypoint) > .35:
            raise PavingBlocked('Paving reposition stopped outside the verified pose')
    if not _player_body_clear(observed, pos):
        _log_blocker(client, pos, 'recovered', 'player_body_after_reposition', observed)
        raise PavingBlocked('Player body still overlaps the paving destination')
    return 'axis'


def _recovered_pre_approach(client, site, pos, record, *, allow_session_rebind=False):
    """Enter entity-observation range without replaying the recovered excavation."""
    state, model, audit = _fresh_context(client, site)
    if _protected(pos, site):
        raise PavingBlocked('Protected house, warehouse, or birch-tree buffer')
    row = _target(model, audit, pos, site, air=True)
    if ((record['world_session'] != client.world and not allow_session_rebind)
            or record['expected'] != row['expected']
            or record['model_hash'] != model['content_hash']):
        raise PavingPending('Recovered cell belongs to another world session or model')
    support = _geometry(_scan(client, pos), pos, row['actual'])
    if _counts(state)[_block(row['expected'])] < 1:
        raise PavingBlocked('Replacement block is no longer held')
    if allow_session_rebind:
        _native_request_settled(client, client.status())
    try:
        approach_faces(client, [pos[0], pos[1] - 1, pos[2]], support['state'],
                       ('up',), stand_distance=2.4)
    except ApproachUnavailable as error:
        raise PavingBlocked('No verified dry support-face approach; recovered cell stays pending') from error


def _place(client, site, pos, path, record, *, settle):
    journal_phase = record['phase']
    state, model, row, support, _ = _cell_check(client, site, pos, air=True,
                                               journal_phase=journal_phase)
    if (record['world_session'] != client.world or record['expected'] != row['expected']
            or record['model_hash'] != model['content_hash']):
        raise PavingPending('Recovered cell belongs to another world session or model')
    direct_vertical = _ready_vertical_pose(client, pos, state)
    if direct_vertical:
        state, model, row, support, _ = _cell_check(client, site, pos, air=True,
                                                   journal_phase=journal_phase)
        if (record['world_session'] != client.world or record['expected'] != row['expected']
                or record['model_hash'] != model['content_hash']):
            raise PavingPending('Recovered cell changed during low-canopy adjustment')
    elif not _player_body_clear(state, pos):
        _log_blocker(client, pos, 'recovered', 'player_body_overlap', state)
        direct_vertical = _reposition_for_placement(client, site, pos, record, state) == 'vertical'
        state, model, row, support, _ = _cell_check(client, site, pos, air=True,
                                                   journal_phase=journal_phase)
    support_pos = [pos[0], 62, pos[2]]
    item = _block(row['expected'])
    client.checked('select_item', item=item)
    if not direct_vertical:
        try:
            approach_faces(client, support_pos, support['state'], ('up',), stand_distance=2.4)
        except ApproachUnavailable as error:
            raise PavingBlocked('No verified dry support-face approach; recovered cell stays pending') from error
    state, model, row, support, _ = _cell_check(client, site, pos, air=True,
                                               journal_phase=journal_phase)
    if (record['world_session'] != client.world or record['expected'] != row['expected']
            or record['model_hash'] != model['content_hash']):
        raise PavingPending('Recovered cell changed during placement approach')
    if not _player_body_clear(state, pos):
        _log_blocker(client, pos, 'recovered', 'player_body_after_approach', state)
        raise PavingBlocked('Player body overlaps the paving destination after approach')
    if direct_vertical:
        state = _direct_vertical_support_face(client, site, pos, state, support, item)
    if state.get('hand', {}).get('item') != item:
        raise PavingBlocked('Replacement is not in the selected hand')
    before = _counts(state)[item]
    record = _record(path, record, 'place_intent', support_state=support['state'], material_before=before)
    reply = client.request('interact', pos=support_pos, face='up',
                           expected_state=support['state'], expected_hand=item,
                           expected_placed_state=row['expected'], dry_paving_guard=True)
    record = _record(path, record, 'place_intent',
                     native_reply=_paving_reply_receipt(reply))
    _confirmed_native_paving_reply(reply, stage='place', pos=pos, state=row['expected'])
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
        if record['phase'] in ('recovered', 'drop_lost'):
            if record['phase'] == 'drop_lost':
                _confirmed_drop_lost_journal(record)
            player = state.get('pos')
            if (not isinstance(player, list) or len(player) != 3
                    or any(type(v) not in (int, float) or not math.isfinite(v)
                           for v in player)):
                raise PavingBlocked('Player position is unavailable for recovered paving')
            if record['world_session'] != client.world:
                if record['phase'] == 'recovered':
                    _confirmed_recovered_journal(record)
                if math.dist(player, [pos[0] + .5, pos[1] + .5, pos[2] + .5]) > 12:
                    _recovered_pre_approach(client, site, pos, record,
                                            allow_session_rebind=True)
                record = _rebind_recovered(client, site, pos, path, record)
                state = client.status()
                player = state['pos']
            if math.dist(player, [pos[0] + .5, pos[1] + .5, pos[2] + .5]) > 12:
                _recovered_pre_approach(client, site, pos, record)
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
    record = _record(path, record, 'mine_intent',
                     native_reply=_paving_reply_receipt(reply))
    _confirmed_native_paving_reply(reply, stage='mine', pos=pos,
                                   state='Block{minecraft:air}')
    settle(.8)
    if _scan(client, pos).get(pos) is not None:
        raise PavingPending('Server did not confirm air after the one mining request')
    record = _record(path, record, 'mined', old_state=row['actual'], server_air=True,
                     server_confirmed=True,
                     confirmation_scope=reply['confirmation_scope'],
                     native_request_id=reply.get('id'))
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
