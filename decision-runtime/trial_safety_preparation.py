"""A small verified shelter and a carried-material sword for the local trial."""
from collections import Counter
import math

from singleplayer_trial_bridge import Paused
from survival_world import cell, center, distance
from trial_surface_recovery import protected_cells

SWORDS = ('netherite_sword', 'diamond_sword', 'iron_sword', 'stone_sword', 'wooden_sword', 'golden_sword')
SITE_PLANTS = frozenset({'short_grass', 'leaf_litter', 'fern'})


def _layout(inside):
    x, y, z = inside
    door = (x, y, z + 1)
    walls = [(bx, by, bz) for by in (y, y + 1) for bx in range(x - 1, x + 2)
             for bz in range(z - 1, z + 2)
             if (bx != x or bz != z) and (bx, bz) != (x, z + 1)]
    roof = [(bx, y + 2, bz) for bx in range(x - 1, x + 2) for bz in range(z - 1, z + 2)]
    roof.sort(key=lambda point: point[0] == x and point[2] == z)
    floor = [(bx, y - 1, bz) for bx in range(x - 1, x + 2) for bz in range(z - 1, z + 2)]
    return {'inside': list(inside), 'door': list(door), 'walls': [list(p) for p in walls],
            'roof': [list(p) for p in roof], 'layout': [list(p) for p in walls + roof],
            'floor': [list(p) for p in floor]}


def _site_at(world, point, protected, allow_plants=False):
    plan = _layout(point)
    footprint = [tuple(p) for p in plan['floor']]
    empty = [(x, y, z) for x, fy, z in footprint for y in range(fy + 1, fy + 4)]
    if any(p in protected or not world.full(p) or world.row(p).get('block_entity') for p in footprint):
        return None
    clearance = []
    for p in empty:
        if p in protected or not world.safe(p) or world.row(p).get('block_entity'):
            return None
        name = world.name(p)
        if name == 'air':
            continue
        if (not allow_plants or p[1] != point[1] or name not in SITE_PLANTS
                or not world.open(p)):
            return None
        clearance.append(list(p))
    if len(clearance) > 9:
        return None
    return {**plan, 'clearance': clearance}


def shelter_site(world, pos, protected=(), max_distance=6, allow_plants=False):
    """Pure 3x3 supported site; no existing structure is treated as empty."""
    protected = set(protected)
    parents = world.paths(pos)
    choices = []
    for point in parents:
        if distance(center(point), pos) > max_distance:
            continue
        plan = _site_at(world, point, protected, allow_plants)
        if plan is None:
            continue
        route = world.route(parents, point)
        if len(route) <= 32:
            choices.append((len(plan['clearance']), distance(center(point), pos), len(route), point, plan))
    return min(choices)[-1] if choices else None


def _counts(state):
    result = Counter()
    for row in state.get('inventory', []):
        result[row['item'].removeprefix('minecraft:')] += row.get('count', 0)
    return result


def _ready(skills):
    if skills.b.halted or skills.b.pending_mutations:
        raise Paused('Unconfirmed native operation preserved; no safety preparation is replayed')
    return skills.b.read()


