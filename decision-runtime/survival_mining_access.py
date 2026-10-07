"""Conservative mining rays for the existing normal Kit mine_block API.

Walking passability is not OUTLINE ray transparency. Plans use the actual eye
and the host's existing face-centre aim; native sequence receipts still decide
whether a block was removed. Only a small natural-plant allowlist may be cleared.
"""
import math

NATURAL_PLANTS = frozenset({'short_grass', 'fern', 'leaf_litter',
                            'brown_mushroom', 'red_mushroom'})
FACE_STEPS = {None: (0, 0, 0), 'up': (0, 1, 0), 'down': (0, -1, 0),
              'north': (0, 0, -1), 'south': (0, 0, 1),
              'east': (1, 0, 0), 'west': (-1, 0, 0)}


def ray_cells(start, end):
    """Every voxel with positive-length intersection, in exact ray order."""
    crossings = {0.0, 1.0}
    for a, b in zip(start, end):
        if abs(b - a) < 1e-12:
            continue
        for boundary in range(math.floor(min(a, b)) + 1, math.ceil(max(a, b))):
            ratio = (boundary - a) / (b - a)
            if 0 < ratio < 1:
                crossings.add(ratio)
    values = sorted(crossings)
    result = []
    for low, high in zip(values, values[1:]):
        ratio = (low + high) / 2
        point = tuple(math.floor(a + (b - a) * ratio) for a, b in zip(start, end))
        if not result or result[-1] != point:
            result.append(point)
    return result


def clearable_plant(world, point, protected=()):
    row = world.row(point)
    return (point not in protected and world.name(point) in NATURAL_PLANTS
            and row.get('solid') is False and row.get('passable') is True
            and row.get('fluid') is False and row.get('block_entity') is False
            and all(world.safe(tuple(a + b for a, b in zip(point, delta)))
                    for delta in ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
                                  (0, -1, 0), (0, 0, 1), (0, 0, -1))))


def soil_top_exposed(world, target, protected=()):
    """Never harvest soil supporting a tree, crop, station or foreign structure."""
    above = (target[0], target[1] + 1, target[2])
    return (above not in protected
            and (world.name(above) == 'air' or clearable_plant(world, above, protected)))


def mining_plan(world, feet, target, protected=(), *, margin=0.0, max_plants=2):
    """Return an existing native face and bounded plant blockers, or no plan.

    Non-air cells are conservatively opaque, even when walking can pass through
    them. Margin checks are used for proposed walking stances; after arrival the
    exact current eye is checked again before each normal dig.
    """
    target = tuple(target)
    epsilon = 1e-7
    floors = {(x, math.floor(feet[1]) - 1, z)
              for x in range(math.floor(feet[0] - .3 + epsilon), math.floor(feet[0] + .3 - epsilon) + 1)
              for z in range(math.floor(feet[2] - .3 + epsilon), math.floor(feet[2] + .3 - epsilon) + 1)}
    protected = set(protected) | floors
    if target in protected or not world.row(target) or world.row(target).get('block_entity'):
        return None
    if world.name(target) in {'dirt', 'grass_block'} and not soil_top_exposed(world, target, protected):
        return None
    faces = ('down', None, 'up', 'north', 'south', 'east', 'west') if world.name(target) == 'leaf_litter' else tuple(FACE_STEPS)
    offsets = [(0, 0)] if not margin else [(0, 0), (margin, margin),
                    (margin, -margin), (-margin, margin), (-margin, -margin)]
    choices = []
    for index, face in enumerate(faces):
        end = [value + .5 + step * .499 for value, step in zip(target, FACE_STEPS[face])]
        plants = set()
        valid = True
        for dx, dz in offsets:
            start = [feet[0] + dx, feet[1] + 1.62, feet[2] + dz]
            if math.dist(start, end) > 3.6:
                valid = False
                break
            for point in ray_cells(start, end):
                if point == target:
                    break
                if world.name(point) == 'air':
                    continue
                if not clearable_plant(world, point, protected):
                    valid = False
                    break
                plants.add(point)
                if len(plants) > max_plants:
                    valid = False
                    break
            if not valid:
                break
        if valid:
            # Prefer a ray needing no vegetation removal, then the host's
            # ordinary centre aim. A leaf-litter endpoint must be near its base.
            choices.append((len(plants), index, face, tuple(sorted(plants))))
    if not choices:
        return None
    _, _, face, plants = min(choices, key=lambda row: row[:2])
    return {'face': face, 'plants': plants}


def mining_stance(world, feet, target, protected=()):
    """A short supported route with robust aim and no mining of its own floor."""
    parents = world.paths(feet)
    choices = []
    for stance in parents:
        actual = [stance[0] + .5, stance[1], stance[2] + .5]
        if math.dist(actual, feet) <= .3:
            continue
        if math.dist([actual[0], actual[1] + 1.62, actual[2]], [value + .5 for value in target]) > 4.2:
            continue
        route = world.route(parents, stance)
        floors = {(point[0], point[1] - 1, point[2]) for point in route}
        floors.add((stance[0], stance[1] - 1, stance[2]))
        if tuple(target) in floors or len(route) > 24:
            continue
        plan = mining_plan(world, actual, target, set(protected) | floors, margin=.18)
        if plan is not None:
            choices.append((len(plan['plants']), len(route), stance, route))
    return min(choices, default=(None, None, None, None))[-1]
