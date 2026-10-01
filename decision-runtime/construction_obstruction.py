"""Explicit, one-shot construction obstruction policy for a single horse.

This module never treats another passive entity as attackable and never retries a
spent nudge.  The native host owns the final identity, geometry, damage and
one-packet checks.
"""
import hashlib
import json
import math
from pathlib import Path
import time
import uuid


BLOCKER_RADIUS = 4.0
REQUIRED_CLEARANCE = 6.0
MIN_HORSE_HEALTH = 8.0
SCOUT_Y = 74.0
WAIT_FOR_HORSE_SECONDS = 30.0
SCOUT_STABILIZE_SECONDS = 8.0
SCOUT_HORIZONTAL_TOLERANCE = .65
SCOUT_VERTICAL_TOLERANCE = .65
SCOUT_MAX_SPEED = .08
ESCAPE_RADIUS = 6.75
STAND_DISTANCE = 2.0
SAFE_GROUND = frozenset({
    'minecraft:grass_block', 'minecraft:dirt', 'minecraft:coarse_dirt',
    'minecraft:podzol', 'minecraft:stone', 'minecraft:cobblestone',
    'minecraft:stone_bricks', 'minecraft:polished_andesite',
})
MOVEMENT_HAZARDS = frozenset({
    'minecraft:fire', 'minecraft:soul_fire', 'minecraft:cobweb',
    'minecraft:powder_snow', 'minecraft:cactus', 'minecraft:magma_block',
    'minecraft:campfire', 'minecraft:soul_campfire', 'minecraft:sweet_berry_bush',
})


class HorseObstructionBlocked(RuntimeError):
    pass


class HorseNudgeWaiting(RuntimeError):
    def __init__(self, message, reply):
        super().__init__(message)
        self.reply = reply


def _point(value, name):
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in value)):
        raise HorseObstructionBlocked(name + ' must contain three finite coordinates')
    return [float(v) for v in value]


def _block_id(row):
    state = row.get('state') if isinstance(row, dict) else None
    return state.split('}', 1)[0].removeprefix('Block{') if isinstance(state, str) else ''


def _scan(client, low, high):
    low = [math.floor(v) for v in _point(low, 'Scan minimum')]
    high = [math.floor(v) for v in _point(high, 'Scan maximum')]
    if any(high[i] < low[i] for i in range(3)):
        raise HorseObstructionBlocked('Construction obstruction scan bounds are invalid')
    volume = math.prod(high[i] - low[i] + 1 for i in range(3))
    if volume > 12_000:
        raise HorseObstructionBlocked('Construction obstruction scan is not bounded')
    reply = client.request('scan', min=low, max=high, details=True)
    if (reply.get('phase') not in (None, 'done')
            or reply.get('world_session') != client.world
            or not isinstance(reply.get('blocks'), list)):
        raise HorseObstructionBlocked('Construction obstruction scan is unconfirmed')
    rows = {}
    for row in reply['blocks']:
        pos = row.get('pos') if isinstance(row, dict) else None
        if (not isinstance(pos, list) or len(pos) != 3
                or any(type(v) is not int for v in pos)
                or any(pos[i] < low[i] or pos[i] > high[i] for i in range(3))
                or tuple(pos) in rows):
            raise HorseObstructionBlocked('Construction obstruction scan returned malformed cells')
        rows[tuple(pos)] = row
    return rows


def _passable(rows, x, y, z):
    row = rows.get((x, y, z))
    if row is None:
        return True
    return (row.get('passable') is True and row.get('fluid') is False
            and row.get('block_entity') is False and _block_id(row) not in MOVEMENT_HAZARDS)


def _body_clear(rows, pos, half_width, height):
    x, y, z = pos
    for bx in range(math.floor(x - half_width), math.floor(x + half_width - 1e-6) + 1):
        for by in range(math.floor(y + .01), math.floor(y + height - 1e-6) + 1):
            for bz in range(math.floor(z - half_width), math.floor(z + half_width - 1e-6) + 1):
                if not _passable(rows, bx, by, bz):
                    return False
    return True