def find_shelter_site(skills):
    """Prefer empty ground; extend one bounded scan before clearing plants."""
    state = _ready(skills)
    local = skills.scan()
    protected = protected_cells(skills)
    plan = shelter_site(local, state['pos'], protected, max_distance=10)
    broad = None
    if plan is None:
        before = _ready(skills)
        x, y, z = cell(before['pos'])
        low, high = [x - 16, max(-64, y - 8), z - 16], [x + 16, min(319, y + 8), z + 16]
        volume = math.prod(b - a + 1 for a, b in zip(low, high))
        result = skills.b.request('scan', min=low, max=high, details=True)
        if (volume > 18_513 or result.get('scan_cells_read') != volume
                or result.get('scan_total_cells') != volume
                or any(result.get(key) != before.get(key) for key in
                       ('world_id', 'world_session', 'dimension', 'control_revision'))
                or distance(result['pos'], before['pos']) > .3):
            raise Paused('Shelter search scan is partial or changed; no route or clearance starts')
        broad = type(local)(result['blocks'], low, high)
        plan = shelter_site(broad, result['pos'], protected, max_distance=24)
    world = local if broad is None else broad
    if plan is None:
        plan = shelter_site(local, _ready(skills)['pos'], protected, max_distance=10, allow_plants=True)
        if plan is not None:
            world = local
        elif broad is not None:
            plan = shelter_site(broad, _ready(skills)['pos'], protected, max_distance=24, allow_plants=True)
    if plan is None:
        raise Paused('No fresh safe reachable 3x3 small shelter site within the bounded search')
    inside = tuple(plan['inside'])
    parents = world.paths(_ready(skills)['pos'])
    if inside not in parents or len(world.route(parents, inside)) > 32:
        raise Paused('Selected shelter site lacks its checked normal walking route')
    skills.walk(world.route(parents, inside))
    if distance(_ready(skills)['pos'], center(inside)) > .7:
        raise Paused('Actual shelter-site arrival is unconfirmed; no walking replay')
    for point in sorted(plan['clearance'], key=lambda p: distance(center(p), center(inside))):
        _ready(skills)
        fresh = skills.scan()
        p = tuple(point)
        if fresh.name(p) == 'air':
            continue
        if (_site_at(fresh, inside, protected, allow_plants=True) is None
                or p in protected or fresh.name(p) not in SITE_PLANTS
                or fresh.row(p).get('block_entity') or not fresh.safe(p)
                or not fresh.sight(cell(skills.b.read()['pos']), p)):
            raise Paused('Natural plant clearance changed; preserve the selected site')
        receipt = skills.b.request('mine_block', pos=point, expected_state=fresh.row(p)['state'], seconds=10)
        if (receipt.get('phase') != 'done' or receipt.get('server_confirmed') is not True
                or receipt.get('outcome_pending') is True):
            skills.b.halted = True
            raise Paused('Shelter plant mining is unconfirmed; preserve its request without replay')
        fresh = skills.scan()
        if fresh.name(p) != 'air':
            skills.b.halted = True
            raise Paused('Shelter plant has no fresh air confirmation; no repeated mining')
        skills.event('shelter_natural_plant_cleared', target=point, request_id=receipt.get('id'))
    fresh = skills.scan()
    verified = _site_at(fresh, inside, protected)
    if verified is None:
        raise Paused('Selected shelter site no longer has verified support and clear space')
    skills.event('small_shelter_site_verified', inside=plan['inside'],
                 cleared_plants=len(plan['clearance']), flight_used=False)
    return verified


def _wooden_door(inv):
    return next((name for name in sorted(inv) if name.endswith('_door')
                 and name != 'iron_door' and inv[name] > 0), None)


def _valid_door(world, door, item, opened=None):
    lower, upper = tuple(door), (door[0], door[1] + 1, door[2])
    return (world.name(lower) == item and world.name(upper) == item
            and 'half=lower' in world.row(lower).get('state', '')
            and 'half=upper' in world.row(upper).get('state', '')
            and (opened is None or all('open=' + str(opened).lower() in world.row(p).get('state', '')
                                       for p in (lower, upper))))


def _house_verified(world, plan, item):
    return (all(world.earth(tuple(point)) for point in plan['layout'])
            and all(world.full(tuple(point)) and not world.row(tuple(point)).get('block_entity')
                    for point in plan['floor'])
            and world.open(tuple(plan['inside']))
            and world.open((plan['inside'][0], plan['inside'][1] + 1, plan['inside'][2]))
            and _valid_door(world, plan['door'], item))


def _door_face(pos, door):
    return 'north' if pos[2] < door[2] + .5 else 'south'


