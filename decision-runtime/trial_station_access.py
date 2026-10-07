"""Conservative real-face planning for full-cube local workstations.

The native bridge remains the authority for actual outlines, reach and normal
useItemOn. These plans use only a fresh complete scan, never remembered air.
Placement callers retain their requested face rather than using this fallback.
"""
import math

from survival_world import cell, center, distance

STATIONS = {'crafting_table', 'furnace'}
FACE_AXES = {'west': (0, -1), 'east': (0, 1), 'down': (1, -1),
             'up': (1, 1), 'north': (2, -1), 'south': (2, 1)}


def _air_ray(world, eye, surface, target):
    """Traverse every voxel crossed before the requested cube surface."""
    position = list(cell(eye))
    delta = [b - a for a, b in zip(eye, surface)]
    steps = [1 if v > 0 else -1 if v < 0 else 0 for v in delta]
    boundary = []
    interval = []
    for axis, step in enumerate(steps):
        if not step:
            boundary.append(math.inf)
            interval.append(math.inf)
        else:
            plane = position[axis] + (1 if step > 0 else 0)
            boundary.append((plane - eye[axis]) / delta[axis])
            interval.append(abs(1 / delta[axis]))
    # Reach is at most 3.6; 32 crossings is comfortably above its maximum.
    for unused in range(32):
        point = tuple(position)
        if point == target:
            return True
        if not world.known(point) or world.name(point) != 'air':
            return False
        next_t = min(boundary)
        if next_t >= 1 - 1e-9:
            return True
        # At a corner check all touching cells conservatively. Taking a ray
        # through a solid edge is not sufficient evidence of a visible face.
        axes = [axis for axis, value in enumerate(boundary) if abs(value - next_t) < 1e-9]
        if len(axes) > 1:
            for mask in range(1, 1 << len(axes)):
                adjacent = list(position)
                for index, axis in enumerate(axes):
                    if mask & (1 << index):
                        adjacent[axis] += steps[axis]
                adjacent = tuple(adjacent)
                if adjacent != target and (not world.known(adjacent) or world.name(adjacent) != 'air'):
                    return False
        for axis in axes:
            position[axis] += steps[axis]
            boundary[axis] += interval[axis]
    return False


def visible_station_faces(world, feet, target, reach=3.6):
    target = tuple(target)
    if world.name(target) not in STATIONS:
        return []
    return visible_full_faces(world, feet, target, reach)


def visible_full_faces(world, feet, target, reach=3.6):
    """Scan solid means isCollisionShapeFullBlock; use its actual cube faces."""
    target = tuple(target)
    if not world.full(target):
        return []
    eye = [feet[0], feet[1] + 1.62, feet[2]]
    choices = []
    for face, (axis, direction) in FACE_AXES.items():
        surface = [v + .5 for v in target]
        surface[axis] = target[axis] + (1 if direction > 0 else 0)
        # A ray from beneath the cube cannot hit its top face, even when the
        # block centre is close and World.sight sees the side of the block.
        if direction * (eye[axis] - surface[axis]) <= 1e-5:
            continue
        separation = distance(eye, surface)
        if separation <= reach and _air_ray(world, eye, surface, target):
            choices.append((separation, face))
    return [face for unused, face in sorted(choices)]


def station_access_plan(world, state, target, rejected=(), reach=3.6):
    """Choose current actual feet first, then a supported normal walk stance."""
    target = tuple(target)
    choices = []
    actual = state['pos']
    feet_key = lambda feet: tuple(round(v, 3) for v in feet)
    for face in visible_station_faces(world, actual, target, reach):
        signature = (feet_key(actual), face)
        if signature not in rejected:
            choices.append((0, 0, face, [], signature))
    parents = world.paths(actual)
    for stance in parents:
        route = world.route(parents, stance)
        if not route or len(route) > 32:
            continue
        feet = center(stance)
        for face in visible_station_faces(world, feet, target, reach):
            signature = (feet_key(feet), face)
            if signature not in rejected:
                choices.append((1, len(route), face, route, signature))
    if not choices:
        return None
    unused, unused_steps, face, route, signature = min(choices)
    return {'face': face, 'route': route, 'signature': signature}