def _solid_ground(rows, pos, half_width):
    x, y, z = pos
    floor_y = math.floor(y - .05)
    for bx in range(math.floor(x - half_width + .01), math.floor(x + half_width - .01) + 1):
        for bz in range(math.floor(z - half_width + .01), math.floor(z + half_width - .01) + 1):
            row = rows.get((bx, floor_y, bz))
            if (row is None or row.get('solid') is not True or row.get('fluid') is not False
                    or row.get('block_entity') is not False
                    or _block_id(row) not in SAFE_GROUND):
                return False
    return True


def _sweep_clear(rows, start, end, half_width=.31, height=1.8):
    distance = math.dist(start, end)
    steps = max(1, math.ceil(distance / .25))
    return all(_body_clear(rows, [start[i] + (end[i] - start[i]) * step / steps
                                  for i in range(3)], half_width, height)
               for step in range(steps + 1))


def _scan_sweep(client, start, end, *, floor=False):
    low = [min(start[0], end[0]) - 1, min(start[1], end[1]) - (1 if floor else 0),
           min(start[2], end[2]) - 1]
    high = [max(start[0], end[0]) + 1, max(start[1], end[1]) + 2,
            max(start[2], end[2]) + 1]
    rows = _scan(client, low, high)
    if not _sweep_clear(rows, start, end):
        raise HorseObstructionBlocked('Fresh scan found an obstruction in the exact player-body route')
    return rows


def explicit_horse_blocker(state, cell):
    """Return one fully identified horse only when it is the sole local blocker."""
    cell = _point(cell, 'Construction cell')
    player = _point(state.get('pos'), 'Player position')
    center = [cell[0] + .5, cell[1] + .5, cell[2] + .5]
    if math.dist(player, center) > 12 or not isinstance(state.get('entities'), list):
        raise HorseObstructionBlocked('Horse blocker coverage is unavailable')
    nearby = []
    for entity in state['entities']:
        if not isinstance(entity, dict):
            raise HorseObstructionBlocked('Nearby entity observation is malformed')
        pos = _point(entity.get('pos'), 'Nearby entity position')
        if math.dist(pos, center) <= BLOCKER_RADIUS:
            nearby.append((entity, pos))
    if len(nearby) != 1 or nearby[0][0].get('type') != 'minecraft:horse':
        raise HorseObstructionBlocked('The construction blocker is not one explicit horse')
    horse, pos = nearby[0]
    try:
        uuid.UUID(horse.get('uuid', ''))
    except (ValueError, TypeError, AttributeError) as error:
        raise HorseObstructionBlocked('Horse UUID is invalid') from error
    if (type(horse.get('id')) is not int or horse.get('visible') is not True
            or type(horse.get('health')) not in (int, float)
            or not math.isfinite(horse['health']) or horse['health'] < MIN_HORSE_HEALTH):
        raise HorseObstructionBlocked('Horse identity, visibility, or survival margin is incomplete')
    return {**horse, 'pos': pos}


def _lease_guard_scope(client, state):
    lease = state.get('supervision_lease') or {}
    heartbeat = getattr(getattr(client, 'heartbeat', None), 'id', None)
    task = getattr(client, 'task', None);world = getattr(client, 'world', None)
    revision = state.get('control_revision')
    return (state.get('connected') is True and state.get('health', 0) >= 19
            and state.get('manual_movement') is False
            and state.get('screen') == '' and state.get('guard_armed') is True
            and state.get('guard_pve_only') is True and state.get('guard_busy') is False
            and state.get('flight') is True and not state.get('air_return_active')
            and isinstance(heartbeat, str) and bool(heartbeat)
            and isinstance(task, str) and bool(task)
            and isinstance(world, str) and bool(world)
            and state.get('world_session') == world
            and type(revision) is int
            and lease.get('kind') == 'materials'
            and lease.get('id') == heartbeat and lease.get('job_session') == task
            and lease.get('world_session') == world
            and type(lease.get('revision')) is int and lease.get('revision') == revision)