def prepare_small_shelter(skills):
    state = _ready(skills)
    saved = getattr(skills, 'small_shelter', None)
    plan, door_item, missing = None, None, 23
    if saved:
        if (saved.get('schema') != 1 or saved.get('world_id') != state.get('world_id')
                or saved.get('dimension') != state.get('dimension')):
            raise Paused('Small shelter record belongs to another save or dimension')
        plan = _layout(saved['inside'])
        if any(saved.get(key) != plan[key] for key in plan):
            raise Paused('Small shelter coordinates differ from the bounded layout')
        door_item = saved['door_item']
        skills.excluded.update(tuple(point) for point in (*plan['floor'], *plan['layout']))
        from trial_shelter_access import observe_partial_shelter
        world = observe_partial_shelter(skills, plan)
        if (any(world.name(tuple(point)) not in {'air', 'dirt', 'grass_block'} for point in plan['layout'])
                or any(not world.full(tuple(point)) or world.row(tuple(point)).get('block_entity')
                       for point in plan['floor'])):
            raise Paused('Partial small shelter has an unexpected current block or changed floor; preserve it')
        missing = sum(not world.earth(tuple(point)) for point in plan['layout'])
    if _counts(_ready(skills))['dirt'] < missing:
        skills.gather({'dirt', 'grass_block'}, {'dirt'}, missing)
        if _counts(_ready(skills))['dirt'] < missing:
            raise Paused('Missing actual dirt for the small shelter; no placement starts')
    inv = _counts(_ready(skills))
    existing_door = bool(plan and _valid_door(skills.scan(), plan['door'], door_item))
    if not existing_door:
        door_item = _wooden_door(inv)
        if door_item is None:
            plank = skills.planks(6)
            door_item = plank.removesuffix('_planks') + '_door'
            skills.craft(door_item, {(row, column): plank for row in range(3) for column in range(2)},
                         width=3, produces=3)
            if _counts(_ready(skills))[door_item] < 1:
                raise Paused('Wooden door has no verified carried output')
    if plan is None:
        plan = find_shelter_site(skills)
    record = {'schema': 1, 'world_id': state.get('world_id'), 'dimension': state.get('dimension'),
              **plan, 'door_item': door_item, 'verified': False}
    skills.small_shelter = record
    skills.excluded.update(tuple(point) for point in plan['floor'])
    skills.event('small_shelter_planned', **record, required_dirt=missing)
    for point in plan['layout']:
        _ready(skills)
        skills.place('dirt', point)
    if not existing_door:
        _ready(skills)
        skills.place(door_item, plan['door'])
    world = skills.scan()
    if not _house_verified(world, plan, door_item):
        raise Paused('Small shelter walls, roof, door or floor lack fresh verification')
    upper = [plan['door'][0], plan['door'][1] + 1, plan['door'][2]]
    skills.owned[','.join(map(str, upper))] = door_item
    inside = tuple(plan['inside'])
    parents = world.paths(skills.b.read()['pos'])
    if inside not in parents:
        skills.go_near(plan['door'])
        skills.interact(plan['door'], face=_door_face(skills.b.read()['pos'], plan['door']))
        world = skills.scan()
        if not _valid_door(world, plan['door'], door_item, True):
            raise Paused('Small shelter door opening is not freshly confirmed; no repeated click')
        parents = world.paths(skills.b.read()['pos'])
    if inside not in parents:
        raise Paused('Small shelter has no fresh normal entry route')
    skills.walk(world.route(parents, inside))
    state = _ready(skills)
    if (state.get('on_ground') is not True or distance(state['pos'], center(inside)) > .7
            or abs(state['pos'][1] - inside[1]) > .2):
        raise Paused('Actual small shelter entry is unconfirmed; no walking replay')
    world = skills.scan()
    if not _valid_door(world, plan['door'], door_item, False):
        if not _valid_door(world, plan['door'], door_item, True):
            raise Paused('Small shelter door changed before closing')
        skills.interact(plan['door'], face=_door_face(state['pos'], plan['door']))
        world = skills.scan()
    if not _house_verified(world, plan, door_item) or not _valid_door(world, plan['door'], door_item, False):
        raise Paused('Small shelter closure or enclosure is unconfirmed; no repeated interaction')
    state = _ready(skills)
    record.update(verified=True, verified_at=state.get('time'), verified_position=list(state['pos']))
    skills.event('small_shelter_entered_and_closed', **record)
    return dict(record)


def prepare_sword(skills, upgrade_stone=False):
    state = _ready(skills)
    inv = _counts(state)
    sword = next((name for name in SWORDS if inv[name] > 0), None)
    acquired = False
    if upgrade_stone and sword not in {'netherite_sword', 'diamond_sword', 'iron_sword', 'stone_sword'}:
        if inv['cobblestone'] < 2:
            skills.gather({'stone', 'cobblestone'}, {'cobblestone'}, 2)
            inv = _counts(_ready(skills))
            if inv['cobblestone'] < 2:
                raise Paused('Stone sword upgrade lacks confirmed cobblestone; carried sword is preserved')
            acquired = True
        sword = None  # The carried weaker sword is retained, never consumed.
    if sword is None:
        if inv['cobblestone'] >= 2:
            sword, material = 'stone_sword', 'cobblestone'
        else:
            sword, material = 'wooden_sword', None
        # Only carried wood can supply missing sticks or a temporary wooden
        # blade. Never mine more stone merely to postpone protection at night.
        skills.sticks(1)
        if material is None:
            material = skills.planks(2)
        _ready(skills)
        skills.craft(sword, {(0, 0): material, (1, 0): material, (2, 0): 'stick'}, width=3)
        if _counts(_ready(skills))[sword] < 1:
            raise Paused('Sword craft has no verified inventory output')
    skills.b.select(sword)
    state = _ready(skills)
    if _counts(state)[sword] < 1:
        raise Paused('Actual sword disappeared before use')
    skills.event('carried_sword_verified', item=sword, count=_counts(state)[sword],
                 upgrade_requested=bool(upgrade_stone), acquisition_performed=acquired)
    return {'item': sword, 'count': _counts(state)[sword], 'inventory_verified': True}
