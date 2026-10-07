"""Short normal entry/exit routes for an already verified small trial shelter."""
import re

from singleplayer_trial_bridge import Paused
from survival_world import cell, center, distance
from trial_safety_preparation import _layout, _ready, _valid_door, _house_verified, _door_face


def _scope(state):
    return tuple(state.get(key) for key in ('world_id', 'world_session', 'dimension'))


def _fresh(skills, scope):
    state = _ready(skills)
    if _scope(state) != scope:
        raise Paused('Shelter route world/session/dimension changed; no old coordinates are used')
    world = skills.scan()
    state = _ready(skills)
    if _scope(state) != scope:
        raise Paused('Shelter route scope changed during its fresh scan')
    return state, world


def _door_state(world, record):
    """Both halves must describe the same unpowered wooden doorway."""
    item, door = record['door_item'], record['door']
    if item == 'iron_door' or not _valid_door(world, door, item):
        raise Paused('Recorded shelter has no matching ordinary wooden door halves')
    properties = []
    for height in (door[1], door[1] + 1):
        raw = world.row((door[0], height, door[2])).get('state', '')
        match = re.search(r'\[([^]]+)\]', raw)
        try:values = dict(part.split('=', 1) for part in match[1].split(',')) if match else {}
        except ValueError:raise Paused('Shelter door properties are malformed') from None
        properties.append(values)
    lower, upper = properties
    if (lower.get('half') != 'lower' or upper.get('half') != 'upper'
            or any(lower.get(key) != upper.get(key) for key in ('open', 'facing', 'hinge', 'powered'))
            or lower.get('open') not in {'true', 'false'}
            or lower.get('hinge') not in {'left', 'right'}
            or lower.get('powered') != 'false'
            # The existing 3x3 layout has its doorway on the south wall. An
            # east/west closed leaf would leave its centre physically open.
            or lower.get('facing') not in {'north', 'south'}):
        raise Paused('Shelter door halves or doorway orientation are inconsistent')
    return lower['open'] == 'true'


def _record(skills, state, world):
    record = getattr(skills, 'small_shelter', None)
    if (not isinstance(record, dict) or record.get('schema') != 1
            or record.get('verified') is not True or not state.get('world_id')
            or record.get('world_id') != state.get('world_id')
            or record.get('dimension') != state.get('dimension')):
        raise Paused('No verified small shelter in this current save/dimension')
    inside = record.get('inside')
    if (not isinstance(inside, list) or len(inside) != 3
            or any(type(value) is not int for value in inside)):
        raise Paused('Recorded small shelter inside coordinate is invalid')
    layout = _layout(inside)
    if any(record.get(key) != value for key, value in layout.items()):
        raise Paused('Recorded small shelter differs from its bounded verified layout')
    if (not isinstance(record.get('door_item'), str)
            or not record['door_item'].endswith('_door')
            or not _house_verified(world, record, record['door_item'])):
        raise Paused('Known shelter enclosure/support/door is absent from complete fresh terrain')
    _door_state(world, record)
    return record


def _opened_hypothesis(world, record):
    """Preflight a door-open route before sending any toggle or movement."""
    points = {tuple(record['door']), (record['door'][0], record['door'][1] + 1, record['door'][2])}
    rows = []
    for point, row in world.blocks.items():
        value = dict(row)
        if point in points:value['state'] = value['state'].replace('open=false', 'open=true')
        rows.append(value)
    return type(world)(rows, world.low, world.high)


def _interaction_target(world, pos, record):
    eye = [pos[0], pos[1] + 1.62, pos[2]]
    lower = tuple(record['door']);upper = (lower[0], lower[1] + 1, lower[2])
    choices = [point for point in (lower, upper) if distance(eye, [value + .5 for value in point]) <= 3.6
               and world.sight(cell(pos), point)]
    return min(choices, key=lambda point: distance(eye, [value + .5 for value in point]), default=None)