def _stable_scout_frame(state, scout):
    pos = _point(state.get('pos'), 'Horse scout position')
    velocity = state.get('velocity');keys = state.get('movement_keys')
    return (math.hypot(pos[0] - scout[0], pos[2] - scout[2]) <= SCOUT_HORIZONTAL_TOLERANCE
            and abs(pos[1] - scout[1]) <= SCOUT_VERTICAL_TOLERANCE
            and isinstance(velocity, list) and len(velocity) == 3
            and all(type(v) in (int, float) and math.isfinite(v) for v in velocity)
            and math.hypot(velocity[0], velocity[2]) <= SCOUT_MAX_SPEED
            and abs(velocity[1]) <= SCOUT_MAX_SPEED
            and isinstance(keys, dict)
            and all(keys.get(name) is False for name in ('forward', 'back', 'jump', 'sneak')))


def _wait_scope(client, state, scout):
    return _lease_guard_scope(client, state) and _stable_scout_frame(state, scout)


def _scout_frame(state):
    return {name: state.get(name) for name in
            ('time', 'pos', 'velocity', 'movement_keys', 'health', 'guard_armed',
             'guard_pve_only', 'flight', 'manual_movement', 'world_session',
             'control_revision', 'supervision_lease')}


def stabilize_scout_once(client, scout, arrival_state, *, sleep=time.sleep,
                         monotonic=time.monotonic):
    """Accept two new quiet frames; one scanned recenter is the only correction."""
    record = {'schema': 1, 'world_session': getattr(client, 'world', None),
              'task_session': getattr(client, 'task', None),
              'lease': getattr(getattr(client, 'heartbeat', None), 'id', None),
              'scout': list(scout), 'initial': _scout_frame(arrival_state),
              'recenter_count': 0, 'frames': [], 'status': 'stabilizing'}
    deadline = monotonic() + SCOUT_STABILIZE_SECONDS
    previous_time = arrival_state.get('time');stable = []
    try:
        while len(stable) < 2:
            state = client.status();observed = state.get('time')
            if type(observed) is not int or type(previous_time) is not int:
                raise HorseObstructionBlocked('Scout status has no comparable frame time')
            if observed <= previous_time:
                if monotonic() >= deadline:
                    raise HorseObstructionBlocked('Scout did not publish a genuinely newer frame')
                sleep(.05);continue
            previous_time = observed;record['frames'].append(_scout_frame(state))
            if not _lease_guard_scope(client, state):
                raise HorseObstructionBlocked('Scout stabilization lost health, guard, manual, or lease scope')
            pos = _point(state.get('pos'), 'Horse scout position')
            drift = (math.hypot(pos[0] - scout[0], pos[2] - scout[2])
                     > SCOUT_HORIZONTAL_TOLERANCE
                     or abs(pos[1] - scout[1]) > SCOUT_VERTICAL_TOLERANCE)
            if drift:
                if record['recenter_count'] >= 1:
                    raise HorseObstructionBlocked('Scout drifted again after the one allowed recenter')
                _scan_sweep(client, pos, scout)
                reply = client.request('navigate', target=scout, arrival=.2,
                                       air_only=True, seconds=15)
                if reply.get('phase') != 'done':
                    raise HorseObstructionBlocked('The one scanned scout recenter did not finish')
                record['recenter'] = {'from': pos, 'target': list(scout),
                                      'request_id': reply.get('id'),
                                      'phase': reply.get('phase')}
                record['recenter_count'] = 1;stable.clear()
                latest = client.status();latest_time = latest.get('time')
                record['frames'].append(_scout_frame(latest))
                if type(latest_time) is not int or latest_time <= observed:
                    raise HorseObstructionBlocked('Scout recenter did not publish a newer status frame')
                if not _lease_guard_scope(client, latest):
                    raise HorseObstructionBlocked('Scout recenter lost health, guard, manual, or lease scope')
                latest_pos = _point(latest.get('pos'), 'Recentered scout position')
                if (math.hypot(latest_pos[0] - scout[0], latest_pos[2] - scout[2])
                        > SCOUT_HORIZONTAL_TOLERANCE
                        or abs(latest_pos[1] - scout[1]) > SCOUT_VERTICAL_TOLERANCE):
                    raise HorseObstructionBlocked('Scout drifted again after the one allowed recenter')
                previous_time = latest_time
                continue
            if _stable_scout_frame(state, scout):
                stable.append(state)
            else:stable.clear()
            if monotonic() >= deadline and len(stable) < 2:
                raise HorseObstructionBlocked('Scout never produced two distinct stable quiet frames')
            if len(stable) < 2:sleep(.05)
        record['status'] = 'stable';record['stable_frames'] = [_scout_frame(v) for v in stable]
        return stable[-1]
    except Exception as error:
        record['status'] = 'blocked';record['reason'] = str(error);raise
    finally:
        if hasattr(client, 'out'):
            write_result(Path(client.out) / 'horse-scout-stability.json', record)


