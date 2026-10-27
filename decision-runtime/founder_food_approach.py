"""Use the existing observed-space router before the native short food approach."""
import math
from village_air_route import move
from village_feeding import ground_food_pose
from villager_events import read


def prepare(builder, uid, low, high):
    for _ in range(4):
        scene, cells = builder.scan([low[0], low[1]-1, low[2]], high)
        people = [v for v in scene['scan_entities'] if v['type'] == 'minecraft:villager']
        target = next(v for v in people if v['uuid'] == uid)
        if target['health'] != 20 or target['is_baby']:
            raise RuntimeError('Exact healthy adult food target required')
        state = builder.check()
        flags = read(builder.root, state)
        if flags is None:
            raise RuntimeError('Current founder sleeping state is unavailable')
        if next(v for v in flags['villagers'] if v['uuid'] == uid)['sleeping']:
            return {'ready': False, 'reason': 'founder_sleeping', 'food_inputs': 0}
        distance = math.dist(state['pos'], target['pos'])
        if state['on_ground'] and 1.8 <= distance <= 2.7 and target['visible']:
            return {'ready': True, 'target': uid, 'food_inputs': 0}
        point = ground_food_pose(low, high, cells, target, people, state, standoff=True)
        if point is None:
            raise RuntimeError('No observed dry founder feeding pose')
        # A grounded or raised-bed pose can touch a partial block that the
        # coarse router conservatively treats as full. Rise only if surveyed
        # upper body space is clear, then let it route through the real passage.
        x, z = math.floor(state['pos'][0]), math.floor(state['pos'][2])
        if all((x, y, z) not in cells for y in (low[1]+1, low[1]+2)):
            builder.nav([state['pos'][0], low[1]+1.1, state['pos'][2]])
        move(builder, [point[0], low[1]+.1, point[2]])
        builder.n('walk', target=point, arrival=.1, restore_flight=False, seconds=20)
    return {'ready': False, 'reason': 'moving_founder_needs_new_observation', 'food_inputs': 0}