def _walk_once(skills, route):
    if not route:return
    try:skills.walk(route)
    except (Paused, RuntimeError, ValueError):
        skills.b.halted = True
        raise


def _toggle(skills, record, opened, scope):
    state, world = _fresh(skills, scope)
    _record(skills, state, world)
    if _door_state(world, record) == opened:return world
    target = _interaction_target(world, state['pos'], record)
    if target is None:
        raise Paused('Known shelter door has no verified current interaction reach')
    try:
        result = skills.interact(list(target), face=_door_face(state['pos'], record['door']))
        if isinstance(result, dict) and (result.get('phase') not in (None, 'done')
                                         or result.get('outcome_pending') is True):
            raise Paused('Door interaction returned an unknown native result')
        state, fresh = _fresh(skills, scope)
        _record(skills, state, fresh)
        if not _valid_door(fresh, record['door'], record['door_item'], opened):
            raise Paused('Door interaction has no fresh matching half-state confirmation')
    except (Paused, RuntimeError, ValueError):
        skills.b.halted = True
        raise
    return fresh


def _route(skills, entering):
    initial = _ready(skills);scope = _scope(initial)
    state, world = _fresh(skills, scope);record = _record(skills, state, world)
    if state.get('on_ground') is not True:
        raise Paused('Shelter route requires an observed supported ground stand')
    inside = tuple(record['inside']);floor = {tuple(point) for point in record['floor']}
    # Prospective opening is used only to prove a short supported route. The
    # actual route is rebuilt from a fresh real scan after its one toggle.
    proposed = _opened_hypothesis(world, record);parents = proposed.paths(state['pos'])
    if entering:
        target = inside if inside in parents else None
    else:
        choices = [point for point in parents if (point[0], point[1] - 1, point[2]) not in floor
                   and len(proposed.route(parents, point)) <= 32
                   and _interaction_target(proposed, center(point), record) is not None]
        target = min(choices, key=lambda point: (distance(center(point), state['pos']),
                      len(proposed.route(parents, point)), point), default=None)
    if target is None or len(proposed.route(parents, target)) > 32:
        raise Paused('Known shelter lacks a complete supported short normal route; no action dispatched')
    route = proposed.route(parents, target)
    # Opening may require reaching the door from the current side, without
    # crossing it. Check that approach before committing the overall route.
    if route and not _door_state(world, record):
        actual = world.paths(state['pos'])
        stances = [point for point in actual if _interaction_target(world, center(point), record) is not None]
        stance = min(stances, key=lambda point: len(world.route(actual, point)), default=None)
        if stance is None or len(world.route(actual, stance)) > 32:
            raise Paused('Known shelter door has no short actual approach; no action dispatched')
        _walk_once(skills, world.route(actual, stance))
        world = _toggle(skills, record, True, scope)
    state, world = _fresh(skills, scope);_record(skills, state, world)
    parents = world.paths(state['pos'])
    if target not in parents or len(world.route(parents, target)) > 32:
        raise Paused('Shelter route changed after opening; no movement replay')
    _walk_once(skills, world.route(parents, target))
    state, world = _fresh(skills, scope);_record(skills, state, world)
    if (state.get('on_ground') is not True or distance(state['pos'], center(target)) > .7
            or abs(state['pos'][1] - target[1]) > .2):
        skills.b.halted = True
        raise Paused('Shelter walking arrival is unconfirmed; no repeated walking')
    _toggle(skills, record, False, scope)
    final, world = _fresh(skills, scope);_record(skills, final, world)
    if not _valid_door(world, record['door'], record['door_item'], False):
        raise Paused('Final known shelter door closure is unconfirmed')
    record.update(verified_at=final.get('time'), verified_position=list(final['pos']))
    skills.event('known_shelter_entered' if entering else 'known_shelter_left',
                 target=list(target), position=list(final['pos']), door_closed=True, flight_used=False)
    return final


def enter_known_shelter(skills):
    return _route(skills, True)


def leave_known_shelter(skills):
    return _route(skills, False)