def wait_for_explicit_horse(client, cell, scout, seconds=WAIT_FOR_HORSE_SECONDS,
                            *, initial_state=None, sleep=time.sleep,
                            monotonic=time.monotonic):
    """Observe at the fixed scout only; never move or follow a wandering horse."""
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 <= seconds <= 120:
        raise HorseObstructionBlocked('Horse wait must be between 0 and 120 seconds')
    deadline = monotonic() + seconds
    previous_time = initial_state.get('time') if isinstance(initial_state, dict) else None
    while True:
        state = client.status()
        observed = state.get('time')
        if type(observed) is not int or previous_time is not None and observed < previous_time:
            raise HorseObstructionBlocked('Horse wait status time is invalid or regressed')
        if previous_time is not None and observed == previous_time:
            if monotonic() >= deadline:
                raise HorseObstructionBlocked('No exact horse entered the construction clearance before timeout')
            sleep(.2);continue
        previous_time = observed
        if not _wait_scope(client, state, scout):
            raise HorseObstructionBlocked('Horse wait lost high position, health, guard, or material lease')
        player = _point(state.get('pos'), 'Horse scout position')
        center = [cell[0] + .5, cell[1] + .5, cell[2] + .5]
        if math.dist(player, center) > 12 or not isinstance(state.get('entities'), list):
            raise HorseObstructionBlocked('Horse blocker coverage is unavailable at the fixed scout')
        nearby = []
        for entity in state['entities']:
            if not isinstance(entity, dict):
                raise HorseObstructionBlocked('Nearby entity observation is malformed')
            pos = _point(entity.get('pos'), 'Nearby entity position')
            if math.dist(pos, center) <= BLOCKER_RADIUS:
                nearby.append(entity)
        if nearby:
            if len(nearby) != 1 or nearby[0].get('type') != 'minecraft:horse':
                raise HorseObstructionBlocked('A non-horse or multiple entities occupy the construction clearance')
            return explicit_horse_blocker(state, cell), state
        if monotonic() >= deadline:
            raise HorseObstructionBlocked('No exact horse entered the construction clearance before timeout')
        sleep(.2)


def _same_horse(state, identity):
    matches = [entity for entity in state.get('entities', [])
               if isinstance(entity, dict) and entity.get('uuid') == identity]
    if len(matches) != 1 or matches[0].get('type') != 'minecraft:horse':
        raise HorseObstructionBlocked('The exact horse is no longer observed')
    horse = {**matches[0], 'pos': _point(matches[0].get('pos'), 'Horse position')}
    if (type(horse.get('health')) not in (int, float) or not math.isfinite(horse['health'])
            or horse['health'] < MIN_HORSE_HEALTH or horse.get('visible') is not True):
        raise HorseObstructionBlocked('The exact horse lost visibility or health margin')
    return horse


