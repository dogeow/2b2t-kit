"""Guarded, two-layer Y62 stone -> dirt repair at ten exact south-yard cells.

This is the first top-down template, not a general terrain clearer. A matched
Y63 grass block is temporarily lifted with Silk Touch, the Y62 stone is
replaced, and that same grass is restored immediately. Native stage guards
remain mandatory for every click. Each uncertain intent is durable and is
never automatically replayed.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import time

from drop_collection import collect_drop
import projection_dry_paving as paving


STONE = 'Block{minecraft:stone}'
DIRT = 'Block{minecraft:dirt}'
GRASS = 'Block{minecraft:grass_block}[snowy=false]'
XS = (760994, 760988, 760993, 760995, 760996, 760997, 760998, 760999,
      761003, 761008)
CELLS = tuple((x, 62, 797865) for x in XS)
PINNED = frozenset(CELLS)
POND_BUFFER = (760984, 761012, 797847, 797861)
PHASES = frozenset({'lift_intent', 'grass_mined', 'grass_pickup_intent',
                    'grass_recovered', 'stone_mine_intent', 'stone_mined',
                    'stone_pickup_intent', 'stone_recovered',
                    'dirt_place_intent', 'dirt_placed',
                    'grass_restore_intent', 'grass_decay_wait',
                    'grass_placed', 'complete',
                    'pre_send_rejected'})
UNCERTAIN = frozenset({'lift_intent', 'grass_pickup_intent', 'stone_mine_intent',
                       'stone_pickup_intent', 'dirt_place_intent',
                       'grass_restore_intent'})
TRANSITIONS = {
    None: {'lift_intent'},
    'lift_intent': {'grass_mined', 'pre_send_rejected'},
    'pre_send_rejected': {'lift_intent', 'grass_restore_intent'},
    'grass_mined': {'grass_pickup_intent', 'grass_recovered'},
    'grass_pickup_intent': {'grass_recovered'},
    'grass_recovered': {'stone_mine_intent'},
    'stone_mine_intent': {'stone_mined'},
    'stone_mined': {'stone_pickup_intent', 'stone_recovered'},
    'stone_pickup_intent': {'stone_recovered'},
    'stone_recovered': {'dirt_place_intent'},
    'dirt_place_intent': {'dirt_placed'},
    'dirt_placed': {'grass_restore_intent'},
    'grass_restore_intent': {'grass_placed', 'grass_decay_wait',
                             'pre_send_rejected'},
    'grass_decay_wait': {'grass_placed'},
    'grass_placed': {'complete'},
    'complete': set(),
}
REBINDS = frozenset({'grass_recovered', 'stone_recovered',
                     'dirt_placed', 'grass_placed', 'complete',
                     'pre_send_rejected', 'grass_decay_wait'})
PRE_SEND_EVIDENCE_KIND = 'terrain_pre_send_rejection_evidence'
POST_SEND_LIFT_EVIDENCE_KIND = 'terrain_post_send_lift_evidence'
POST_SEND_CONFIRMATION_SCOPE = (
    'unique_drop_and_owned_inventory_gain_after_single_request')
KNOWN_PRE_SEND_REJECTIONS = frozenset({
    'An entity or loose item approached the terrain replacement',
})
STATION_ARRIVAL = .20
STATION_STABILITY = .005
TRANSIT_POSE_TOLERANCE = .35
LOCAL_LOW_TRANSIT = 4.0
HIGH_TRANSIT_CLEARANCE = 20.0
AIR_HAZARDS = frozenset({
    'minecraft:fire', 'minecraft:soul_fire', 'minecraft:cobweb',
    'minecraft:powder_snow',
})


class _TransitGeometryBlocked(paving.PavingBlocked):
    """A valid fresh scan found occupied body space; observation failures differ."""


def _safe_site(pos):
    x, _, z = pos
    x1, x2, z1, z2 = POND_BUFFER
    return (pos in PINNED and not paving._protected(pos, paving.SITE)
            and not (x1 <= x <= x2 and z1 <= z <= z2))


def _fresh(client, pos, phase):
    state, model, audit = paving._fresh_context(client, paving.SITE)
    if (type(state.get('terrain_replace_protocol')) is not int
            or state['terrain_replace_protocol'] != 1):
        raise paving.PavingBlocked('Native two-layer terrain guard is unavailable')
    if not _safe_site(pos):
        raise paving.PavingBlocked('Cell is not one of the ten protected south-yard targets')
    expected_stone = [r for r in model['expected'] if r.get('pos') == list(pos)]
    expected_grass = [r for r in model['expected']
                      if r.get('pos') == [pos[0], pos[1] + 1, pos[2]]]
    upper = [r for r in model['expected'] if isinstance(r.get('pos'), list)
             and len(r['pos']) == 3 and r['pos'][0] == pos[0] and r['pos'][2] == pos[2]
             and type(r['pos'][1]) is int and pos[1] + 2 <= r['pos'][1] <= pos[1] + 4]
    if (len(expected_stone) != 1 or expected_stone[0].get('state') != DIRT
            or len(expected_grass) != 1 or expected_grass[0].get('state') != GRASS
            or upper):
        raise paving.PavingBlocked('Current model no longer describes the exact bare south lawn')
    by_pos = {tuple(r['pos']): r for r in audit['mismatches']
              if r.get('pos') in (list(pos), [pos[0], pos[1] + 1, pos[2]])}
    top = by_pos.get((pos[0], pos[1] + 1, pos[2]))
    base = by_pos.get(pos)
    expected_states = {
        'initial': (STONE, GRASS),
        'grass_removed': (STONE, 'Block{minecraft:air}'),
        'both_removed': ('Block{minecraft:air}', 'Block{minecraft:air}'),
        'dirt_placed': (DIRT, 'Block{minecraft:air}'),
        'dirt_spread': (GRASS, 'Block{minecraft:air}'),
        'grass_decay_wait': (GRASS, GRASS),
        'complete': (DIRT, GRASS),
    }
    if phase not in expected_states:
        raise ValueError('Unknown two-layer observation phase')
    base_state, top_state = expected_states[phase]
    if (base_state == DIRT and base is not None or base_state != DIRT
            and (base is None or base.get('actual') != base_state
                 or base.get('expected') != DIRT)):
        raise paving.PavingBlocked('Full audit disagrees with the recorded foundation phase')
    if (top_state == GRASS and top is not None or top_state != GRASS
            and (top is None or top.get('actual') not in paving.AIR
                 or top.get('expected') != GRASS)):
        raise paving.PavingBlocked('Full audit disagrees with the recorded grass phase')
    for row in (base, top):
        if row is not None and (row.get('block_entity') is not False
                                or row.get('fluid') is not False
                                or row.get('adjacent_fluid') is not False
                                or row.get('neighbors_loaded') is not True):
            raise paving.PavingBlocked('Two-layer audit has an unsafe or unloaded cell')
    return state, model, audit


def _scan(client, pos, phase):
    x, y, z = pos
    low, high = [x - 1, y - 1, z - 1], [x + 1, y + 4, z + 1]
    reply = client.request('scan', min=low, max=high, details=True)
    if (reply.get('phase') not in (None, 'done') or reply.get('world_session') != client.world
            or not isinstance(reply.get('blocks'), list)):
        raise paving.PavingBlocked('Two-layer local volume was not freshly scanned')
    cells = {}
    for row in reply['blocks']:
        point = paving._position(row.get('pos'))
        if point in cells or any(point[i] < low[i] or point[i] > high[i] for i in range(3)):
            raise paving.PavingBlocked('Two-layer local scan has duplicate or outside cells')
        cells[point] = row
        if row.get('fluid') is not False or row.get('block_entity') is not False:
            raise paving.PavingBlocked('Fluid or block entity is near the two-layer replacement')
    beneath = cells.get((x, y - 1, z))
    if (beneath is None or beneath.get('solid') is not True
            or beneath.get('state') != STONE):
        raise paving.PavingBlocked('Exact dry Y61 stone foundation was not verified')
    expected = {
        'initial': (STONE, GRASS),
        'grass_removed': (STONE, None),
        'both_removed': (None, None),
        'dirt_placed': (DIRT, None),
        'dirt_spread': (GRASS, None),
        'grass_decay_wait': (GRASS, GRASS),
        'complete': (DIRT, GRASS),
    }[phase]
    for point, state in (((x, y, z), expected[0]), ((x, y + 1, z), expected[1])):
        observed = cells.get(point)
        if state is None and observed is not None or state is not None and (
                observed is None or observed.get('state') != state
                or observed.get('solid') is not True):
            raise paving.PavingBlocked('Observed two-layer block differs from the journal phase')
    if any((x, yy, z) in cells for yy in (y + 2, y + 3, y + 4)):
        raise paving.PavingBlocked('A user block, plant, roof, or tree occupies the overhead station')
    # Neighboring flowers remain untouched; attached/non-solid neighbors at
    # the actual work layers are excluded because removing their support may
    # change a user-built feature.
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        for yy in (y, y + 1):
            row = cells.get((x + dx, yy, z + dz))
            if row is not None and row.get('solid') is not True:
                raise paving.PavingBlocked('A neighboring attachment or flower needs preservation')
    return beneath['state']


def _station(pos):
    return [pos[0] + .5, pos[1] + 2.30, pos[2] + .5]


def _station_pose_ok(point, pos):
    """Keep the Python station inside the native policy and arrival envelope."""
    if (not isinstance(point, list) or len(point) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)):
        return False
    target = _station(pos)
    return (math.hypot(point[0] - target[0], point[2] - target[2]) <= STATION_ARRIVAL
            and abs(point[1] - target[1]) <= STATION_ARRIVAL)


def _scan_air_volume(client, low, high):
    if (any(type(v) is not int for v in low + high)
            or any(low[i] > high[i] for i in range(3))
            or math.prod(high[i] - low[i] + 1 for i in range(3)) > 50000):
        raise paving.PavingBlocked('Guarded transit scan bounds are invalid')
    reply = client.request('scan', min=low, max=high, details=True)
    if (not isinstance(reply, dict)
            or reply.get('phase') not in (None, 'done')
            or reply.get('world_session') != client.world
            or not isinstance(reply.get('blocks'), list)):
        raise paving.PavingBlocked('Guarded transit air volume was not fully scanned')
    seen = set()
    for row in reply['blocks']:
        if not isinstance(row, dict):
            raise paving.PavingBlocked('Guarded transit scan returned a malformed block')
        point = row.get('pos')
        if (not isinstance(point, list) or len(point) != 3
                or any(type(v) is not int for v in point)
                or any(point[i] < low[i] or point[i] > high[i] for i in range(3))
                or not isinstance(row.get('state'), str)
                or any(type(row.get(field)) is not bool for field in
                       ('solid', 'replaceable', 'passable', 'fluid', 'block_entity'))
                or row['passable'] and (row['solid'] or row['fluid'])
                or tuple(point) in seen):
            raise paving.PavingBlocked('Guarded transit scan returned an invalid block')
        try:
            paving._block(row['state'])
        except paving.PavingBlocked as error:
            raise paving.PavingBlocked(
                'Guarded transit scan returned an invalid block') from error
        seen.add(tuple(point))
    return reply['blocks']


def _clear_air_volume(client, low, high):
    rows = _scan_air_volume(client, low, high)
    if any(row['passable'] is not True or row['fluid'] is True
           or paving._block(row['state']) in AIR_HAZARDS
           for row in rows):
        raise _TransitGeometryBlocked(
            'Guarded transit air volume contains a block or fluid')


def _air_bounds(start, target, *, start_uncertainty=0):
    for point in (start, target):
        if (not isinstance(point, (list, tuple)) or len(point) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       for v in point)):
            raise paving.PavingBlocked('Guarded transit waypoint is invalid')
    if (type(start_uncertainty) not in (int, float)
            or not math.isfinite(start_uncertainty)
            or not 0 <= start_uncertainty <= TRANSIT_POSE_TOLERANCE):
        raise paving.PavingBlocked('Guarded transit uncertainty is invalid')
    return ([math.floor(min(start[0] - .35 - start_uncertainty,
                            target[0] - .35)),
             math.floor(min(start[1] - start_uncertainty, target[1])),
             math.floor(min(start[2] - .35 - start_uncertainty,
                            target[2] - .35))],
            [math.floor(max(start[0] + .35 + start_uncertainty,
                            target[0] + .35)),
             math.ceil(max(start[1] + 2 + start_uncertainty,
                           target[1] + 2)),
             math.floor(max(start[2] + .35 + start_uncertainty,
                            target[2] + .35))])


def _transit_state(client, state, expected, *, minimum_health=None):
    if not isinstance(state, dict):
        raise paving.PavingBlocked('Guarded transit state is unavailable')
    paving._safe_state(client, state, paving.SITE)
    point = state.get('pos')
    if (not isinstance(point, list) or len(point) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)
            or math.dist(point, expected) > TRANSIT_POSE_TOLERANCE):
        raise paving.PavingBlocked('Guarded transit position changed outside the confirmed leg')
    if (minimum_health is not None
            and (type(state.get('health')) not in (int, float)
                 or state['health'] < minimum_health)):
        raise paving.PavingBlocked('Health changed during guarded transit')
    entities = state.get('entities')
    if not isinstance(entities, list):
        raise paving.PavingBlocked('Guarded transit entity coverage is unavailable')
    for entity in entities:
        entity_pos = entity.get('pos') if isinstance(entity, dict) else None
        if (not isinstance(entity_pos, list) or len(entity_pos) != 3
                or not isinstance(entity.get('type'), str)
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       for v in entity_pos)):
            raise paving.PavingBlocked('Guarded transit entity observation is malformed')
        if entity.get('hostile') is True or math.dist(entity_pos, point) <= 4:
            raise paving.PavingBlocked('An entity is too near the guarded transit leg')
    return state


def _preflight_air_route(client, state, legs):
    """Prove every planned body sweep before the first movement command."""
    anchor = list(state['pos'])
    health = state['health']
    for index, (start, target) in enumerate(legs):
        # Every later leg starts wherever the preceding native arrival settled.
        # Expand its nominal start by the full accepted pose envelope so the
        # complete route is proven before the first movement command.
        uncertainty = 0 if index == 0 else TRANSIT_POSE_TOLERANCE
        low, high = _air_bounds(start, target,
                                start_uncertainty=uncertainty)
        _clear_air_volume(client, low, high)
        state = _transit_state(client, client.status(), anchor,
                               minimum_health=health)
        health = state['health']
    return state


def _air_leg(client, start, target, *, seconds):
    before = _transit_state(client, client.status(), start)
    health = before['health']
    low, high = _air_bounds(before['pos'], target)
    _clear_air_volume(client, low, high)
    fresh = _transit_state(client, client.status(), before['pos'],
                           minimum_health=health)
    reply = client.request('navigate', target=target, arrival=STATION_ARRIVAL,
                           air_only=True, seconds=seconds)
    if not isinstance(reply, dict) or reply.get('phase') != 'done':
        raise paving.PavingBlocked('Native air-only lawn waypoint was not confirmed')
    return _transit_state(client, client.status(), target,
                          minimum_health=fresh['health'])


def _high_transit_y(client, target):
    park = getattr(client, 'park_target', None)
    if (not isinstance(park, (list, tuple)) or len(park) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in park)
            or not target[1] + HIGH_TRANSIT_CLEARANCE <= park[1] <= 320):
        raise paving.PavingBlocked('Verified high transit park height is unavailable')
    return park[1]


def _high_route(client, state, target):
    """Ascend in place, cross at verified height, then descend in target column."""
    transit_y = _high_transit_y(client, target)
    point = list(state['pos'])
    legs = []
    if abs(point[1] - transit_y) > 2:
        high_here = [point[0], transit_y, point[2]]
        legs.append((point, high_here))
        point = high_here
    high_target = [target[0], point[1], target[2]]
    if math.hypot(point[0] - target[0], point[2] - target[2]) > STATION_ARRIVAL:
        legs.append((point, high_target))
        point = high_target
    if math.dist(point, target) > STATION_ARRIVAL:
        legs.append((point, target))
    _preflight_air_route(client, state, legs)
    for start, destination in legs:
        state = _air_leg(client, state['pos'], destination, seconds=60)
    return state


def _station_status(client, pos):
    state = client.status()
    paving._safe_state(client, state, paving.SITE)
    point = state.get('pos')
    if (not _station_pose_ok(point, pos)
            or state.get('on_ground') is not False
            or state.get('flight') is not True
            or state.get('game_mode') != 'survival'):
        raise paving.PavingBlocked('A stable flight pose above the lawn is not confirmed')
    # With only the observed full-block Y61/Y62/Y63 column on the ray, this
    # standing-eye bound leaves room inside vanilla reach for all four upper
    # faces. The native guard verifies the actual eye and line of sight again.
    if point[1] + 1.62 - (pos[1]) > 4.15:
        raise paving.PavingBlocked('Top-down Y61 support face may be out of reach')
    paving._entities(state, pos)
    return state


def _reach_station(client, pos):
    state = client.status()
    target = _station(pos)
    if (not isinstance(state.get('pos'), list) or len(state['pos']) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   for v in state['pos'])
            or math.hypot(state['pos'][0] - target[0], state['pos'][2] - target[2]) > 31):
        raise paving.PavingBlocked('Start within 31 blocks of the guarded lawn station')
    state = _transit_state(client, state, state['pos'])
    horizontal = math.hypot(state['pos'][0] - target[0], state['pos'][2] - target[2])
    low = state['pos'][1] <= target[1] + 3
    if not _station_pose_ok(state.get('pos'), pos) and low and horizontal <= LOCAL_LOW_TRANSIT:
        try:
            state = _air_leg(client, state['pos'], target, seconds=20)
        except _TransitGeometryBlocked:
            # Only an occupied, otherwise valid scan selects the high route.
            # World/scan/guard failures remain failures and are never retyped
            # as local geometry.
            state = _transit_state(client, client.status(), state['pos'],
                                   minimum_health=state['health'])
            state = _high_route(client, state, target)
    elif not _station_pose_ok(state.get('pos'), pos):
        state = _high_route(client, state, target)
    first = _station_status(client, pos)
    return _next_station_frame(client, pos, first)


def _next_station_frame(client, pos, first, *, seconds=1.0):
    """A same-tick read is neither proof of stability nor a reason to move."""
    if type(first.get('time')) is not int:
        raise paving.PavingBlocked('Flight station snapshot has no valid time')
    deadline=time.monotonic()+seconds
    while True:
        time.sleep(.05)
        current=_station_status(client,pos)
        if (type(current.get('time')) is not int
                or current['time'] < first['time']
                or math.hypot(first['pos'][0] - current['pos'][0],
                              first['pos'][2] - current['pos'][2]) > STATION_STABILITY
                or abs(first['pos'][1] - current['pos'][1]) > STATION_STABILITY
                or current.get('health',0) < first.get('health',0)):
            raise paving.PavingBlocked('Flight station moved or lost health while awaiting a new frame')
        if current['time'] > first['time']:
            return current
        if time.monotonic() >= deadline:
            raise paving.PavingBlocked('Flight station has no newer safe snapshot')


def _tool(state, item, *, silk=False):
    rows = [r for r in state.get('inventory', [])
            if type(r.get('slot')) is int and 0 <= r['slot'] < 36
            and r.get('item') == item and r.get('count') == 1
            and r.get('durability', 0) >= 64]
    if silk:
        rows = [r for r in rows if _has_silk_touch(r)]
    if not rows:
        raise paving.PavingBlocked('Required durable tool and enchantment are not verified')
    return max(rows, key=lambda r: r['durability'])


def _has_silk_touch(row):
    value = row.get('enchantments')
    if isinstance(value, dict):
        return value.get('minecraft:silk_touch', 0) >= 1
    if isinstance(value, list):
        return any(isinstance(entry, dict) and entry.get('id') == 'minecraft:silk_touch'
                   and entry.get('level', 0) >= 1 for entry in value)
    return False


def _free_slots(state):
    rows = state.get('inventory')
    if not isinstance(rows, list):
        raise paving.PavingBlocked('Backpack capacity snapshot is unavailable')
    slots = {}
    for row in rows:
        if not isinstance(row, dict):
            raise paving.PavingBlocked('Backpack capacity row is malformed')
        slot = row.get('slot')
        if type(slot) is not int or not 0 <= slot < 36:
            continue  # Equipment/offhand rows are not backpack capacity.
        if slot in slots or not isinstance(row.get('item'), str) or not row['item']:
            raise paving.PavingBlocked('Backpack capacity has a duplicate or malformed slot')
        count = row.get('count')
        if (type(count) is not int or not 0 <= count <= 64
                or count == 0 and row['item'] != 'minecraft:air'
                or count > 0 and row['item'] == 'minecraft:air'):
            raise paving.PavingBlocked('Backpack capacity contains an inconsistent item row')
        slots[slot] = row
    if set(slots) != set(range(36)):
        raise paving.PavingBlocked('Backpack capacity is missing one or more of the 36 slots')
    return sum(row['count'] == 0 for row in slots.values())


def _reject_old_drops(state, pos):
    entities = state.get('entities')
    player = state.get('pos')
    if not isinstance(entities, list) or not isinstance(player, list) or len(player) != 3:
        raise paving.PavingBlocked('Rendered drop coverage is unavailable')
    center = [pos[0] + .5, pos[1] + .5, pos[2] + .5]
    for entity in entities:
        if entity.get('type') != 'minecraft:item':
            continue
        point = entity.get('pos')
        if (not isinstance(point, list) or len(point) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)):
            raise paving.PavingBlocked('Existing item-drop observation is malformed')
        if math.dist(point, player) <= 16 or math.dist(point, center) <= 16:
            raise paving.PavingBlocked('An older item drop could be confused with this excavation')


def _journal_path(client, pos):
    site = paving.SITE
    scope = hashlib.sha256((site['server'] + '\0' + site['dimension']).encode()).hexdigest()[:20]
    return Path(client.root) / 'terrain-replace-south-v1' / scope / ('%d_%d_%d.json' % pos)


def _file_sha256(path, *, limit):
    path = Path(path)
    try:
        if not path.is_file() or path.stat().st_size > limit:
            raise paving.PavingPending('Pre-send evidence source is missing or too large')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            while chunk := stream.read(65536):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as error:
        raise paving.PavingPending('Pre-send evidence source is unavailable') from error


def _verified_source(meta, *, limit, label):
    if (not isinstance(meta, dict) or not isinstance(meta.get('path'), str)
            or not Path(meta['path']).is_absolute()
            or not isinstance(meta.get('sha256'), str)
            or len(meta['sha256']) != 64
            or any(ch not in '0123456789abcdef' for ch in meta['sha256'])):
        raise paving.PavingPending(label + ' evidence identity is invalid')
    path = Path(meta['path'])
    if _file_sha256(path, limit=limit) != meta['sha256']:
        raise paving.PavingPending(label + ' evidence hash changed')
    return path


def _json_file(path, *, label):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError) as error:
        raise paving.PavingPending(label + ' evidence is not valid JSON') from error


def _backpack_rows(state):
    rows = state.get('inventory')
    if not isinstance(rows, list):
        raise paving.PavingPending('Pre-send inventory evidence is unavailable')
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise paving.PavingPending('Pre-send inventory evidence is malformed')
        slot = row.get('slot')
        if type(slot) is int and 0 <= slot < 36:
            count = row.get('count')
            if (type(count) is not int or not 0 <= count <= 64
                    or count == 0 and row.get('item') != 'minecraft:air'
                    or count > 0 and row.get('item') == 'minecraft:air'):
                raise paving.PavingPending('Pre-send inventory evidence is inconsistent')
            result.append(row)
    slots = [row['slot'] for row in result]
    if len(result) != 36 or set(slots) != set(range(36)):
        raise paving.PavingPending('Pre-send inventory evidence lacks exact backpack slots')
    return result


def _grass_count(state):
    return sum(row.get('count', 0) for row in _backpack_rows(state)
               if row.get('item') == 'minecraft:grass_block')


def _matching_silk_tool(state, item, durability, *, selected_slot=None):
    rows = [row for row in _backpack_rows(state)
            if row.get('item') == item and row.get('count') == 1
            and row.get('durability') == durability and _has_silk_touch(row)]
    if selected_slot is not None:
        rows = [row for row in rows if row.get('slot') == selected_slot]
    if len(rows) != 1:
        raise paving.PavingPending('The exact pre-send Silk Touch shovel is not present')
    return rows[0]


def _lift_request_matches(request, record, pos, *, request_id, revision, selected_slot,
                          tool_item, task_session):
    if not isinstance(request, dict):
        return False
    expected = {
        'id': request_id, 'op': 'mine_block', 'world_session': record['world_session'],
        'expected_revision': revision, 'task_session': task_session,
        'background_ok': True, 'pos': [pos[0], pos[1] + 1, pos[2]], 'face': 'up',
        'expected_state': GRASS, 'required_silk_shovel': True,
        'expected_tool_slot': selected_slot, 'expected_tool_item': tool_item,
        'terrain_replace_guard': True, 'terrain_replace_stage': 'lift_grass',
        'replacement_pos': list(pos), 'expected_surface_state': GRASS,
        'expected_below_state': STONE, 'placement_key': record['placement_key'],
    }
    return (isinstance(task_session, str) and task_session
            and all(request.get(key) == value for key, value in expected.items()))


def _restore_request_matches(request, record, pos, *, request_id, revision,
                             foundation_state, task_session):
    if not isinstance(request, dict):
        return False
    expected = {
        'id': request_id, 'op': 'interact', 'world_session': record['world_session'],
        'expected_revision': revision, 'task_session': task_session,
        'background_ok': True, 'pos': list(pos), 'face': 'up',
        'expected_state': foundation_state, 'expected_hand': 'minecraft:grass_block',
        'terrain_replace_guard': True, 'terrain_replace_stage': 'restore_grass',
        'replacement_pos': list(pos), 'expected_surface_state': GRASS,
        'expected_below_state': STONE, 'placement_key': record['placement_key'],
    }
    return (foundation_state in (DIRT, GRASS)
            and isinstance(task_session, str) and task_session
            and all(request.get(key) == value for key, value in expected.items()))


def _pre_send_reply_matches(reply, record, *, request_id, revision, detail):
    return (isinstance(reply, dict) and reply.get('id') == request_id
            and reply.get('phase') == 'error' and reply.get('detail') == detail
            and detail in KNOWN_PRE_SEND_REJECTIONS
            and reply.get('world_session') == record['world_session']
            and reply.get('control_revision') == revision)


def _pre_send_snapshot(reply, record, *, selected_slot, tool_item):
    hand = reply.get('hand') or {}
    durability = hand.get('durability')
    if (reply.get('selected_slot') != selected_slot or hand.get('item') != tool_item
            or hand.get('count') != 1 or type(durability) is not int or durability < 64
            or not _has_silk_touch(hand)
            or _grass_count(reply) != record['grass_inventory_before']):
        raise paving.PavingPending('Pre-send tool or grass inventory evidence changed')
    _matching_silk_tool(reply, tool_item, durability, selected_slot=selected_slot)
    entities = reply.get('entities')
    if not isinstance(entities, list) or any(not isinstance(entity, dict) for entity in entities):
        raise paving.PavingPending('Pre-send entity evidence is unavailable')
    if any(entity.get('type') == 'minecraft:item' for entity in entities):
        raise paving.PavingPending('A pre-send item drop prevents no-action proof')
    return durability


def _restore_pre_send_snapshot(reply, record, *, selected_slot):
    hand = reply.get('hand') or {}
    if (reply.get('selected_slot') != selected_slot
            or hand.get('item') != 'minecraft:grass_block'
            or type(hand.get('count')) is not int or hand['count'] < 1
            or _grass_count(reply) != record['grass_reserve']):
        raise paving.PavingPending('Pre-send restored-grass inventory evidence changed')
    rows = [row for row in _backpack_rows(reply)
            if row.get('slot') == selected_slot
            and row.get('item') == 'minecraft:grass_block'
            and row.get('count') == hand['count']]
    if len(rows) != 1:
        raise paving.PavingPending('Pre-send restored-grass stack is ambiguous')
    entities = reply.get('entities')
    if not isinstance(entities, list) or any(not isinstance(entity, dict) for entity in entities):
        raise paving.PavingPending('Pre-send entity evidence is unavailable')
    if any(entity.get('type') == 'minecraft:item' for entity in entities):
        raise paving.PavingPending('A pre-send item drop prevents no-action proof')
    return hand['count']


def _record_pre_send_rejection(path, record, evidence):
    stage = evidence.get('stage')
    if stage not in ('lift_grass', 'restore_grass'):
        raise paving.PavingPending('Pre-send rejection stage is invalid')
    evidence = {key: value for key, value in evidence.items() if key != 'stage'}
    return paving._record(path, record, 'pre_send_rejected',
                          event='native_preflight_rejected_before_send',
                          action_sent=False, stage=stage, **evidence)


def _validate_legacy_intent_binding(evidence, intent, *, stage, task_session,
                                    request_id, world_session, revision,
                                    selected_slot, expected_state, action_pos):
    """Prefer exact saved intent identity; isolate the one old three-field format."""
    identity = {
        'intent_world_session': world_session, 'task_session': task_session,
        'expected_revision': revision, 'selected_slot': selected_slot,
        'expected_state': expected_state, 'action_pos': list(action_pos),
    }
    present = [key for key in identity if key in intent]
    if present:
        if len(present) != len(identity) or any(intent.get(key) != value
                                                for key, value in identity.items()):
            raise paving.PavingPending('Saved terrain intent belongs to another request task')
        return
    if set(intent) != {'phase', 'stage', 'item_before'}:
        raise paving.PavingPending('Legacy terrain intent has an unknown identity shape')
    canonical = json.dumps(intent, sort_keys=True, separators=(',', ':')).encode()
    fallback = evidence.get('legacy_intent_binding')
    if fallback != {
            'fields_absent': True, 'stage': stage, 'task_session': task_session,
            'request_id': request_id,
            'receipt_sha256': hashlib.sha256(canonical).hexdigest()}:
        raise paving.PavingPending('Legacy terrain intent identity fallback is missing')


def _live_pre_send_rejection(client, pos, path, record, reply, intent):
    """Classify only an exact native dispatch rejection that cannot have clicked."""
    detail = reply.get('detail')
    request_id = reply.get('id')
    revision = intent.get('expected_revision')
    selected_slot = intent.get('selected_slot')
    tool_item = intent.get('tool_item')
    task_session = intent.get('task_session')
    if (reply.get('phase') != 'error' or detail not in KNOWN_PRE_SEND_REJECTIONS
            or not isinstance(request_id, str) or not request_id
            or type(revision) is not int or type(selected_slot) is not int
            or not isinstance(tool_item, str) or not isinstance(task_session, str)
            or task_session != getattr(client, 'task', None)):
        return None
    request_path = Path(client.root) / 'request.json'
    reply_path = Path(client.root) / ('reply-' + request_id + '.json')
    try:
        request = _json_file(request_path, label='Native request')
        persisted_reply = _json_file(reply_path, label='Native reply')
        if (persisted_reply != reply
                or not _lift_request_matches(request, record, pos, request_id=request_id,
                                             revision=revision, selected_slot=selected_slot,
                                             tool_item=tool_item, task_session=task_session)
                or not _pre_send_reply_matches(reply, record, request_id=request_id,
                                               revision=revision, detail=detail)):
            return None
        durability = _pre_send_snapshot(reply, record, selected_slot=selected_slot,
                                        tool_item=tool_item)
        current = client.status()
        if (current.get('world_session') != record['world_session']
                or current.get('control_revision') != revision
                or current.get('last_request') != request_id
                or current.get('phase') != 'error'
                or current.get('detail') != detail
                or _grass_count(current) != record['grass_inventory_before']):
            return None
        _matching_silk_tool(current, tool_item, durability)
        return {
            'stage': 'lift_grass', 'source': 'live_native_request_and_reply',
            'request_id': request_id,
            'task_session': task_session,
            'request_world_session': record['world_session'],
            'expected_revision': revision, 'observed_control_revision': revision,
            'native_phase': 'error', 'native_detail': detail,
            'request_sha256': _file_sha256(request_path, limit=131072),
            'native_reply_sha256': _file_sha256(reply_path, limit=262144),
            'action_pos': [pos[0], pos[1] + 1, pos[2]],
            'selected_slot': selected_slot, 'tool_item': tool_item,
            'tool_durability': durability,
            'grass_inventory_count': record['grass_inventory_before'],
        }
    except paving.PavingPending:
        return None


def _live_restore_pre_send_rejection(client, pos, record, reply, intent):
    """Prove an exact restore dispatch rejection happened before useItemOn."""
    detail = reply.get('detail')
    request_id = reply.get('id')
    revision = intent.get('expected_revision')
    selected_slot = intent.get('selected_slot')
    task_session = intent.get('task_session')
    foundation_state = intent.get('expected_state')
    if (reply.get('phase') != 'error' or detail not in KNOWN_PRE_SEND_REJECTIONS
            or not isinstance(request_id, str) or not request_id
            or type(revision) is not int or type(selected_slot) is not int
            or task_session != getattr(client, 'task', None)
            or foundation_state not in (DIRT, GRASS)):
        return None
    request_path = Path(client.root) / 'request.json'
    reply_path = Path(client.root) / ('reply-' + request_id + '.json')
    try:
        request = _json_file(request_path, label='Native request')
        persisted_reply = _json_file(reply_path, label='Native reply')
        if (persisted_reply != reply
                or not _restore_request_matches(
                    request, record, pos, request_id=request_id, revision=revision,
                    foundation_state=foundation_state, task_session=task_session)
                or not _pre_send_reply_matches(reply, record, request_id=request_id,
                                               revision=revision, detail=detail)):
            return None
        _restore_pre_send_snapshot(reply, record, selected_slot=selected_slot)
        current = client.status()
        if (current.get('world_session') != record['world_session']
                or current.get('control_revision') != revision
                or current.get('last_request') != request_id
                or current.get('phase') != 'error' or current.get('detail') != detail
                or _grass_count(current) != record['grass_reserve']):
            return None
        return {
            'stage': 'restore_grass', 'source': 'live_native_request_and_reply',
            'request_id': request_id, 'task_session': task_session,
            'request_world_session': record['world_session'],
            'expected_revision': revision, 'observed_control_revision': revision,
            'native_phase': 'error', 'native_detail': detail,
            'request_sha256': _file_sha256(request_path, limit=131072),
            'native_reply_sha256': _file_sha256(reply_path, limit=262144),
            'action_pos': list(pos), 'selected_slot': selected_slot,
            'item': 'minecraft:grass_block',
            'grass_inventory_count': record['grass_reserve'],
            'foundation_state_at_request': foundation_state,
        }
    except paving.PavingPending:
        return None


def _legacy_lift_pre_send_rejection(client, pos, path, record, evidence):
    """Bind one old write-ahead intent to immutable event and native reply files."""
    if evidence is None:
        return record
    receipts = record.get('receipts')
    if (record.get('phase') != 'lift_intent' or not isinstance(receipts, list)
            or len(receipts) != 1 or receipts[0].get('phase') != 'lift_intent'):
        raise paving.PavingPending('Pre-send evidence applies only to one original lift intent')
    if (not isinstance(evidence, dict) or evidence.get('schema') != 1
            or evidence.get('kind') != PRE_SEND_EVIDENCE_KIND
            or evidence.get('cell') != list(pos) or evidence.get('stage') != 'lift_grass'):
        raise paving.PavingPending('Pre-send reconciliation evidence scope is invalid')
    journal_meta = evidence.get('journal')
    journal_source = _verified_source(journal_meta, limit=262144, label='Journal')
    if journal_source.resolve() != path.resolve() or _json_file(journal_source, label='Journal') != record:
        raise paving.PavingPending('Pre-send evidence does not match the current journal')
    events_meta = evidence.get('events')
    events_path = _verified_source(events_meta, limit=8 * 1024 * 1024, label='Event log')
    progress_meta = evidence.get('progress')
    progress_path = _verified_source(progress_meta, limit=262144, label='Run progress')
    manifest_meta = evidence.get('run_manifest')
    manifest_path = _verified_source(manifest_meta, limit=262144, label='Run manifest')
    reply_meta = evidence.get('native_reply')
    reply_path = _verified_source(reply_meta, limit=262144, label='Native reply')
    request_id = events_meta.get('request_id') if isinstance(events_meta, dict) else None
    if (not isinstance(request_id, str) or not request_id
            or reply_meta.get('request_id') != request_id
            or events_path.parent.resolve() != progress_path.parent.resolve()
            or events_path.parent.resolve() != manifest_path.parent.resolve()
            or reply_path.resolve() != (Path(client.root) / ('reply-' + request_id + '.json')).resolve()):
        raise paving.PavingPending('Pre-send request identity is invalid')
    try:
        events = [json.loads(line) for line in events_path.read_text(encoding='utf-8').splitlines()
                  if line.strip()]
    except (OSError, ValueError, TypeError) as error:
        raise paving.PavingPending('Pre-send event log is invalid') from error
    matches = [event for event in events if event.get('request_id') == request_id]
    if len(matches) != 1:
        raise paving.PavingPending('Pre-send event identity is missing or duplicated')
    event = matches[0]
    reply = _json_file(reply_path, label='Native reply')
    progress = _json_file(progress_path, label='Run progress')
    manifest = _json_file(manifest_path, label='Run manifest')
    task_session = evidence.get('task_session')
    started = progress.get('started_at')
    ended = progress.get('ended_at')
    if (not isinstance(task_session, str) or not task_session
            or getattr(client, 'task', None) == task_session
            or progress.get('schema') != 1 or progress.get('status') != 'pending_review'
            or progress.get('world_session') != record['world_session']
            or progress.get('task_session') != task_session
            or progress.get('done') != 0
            or not isinstance(progress.get('cells_requested'), list)
            or not progress['cells_requested'] or progress['cells_requested'][0] != list(pos)
            or any(not isinstance(cell, list) or len(cell) != 3
                   or any(type(value) is not int for value in cell)
                   for cell in progress['cells_requested'])
            or len({tuple(cell) for cell in progress['cells_requested']})
               != len(progress['cells_requested'])
            or type(started) not in (int, float) or type(ended) not in (int, float)
            or not started <= record['updated_at_ns'] / 1_000_000_000 <= ended
            or manifest.get('schema') != 1 or manifest.get('task_session') != task_session
            or manifest.get('world_session') != record['world_session']
            or manifest.get('placement_key') != record['placement_key']
            or manifest.get('complete') is not False
            or type(manifest.get('created_at')) is not int
            or manifest['created_at'] > int(started * 1000)):
        raise paving.PavingPending('Run evidence does not bind this lift intent to one task')
    params = event.get('params') or {}
    revision = event.get('revision_before')
    selected_slot = params.get('expected_tool_slot')
    tool_item = params.get('expected_tool_item')
    detail = event.get('detail')
    event_time = event.get('time')
    if (event.get('op') != 'mine_block' or event.get('world_session') != record['world_session']
            or event.get('phase') != 'error' or detail not in KNOWN_PRE_SEND_REJECTIONS
            or type(revision) is not int or event.get('revision_after') != revision
            or event.get('inventory_delta') != {}
            or event.get('position_before') != event.get('position_after')
            or event.get('health_before') != event.get('health_after')
            or type(event_time) not in (int, float)
            or not started <= event_time <= ended
            or not 0 <= int(event_time * 1_000_000_000) - record['updated_at_ns'] <= 5_000_000_000
            or not _lift_request_matches(
                {'id': request_id, 'op': event['op'], 'world_session': event['world_session'],
                 'expected_revision': revision, **params}, record, pos,
                request_id=request_id, revision=revision, selected_slot=selected_slot,
                tool_item=tool_item, task_session=task_session)
            or not _pre_send_reply_matches(reply, record, request_id=request_id,
                                           revision=revision, detail=detail)):
        raise paving.PavingPending('Old event is not an exact known pre-send rejection')
    durability = _pre_send_snapshot(reply, record, selected_slot=selected_slot,
                                    tool_item=tool_item)
    _validate_legacy_intent_binding(
        evidence, receipts[-1], stage='lift_grass', task_session=task_session,
        request_id=request_id, world_session=record['world_session'],
        revision=revision, selected_slot=selected_slot, expected_state=GRASS,
        action_pos=[pos[0], pos[1] + 1, pos[2]])
    expected = evidence.get('expected_unchanged_state')
    if (evidence.get('known_error') != detail or expected != {
            'foundation': STONE, 'surface': GRASS,
            'grass_inventory': record['grass_inventory_before'],
            'tool_item': tool_item, 'tool_durability': durability}):
        raise paving.PavingPending('Pre-send evidence summary disagrees with its immutable sources')
    return _record_pre_send_rejection(path, record, {
        'stage': 'lift_grass', 'source': 'immutable_legacy_event_and_reply',
        'request_id': request_id,
        'task_session': task_session,
        'request_world_session': record['world_session'],
        'expected_revision': revision, 'observed_control_revision': revision,
        'native_phase': 'error', 'native_detail': detail,
        'events_sha256': events_meta['sha256'],
        'progress_sha256': progress_meta['sha256'],
        'run_manifest_sha256': manifest_meta['sha256'],
        'native_reply_sha256': reply_meta['sha256'],
        'journal_sha256': journal_meta['sha256'],
        'action_pos': [pos[0], pos[1] + 1, pos[2]],
        'selected_slot': selected_slot, 'tool_item': tool_item,
        'tool_durability': durability,
        'grass_inventory_count': record['grass_inventory_before'],
    })


def _legacy_restore_pre_send_rejection(client, pos, path, record, evidence):
    """Bind the interrupted restore intent to its run and later read-only proof."""
    receipts = record.get('receipts')
    if (record.get('phase') != 'grass_restore_intent' or not isinstance(receipts, list)
            or not receipts or receipts[-1].get('phase') != 'grass_restore_intent'
            or receipts[-1].get('stage') != 'restore_grass'):
        raise paving.PavingPending('Restore evidence applies only to the latest restore intent')
    if (not isinstance(evidence, dict) or evidence.get('schema') != 1
            or evidence.get('kind') != PRE_SEND_EVIDENCE_KIND
            or evidence.get('cell') != list(pos) or evidence.get('stage') != 'restore_grass'):
        raise paving.PavingPending('Restore pre-send evidence scope is invalid')
    journal_meta = evidence.get('journal')
    journal_source = _verified_source(journal_meta, limit=262144, label='Journal')
    if journal_source.resolve() != path.resolve() or _json_file(journal_source, label='Journal') != record:
        raise paving.PavingPending('Restore evidence does not match the current journal')
    events_meta = evidence.get('events')
    events_path = _verified_source(events_meta, limit=8 * 1024 * 1024, label='Event log')
    progress_meta = evidence.get('progress')
    progress_path = _verified_source(progress_meta, limit=262144, label='Run progress')
    manifest_meta = evidence.get('run_manifest')
    manifest_path = _verified_source(manifest_meta, limit=262144, label='Run manifest')
    reply_meta = evidence.get('native_reply')
    reply_path = _verified_source(reply_meta, limit=262144, label='Native reply')
    observation_meta = evidence.get('post_failure_observation')
    observation_path = _verified_source(
        observation_meta, limit=262144, label='Post-failure observation')
    request_id = events_meta.get('request_id') if isinstance(events_meta, dict) else None
    if (not isinstance(request_id, str) or not request_id
            or reply_meta.get('request_id') != request_id
            or events_path.parent.resolve() != progress_path.parent.resolve()
            or events_path.parent.resolve() != manifest_path.parent.resolve()
            or reply_path.resolve() != (Path(client.root) / ('reply-' + request_id + '.json')).resolve()):
        raise paving.PavingPending('Restore pre-send request identity is invalid')
    try:
        events = [json.loads(line) for line in events_path.read_text(encoding='utf-8').splitlines()
                  if line.strip()]
    except (OSError, ValueError, TypeError) as error:
        raise paving.PavingPending('Restore pre-send event log is invalid') from error
    matches = [event for event in events if event.get('request_id') == request_id]
    if len(matches) != 1:
        raise paving.PavingPending('Restore event identity is missing or duplicated')
    event = matches[0]
    reply = _json_file(reply_path, label='Native reply')
    progress = _json_file(progress_path, label='Run progress')
    manifest = _json_file(manifest_path, label='Run manifest')
    observation = _json_file(observation_path, label='Post-failure observation')
    task_session = evidence.get('task_session')
    started, ended = progress.get('started_at'), progress.get('ended_at')
    if (not isinstance(task_session, str) or not task_session
            or getattr(client, 'task', None) == task_session
            or progress.get('schema') != 1 or progress.get('status') != 'pending_review'
            or progress.get('world_session') != record['world_session']
            or progress.get('task_session') != task_session or progress.get('done') != 0
            or progress.get('cells_requested') != [list(pos)]
            or type(started) not in (int, float) or type(ended) not in (int, float)
            or not started <= record['updated_at_ns'] / 1_000_000_000 <= ended
            or manifest.get('schema') != 1 or manifest.get('task_session') != task_session
            or manifest.get('world_session') != record['world_session']
            or manifest.get('placement_key') != record['placement_key']
            or manifest.get('complete') is not False
            or type(manifest.get('created_at')) is not int
            or manifest['created_at'] > int(started * 1000)):
        raise paving.PavingPending('Run evidence does not bind this restore intent')
    params = event.get('params') or {}
    revision = event.get('revision_before')
    detail = event.get('detail')
    event_time = event.get('time')
    foundation_at_request = params.get('expected_state')
    selected_slot = reply.get('selected_slot')
    if (event.get('op') != 'interact' or event.get('world_session') != record['world_session']
            or event.get('phase') != 'error' or detail not in KNOWN_PRE_SEND_REJECTIONS
            or type(revision) is not int or event.get('revision_after') != revision
            or event.get('inventory_delta') != {}
            or event.get('position_before') != event.get('position_after')
            or event.get('health_before') != event.get('health_after')
            or type(event_time) not in (int, float) or not started <= event_time <= ended
            or not 0 <= int(event_time * 1_000_000_000) - record['updated_at_ns'] <= 5_000_000_000
            or not _restore_request_matches(
                {'id': request_id, 'op': event['op'], 'world_session': event['world_session'],
                 'expected_revision': revision, **params}, record, pos,
                request_id=request_id, revision=revision,
                foundation_state=foundation_at_request, task_session=task_session)
            or not _pre_send_reply_matches(reply, record, request_id=request_id,
                                           revision=revision, detail=detail)
            or type(selected_slot) is not int):
        raise paving.PavingPending('Old event is not an exact restore pre-send rejection')
    _restore_pre_send_snapshot(reply, record, selected_slot=selected_slot)
    _validate_legacy_intent_binding(
        evidence, receipts[-1], stage='restore_grass', task_session=task_session,
        request_id=request_id, world_session=record['world_session'],
        revision=revision, selected_slot=selected_slot,
        expected_state=foundation_at_request, action_pos=pos)
    rows = observation.get('observations')
    if (observation.get('world_session') != record['world_session']
            or not isinstance(rows, list) or len(rows) < 2):
        raise paving.PavingPending('Post-failure restore observations are incomplete')
    observed_foundation = None
    previous_time = -1
    for row in rows:
        if not isinstance(row, dict):
            raise paving.PavingPending('Post-failure restore observation is malformed')
        blocks = row.get('blocks')
        if (not isinstance(blocks, list)
                or any(not isinstance(block, dict) or not isinstance(block.get('pos'), list)
                       or len(block['pos']) != 3 for block in blocks)):
            raise paving.PavingPending('Post-failure restore blocks are malformed')
        block_map = {tuple(block['pos']): block for block in blocks or []
                     if isinstance(block, dict) and isinstance(block.get('pos'), list)}
        current_foundation = block_map.get(pos, {}).get('state')
        if (type(row.get('time')) is not int or row['time'] <= previous_time
                or block_map.get((pos[0], pos[1] - 1, pos[2]), {}).get('state') != STONE
                or current_foundation not in (DIRT, GRASS)
                or (pos[0], pos[1] + 1, pos[2]) in block_map
                or row.get('grass_inventory') != record['grass_reserve']
                or any(block.get('solid') is not True
                       or block.get('fluid') is not False
                       or block.get('block_entity') is not False
                       for block in block_map.values())
                or observed_foundation is not None and current_foundation != observed_foundation):
            raise paving.PavingPending('Post-failure restore observation changed')
        observed_foundation = current_foundation
        previous_time = row['time']
    audit = observation.get('audit') or {}
    targets = audit.get('target')
    target_map = {tuple(row['pos']): row for row in targets or []
                  if isinstance(row, dict) and isinstance(row.get('pos'), list)}
    surface = target_map.get((pos[0], pos[1] + 1, pos[2]))
    foundation = target_map.get(pos)
    if (audit.get('loaded') is not True or not isinstance(targets, list)
            or surface is None or surface.get('expected') != GRASS
            or surface.get('actual') not in paving.AIR or surface.get('kind') != 'missing'
            or any(surface.get(key) is not expected for key, expected in (
                ('block_entity', False), ('fluid', False), ('neighbors_loaded', True),
                ('adjacent_fluid', False)))
            or observed_foundation == GRASS and (
                foundation is None or foundation.get('expected') != DIRT
                or foundation.get('actual') != GRASS or foundation.get('kind') != 'occupied'
                or any(foundation.get(key) is not expected for key, expected in (
                    ('block_entity', False), ('fluid', False), ('neighbors_loaded', True),
                    ('adjacent_fluid', False))))
            or observed_foundation == DIRT and foundation is not None):
        raise paving.PavingPending('Post-failure full audit does not match the restore column')
    expected = evidence.get('expected_unchanged_state')
    if (evidence.get('known_error') != detail or expected != {
            'foundation_at_request': foundation_at_request,
            'surface_at_request': 'Block{minecraft:air}',
            'post_failure_foundation': observed_foundation,
            'grass_inventory': record['grass_reserve'],
            'item': 'minecraft:grass_block'}):
        raise paving.PavingPending('Restore evidence summary disagrees with its sources')
    return _record_pre_send_rejection(path, record, {
        'stage': 'restore_grass', 'source': 'immutable_legacy_event_and_reply',
        'request_id': request_id, 'task_session': task_session,
        'request_world_session': record['world_session'],
        'expected_revision': revision, 'observed_control_revision': revision,
        'native_phase': 'error', 'native_detail': detail,
        'events_sha256': events_meta['sha256'],
        'progress_sha256': progress_meta['sha256'],
        'run_manifest_sha256': manifest_meta['sha256'],
        'native_reply_sha256': reply_meta['sha256'],
        'journal_sha256': journal_meta['sha256'],
        'post_failure_observation_sha256': observation_meta['sha256'],
        'action_pos': list(pos), 'selected_slot': selected_slot,
        'item': 'minecraft:grass_block',
        'grass_inventory_count': record['grass_reserve'],
        'foundation_state_at_request': foundation_at_request,
        'post_failure_foundation_state': observed_foundation,
    })


def _legacy_pre_send_rejection(client, pos, path, record, evidence):
    stage = evidence.get('stage') if isinstance(evidence, dict) else None
    if stage == 'lift_grass':
        return _legacy_lift_pre_send_rejection(client, pos, path, record, evidence)
    if stage == 'restore_grass':
        return _legacy_restore_pre_send_rejection(client, pos, path, record, evidence)
    raise paving.PavingPending('Pre-send evidence stage is unsupported')


def _json_lines(path, *, label):
    try:
        rows = [json.loads(line) for line in Path(path).read_text(
            encoding='utf-8').splitlines() if line.strip()]
    except (OSError, ValueError, TypeError) as error:
        raise paving.PavingPending(label + ' evidence is not valid JSONL') from error
    if any(not isinstance(row, dict) for row in rows):
        raise paving.PavingPending(label + ' evidence contains a non-object row')
    return rows


def _post_send_unique_drop(reply, record, pos, drop_uuid):
    entities = reply.get('entities')
    if (not isinstance(drop_uuid, str) or not drop_uuid
            or not isinstance(entities, list)
            or any(not isinstance(entity, dict) for entity in entities)):
        raise paving.PavingPending('Post-send drop evidence is unavailable')
    center = [pos[0] + .5, pos[1] + .5, pos[2] + .5]
    nearby = []
    for entity in entities:
        point = entity.get('pos')
        if (not isinstance(point, list) or len(point) != 3
                or any(type(value) not in (int, float) or not math.isfinite(value)
                       for value in point)):
            raise paving.PavingPending('Post-send entity position is malformed')
        if math.dist(point, center) <= 4:
            nearby.append(entity)
    new = [entity for entity in nearby
           if entity.get('uuid') not in record['nearby_before']]
    if (len(new) != 1 or new[0].get('uuid') != drop_uuid
            or new[0].get('type') != 'minecraft:item'
            or new[0].get('stack', {}).get('item') != 'minecraft:grass_block'
            or new[0].get('stack', {}).get('count') != 1
            or math.dist(new[0]['pos'], center) > 1.5):
        raise paving.PavingPending('Post-send grass drop is not unique to the lift request')
    return new[0]


def _post_send_lift_evidence(client, pos, path, record, evidence):
    """Bind one waiting lift to its unique drop and owned inventory gain."""
    receipts = record.get('receipts')
    if (record.get('phase') != 'lift_intent' or not isinstance(receipts, list)
            or len(receipts) != 1 or receipts[0].get('phase') != 'lift_intent'
            or receipts[0].get('stage') != 'lift_grass'):
        raise paving.PavingPending(
            'Post-send lift evidence applies only to one original lift intent')
    if (not isinstance(evidence, dict) or evidence.get('schema') != 1
            or evidence.get('kind') != POST_SEND_LIFT_EVIDENCE_KIND
            or evidence.get('cell') != list(pos)
            or evidence.get('stage') != 'lift_grass'
            or evidence.get('confirmation_scope')
               != POST_SEND_CONFIRMATION_SCOPE):
        raise paving.PavingPending('Post-send lift evidence scope is invalid')
    journal_meta = evidence.get('journal')
    journal_source = _verified_source(journal_meta, limit=262144, label='Journal')
    if (journal_source.resolve() != path.resolve()
            or _json_file(journal_source, label='Journal') != record):
        raise paving.PavingPending('Post-send evidence does not match the current journal')
    events_meta = evidence.get('events')
    events_path = _verified_source(events_meta, limit=8 * 1024 * 1024,
                                   label='Event log')
    progress_meta = evidence.get('progress')
    progress_path = _verified_source(progress_meta, limit=262144,
                                     label='Run progress')
    manifest_meta = evidence.get('run_manifest')
    manifest_path = _verified_source(manifest_meta, limit=262144,
                                     label='Run manifest')
    reply_meta = evidence.get('native_reply')
    reply_path = _verified_source(reply_meta, limit=262144, label='Native reply')
    mine_id = evidence.get('mine_request_id')
    ascent_id = evidence.get('safety_ascent_request_id')
    drop_uuid = evidence.get('drop_uuid')
    if (not isinstance(mine_id, str) or not mine_id
            or not isinstance(ascent_id, str) or not ascent_id or ascent_id == mine_id
            or reply_meta.get('request_id') != mine_id
            or events_meta.get('mine_request_id') != mine_id
            or events_meta.get('safety_ascent_request_id') != ascent_id
            or events_path.parent.resolve() != progress_path.parent.resolve()
            or events_path.parent.resolve() != manifest_path.parent.resolve()
            or reply_path.resolve()
               != (Path(client.root) / ('reply-' + mine_id + '.json')).resolve()):
        raise paving.PavingPending('Post-send request identity is invalid')
    events = _json_lines(events_path, label='Post-send event log')
    mine_matches = [event for event in events if event.get('request_id') == mine_id]
    ascent_matches = [event for event in events if event.get('request_id') == ascent_id]
    if len(mine_matches) != 1 or len(ascent_matches) != 1:
        raise paving.PavingPending('Post-send event identity is missing or duplicated')
    mine, ascent = mine_matches[0], ascent_matches[0]
    intent = receipts[0]
    progress = _json_file(progress_path, label='Run progress')
    manifest = _json_file(manifest_path, label='Run manifest')
    reply = _json_file(reply_path, label='Native reply')
    task_session = evidence.get('task_session')
    started, ended = progress.get('started_at'), progress.get('ended_at')
    if (not isinstance(task_session, str) or not task_session
            or task_session == getattr(client, 'task', None)
            or progress.get('schema') != 1
            or progress.get('status') != 'pending_review'
            or progress.get('world_session') != record['world_session']
            or progress.get('task_session') != task_session
            or progress.get('cells_requested') != [list(pos)]
            or progress.get('done') != 0
            or type(started) not in (int, float) or type(ended) not in (int, float)
            or not started <= record['updated_at_ns'] / 1_000_000_000 <= ended
            or manifest.get('schema') != 1
            or manifest.get('task_session') != task_session
            or manifest.get('world_session') != record['world_session']
            or manifest.get('placement_key') != record['placement_key']
            or manifest.get('complete') is not False
            or type(manifest.get('created_at')) is not int
            or manifest['created_at'] > int(started * 1000)):
        raise paving.PavingPending('Run evidence does not bind this post-send lift')
    params = mine.get('params') or {}
    revision_before = mine.get('revision_before')
    revision_after = mine.get('revision_after')
    selected_slot = params.get('expected_tool_slot')
    tool_item = params.get('expected_tool_item')
    detail = mine.get('detail')
    mine_time, ascent_time = mine.get('time'), ascent.get('time')
    if (mine.get('op') != 'mine_block'
            or mine.get('world_session') != record['world_session']
            or mine.get('phase') != 'waiting'
            or detail != 'An entity or loose item approached the terrain replacement'
            or type(revision_before) is not int
            or revision_before != intent.get('expected_revision')
            or revision_after != revision_before + 1
            or mine.get('inventory_delta') != {}
            or mine.get('position_before') != mine.get('position_after')
            or mine.get('health_before') != mine.get('health_after')
            or type(mine_time) not in (int, float)
            or not started <= mine_time <= ended
            or not 0 <= int(mine_time * 1_000_000_000) - record['updated_at_ns']
               <= 5_000_000_000
            or not _lift_request_matches(
                {'id': mine_id, 'op': mine['op'],
                 'world_session': mine['world_session'],
                 'expected_revision': revision_before, **params},
                record, pos, request_id=mine_id, revision=revision_before,
                selected_slot=selected_slot, tool_item=tool_item,
                task_session=task_session)):
        raise paving.PavingPending('Waiting lift event is not the exact journaled request')
    lift_requests = [event for event in events
                     if event.get('op') == 'mine_block'
                     and (event.get('params') or {}).get('terrain_replace_stage')
                     == 'lift_grass'
                     and (event.get('params') or {}).get('replacement_pos') == list(pos)]
    if (len(lift_requests) != 1
            or any(event.get('op') == 'interact'
                   and (event.get('params') or {}).get('task_session') == task_session
                   for event in events)):
        raise paving.PavingPending(
            'Post-send run contains another lift or a placement request')
    hand = reply.get('hand') or {}
    post_durability = hand.get('durability')
    if (reply.get('id') != mine_id or reply.get('phase') != 'waiting'
            or reply.get('detail') != detail
            or reply.get('world_session') != record['world_session']
            or reply.get('control_revision') != revision_after
            or reply.get('selected_slot') != selected_slot
            or hand.get('item') != tool_item or hand.get('count') != 1
            or not _has_silk_touch(hand)
            or type(post_durability) is not int
            or post_durability != intent.get('tool_durability') - 1
            or _grass_count(reply) != record['grass_inventory_before']):
        raise paving.PavingPending('Waiting native reply does not prove the one grass lift')
    _matching_silk_tool(reply, tool_item, post_durability,
                        selected_slot=selected_slot)
    _post_send_unique_drop(reply, record, pos, drop_uuid)
    ascent_params = ascent.get('params') or {}
    target = ascent_params.get('target')
    before_position = ascent.get('position_before')
    if (ascent.get('op') != 'navigate'
            or ascent.get('world_session') != record['world_session']
            or ascent.get('phase') != 'done'
            or ascent_params.get('task_session') != task_session
            or ascent_params.get('background_ok') is not True
            or ascent_params.get('air_only') is not True
            or ascent.get('revision_before') != revision_after
            or ascent.get('revision_after') != revision_after + 1
            or ascent.get('inventory_delta') != {'minecraft:grass_block': 1}
            or ascent.get('health_before') != ascent.get('health_after')
            or before_position != mine.get('position_after')
            or not isinstance(target, list) or len(target) != 3
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   for value in target)
            or not isinstance(before_position, list) or len(before_position) != 3
            or math.hypot(target[0] - before_position[0],
                          target[2] - before_position[2]) > .25
            or target[1] < before_position[1] + 20
            or type(ascent_time) not in (int, float)
            or not mine_time < ascent_time <= ended
            or any(event.get('inventory_delta', {}).get('minecraft:grass_block')
                   for event in events
                   if event is not ascent and mine_time <= event.get('time', -1) <= ascent_time)):
        raise paving.PavingPending('Owned safety ascent does not prove the exact grass gain')
    expected = evidence.get('expected_transition')
    if expected != {
            'mine_revision_before': revision_before,
            'mine_revision_after': revision_after,
            'safety_ascent_revision_after': revision_after + 1,
            'grass_inventory_before': record['grass_inventory_before'],
            'grass_inventory_after': record['grass_reserve'],
            'tool_durability_before': intent['tool_durability'],
            'tool_durability_after': post_durability}:
        raise paving.PavingPending('Post-send evidence summary disagrees with its sources')
    return {
        'request_id': mine_id, 'safety_ascent_request_id': ascent_id,
        'task_session': task_session, 'request_world_session': record['world_session'],
        'expected_revision': revision_before,
        'observed_control_revision': revision_after,
        'safety_ascent_revision': revision_after + 1,
        'drop_uuid': drop_uuid, 'tool_item': tool_item,
        'tool_durability_before': intent['tool_durability'],
        'tool_durability_after': post_durability,
        'grass_inventory_before': record['grass_inventory_before'],
        'grass_inventory_after': record['grass_reserve'],
        'journal_sha256': journal_meta['sha256'],
        'events_sha256': events_meta['sha256'],
        'progress_sha256': progress_meta['sha256'],
        'run_manifest_sha256': manifest_meta['sha256'],
        'native_reply_sha256': reply_meta['sha256'],
    }


def _post_send_current_observation(client, pos, record, source, *, settle):
    observations = []
    for index in range(2):
        state, model, audit = _fresh(client, pos, 'grass_removed')
        support = _scan(client, pos, 'grass_removed')
        entities = state.get('entities')
        if (model['content_hash'] != record['model_hash']
                or support != record['support_below']
                or _grass_count(state) != record['grass_reserve']
                or not isinstance(entities, list)
                or any(not isinstance(entity, dict) for entity in entities)
                or source['drop_uuid'] in {
                    entity.get('uuid') for entity in entities}):
            raise paving.PavingPending(
                'Current post-send grass, drop, support, or model evidence changed')
        tools = [row for row in _backpack_rows(state)
                 if row.get('item') == source['tool_item']
                 and row.get('count') == 1 and _has_silk_touch(row)
                 and type(row.get('durability')) is int
                 and row['durability'] >= source['tool_durability_after']]
        if len(tools) != 1:
            raise paving.PavingPending(
                'Original Silk Touch shovel decreased or became ambiguous')
        observations.append({
            'world_session': client.world, 'model_hash': model['content_hash'],
            'model_observed_at': model['observed_at'],
            'audit_observed_at': audit['observed_at'],
            'grass_inventory': _grass_count(state),
            'tool_slot': tools[0]['slot'],
            'tool_durability': tools[0]['durability'],
            'drop_absent': True,
        })
        if index == 0:
            settle(.15)
    first, second = observations
    if (second['model_observed_at'] < first['model_observed_at']
            or second['audit_observed_at'] < first['audit_observed_at']
            or second['tool_slot'] != first['tool_slot']
            or second['tool_durability'] < first['tool_durability']):
        raise paving.PavingPending('Current post-send double observation was not stable')
    return second


def _append_post_send_grass_recovered(path, record, source, observation):
    return paving._record(
        path, record, 'grass_recovered', stage='lift_grass',
        event='owned_safety_ascent_grass_recovered',
        item='minecraft:grass_block', inventory_after=record['grass_reserve'],
        server_confirmed=False,
        confirmation_scope=POST_SEND_CONFIRMATION_SCOPE,
        request_id=source['request_id'],
        safety_ascent_request_id=source['safety_ascent_request_id'],
        task_session=source['task_session'], drop_uuid=source['drop_uuid'],
        request_world_session=source['request_world_session'],
        previous_observation_world_session=source['current_world_session'],
        current_world_session=observation['world_session'],
        loaded_double_scan=True, full_projection_confirmed=True,
        model_hash=observation['model_hash'], drop_absent=True,
        tool_item=source['tool_item'],
        tool_durability_after=source['tool_durability_after'],
        current_tool_durability=observation['tool_durability'])


def _finish_post_send_lift_recovery(client, pos, path, record, source=None,
                                    *, settle):
    if record['phase'] == 'lift_intent':
        if source is None:
            raise paving.PavingPending('Post-send lift requires explicit immutable evidence')
        observation = _post_send_current_observation(
            client, pos, record, source, settle=settle)
        record = paving._record(
            path, record, 'grass_mined', stage='lift_grass',
            event='single_waiting_lift_reconciled', server_confirmed=False,
            confirmation_scope=POST_SEND_CONFIRMATION_SCOPE,
            action_sent_once=True, request_id=source['request_id'],
            safety_ascent_request_id=source['safety_ascent_request_id'],
            task_session=source['task_session'],
            request_world_session=source['request_world_session'],
            expected_revision=source['expected_revision'],
            observed_control_revision=source['observed_control_revision'],
            safety_ascent_revision=source['safety_ascent_revision'],
            drop_uuid=source['drop_uuid'], tool_item=source['tool_item'],
            tool_durability_before=source['tool_durability_before'],
            tool_durability_after=source['tool_durability_after'],
            grass_inventory_before=source['grass_inventory_before'],
            recovered_inventory_after=source['grass_inventory_after'],
            current_world_session=observation['world_session'],
            loaded_double_scan=True, full_projection_confirmed=True,
            current_model_hash=observation['model_hash'], drop_absent=True,
            current_tool_durability=observation['tool_durability'],
            journal_sha256=source['journal_sha256'],
            events_sha256=source['events_sha256'],
            progress_sha256=source['progress_sha256'],
            run_manifest_sha256=source['run_manifest_sha256'],
            native_reply_sha256=source['native_reply_sha256'])
    if record['phase'] != 'grass_mined':
        raise paving.PavingPending('Post-send lift recovery phase is invalid')
    mined = record['receipts'][-1]
    if mined.get('confirmation_scope') != POST_SEND_CONFIRMATION_SCOPE:
        raise paving.PavingPending('Grass mine lacks the explicit post-send receipt')
    source = {
        key: mined[key] for key in (
            'request_id', 'safety_ascent_request_id', 'task_session',
            'request_world_session', 'drop_uuid', 'tool_item',
            'tool_durability_after', 'current_world_session')}
    observation = _post_send_current_observation(
        client, pos, record, source, settle=settle)
    return _append_post_send_grass_recovered(
        path, record, source, observation)


def _load(path, state, model, pos):
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding='utf-8'))
    if (record.get('schema') != 1 or record.get('server') != paving.SITE['server']
            or record.get('dimension') != paving.SITE['dimension']
            or record.get('pos') != list(pos)
            or record.get('placement_key') != state['projection_selection']['key']
            or record.get('model_hash') != model['content_hash']
            or record.get('source') != STONE or record.get('replacement') != DIRT
            or record.get('grass') != GRASS or record.get('phase') not in PHASES):
        raise paving.PavingPending('Existing two-layer journal does not match this projection')
    _validated_history(record)
    return record


def _validated_history(record):
    """Never infer a safe continuation from an editable phase label alone."""
    receipts = record.get('receipts')
    reserve = record.get('grass_reserve')
    starting_grass = record.get('grass_inventory_before')
    nearby_before = record.get('nearby_before')
    if (not isinstance(receipts, list) or not receipts
            or type(reserve) is not int or reserve < 1
            or type(starting_grass) is not int or starting_grass < 0
            or reserve != starting_grass + 1
            or record.get('support_below') != STONE):
        raise paving.PavingPending('Two-layer journal lacks original grass or support evidence')
    if (not isinstance(nearby_before, list)
            or any(type(uuid) is not str or not uuid.strip() for uuid in nearby_before)
            or len(nearby_before) != len(set(nearby_before))):
        raise paving.PavingPending('Two-layer journal has invalid prior entity UUID evidence')
    phase = None
    history_world = None
    pre_send_identity = None
    pre_send_seen = False
    legacy_unbound = None
    strict_world_history = False
    resume_task_session = None
    post_send_lift = None
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise paving.PavingPending('Two-layer journal contains an invalid receipt')
        current = receipt.get('phase')
        if receipt.get('event') == 'pre_send_task_rebind':
            expected_owner_task = (resume_task_session
                                   if resume_task_session is not None
                                   else pre_send_identity.get('task_session')
                                   if pre_send_identity is not None else None)
            if (current != phase or current != 'pre_send_rejected'
                    or pre_send_identity is None
                    or receipt.get('world_session') != history_world
                    or receipt.get('pre_send_request_id') != pre_send_identity['request_id']
                    or receipt.get('pre_send_stage') != pre_send_identity['stage']
                    or receipt.get('previous_task_session') != expected_owner_task
                    or not isinstance(receipt.get('current_task_session'), str)
                    or not receipt['current_task_session']
                    or receipt['current_task_session'] == receipt['previous_task_session']
                    or receipt.get('original_column_confirmed') is not True
                    or receipt.get('no_item_drop') is not True
                    or receipt.get('entity_guard_clear') is not True):
                raise paving.PavingPending('Pre-send task rebind lacks exact unchanged-state evidence')
            resume_task_session = receipt['current_task_session']
            continue
        if receipt.get('event') == 'world_session_rebind':
            if current != phase or current not in REBINDS:
                raise paving.PavingPending('Two-layer rebind has no confirmed predecessor')
            previous_world = receipt.get('previous_world_session')
            current_world = receipt.get('current_world_session')
            expected_owner_task = (resume_task_session
                                   if resume_task_session is not None
                                   else pre_send_identity.get('task_session')
                                   if pre_send_identity is not None else None)
            if current == 'pre_send_rejected' and (
                    pre_send_identity is None
                    or not isinstance(previous_world, str)
                    or not isinstance(current_world, str)
                    or previous_world == current_world
                    or previous_world != history_world
                    or (receipt.get('pre_send_request_id') != pre_send_identity['request_id']
                        and legacy_unbound is None)
                    or (receipt.get('pre_send_stage') != pre_send_identity['stage']
                        and legacy_unbound is None)
                    or (receipt.get('previous_task_session') != expected_owner_task
                        and legacy_unbound is None)
                    or (not isinstance(receipt.get('current_task_session'), str)
                        and legacy_unbound is None)
                    or history_world != previous_world
                    or not isinstance(receipt.get('previous_nearby_before'), list)
                    or not isinstance(receipt.get('nearby_before'), list)
                    or any(not isinstance(uuid, str) or not uuid
                           for uuid in (receipt['previous_nearby_before']
                                        + receipt['nearby_before']))
                    or receipt.get('original_column_confirmed') is not True
                    or receipt.get('no_item_drop') is not True
                    or receipt.get('entity_guard_clear') is not True):
                raise paving.PavingPending('Pre-send rebind lacks exact unchanged-state evidence')
            has_world_binding = (isinstance(previous_world, str)
                                 and isinstance(current_world, str))
            if has_world_binding:
                if (previous_world == current_world
                        or history_world is not None and history_world != previous_world):
                    raise paving.PavingPending('World-bound two-layer history has an invalid rebind')
                history_world = current_world
                if current == 'pre_send_rejected' and legacy_unbound is None:
                    if receipt['current_task_session'] == receipt['previous_task_session']:
                        raise paving.PavingPending('Pre-send world rebind did not rotate task ownership')
                    resume_task_session = receipt['current_task_session']
            elif strict_world_history or pre_send_seen:
                raise paving.PavingPending('World-bound two-layer history lacks a rebind identity')
            else:
                history_world = None
            continue
        if current not in TRANSITIONS.get(phase, set()):
            raise paving.PavingPending('Two-layer journal phases are incomplete or out of order')
        if phase == 'pre_send_rejected' and pre_send_identity is not None:
            expected_intent = ('lift_intent' if pre_send_identity['stage'] == 'lift_grass'
                               else 'grass_restore_intent')
            if current != expected_intent:
                raise paving.PavingPending('Pre-send recovery resumed the wrong terrain stage')
            if (resume_task_session is not None
                    and receipt.get('task_session') != resume_task_session):
                raise paving.PavingPending('Pre-send recovery resumed under another material task')
            resume_task_session = None
        if (current == 'lift_intent' and receipt.get('stage') != 'lift_grass'
                or current == 'grass_mined' and receipt.get('stage') != 'lift_grass'
                or current == 'stone_mine_intent' and receipt.get('stage') != 'mine_stone'
                or current == 'stone_mined' and receipt.get('stage') != 'mine_stone'
                or current == 'dirt_place_intent' and receipt.get('stage') != 'place_dirt'
                or current == 'dirt_placed' and receipt.get('stage') != 'place_dirt'
                or current == 'grass_restore_intent' and receipt.get('stage') != 'restore_grass'
                or current == 'grass_decay_wait' and receipt.get('stage') != 'restore_grass'
                or current == 'grass_placed' and receipt.get('stage') != 'restore_grass'):
            raise paving.PavingPending('Two-layer journal stage receipt is invalid')
        if current in ('lift_intent', 'grass_restore_intent') and receipt.get('intent_world_session') is not None:
            intent_world = receipt.get('intent_world_session')
            if (not isinstance(intent_world, str) or not intent_world
                    or history_world is not None and history_world != intent_world
                    or (not isinstance(receipt.get('task_session'), str)
                        or not receipt['task_session']) and legacy_unbound is None):
                raise paving.PavingPending('Terrain intent world or task identity is invalid')
            history_world = intent_world
            if isinstance(receipt.get('task_session'), str) and receipt['task_session']:
                strict_world_history = True
        if current == 'pre_send_rejected':
            legacy = receipt.get('source') == 'immutable_legacy_event_and_reply'
            stage = receipt.get('stage')
            unbound = (legacy and not receipt.get('task_session')
                       and not receipt.get('progress_sha256')
                       and not receipt.get('run_manifest_sha256'))
            digests = (('native_reply_sha256', 'events_sha256', 'journal_sha256')
                       if unbound else
                       ('native_reply_sha256', 'events_sha256', 'journal_sha256',
                        'progress_sha256', 'run_manifest_sha256')
                       if legacy else ('native_reply_sha256', 'request_sha256'))
            if legacy and stage == 'restore_grass' and not unbound:
                digests = (*digests, 'post_failure_observation_sha256')
            expected_action = ([record['pos'][0], record['pos'][1] + 1, record['pos'][2]]
                               if stage == 'lift_grass' else list(record['pos']))
            stage_evidence_invalid = (
                stage == 'lift_grass' and (
                    receipt.get('tool_item') not in ('minecraft:diamond_shovel',
                                                     'minecraft:netherite_shovel')
                    or type(receipt.get('tool_durability')) is not int
                    or receipt['tool_durability'] < 64
                    or receipt.get('grass_inventory_count') != starting_grass)
                or stage == 'restore_grass' and (
                    receipt.get('item') != 'minecraft:grass_block'
                    or receipt.get('grass_inventory_count') != reserve
                    or receipt.get('foundation_state_at_request') not in (DIRT, GRASS)))
            if (receipt.get('event') != 'native_preflight_rejected_before_send'
                    or receipt.get('action_sent') is not False
                    or stage not in ('lift_grass', 'restore_grass')
                    or receipt.get('source') not in (
                        'immutable_legacy_event_and_reply', 'live_native_request_and_reply')
                    or receipt.get('native_phase') != 'error'
                    or receipt.get('native_detail') not in KNOWN_PRE_SEND_REJECTIONS
                    or not isinstance(receipt.get('request_id'), str)
                    or not receipt['request_id']
                    or (not isinstance(receipt.get('task_session'), str)
                        or not receipt['task_session']) and not unbound
                    or not isinstance(receipt.get('request_world_session'), str)
                    or type(receipt.get('expected_revision')) is not int
                    or receipt.get('observed_control_revision') != receipt['expected_revision']
                    or receipt.get('action_pos') != expected_action
                    or stage_evidence_invalid
                    or any(not isinstance(receipt.get(name), str)
                           or len(receipt[name]) != 64
                           or any(ch not in '0123456789abcdef' for ch in receipt[name])
                           for name in digests)):
                raise paving.PavingPending('Pre-send rejection receipt is incomplete')
            request_world = receipt['request_world_session']
            if history_world is not None and history_world != request_world:
                raise paving.PavingPending('Pre-send rejection belongs to another intent world')
            history_world = request_world
            pre_send_identity = {'world_session': request_world,
                                 'request_id': receipt['request_id'], 'stage': stage,
                                 'task_session': receipt.get('task_session')}
            pre_send_seen = True
            strict_world_history = True
            if unbound:
                legacy_unbound = {**pre_send_identity, 'stage': receipt['stage']}
        if (current == 'grass_recovered'
                and (receipt.get('item') != 'minecraft:grass_block'
                     or type(receipt.get('inventory_after')) is not int
                     or receipt['inventory_after'] < reserve)
                or current == 'stone_recovered'
                and (receipt.get('item') not in ('minecraft:cobblestone', 'minecraft:stone')
                     or type(receipt.get('inventory_after')) is not int
                     or receipt['inventory_after'] < 1)
                or current in ('grass_pickup_intent', 'stone_pickup_intent')
                and (not isinstance(receipt.get('drop_uuid'), str)
                     or not receipt['drop_uuid'])):
            raise paving.PavingPending('Two-layer journal lacks a uniquely recovered drop')
        if current == 'grass_pickup_intent' and post_send_lift is not None:
            raise paving.PavingPending(
                'Post-send inventory recovery must not replay drop collection')
        if current == 'grass_mined' and receipt.get(
                'confirmation_scope') == POST_SEND_CONFIRMATION_SCOPE:
            digests = ('journal_sha256', 'events_sha256', 'progress_sha256',
                       'run_manifest_sha256', 'native_reply_sha256')
            if (receipt.get('event') != 'single_waiting_lift_reconciled'
                    or receipt.get('server_confirmed') is not False
                    or receipt.get('action_sent_once') is not True
                    or receipt.get('request_world_session') != history_world
                    or receipt.get('task_session')
                       != receipts[0].get('task_session')
                    or type(receipt.get('expected_revision')) is not int
                    or receipt.get('expected_revision')
                       != receipts[0].get('expected_revision')
                    or receipt.get('observed_control_revision')
                       != receipt.get('expected_revision') + 1
                    or receipt.get('safety_ascent_revision')
                       != receipt.get('observed_control_revision') + 1
                    or not isinstance(receipt.get('request_id'), str)
                    or not receipt['request_id']
                    or not isinstance(receipt.get('safety_ascent_request_id'), str)
                    or not receipt['safety_ascent_request_id']
                    or receipt['request_id'] == receipt['safety_ascent_request_id']
                    or not isinstance(receipt.get('drop_uuid'), str)
                    or not receipt['drop_uuid']
                    or receipt.get('tool_item') != receipts[0].get('tool_item')
                    or type(receipt.get('tool_durability_before')) is not int
                    or receipt.get('tool_durability_before')
                       != receipts[0].get('tool_durability')
                    or receipt.get('tool_durability_after')
                       != receipt.get('tool_durability_before') - 1
                    or type(receipt.get('current_tool_durability')) is not int
                    or receipt['current_tool_durability']
                       < receipt['tool_durability_after']
                    or receipt.get('grass_inventory_before') != starting_grass
                    or receipt.get('recovered_inventory_after') != reserve
                    or not isinstance(receipt.get('current_world_session'), str)
                    or not receipt['current_world_session']
                    or receipt.get('loaded_double_scan') is not True
                    or receipt.get('full_projection_confirmed') is not True
                    or receipt.get('current_model_hash') != record['model_hash']
                    or receipt.get('drop_absent') is not True
                    or any(not isinstance(receipt.get(name), str)
                           or len(receipt[name]) != 64
                           or any(ch not in '0123456789abcdef'
                                  for ch in receipt[name])
                           for name in digests)):
                raise paving.PavingPending(
                    'Post-send grass mine receipt is incomplete')
            post_send_lift = {
                'request_id': receipt['request_id'],
                'safety_ascent_request_id': receipt['safety_ascent_request_id'],
                'task_session': receipt['task_session'],
                'request_world_session': receipt['request_world_session'],
                'current_world_session': receipt['current_world_session'],
                'drop_uuid': receipt['drop_uuid'],
                'tool_item': receipt['tool_item'],
                'tool_durability_after': receipt['tool_durability_after'],
            }
        if (current == 'grass_recovered'
                and receipt.get('confirmation_scope') == POST_SEND_CONFIRMATION_SCOPE):
            if (post_send_lift is None
                    or receipt.get('event')
                       != 'owned_safety_ascent_grass_recovered'
                    or receipt.get('server_confirmed') is not False
                    or any(receipt.get(key) != value
                           for key, value in post_send_lift.items()
                           if key != 'current_world_session')
                    or receipt.get('previous_observation_world_session')
                       != post_send_lift['current_world_session']
                    or not isinstance(receipt.get('current_world_session'), str)
                    or not receipt['current_world_session']
                    or receipt.get('inventory_after') != reserve
                    or receipt.get('loaded_double_scan') is not True
                    or receipt.get('full_projection_confirmed') is not True
                    or receipt.get('model_hash') != record['model_hash']
                    or receipt.get('drop_absent') is not True
                    or type(receipt.get('current_tool_durability')) is not int
                    or receipt['current_tool_durability']
                       < post_send_lift['tool_durability_after']):
                raise paving.PavingPending(
                    'Post-send grass recovery receipt is incomplete')
            post_send_lift = None
        if current == 'complete' and receipt.get('event') != 'full_projection_confirmed':
            raise paving.PavingPending('Two-layer completion lacks full projection evidence')
        if current in ('grass_mined', 'stone_mined', 'dirt_placed',
                       'grass_decay_wait', 'grass_placed') and not (
                current == 'grass_mined'
                and receipt.get('confirmation_scope') == POST_SEND_CONFIRMATION_SCOPE) and (
                receipt.get('server_confirmed') is not True
                or receipt.get('confirmation_scope') != 'matched_server_block_update_after_native_send'):
            raise paving.PavingPending('Two-layer stage lacks its matching native server packet receipt')
        if current == 'grass_decay_wait' and (
                receipt.get('foundation_state_before') != GRASS
                or receipt.get('item_after') != starting_grass):
            raise paving.PavingPending('Grass decay wait lacks exact spread-foundation placement proof')
        if current == 'grass_placed' and receipt.get('event') == 'covered_foundation_naturally_decayed' and (
                receipt.get('foundation_state') != DIRT or receipt.get('surface_state') != GRASS
                or receipt.get('item_after') != starting_grass
                or receipt.get('loaded_double_scan') is not True
                or receipt.get('full_projection_confirmed') is not True):
            raise paving.PavingPending('Natural grass decay completion evidence is incomplete')
        if current == 'grass_mined' and legacy_unbound is not None:
            legacy_unbound = None
        phase = current
    if phase != record.get('phase'):
        raise paving.PavingPending('Two-layer phase label disagrees with its receipt chain')
    if strict_world_history and history_world != record.get('world_session'):
        raise paving.PavingPending('Two-layer journal world disagrees with pre-send history')
    if legacy_unbound is not None:
        raise paving.PavingPending('Unbound legacy pre-send evidence has no later confirmed lift')
    if post_send_lift is not None and phase != 'grass_mined':
        raise paving.PavingPending('Post-send lift lacks its owned inventory recovery')


def _request_fields(state, pos, below, stage):
    return {'terrain_replace_guard': True, 'terrain_replace_stage': stage,
            'replacement_pos': list(pos),
            'expected_surface_state': GRASS,
            'expected_below_state': below,
            'placement_key': state['projection_selection']['key']}


def _collect_one(client, pos, path, record, *, item_set, mined_phase,
                 pickup_phase, recovered_phase, before):
    state = client.status()
    center = [pos[0] + .5, pos[1] + .5, pos[2] + .5]
    if (math.dist(state['pos'], center) > 12 or not isinstance(state.get('entities'), list)):
        raise paving.PavingPending('Drop and nearby entity coverage was lost')
    nearby = [e for e in state['entities'] if isinstance(e.get('pos'), list)
              and len(e['pos']) == 3 and math.dist(e['pos'], center) <= 4]
    if any(e.get('type') != 'minecraft:item' for e in nearby):
        raise paving.PavingPending('An animal or player approached the open cell')
    gained = {item: paving._counts(state)[item] - before[item] for item in item_set}
    if any(n < 0 or n > 1 for n in gained.values()):
        raise paving.PavingPending('Drop inventory changed by an unexpected quantity')
    new = [e for e in nearby if e.get('uuid') not in record['nearby_before']]
    if (any(e.get('stack', {}).get('item') not in item_set
            or e.get('stack', {}).get('count') != 1 for e in nearby)
            or any(math.dist(e['pos'], center) > 1.5 for e in new)
            or len(new) + sum(gained.values()) != 1):
        raise paving.PavingPending('Excavation drop identity is not unique')
    if new:
        drop = new[0]
        record = paving._record(path, record, pickup_phase, drop_uuid=drop['uuid'],
                               item=drop['stack']['item'])
        if not collect_drop(client, drop, observation=state):
            raise paving.PavingPending('Owned drop pickup was not confirmed')
        if paving._counts(client.status())[drop['stack']['item']] != before[drop['stack']['item']] + 1:
            raise paving.PavingPending('Collected inventory did not match the original cell')
        item = drop['stack']['item']
    else:
        item = next(item for item, n in gained.items() if n == 1)
    return paving._record(path, record, recovered_phase,
                          item=item, inventory_after=paving._counts(client.status())[item])


def _confirm_block(client, pos, expected):
    reply = client.request('scan', min=list(pos), max=list(pos), details=True)
    if (reply.get('phase') not in (None, 'done') or reply.get('world_session') != client.world
            or not isinstance(reply.get('blocks'), list)):
        raise paving.PavingPending('Exact server block scan is unavailable')
    rows = reply['blocks']
    if expected is None:
        return not rows
    return len(rows) == 1 and rows[0].get('pos') == list(pos) and rows[0].get('state') == expected


def _stage(client, pos, path, record, *, stage, intent, complete,
           op, target, face, expected, hand=None, source_slot=None,
           settle=time.sleep, observed_phase=None):
    phase_before = observed_phase or {
        'lift_grass': 'initial', 'mine_stone': 'grass_removed',
        'place_dirt': 'both_removed', 'restore_grass': 'dirt_placed',
    }[stage]
    state, model, _ = _fresh(client, pos, phase_before)
    below = _scan(client, pos, phase_before)
    if record['world_session'] != client.world or record['model_hash'] != model['content_hash']:
        raise paving.PavingPending('Two-layer journal changed across world or model')
    _reach_station(client, pos)
    if hand is not None:
        client.checked('select_item', item=hand,
                       **({'slot': source_slot} if source_slot is not None else {}))
    state, model, _ = _fresh(client, pos, phase_before)
    current_below = _scan(client, pos, phase_before)
    ready = _station_status(client, pos)
    if op == 'mine_block':
        _reject_old_drops(ready, pos)
    selected=ready.get('selected_slot')
    held=ready.get('hand') or {}
    revision=ready.get('control_revision')
    selected_rows=[row for row in ready.get('inventory',[])
                   if row.get('slot')==selected]
    if (current_below != below or record['model_hash'] != model['content_hash']
            or hand is not None and held.get('item') != hand
            or type(selected) is not int or not 0 <= selected <= 8
            or type(revision) is not int
            or state.get('selected_slot') != selected
            or hand is not None and (len(selected_rows) != 1
                                     or selected_rows[0].get('item') != hand
                                     or type(selected_rows[0].get('count')) is not int
                                     or selected_rows[0]['count'] < 1)
            or op == 'mine_block' and (len(selected_rows) != 1
                                      or selected_rows[0].get('count') != 1
                                      or type(held.get('durability')) is not int
                                      or held['durability'] < 64
                                      or stage == 'lift_grass'
                                      and (not _has_silk_touch(held)
                                           or not _has_silk_touch(selected_rows[0])))):
        raise paving.PavingPending('Tool, foundation, or model changed before an exact stage')
    stock_before = Counter(paving._counts(ready))
    intent_evidence={'stage':stage,
                     'item_before':stock_before.get(hand,0) if hand else None}
    if stage == 'lift_grass':
        intent_evidence.update(
            request_op=op, intent_world_session=client.world,
            task_session=client.task,
            expected_revision=revision, action_pos=list(target),
            expected_state=expected, selected_slot=selected,
            tool_item=hand, tool_durability=held.get('durability'),
            grass_inventory_count=paving._counts(ready)['minecraft:grass_block'])
    elif stage == 'restore_grass':
        intent_evidence.update(
            request_op=op, intent_world_session=client.world,
            task_session=client.task, expected_revision=revision,
            action_pos=list(target), expected_state=expected,
            selected_slot=selected, item='minecraft:grass_block',
            grass_inventory_count=paving._counts(ready)['minecraft:grass_block'])
    record = paving._record(path, record, intent, **intent_evidence)
    intent_receipt=record['receipts'][-1]
    fields = _request_fields(ready, pos, below, stage)
    reply = client.request(op, pos=target, face=face, expected_state=expected,
                           **({'expected_hand': hand} if op == 'interact' else {}),
                           **({'required_silk_shovel': True,
                               'expected_tool_slot': selected,
                               'expected_tool_item': hand} if stage == 'lift_grass' else {}),
                           **({'seconds': 20} if op == 'mine_block' else {}), **fields)
    if (reply.get('phase') != 'done' or reply.get('server_confirmed') is not True
            or reply.get('confirmation_scope') != 'matched_server_block_update_after_native_send'):
        if stage == 'lift_grass':
            rejected=_live_pre_send_rejection(client,pos,path,record,reply,intent_receipt)
        elif stage == 'restore_grass':
            rejected=_live_restore_pre_send_rejection(client,pos,record,reply,intent_receipt)
        else:
            rejected=None
        if rejected is not None:
            _record_pre_send_rejection(path,record,rejected)
            raise paving.PavingPending(
                'Native '+stage+' was rejected before send; reconnect and reconcile before retry')
        raise paving.PavingPending('Native ' + stage + ' lacks a matching server block update; never replay it')
    settle(.8)
    if not _confirm_block(client, target if stage != 'place_dirt' and stage != 'restore_grass'
                          else ([pos[0], pos[1], pos[2]] if stage == 'place_dirt'
                                else [pos[0], pos[1] + 1, pos[2]]),
                          None if stage in ('lift_grass', 'mine_stone')
                          else DIRT if stage == 'place_dirt' else GRASS):
        raise paving.PavingPending('Server did not confirm ' + stage + ' block transition')
    settle(.15)
    if not _confirm_block(client, target if stage not in ('place_dirt', 'restore_grass')
                          else ([pos[0], pos[1], pos[2]] if stage == 'place_dirt'
                                else [pos[0], pos[1] + 1, pos[2]]),
                          None if stage in ('lift_grass', 'mine_stone')
                          else DIRT if stage == 'place_dirt' else GRASS):
        raise paving.PavingPending('Second server-state observation changed after ' + stage)
    if op == 'interact' and paving._counts(client.status())[hand] != stock_before[hand] - 1:
        raise paving.PavingPending('Placement inventory did not confirm ' + stage)
    complete_evidence = {
        'stage': stage,
        'item_after': paving._counts(client.status())[hand] if hand else None,
        'server_confirmed': True,
        'confirmation_scope': reply['confirmation_scope'],
    }
    if stage == 'restore_grass':
        complete_evidence['foundation_state_before'] = expected
    return paving._record(path, record, complete, **complete_evidence), stock_before


def _raw_restore_column(client, pos):
    reply = client.request('scan', min=[pos[0], pos[1] - 1, pos[2]],
                           max=[pos[0], pos[1] + 1, pos[2]], details=True)
    if (reply.get('phase') not in (None, 'done') or reply.get('world_session') != client.world
            or not isinstance(reply.get('blocks'), list)):
        raise paving.PavingPending('Restore column scan is unavailable')
    cells = {}
    for row in reply['blocks']:
        point = paving._position(row.get('pos'))
        if point in cells or point not in (
                (pos[0], pos[1] - 1, pos[2]), pos,
                (pos[0], pos[1] + 1, pos[2])):
            raise paving.PavingPending('Restore column scan is malformed')
        if (row.get('fluid') is not False or row.get('block_entity') is not False
                or row.get('solid') is not True):
            raise paving.PavingPending('Restore column contains an unsafe block')
        cells[point] = row
    if cells.get((pos[0], pos[1] - 1, pos[2]), {}).get('state') != STONE:
        raise paving.PavingPending('Restore column lost its Y61 stone support')
    base = cells.get(pos, {}).get('state')
    top = cells.get((pos[0], pos[1] + 1, pos[2]), {}).get('state')
    return base, top


def _observe_restore_phase(client, pos):
    first = _raw_restore_column(client, pos)
    phases = {
        (DIRT, None): 'dirt_placed', (GRASS, None): 'dirt_spread',
        (GRASS, GRASS): 'grass_decay_wait', (DIRT, GRASS): 'complete',
    }
    phase = phases.get(first)
    if phase is None:
        raise paving.PavingPending('Restore column is outside the safe dirt/grass states')
    state, model, _ = _fresh(client, pos, phase)
    _scan(client, pos, phase)
    if _raw_restore_column(client, pos) != first:
        raise paving.PavingPending('Restore column changed during one loaded observation')
    return phase, state, model


def _double_restore_phase(client, pos, *, allowed, settle):
    for _ in range(3):
        first, state, model = _observe_restore_phase(client, pos)
        settle(.8)
        second, second_state, second_model = _observe_restore_phase(client, pos)
        if first == second:
            if first not in allowed or model['content_hash'] != second_model['content_hash']:
                raise paving.PavingPending('Restore phase is not allowed for this recovery')
            return first, second_state, second_model
    raise paving.PavingPending('Restore column changed during double observation')


def _terrain_entity_guard(state, pos):
    """Conservatively mirror the native surface.inflate(4) point envelope."""
    entities = state.get('entities')
    if not isinstance(entities, list):
        raise paving.PavingPending('Terrain entity coverage is unavailable for retry')
    x, y, z = pos
    for entity in entities:
        point = entity.get('pos') if isinstance(entity, dict) else None
        if (not isinstance(point, list) or len(point) != 3
                or any(type(value) not in (int, float) or not math.isfinite(value)
                       for value in point)):
            raise paving.PavingPending('Terrain entity evidence is malformed')
        if (x - 4 <= point[0] <= x + 5 and y - 3 <= point[1] <= y + 6
                and z - 4 <= point[2] <= z + 5):
            raise paving.PavingBlocked('Current native terrain entity guard would reject this cell')


def _pre_send_receipt(record):
    matches = [receipt for receipt in record.get('receipts', [])
               if receipt.get('phase') == 'pre_send_rejected'
               and receipt.get('event') == 'native_preflight_rejected_before_send']
    if not matches:
        raise paving.PavingPending('Pre-send rejection receipt is missing')
    return matches[-1]


def _pre_send_rebind_kind(client, record, rejection):
    old_world = record['world_session']
    old_task = rejection.get('task_session')
    current_task = getattr(client, 'task', None)
    if not isinstance(old_task, str) or not old_task:
        raise paving.PavingPending('Pre-send rejection has no original material task')
    if not isinstance(current_task, str) or not current_task:
        raise paving.PavingPending('Pre-send recovery requires a material task session')
    last = record.get('receipts', [])[-1]
    anchored = (last.get('phase') == 'pre_send_rejected'
                and last.get('event') in ('world_session_rebind', 'pre_send_task_rebind')
                and last.get('pre_send_request_id') == rejection['request_id']
                and last.get('pre_send_stage') == rejection['stage'])
    if anchored:
        owner_world = (last.get('current_world_session')
                       if last.get('event') == 'world_session_rebind'
                       else last.get('world_session'))
        owner_task = last.get('current_task_session')
        if (not isinstance(owner_world, str) or owner_world != old_world
                or not isinstance(owner_task, str) or not owner_task):
            raise paving.PavingPending('Pre-send rebind chain no longer owns this journal')
        if client.world == owner_world and current_task == owner_task:
            return 'already_rebound', owner_task
        if current_task == owner_task:
            raise paving.PavingPending('World change requires a new material task session')
        return (('world_session_rebind' if client.world != owner_world
                 else 'pre_send_task_rebind'), owner_task)
    if old_world != rejection['request_world_session']:
        raise paving.PavingPending('Pre-send rejection world does not own this journal')
    if current_task == old_task:
        raise paving.PavingPending('Pre-send recovery requires a new material task session')
    return ('world_session_rebind' if old_world != client.world
            else 'pre_send_task_rebind'), old_task


def _record_pre_send_rebind(path, record, rejection, client, kind, previous_task,
                            nearby, **proof):
    if kind == 'already_rebound':
        return record
    common = {
        'pre_send_request_id': rejection['request_id'],
        'pre_send_stage': rejection['stage'],
        'previous_task_session': previous_task,
        'current_task_session': client.task,
        'previous_nearby_before': record['nearby_before'],
        'nearby_before': nearby,
        'original_column_confirmed': True,
        'no_item_drop': True,
        'entity_guard_clear': True,
        **proof,
    }
    if kind == 'world_session_rebind':
        return paving._record(
            path, {**record, 'world_session': client.world, 'nearby_before': nearby},
            'pre_send_rejected', event=kind,
            previous_world_session=record['world_session'],
            current_world_session=client.world, **common)
    if kind == 'pre_send_task_rebind':
        return paving._record(
            path, {**record, 'nearby_before': nearby}, 'pre_send_rejected',
            event=kind, world_session=client.world, **common)
    raise paving.PavingPending('Unsupported pre-send rebind kind')


def _reconcile_lift_pre_send(client, pos, path, record):
    """Rebind an unsent lift only after a new session proves the original state."""
    rejection = _pre_send_receipt(record)
    kind, previous_task = _pre_send_rebind_kind(client, record, rejection)
    state, model, _ = _fresh(client, pos, 'initial')
    support = _scan(client, pos, 'initial')
    if (model['content_hash'] != record['model_hash'] or support != record['support_below']
            or _grass_count(state) != rejection['grass_inventory_count']
            or rejection['grass_inventory_count'] != record['grass_inventory_before']):
        raise paving.PavingPending('Original terrain or grass inventory changed before reconciliation')
    _matching_silk_tool(state, rejection['tool_item'], rejection['tool_durability'])
    _reach_station(client, pos)
    fresh, fresh_model, _ = _fresh(client, pos, 'initial')
    fresh_support = _scan(client, pos, 'initial')
    observed = _station_status(client, pos)
    if (fresh_model['content_hash'] != record['model_hash']
            or fresh_support != record['support_below']
            or _grass_count(fresh) != rejection['grass_inventory_count']
            or _grass_count(observed) != rejection['grass_inventory_count']):
        raise paving.PavingPending('Fresh original-column proof changed while reconciling')
    shovel = _matching_silk_tool(observed, rejection['tool_item'],
                                 rejection['tool_durability'])
    _terrain_entity_guard(observed, pos)
    _reject_old_drops(observed, pos)
    nearby = []
    for entity in observed['entities']:
        uuid = entity.get('uuid')
        if not isinstance(uuid, str) or not uuid:
            raise paving.PavingPending('Reconciled entity identity is unavailable')
        nearby.append(uuid)
    record = _record_pre_send_rebind(
        path, record, rejection, client, kind, previous_task, nearby,
        foundation_state=STONE, surface_state=GRASS, support_state=fresh_support,
        grass_inventory_count=rejection['grass_inventory_count'],
        tool_item=rejection['tool_item'], tool_durability=rejection['tool_durability'],
        model_hash=fresh_model['content_hash'])
    return record, shovel


def _retry_pre_send_lift(client, pos, path, record, shovel, *, settle):
    state, model, _ = _fresh(client, pos, 'initial')
    if model['content_hash'] != record['model_hash']:
        raise paving.PavingPending('Projection changed before the reconciled lift')
    _scan(client, pos, 'initial')
    _tool(state, 'minecraft:diamond_pickaxe')
    if paving._counts(state)['minecraft:dirt'] < 1 or _free_slots(state) < 2:
        raise paving.PavingBlocked('Dirt and two confirmed empty drop slots are required')
    record, before = _stage(client, pos, path, record, stage='lift_grass',
                            intent='lift_intent', complete='grass_mined',
                            op='mine_block', target=[pos[0], pos[1] + 1, pos[2]],
                            face='up', expected=GRASS, hand=shovel['item'],
                            source_slot=shovel['slot'], settle=settle)
    record = _collect_one(client, pos, path, record,
                          item_set={'minecraft:grass_block'}, mined_phase='grass_mined',
                          pickup_phase='grass_pickup_intent',
                          recovered_phase='grass_recovered', before=before)
    return _finish_stone_and_restore(client, pos, path, record, settle=settle)


def _grass_stack(state, expected_total):
    rows = [row for row in _backpack_rows(state)
            if row.get('item') == 'minecraft:grass_block' and row.get('count', 0) > 0]
    if not rows or sum(row['count'] for row in rows) != expected_total:
        raise paving.PavingPending('Exact recovered grass inventory is unavailable')
    return max(rows, key=lambda row: row['count'])


def _reconcile_restore_pre_send(client, pos, path, record, *, settle):
    rejection = _pre_send_receipt(record)
    if rejection.get('stage') != 'restore_grass':
        raise paving.PavingPending('Restore recovery lacks its exact pre-send receipt')
    kind, previous_task = _pre_send_rebind_kind(client, record, rejection)
    phase, state, model = _double_restore_phase(
        client, pos, allowed={'dirt_placed', 'dirt_spread'}, settle=settle)
    if (model['content_hash'] != record['model_hash']
            or _grass_count(state) != record['grass_reserve']):
        raise paving.PavingPending('Restore projection or grass inventory changed across reconnect')
    _reach_station(client, pos)
    phase, observed, model = _double_restore_phase(
        client, pos, allowed={'dirt_placed', 'dirt_spread'}, settle=settle)
    if (model['content_hash'] != record['model_hash']
            or _grass_count(observed) != record['grass_reserve']):
        raise paving.PavingPending('Restore state changed at the exact work station')
    observed = _station_status(client, pos)
    _terrain_entity_guard(observed, pos)
    _reject_old_drops(observed, pos)
    stack = _grass_stack(observed, record['grass_reserve'])
    foundation_state = DIRT if phase == 'dirt_placed' else GRASS
    nearby = []
    for entity in observed['entities']:
        uuid = entity.get('uuid')
        if not isinstance(uuid, str) or not uuid:
            raise paving.PavingPending('Reconciled restore entity identity is unavailable')
        nearby.append(uuid)
    record = _record_pre_send_rebind(
        path, record, rejection, client, kind, previous_task, nearby,
        foundation_state=foundation_state, surface_state='Block{minecraft:air}',
        support_state=STONE, grass_inventory_count=record['grass_reserve'],
        model_hash=model['content_hash'])
    return record, stack, foundation_state


def _finish_grass_decay_wait(client, pos, path, record, *, settle):
    phase, state, _ = _double_restore_phase(
        client, pos, allowed={'grass_decay_wait', 'complete'}, settle=settle)
    if _grass_count(state) != record['grass_reserve'] - 1:
        raise paving.PavingPending('Placed grass inventory changed while waiting for decay')
    if record['world_session'] != client.world:
        previous_world = record['world_session']
        record = paving._record(
            path, {**record, 'world_session': client.world}, 'grass_decay_wait',
            event='world_session_rebind', previous_world_session=previous_world,
            current_world_session=client.world, observed_phase=phase)
    if phase == 'grass_decay_wait':
        raise paving.PavingPending(
            'Covered Y62 grass is still grass; wait loaded for natural dirt decay')
    wait_receipts = [receipt for receipt in record['receipts']
                     if receipt.get('phase') == 'grass_decay_wait'
                     and receipt.get('server_confirmed') is True]
    if not wait_receipts:
        raise paving.PavingPending('Decay wait lacks the confirmed Y63 grass placement')
    source = wait_receipts[-1]
    record = paving._record(
        path, record, 'grass_placed', stage='restore_grass',
        event='covered_foundation_naturally_decayed', item_after=_grass_count(state),
        foundation_state=DIRT, surface_state=GRASS,
        loaded_double_scan=True, full_projection_confirmed=True,
        server_confirmed=True, confirmation_scope=source['confirmation_scope'])
    _fresh(client, pos, 'complete')
    paving._record(path, record, 'complete', event='full_projection_confirmed')
    return {'pos': list(pos), 'result': 'placed', 'expected': DIRT}


def _retry_pre_send_restore(client, pos, path, record, stack, foundation_state, *, settle):
    phase_before = 'dirt_placed' if foundation_state == DIRT else 'dirt_spread'
    complete_phase = 'grass_placed' if foundation_state == DIRT else 'grass_decay_wait'
    record, _ = _stage(
        client, pos, path, record, stage='restore_grass',
        intent='grass_restore_intent', complete=complete_phase,
        op='interact', target=list(pos), face='up', expected=foundation_state,
        hand='minecraft:grass_block', source_slot=stack['slot'], settle=settle,
        observed_phase=phase_before)
    if foundation_state == GRASS:
        return _finish_grass_decay_wait(client, pos, path, record, settle=settle)
    _fresh(client, pos, 'complete')
    paving._record(path, record, 'complete', event='full_projection_confirmed')
    return {'pos': list(pos), 'result': 'placed', 'expected': DIRT}


def _resume(client, pos, path, record, *, settle=time.sleep,
            pre_send_evidence=None, post_send_evidence=None):
    if pre_send_evidence is not None and post_send_evidence is not None:
        raise ValueError('Choose only one terrain reconciliation evidence kind')
    if post_send_evidence is not None:
        scope_matches = (isinstance(post_send_evidence, dict)
                         and post_send_evidence.get('schema') == 1
                         and post_send_evidence.get('kind')
                         == POST_SEND_LIFT_EVIDENCE_KIND
                         and post_send_evidence.get('cell') == list(pos)
                         and post_send_evidence.get('stage') == 'lift_grass'
                         and post_send_evidence.get('confirmation_scope')
                         == POST_SEND_CONFIRMATION_SCOPE)
        if not scope_matches:
            raise paving.PavingPending('Post-send lift evidence scope is invalid')
        if record['phase'] == 'lift_intent':
            source = _post_send_lift_evidence(
                client, pos, path, record, post_send_evidence)
            record = _finish_post_send_lift_recovery(
                client, pos, path, record, source, settle=settle)
            _validated_history(record)
            return _resume(client, pos, path, record, settle=settle)
        if (record['phase'] == 'grass_mined'
                and record['receipts'][-1].get('confirmation_scope')
                == POST_SEND_CONFIRMATION_SCOPE):
            record = _finish_post_send_lift_recovery(
                client, pos, path, record, settle=settle)
            _validated_history(record)
            return _resume(client, pos, path, record, settle=settle)
        if (record['phase'] == 'grass_recovered'
                and any(receipt.get('phase') == 'grass_recovered'
                        and receipt.get('confirmation_scope')
                        == POST_SEND_CONFIRMATION_SCOPE
                        for receipt in record['receipts'])):
            return _resume(client, pos, path, record, settle=settle)
        else:
            raise paving.PavingPending(
                'Post-send lift evidence has no matching unresolved lift intent')
    if record['phase'] in ('lift_intent', 'grass_restore_intent') and pre_send_evidence is not None:
        record = _legacy_pre_send_rejection(client, pos, path, record, pre_send_evidence)
    if record['phase'] == 'pre_send_rejected':
        rejection = _pre_send_receipt(record)
        if rejection.get('stage') == 'lift_grass':
            record, shovel = _reconcile_lift_pre_send(client, pos, path, record)
            return _retry_pre_send_lift(client, pos, path, record, shovel, settle=settle)
        if rejection.get('stage') == 'restore_grass':
            record, stack, foundation = _reconcile_restore_pre_send(
                client, pos, path, record, settle=settle)
            return _retry_pre_send_restore(
                client, pos, path, record, stack, foundation, settle=settle)
        raise paving.PavingPending('Pre-send rejection stage is unsupported')
    if record['phase'] == 'grass_decay_wait':
        return _finish_grass_decay_wait(client, pos, path, record, settle=settle)
    if (record['phase'] == 'grass_mined'
            and record['receipts'][-1].get('confirmation_scope')
            == POST_SEND_CONFIRMATION_SCOPE):
        record = _finish_post_send_lift_recovery(
            client, pos, path, record, settle=settle)
        _validated_history(record)
        return _resume(client, pos, path, record, settle=settle)
    if record['phase'] in UNCERTAIN:
        raise paving.PavingPending('An uncertain two-layer intent requires inspection; no request repeated')
    if record['world_session'] != client.world:
        # Only a confirmed phase may rebind. The current block state, model,
        # retained grass item and native request settlement must all agree.
        phase = {'grass_recovered': 'grass_removed', 'stone_recovered': 'both_removed',
                 'dirt_placed': 'dirt_placed', 'grass_placed': 'complete',
                 'complete': 'complete'}.get(record['phase'])
        if phase is None:
            raise paving.PavingPending('Cross-session recovery lacks a confirmed drop or block')
        previous_world = record['world_session']
        state, model, _ = _fresh(client, pos, phase)
        _scan(client, pos, phase)
        if (model['content_hash'] != record['model_hash']
                or record['phase'] not in ('grass_placed', 'complete')
                and paving._counts(state)['minecraft:grass_block'] < record.get('grass_reserve', 1)):
            raise paving.PavingPending('Two-layer inventory or model changed across sessions')
        paving._native_request_settled(client, client.status())
        record = paving._record(path, {**record, 'world_session': client.world},
                               record['phase'], event='world_session_rebind',
                               previous_world_session=previous_world,
                               current_world_session=client.world,
                               observed_phase=phase)
    if record['phase'] == 'complete':
        _fresh(client, pos, 'complete')
        return {'pos': list(pos), 'result': 'already_complete'}
    if record['phase'] == 'grass_placed':
        _fresh(client, pos, 'complete')
        paving._record(path, record, 'complete', event='full_projection_confirmed')
        return {'pos': list(pos), 'result': 'placed', 'expected': DIRT}
    if record['phase'] == 'grass_recovered':
        return _finish_stone_and_restore(client, pos, path, record, settle=settle)
    if record['phase'] == 'stone_recovered':
        return _finish_dirt_and_grass(client, pos, path, record, settle=settle)
    if record['phase'] == 'dirt_placed':
        return _finish_grass(client, pos, path, record, settle=settle)
    raise paving.PavingPending('Partial two-layer receipt has not been reconciled')


def _finish_stone_and_restore(client, pos, path, record, *, settle):
    state, _, _ = _fresh(client, pos, 'grass_removed')
    if (paving._counts(state)['minecraft:grass_block'] < record['grass_reserve']
            or paving._counts(state)['minecraft:dirt'] < 1
            or _free_slots(state) < 1):
        raise paving.PavingBlocked('Recovered grass, replacement dirt, or stone drop room was lost')
    tool = _tool(state, 'minecraft:diamond_pickaxe')
    record, before = _stage(client, pos, path, record, stage='mine_stone',
                            intent='stone_mine_intent', complete='stone_mined',
                            op='mine_block', target=list(pos), face='up',
                            expected=STONE, hand=tool['item'], source_slot=tool['slot'],
                            settle=settle)
    record = _collect_one(client, pos, path, record,
                          item_set={'minecraft:cobblestone', 'minecraft:stone'},
                          mined_phase='stone_mined', pickup_phase='stone_pickup_intent',
                          recovered_phase='stone_recovered', before=before)
    return _finish_dirt_and_grass(client, pos, path, record, settle=settle)


def _finish_dirt_and_grass(client, pos, path, record, *, settle):
    state, _, _ = _fresh(client, pos, 'both_removed')
    if (paving._counts(state)['minecraft:grass_block'] < record['grass_reserve']
            or paving._counts(state)['minecraft:dirt'] < 1):
        raise paving.PavingBlocked('Grass reserve or dirt was lost before foundation refill')
    record, before = _stage(client, pos, path, record, stage='place_dirt',
                            intent='dirt_place_intent', complete='dirt_placed',
                            op='interact', target=[pos[0], pos[1] - 1, pos[2]], face='up',
                            expected=record['support_below'], hand='minecraft:dirt',
                            settle=settle)
    if paving._counts(client.status())['minecraft:dirt'] != before['minecraft:dirt'] - 1:
        raise paving.PavingPending('Dirt inventory did not confirm the foundation placement')
    return _finish_grass(client, pos, path, record, settle=settle)


def _finish_grass(client, pos, path, record, *, settle):
    phase, state, model = _double_restore_phase(
        client, pos, allowed={'dirt_placed', 'dirt_spread'}, settle=settle)
    if (model['content_hash'] != record['model_hash']
            or _grass_count(state) != record['grass_reserve']):
        raise paving.PavingBlocked('Original grass reserve or restore column changed')
    stack = _grass_stack(state, record['grass_reserve'])
    foundation_state = DIRT if phase == 'dirt_placed' else GRASS
    complete_phase = 'grass_placed' if foundation_state == DIRT else 'grass_decay_wait'
    record, _ = _stage(client, pos, path, record, stage='restore_grass',
                            intent='grass_restore_intent', complete=complete_phase,
                            op='interact', target=list(pos), face='up',
                            expected=foundation_state, hand='minecraft:grass_block',
                            source_slot=stack['slot'], settle=settle,
                            observed_phase=phase)
    if foundation_state == GRASS:
        return _finish_grass_decay_wait(client, pos, path, record, settle=settle)
    _fresh(client, pos, 'complete')
    paving._record(path, record, 'complete', event='full_projection_confirmed')
    return {'pos': list(pos), 'result': 'placed', 'expected': DIRT}


def _one(client, pos, *, settle=time.sleep, pre_send_evidence=None,
         post_send_evidence=None):
    state, model, _ = paving._fresh_context(client, paving.SITE)
    if type(state.get('terrain_replace_protocol')) is not int or state['terrain_replace_protocol'] != 1:
        raise paving.PavingBlocked('Native two-layer terrain guard is unavailable')
    if not _safe_site(pos):
        raise paving.PavingBlocked('Cell is not one of the ten protected south-yard targets')
    path = _journal_path(client, pos)
    record = _load(path, state, model, pos)
    if record is not None:
        return _resume(client, pos, path, record, settle=settle,
                       pre_send_evidence=pre_send_evidence,
                       post_send_evidence=post_send_evidence)
    if pre_send_evidence is not None or post_send_evidence is not None:
        raise paving.PavingPending(
            'Reconciliation evidence has no matching terrain intent')
    state, model, _ = _fresh(client, pos, 'initial')
    _scan(client, pos, 'initial')
    shovel = _tool(state, 'minecraft:diamond_shovel', silk=True)
    _tool(state, 'minecraft:diamond_pickaxe')
    if paving._counts(state)['minecraft:dirt'] < 1 or _free_slots(state) < 2:
        raise paving.PavingBlocked('Dirt and two confirmed empty drop slots are required')
    _reach_station(client, pos)
    state, model, _ = _fresh(client, pos, 'initial')
    support = _scan(client, pos, 'initial')
    _station_status(client, pos)
    _reject_old_drops(state, pos)
    record = {'schema': 1, 'server': paving.SITE['server'],
              'dimension': paving.SITE['dimension'],
              'placement_key': state['projection_selection']['key'],
              'model_hash': model['content_hash'], 'world_session': client.world,
              'pos': list(pos), 'source': STONE, 'replacement': DIRT,
              'grass': GRASS, 'support_below': support,
              'grass_inventory_before': paving._counts(state)['minecraft:grass_block'],
              'grass_reserve': paving._counts(state)['minecraft:grass_block'] + 1,
              'nearby_before': [e['uuid'] for e in state['entities']], 'receipts': []}
    record, before = _stage(client, pos, path, record, stage='lift_grass',
                            intent='lift_intent', complete='grass_mined',
                            op='mine_block', target=[pos[0], pos[1] + 1, pos[2]],
                            face='up', expected=GRASS, hand=shovel['item'],
                            source_slot=shovel['slot'], settle=settle)
    record = _collect_one(client, pos, path, record,
                          item_set={'minecraft:grass_block'}, mined_phase='grass_mined',
                          pickup_phase='grass_pickup_intent',
                          recovered_phase='grass_recovered', before=before)
    return _finish_stone_and_restore(client, pos, path, record, settle=settle)


def replace_batch(client, *, cells=None, max_cells=1, settle=time.sleep,
                  pre_send_evidence=None, post_send_evidence=None):
    """Default to one exact two-layer transaction; never extend the target set."""
    if type(max_cells) is not int or not 1 <= max_cells <= len(CELLS):
        raise ValueError('First-phase terrain batch must contain 1..10 cells')
    points = [paving._position(p) for p in (cells or CELLS[:max_cells])]
    if len(points) != max_cells or len(set(points)) != len(points) or any(p not in PINNED for p in points):
        raise ValueError('Only unique named south-yard cells are permitted')
    if pre_send_evidence is not None and post_send_evidence is not None:
        raise ValueError('Choose only one terrain reconciliation evidence kind')
    if ((pre_send_evidence is not None or post_send_evidence is not None)
            and (max_cells != 1 or len(points) != 1)):
        raise ValueError('Terrain reconciliation is restricted to one exact cell')
    with paving._batch_lock(client):
        results = []
        for pos in points:
            result = _one(client, pos, settle=settle,
                          pre_send_evidence=pre_send_evidence,
                          post_send_evidence=post_send_evidence)
            results.append(result)
            if result.get('result') != 'placed':
                raise paving.PavingPending('Completed old cell was selected again; no further work')
        return results
