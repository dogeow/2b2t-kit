import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from survival import Runner
from survival_bridge import Paused
from survival_mining_access import mining_plan, ray_cells
from survival_world import World
from test_survival import MiningBridge, row, terrain


def observation():
    return json.loads((Path(__file__).parent / 'fixtures/trial-soil-outline-20261007.json').read_text())


def litter_bank():
    return terrain() + [row((x, 1, 0), 'dirt') for x in (0, 1, 2)] + [
        row((x, 2, 0), 'leaf_litter', solid=False, passable=True) for x in (1, 2)]


class SoilMiningBridge(MiningBridge):
    def request(self, op, **args):
        if op != 'mine_block':
            return super().request(op, **args)
        self.requests.append((op, args))
        target = next(r for r in self.rows if r['pos'] == args['pos'])
        self.rows.remove(target)
        if 'grass_block' in target['state'] or target['state'] == 'Block{minecraft:dirt}':
            self.state['inventory'].append({'item': 'minecraft:dirt', 'count': 1})
        return self.state


class MiningAccessTests(unittest.TestCase):
    def test_real_scan_does_not_remove_soil_supporting_the_dark_oak_trunk(self):
        data = observation()
        world = World(data['blocks'], data['min'], data['max'])
        target = (17, 63, -65)
        self.assertIsNone(mining_plan(world, data['pos'], target))
        selected = world.resource(data['pos'], {'dirt', 'grass_block'})
        self.assertTrue(selected is None or selected[0] != target)

    def test_real_arrival_drift_uses_visible_side_instead_of_aiming_through_log(self):
        data = observation()
        world = World(data['blocks'], data['min'], data['max'])
        target = (16, 63, -65)
        eye = [data['pos'][0], data['pos'][1] + 1.62, data['pos'][2]]
        ray = ray_cells(eye, [v + .5 for v in target])
        self.assertIn((17, 64, -65), ray)
        self.assertEqual(world.name((17, 64, -65)), 'dark_oak_log')
        plan = mining_plan(world, data['pos'], target)
        self.assertEqual(plan, {'face': 'west', 'plants': ()})

    def test_passable_litter_is_a_blocker_for_soil_ray_and_is_not_dirt(self):
        rows = litter_bank()
        world = World(rows, [-6, 0, -6], [6, 5, 6])
        # A higher eye cannot reach the soil without passing through its litter.
        plan = mining_plan(world, [.5, 2, .5], (2, 1, 0))
        self.assertEqual(plan['plants'], ((1, 2, 0), (2, 2, 0)))
        self.assertEqual(mining_plan(world, [.5, 2, .5], (1, 2, 0), max_plants=0)['face'], 'down')

    def test_crop_and_owned_litter_never_become_a_vegetation_clearance(self):
        for plant in ('wheat', 'leaf_litter'):
            with self.subTest(plant=plant):
                rows = terrain() + [row((2, 1, 0), 'dirt'),
                        row((2, 2, 0), plant, solid=False, passable=True)]
                world = World(rows, [-6, 0, -6], [6, 5, 6])
                protected = {(2, 2, 0)} if plant == 'leaf_litter' else set()
                self.assertIsNone(mining_plan(world, [.5, 3, .5], (2, 1, 0), protected))

    def test_unknown_and_container_rays_do_not_clear_an_opaque_block(self):
        for name in ('unknown', 'chest', 'oak_log'):
            rows = terrain() + [row((2, 1, 0), 'dirt'), row((1, 1, 0), name), row((1, 2, 0), name)]
            world = World(rows, [-6, 0, -6], [6, 5, 6])
            self.assertIsNone(mining_plan(world, [.5, 1, .5], (2, 1, 0)))

    def test_fresh_actual_body_edge_never_mines_one_of_its_supports(self):
        world = World(terrain(), [-6, -1, -6], [6, 5, 6])
        self.assertIsNone(mining_plan(world, [.98, 1, .02], (1, 0, -1)))

    def test_plant_clearance_budget_and_fluid_boundary_are_rejected(self):
        world = World(litter_bank(), [-6, 0, -6], [6, 5, 6])
        self.assertIsNone(mining_plan(world, [.5, 2, .5], (2, 1, 0), max_plants=1))
        rows = litter_bank() + [row((1, 2, 1), 'water', solid=False, passable=True)]
        world = World(rows, [-6, 0, -6], [6, 5, 6])
        self.assertIsNone(mining_plan(world, [.5, 2, .5], (2, 1, 0)))

    def test_normal_gather_clears_only_litter_then_confirms_soil_inventory(self):
        rows = litter_bank()
        with tempfile.TemporaryDirectory() as tmp:
            bridge = SoilMiningBridge(tmp, rows)
            bridge.state['pos'] = [.5, 2, .5]
            runner = Runner(bridge, None, tmp)
            with patch.object(World, 'resource', return_value=((2, 1, 0), [])):
                runner.gather({'dirt', 'grass_block'}, {'dirt'}, 1)
            digs = [args for op, args in bridge.requests if op == 'mine_block']
            self.assertEqual([args['pos'] for args in digs], [[1, 2, 0], [2, 2, 0], [2, 1, 0]])
            self.assertEqual(digs[0]['face'], 'down')
            self.assertEqual(runner.count('dirt'), 1)
            events = [json.loads(line) for line in (Path(tmp) / 'events.jsonl').read_text().splitlines()]
            self.assertEqual(sum(e['event'] == 'mining_vegetation_cleared' for e in events), 2)

    def test_unconfirmed_plant_dig_stops_before_soil_dig(self):
        rows = litter_bank()
        with tempfile.TemporaryDirectory() as tmp:
            bridge = SoilMiningBridge(tmp, rows)
            bridge.state['pos'] = [.5, 2, .5]
            runner = Runner(bridge, None, tmp)
            original = bridge.request
            def unknown(op, **args):
                if op == 'mine_block':
                    bridge.requests.append((op, args))
                    raise Paused('single target outcome pending; no second excavation sent')
                return original(op, **args)
            with patch.object(World, 'resource', return_value=((2, 1, 0), [])), patch.object(bridge, 'request', side_effect=unknown):
                with self.assertRaisesRegex(Paused, 'outcome pending'):
                    runner.gather({'dirt', 'grass_block'}, {'dirt'}, 1)
            self.assertEqual([args['pos'] for op, args in bridge.requests if op == 'mine_block'], [[1, 2, 0]])

    def test_legacy_owned_soil_is_excluded_from_candidate_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = SoilMiningBridge(tmp, terrain() + [row((2, 1, 0), 'dirt')])
            runner = Runner(bridge, None, tmp)
            runner.owned = {'2,1,0': 'dirt'}
            with self.assertRaises(Paused):
                runner.gather({'dirt', 'grass_block'}, {'dirt'}, 1)
            self.assertFalse(any(op == 'mine_block' for op, args in bridge.requests))


if __name__ == '__main__':
    unittest.main()