def _directions(cell, horse):
    center = [cell[0] + .5, cell[2] + .5]
    radial = [horse['pos'][0] - center[0], horse['pos'][2] - center[1]]
    length = math.hypot(*radial)
    candidates = [(1., 0.), (-1., 0.), (0., 1.), (0., -1.),
                  (2**-.5, 2**-.5), (2**-.5, -2**-.5),
                  (-2**-.5, 2**-.5), (-2**-.5, -2**-.5)]
    if length < .15:
        return candidates
    unit = [radial[0] / length, radial[1] / length]
    outward = [direction for direction in candidates
               if direction[0] * unit[0] + direction[1] * unit[1] >= .35]
    return sorted(outward, key=lambda direction: -(direction[0] * unit[0]
                                                    + direction[1] * unit[1]))


def _candidate(cell, horse, direction, scout_y):
    center = [cell[0] + .5, cell[2] + .5]
    escape = [center[0] + direction[0] * ESCAPE_RADIUS,
              horse['pos'][1], center[1] + direction[1] * ESCAPE_RADIUS]
    dx, dz = escape[0] - horse['pos'][0], escape[2] - horse['pos'][2]
    length = math.hypot(dx, dz)
    if length < 1:
        raise HorseObstructionBlocked('Horse escape target is too close')
    ux, uz = dx / length, dz / length
    stand = [horse['pos'][0] - ux * STAND_DISTANCE,
             horse['pos'][1], horse['pos'][2] - uz * STAND_DISTANCE]
    hover = [stand[0], scout_y, stand[2]]
    return {'direction': [ux, uz], 'escape': escape, 'stand': stand, 'hover': hover}


def _other_entity_clear(state, horse_uuid, points, radius=1.8):
    for entity in state.get('entities', []):
        if not isinstance(entity, dict) or entity.get('uuid') == horse_uuid:
            continue
        pos = _point(entity.get('pos'), 'Nearby entity position')
        for point in points:
            if math.dist(pos, point) < radius:
                return False
    return True


def _candidate_safe(rows, state, cell, horse, candidate):
    escape, stand = candidate['escape'], candidate['stand']
    if not _solid_ground(rows, stand, .31) or not _body_clear(rows, stand, .31, 1.8):
        return False
    distance = math.dist([horse['pos'][0], horse['pos'][2]], [escape[0], escape[2]])
    steps = max(1, math.ceil(distance / .4));horse_points = []
    for step in range(steps + 1):
        ratio = step / steps
        point = [horse['pos'][0] + (escape[0] - horse['pos'][0]) * ratio,
                 horse['pos'][1], horse['pos'][2] + (escape[2] - horse['pos'][2]) * ratio]
        horse_points.append(point)
        if not _solid_ground(rows, point, .7) or not _body_clear(rows, point, .7, 1.7):
            return False
        center = [cell[0] + .5, cell[2] + .5]
        if step and math.dist(point[::2], center) + .01 < math.dist(horse_points[-2][::2], center):
            return False
    if not _sweep_clear(rows, candidate['hover'], stand):
        return False
    return _other_entity_clear(state, horse['uuid'], horse_points + [stand, candidate['hover']])


