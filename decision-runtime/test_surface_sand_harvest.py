import copy
import tempfile
import unittest
from pathlib import Path

from surface_sand_harvest import (SAND, SAND_STATE, candidates, harvest,
                                  merge_local, mine_one, safe_state, sand_candidate)


def block(pos, state, solid=True, fluid=False, block_entity=False):
    return {'pos': list(pos), 'state': state, 'solid': solid,
            'fluid': fluid, 'block_entity': block_entity}


def slots(sand=0):
    inventory = [{'slot': i, 'item': 'minecraft:air', 'count': 0} for i in range(36)]
    inventory[0] = {'slot': 0, 'item': 'minecraft:diamond_shovel',
                    'count': 1, 'durability': 900}
    if sand:
        inventory[1] = {'slot': 1, 'item': SAND, 'count': sand, 'max_stack': 64}
    return inventory


class FakeClient:
    def __init__(self, positions, sand=0, first_out_of_reach=False, ambiguous=False):
        self.world = {tuple(p): block(p, SAND_STATE) for p in positions}
        for x, y, z in positions:
            self.world[(x, y - 1, z)] = block([x, y - 1, z], 'Block{minecraft:stone}')
        self.inventory = slots(sand)
        self.pos = [positions[0][0] + .5, positions[0][1] + 2.0, positions[0][2] + .5]
        self.actions = []
        self.first_out_of_reach = first_out_of_reach
        self.ambiguous = ambiguous

    def status(self):
        return {'inventory': copy.deepcopy(self.inventory), 'pos': list(self.pos), 'health': 20,
                'guard_armed': True, 'under_water': False,
                'world_session': 'sample-world', 'entities': [],
                'safety_hold': {'active': False}}

    def checked(self, op, **params):
        response = self.request(op, **params)
        if response.get('phase') != 'done':
            raise RuntimeError(response.get('detail', op))
        return response

    def request(self, op, **params):
        self.actions.append(op)
        if op == 'scan':
            low, high = params['min'], params['max']
            return {'blocks': [row for p, row in self.world.items()
                               if all(low[i] <= p[i] <= high[i] for i in range(3))]}
        if op == 'select_item':
            return {'phase': 'done'}
        if op == 'approach_block':
            return {'phase': 'done'}
        if op == 'mine_block':
            if self.first_out_of_reach:
                self.first_out_of_reach = False
                return {'phase': 'error', 'detail': 'Mining target out of reach'}
            if self.ambiguous:
                return {'phase': 'waiting', 'detail': 'server did not confirm'}
            self.world.pop(tuple(params['pos']))
            sand_slot = self.inventory[1]
            if sand_slot['count'] == 0:
                self.inventory[1] = {'slot': 1, 'item': SAND, 'count': 1,
                                     'max_stack': 64}
            else:
                sand_slot['count'] += 1
            return {'phase': 'done'}
        raise AssertionError(op)


class SurfaceSandHarvestTest(unittest.TestCase):
    def test_health_below_nineteen_stops_before_dry_quarry_work(self):
        state=FakeClient([[10,64,20]]).status()
        state['health']=18.5
        with self.assertRaises(RuntimeError):
            safe_state(state)

    def test_only_dry_exposed_supported_sand_is_selected(self):
        p = [10, 64, 20]
        rows = [block(p, SAND_STATE), block([10, 63, 20], 'Block{minecraft:stone}')]
        self.assertTrue(sand_candidate(rows, p))
        self.assertFalse(sand_candidate(rows[:1], p))
        self.assertFalse(sand_candidate(rows + [block([10, 65, 20], SAND_STATE)], p))
        self.assertFalse(sand_candidate(rows + [block([13, 64, 20],
                                                       'Block{minecraft:water}[level=0]', fluid=True)], p))
        self.assertFalse(sand_candidate(rows + [block([11, 64, 20],
                                                       'Block{minecraft:chest}', block_entity=True)], p))
        self.assertTrue(sand_candidate(rows + [block([14, 64, 20],
                                                      'Block{minecraft:water}[level=0]', fluid=True)], p))

    def test_nearby_sand_mines_without_approach_and_keeps_trip_open(self):
        client = FakeClient([[10, 64, 20], [11, 64, 20]])
        with tempfile.TemporaryDirectory() as directory:
            result = harvest(client, [10, 64, 20], [11, 64, 20], 2, directory)
            self.assertTrue((Path(directory) / 'progress.json').exists())
        self.assertEqual(2, result['gained'])
        self.assertTrue(result['target_reached'])
        self.assertEqual(5, client.actions.count('scan'))
        self.assertNotIn('approach_block', client.actions)

    def test_exact_out_of_reach_rejection_is_rechecked_then_approached(self):
        client = FakeClient([[10, 64, 20]], first_out_of_reach=True)
        result = mine_one(client, [10, 64, 20])
        self.assertEqual(1, result['sand_gain'])
        self.assertEqual(2, client.actions.count('mine_block'))
        self.assertEqual(1, client.actions.count('approach_block'))

    def test_ambiguous_mine_is_never_replayed(self):
        client = FakeClient([[10, 64, 20]], ambiguous=True)
        with self.assertRaisesRegex(RuntimeError, 'not confirmed'):
            mine_one(client, [10, 64, 20])
        self.assertEqual(1, client.actions.count('mine_block'))

    def test_local_cache_replacement_discovers_new_layer(self):
        original = {(10, 64, 20): block([10, 64, 20], SAND_STATE),
                    (10, 63, 20): block([10, 63, 20], SAND_STATE)}
        fresh = [block([10, 63, 20], SAND_STATE),
                 block([10, 62, 20], 'Block{minecraft:stone}')]
        merge_local(original, fresh, [10, 64, 20])
        self.assertNotIn((10, 64, 20), original)
        self.assertEqual([[10, 63, 20]],
                         candidates(original.values(), [10, 63, 20], [10, 64, 20], [10.5, 65, 20.5]))


if __name__ == '__main__':
    unittest.main()
