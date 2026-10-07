"""Fresh normal placement access; every candidate still targets one exact cell."""
from survival_world import center, distance
from trial_station_access import FACE_AXES, visible_full_faces


def body_overlap(feet, target):
    x, y, z = target
    return (x < feet[0] + .31 and x + 1 > feet[0] - .31
            and z < feet[2] + .31 and z + 1 > feet[2] - .31
            and y < feet[1] + 1.8 and y + 1 > feet[1])


def placement_access_plan(world, state, target, rejected=(), *, door_axis=None, reach=3.6):
    target = tuple(target)
    if not world.known(target) or world.name(target) != 'air':
        return None
    parents = world.paths(state['pos'])
    stances = [(state['pos'], [])]
    for stance in parents:
        route = world.route(parents, stance)
        if route and len(route) <= 32:
            stances.append((center(stance), route))
    choices = []
    for face, (axis, direction) in FACE_AXES.items():
        support = list(target)
        support[axis] -= direction
        support = tuple(support)
        if not world.full(support) or world.row(support).get('block_entity'):
            continue
        if door_axis and (face != 'up' or not world.known((target[0], target[1] + 1, target[2]))
                          or world.name((target[0], target[1] + 1, target[2])) != 'air'):
            continue
        for feet, route in stances:
            if body_overlap(feet, target) or door_axis and body_overlap(feet, (target[0], target[1] + 1, target[2])):
                continue
            if door_axis == 'z' and (abs(feet[0] - target[0] - .5) > .2
                                    or target[2] < feet[2] < target[2] + 1):
                continue
            if face not in visible_full_faces(world, feet, support, reach):
                continue
            signature = (support, face, tuple(round(v, 3) for v in feet))
            if signature in rejected:
                continue
            eye = [feet[0], feet[1] + 1.62, feet[2]]
            choices.append((len(route), distance(eye, [v + .5 for v in support]),
                            support, face, route, signature))
    if not choices:
        return None
    unused, unused_distance, support, face, route, signature = min(choices)
    return {'target': target, 'support': support, 'face': face, 'route': route, 'signature': signature}