def choose_grounded_nudge_pose(client, state, cell, horse, scout_y):
    """Choose one scanned direction; candidates are observations, never movement guesses."""
    for direction in _directions(cell, horse):
        candidate = _candidate(cell, horse, direction, scout_y)
        low = [min(horse['pos'][0], candidate['stand'][0], candidate['escape'][0]) - 1,
               math.floor(horse['pos'][1] - .05),
               min(horse['pos'][2], candidate['stand'][2], candidate['escape'][2]) - 1]
        high = [max(horse['pos'][0], candidate['stand'][0], candidate['escape'][0]) + 1,
                scout_y + 2,
                max(horse['pos'][2], candidate['stand'][2], candidate['escape'][2]) + 1]
        rows = _scan(client, low, high)
        if _candidate_safe(rows, state, cell, horse, candidate):
            candidate['scan_min'] = [math.floor(v) for v in low]
            candidate['scan_max'] = [math.floor(v) for v in high]
            return candidate
    raise HorseObstructionBlocked('No freshly scanned solid escape and grounded attack pose exists')


def spent_key(state, cell, horse):
    selection = state.get('projection_selection') or {}
    raw = '\0'.join((state.get('server', ''), state.get('dimension', ''),
                     selection.get('key', ''), horse['uuid'],
                     ','.join(str(int(v)) for v in cell)))
    return 'horse-nudge-' + hashlib.sha256(raw.encode()).hexdigest()[:32]


def make_request(state, cell, escape_target, expected_construction_state):
    cell = _point(cell, 'Construction cell')
    if any(v != math.floor(v) for v in cell):
        raise HorseObstructionBlocked('Construction cell must be integral')
    escape = _point(escape_target, 'Horse escape target')
    horse = explicit_horse_blocker(state, cell)
    selection = state.get('projection_selection') or {}
    if (state.get('horse_nudge_protocol') != 1 or not state.get('world_session')
            or type(state.get('control_revision')) is not int or type(state.get('time')) is not int
            or not state.get('guard_armed') or not state.get('guard_pve_only')
            or state.get('guard_busy') or not state.get('kill_aura')
            or not isinstance(selection.get('key'), str) or not selection['key']
            or not isinstance(expected_construction_state, str)
            or not expected_construction_state.startswith('Block{minecraft:')):
        raise HorseObstructionBlocked('Current guarded construction scope cannot nudge a horse')
    return {
        'entity_id': horse['id'], 'expected_uuid': horse['uuid'],
        'expected_type': 'minecraft:horse', 'expected_pos': horse['pos'],
        'expected_health': horse['health'], 'observed_at': state['time'],
        'clearance_cell': [int(v) for v in cell], 'escape_target': escape,
        'placement_key': selection['key'],
        'expected_construction_state': expected_construction_state,
        'spent_key': spent_key(state, cell, horse),
    }


def nudge_explicit_horse(client, cell, escape_target, expected_construction_state):
    """Ask the native host for one exact nudge; a waiting result is never replayed."""
    state = client.status()
    params = make_request(state, cell, escape_target, expected_construction_state)
    reply = client.request('nudge_horse', **params)
    evidence = reply.get('horse_nudge') if isinstance(reply, dict) else None
    if not isinstance(evidence, dict) or evidence.get('spent_key') != params['spent_key']:
        if isinstance(reply, dict) and reply.get('phase') == 'error':
            raise HorseObstructionBlocked(reply.get('detail', 'Horse nudge was rejected before send'))
        raise HorseNudgeWaiting('Horse nudge has no exact native receipt; do not retry', reply)
    if evidence.get('attack_count') not in (1, -1):
        raise HorseNudgeWaiting('Horse nudge attack count is unconfirmed; spent key blocks retry', reply)
    if reply.get('phase') == 'done':
        if (evidence.get('attack_count') != 1 or evidence.get('expected_uuid') != params['expected_uuid']
                or evidence.get('same_uuid_observed') is not True or evidence.get('alive') is not True
                or type(evidence.get('health')) not in (int, float) or evidence['health'] <= 0
                or type(evidence.get('clearance_distance')) not in (int, float)
                or evidence['clearance_distance'] < REQUIRED_CLEARANCE
                or evidence.get('pve_guard_armed') is not True
                or evidence.get('kill_aura_can_target_horse') is not False):
            raise HorseNudgeWaiting('Native horse nudge completion evidence is incomplete; do not retry', reply)
        return reply
    raise HorseNudgeWaiting(reply.get('detail', 'Spent horse nudge did not confirm clearance; do not retry'), reply)


def _confirmed_air_arrival(client, target, *, seconds=30, require_position=True):
    before = client.status()
    _scan_sweep(client, before['pos'], target)
    reply = client.request('navigate', target=target, arrival=.2, air_only=True,
                           seconds=seconds)
    after = client.status();position = _point(after.get('pos'), 'Guarded air position')
    if (reply.get('phase') != 'done' or require_position and math.dist(position, target) > .65
            or not after.get('guard_armed') or not after.get('guard_pve_only')
            or not after.get('flight') or after.get('guard_busy')):
        raise HorseObstructionBlocked('Collision-checked horse approach did not reach guarded air')
    return after


def _land_behind_horse(client, candidate, horse, *, sleep=time.sleep):
    hover, stand = candidate['hover'], candidate['stand']
    rows = _scan_sweep(client, hover, stand, floor=True)
    if not _solid_ground(rows, stand, .31) or not _body_clear(rows, stand, .31, 1.8):
        raise HorseObstructionBlocked('Fresh landing column lost its solid grounded pose')
    landing = [stand[0], stand[1] + .02, stand[2]]
    descended = client.request('navigate', target=landing, arrival=.12,
                                air_only=True, seconds=20)
    if descended.get('phase') != 'done':
        raise HorseObstructionBlocked('Collision-checked horse landing descent did not finish')
    dropped = client.request('walk', target=stand, arrival=.12, restore_flight=False,
                             seconds=8)
    if dropped.get('phase') != 'done':
        raise HorseObstructionBlocked('Ground handoff behind the horse did not finish')
    deadline = time.monotonic() + 3
    while True:
        state = client.status();pos = _point(state.get('pos'), 'Grounded player position')
        if state.get('on_ground'):
            break
        if time.monotonic() >= deadline:
            raise HorseObstructionBlocked('Player did not settle on verified ground behind the horse')
        sleep(.05)
    if (math.hypot(pos[0] - stand[0], pos[2] - stand[2]) > .25
            or abs(pos[1] - stand[1]) > .2 or state.get('flight')
            or not state.get('guard_armed') or not state.get('guard_pve_only')
            or state.get('guard_busy') or state.get('health', 0) < 19):
        raise HorseObstructionBlocked('Grounded horse attack pose or PvE guard is unconfirmed')
    return state


def _aligned_for_nudge(state, horse, candidate):
    player = _point(state.get('pos'), 'Grounded player position')
    escape = candidate['escape']
    ex, ez = escape[0] - horse['pos'][0], escape[2] - horse['pos'][2]
    px, pz = horse['pos'][0] - player[0], horse['pos'][2] - player[2]
    escape_length, player_distance = math.hypot(ex, ez), math.hypot(px, pz)
    return (escape_length >= 1 and 1 <= player_distance <= 2.8
            and (ex * px + ez * pz) / (escape_length * player_distance) >= .92)


def _return_to_guarded_air(client, scout_y):
    state = client.status();pos = _point(state.get('pos'), 'Post-nudge player position')
    target = [pos[0], scout_y, pos[2]]
    rows = _scan_sweep(client, pos, target)
    if not _sweep_clear(rows, pos, target):
        raise HorseObstructionBlocked('Post-nudge ascent column changed')
    reply = client.request('navigate', target=target, arrival=.25, air_only=True, seconds=25)
    after = client.status();position = _point(after.get('pos'), 'Post-nudge air position')
    if (reply.get('phase') != 'done' or math.dist(position, target) > .75
            or not after.get('flight') or not after.get('guard_armed')
            or not after.get('guard_pve_only')):
        raise HorseObstructionBlocked('Post-nudge high guard handoff was not confirmed')
    return after


def approach_and_nudge_explicit_horse(client, cell, expected_construction_state,
                                      *, scout_y=SCOUT_Y,
                                      wait_for_horse_seconds=WAIT_FOR_HORSE_SECONDS,
                                      sleep=time.sleep, monotonic=time.monotonic):
    """Bounded scout, scanned landing, one nudge, and same-column guarded ascent."""
    cell = _point(cell, 'Construction cell')
    if any(v != math.floor(v) for v in cell):
        raise HorseObstructionBlocked('Construction cell must be integral')
    if (type(scout_y) not in (int, float) or not math.isfinite(scout_y)
            or not 8 <= scout_y - (cell[1] + .5) <= 12):
        raise HorseObstructionBlocked('Scout height must remain 8..12 blocks above the construction cell')
    initial = client.status();scout = [cell[0] + .5, float(scout_y), cell[2] + .5]
    observed = _confirmed_air_arrival(client, scout,
        seconds=min(60, max(20, math.ceil(math.dist(initial['pos'], scout) / 2) + 12)),
        require_position=False)
    observed = stabilize_scout_once(client, scout, observed, sleep=sleep, monotonic=monotonic)
    horse, observed = wait_for_explicit_horse(
        client, cell, scout, wait_for_horse_seconds, initial_state=observed,
        sleep=sleep, monotonic=monotonic)
    identity = horse['uuid']
    candidate = choose_grounded_nudge_pose(client, observed, cell, horse, scout_y)
    if hasattr(client, 'out'):
        write_result(Path(client.out) / 'horse-approach-plan.json', {
            'schema': 1, 'world_session': getattr(client, 'world', None),
            'cell': [int(v) for v in cell], 'scout': scout,
            'horse_uuid': identity, 'horse_pos': horse['pos'],
            'escape_target': candidate['escape'], 'grounded_player_pose': candidate['stand'],
            'hover_pose': candidate['hover'], 'scan_min': candidate['scan_min'],
            'scan_max': candidate['scan_max'], 'status': 'scanned_before_ground_approach',
        })
    hover_state = _confirmed_air_arrival(client, candidate['hover'], seconds=20)
    hover_horse = _same_horse(hover_state, identity)
    if (math.dist(hover_horse['pos'], horse['pos']) > .35
            or abs(hover_horse['health'] - horse['health']) > .01):
        raise HorseObstructionBlocked('Horse moved or changed health before the grounded approach')
    needs_ascent = False;spent_reply = None;spent_waiting = None
    try:
        needs_ascent = True
        ground_state = _land_behind_horse(client, candidate, horse, sleep=sleep)
        fresh_horse = explicit_horse_blocker(ground_state, cell)
        if (fresh_horse['uuid'] != identity or math.dist(fresh_horse['pos'], horse['pos']) > .35
                or abs(fresh_horse['health'] - horse['health']) > .01
                or not _aligned_for_nudge(ground_state, fresh_horse, candidate)):
            raise HorseObstructionBlocked('Exact horse or player alignment changed after landing')
        rows = _scan(client, candidate['scan_min'], candidate['scan_max'])
        if not _candidate_safe(rows, ground_state, cell, fresh_horse, candidate):
            raise HorseObstructionBlocked('Horse escape or grounded attack pose changed after landing')
        try:
            spent_reply = nudge_explicit_horse(
                client, cell, candidate['escape'], expected_construction_state)
        except HorseNudgeWaiting as waiting:
            spent_reply = waiting.reply;spent_waiting = waiting
    finally:
        if needs_ascent:
            try:_return_to_guarded_air(client, scout_y)
            except HorseObstructionBlocked as ascent:
                if spent_reply is not None:
                    raise HorseNudgeWaiting(
                        'Horse nudge is spent but guarded ascent was not confirmed: ' + str(ascent),
                        spent_reply) from ascent
                raise
    if spent_waiting is not None:
        raise spent_waiting
    return spent_reply


def write_result(path, result):
    path = Path(path);path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
