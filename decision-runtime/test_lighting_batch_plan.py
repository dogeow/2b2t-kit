"""One-snapshot lighting predictions; no game, input, or deployment."""
import copy
import math
import unittest
from unittest.mock import patch

import lighting_batch_plan as batch
import lighting_cli as lighting


def block(x, y=63, z=0, *, dark=True, state='Block{minecraft:grass_block}[snowy=false]'):
    return {'pos': [x, y, z], 'state': state, 'solid': True, 'fluid': False,
            'block_entity': False, 'spawn_block_light': 0,
            'monster_spawn_block_light_limit': 0, 'zombie_spawn_floor': dark,
            'zombie_block_light_risk': dark}


def floor(width=17, depth=17, y=63):
    return {(x, y, z): block(x, y, z) for x in range(width) for z in range(depth)}


class LightingBatchPlanTests(unittest.TestCase):
    def test_one_snapshot_source_contract_and_sparse_flat_ground_batch(self):
        cells = floor()
        original = copy.deepcopy(cells)
        with patch.object(lighting, 'candidates', wraps=lighting.candidates) as candidates, \
                patch.object(lighting, 'risk_counts', wraps=lighting.risk_counts) as risks:
            planned = batch.plan(cells, (0, 60, 0), (16, 90, 16), [8.5, 65.5, 8.5])
        self.assertEqual(candidates.call_count, 1)
        self.assertEqual(risks.call_count, 1)
        self.assertEqual(cells, original)
        self.assertLessEqual(len(planned), 4)
        self.assertEqual(sum(row['predicted_coverage_count'] for row in planned), len(cells))
        for candidate in planned:
            support, target = tuple(candidate['support']), tuple(candidate['target'])
            self.assertEqual(target, (support[0], support[1] + 1, support[2]))
            self.assertNotIn(target, cells)
            self.assertEqual(candidate['support_state'], original[support]['state'])
            self.assertGreater(candidate['predicted_coverage_count'], 0)
            self.assertFalse({'placed', 'completed', 'verified'} & set(candidate))
        # On open level land the torch's positive light reaches at most 13 AIR
        # steps. Every observed floor is covered by the small predicted batch.
        self.assertTrue(all(any(sum(abs(a - b) for a, b in zip(pos, c['support'])) <= 13
                                for c in planned) for pos in cells))

    def test_equal_coverage_prefers_nearest_station_and_stable_order(self):
        cells = floor(width=5, depth=3)
        start = [0.5, 65.5, 0.5]
        planned = batch.plan(cells, (0, 60, 0), (4, 90, 2), start)
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0]['support'], [0, 63, 0])
        self.assertEqual(planned[0]['distance'], 0)
        self.assertEqual(planned, batch.plan(cells, (0, 60, 0), (4, 90, 2), start))

    def test_opaque_wall_requires_torches_on_both_sides(self):
        cells = floor(width=13, depth=3)
        for z in range(3):
            cells[(6, 63, z)] = block(6, 63, z, dark=False)
            for y in range(64, 91):
                cells[(6, y, z)] = block(6, y, z, dark=False, state='Block{minecraft:stone}')
        bounds = (0, 60, 0), (12, 90, 2)
        single = batch.plan(cells, *bounds, [2.5, 65.5, 1.5], limit=1)
        self.assertEqual(single[0]['predicted_coverage_count'], 18)
        planned = batch.plan(cells, *bounds, [2.5, 65.5, 1.5])
        self.assertEqual(len(planned), 2)
        self.assertLess(planned[0]['support'][0], 6)
        self.assertGreater(planned[1]['support'][0], 6)
        self.assertEqual(sum(c['predicted_coverage_count'] for c in planned), 36)

    def test_opaque_roof_does_not_predict_light_on_floor_below(self):
        cells = floor(width=5, depth=5)
        cells.update({(x, 66, z): block(x, 66, z, state='Block{minecraft:stone}')
                      for x in range(5) for z in range(5)})
        planned = batch.plan(cells, (0, 60, 0), (4, 94, 4), [2.5, 68.5, 2.5])
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0]['support'][1], 66)
        self.assertEqual(planned[0]['predicted_coverage_count'], 25)

    def test_protected_support_target_and_coverage_are_excluded(self):
        cells = floor(width=7, depth=3)
        protected = [{'min': [0, 63, 0], 'max': [1, 63, 2]},
                     {'min': [5, 64, 0], 'max': [6, 64, 2]}]
        planned = batch.plan(cells, (0, 60, 0), (6, 90, 2), [3.5, 65.5, 1.5], protected)
        self.assertEqual(sum(c['predicted_coverage_count'] for c in planned), 9)
        for candidate in planned:
            self.assertFalse(lighting.candidate_protected(candidate['support'], candidate['target'], protected))
            for pos in (candidate['support'], candidate['target']):
                self.assertTrue(all((0, 60, 0)[i] <= pos[i] <= (6, 90, 2)[i] for i in range(3)))
        all_protected = [{'min': [0, 60, 0], 'max': [6, 90, 2]}]
        self.assertEqual(batch.plan(cells, (0, 60, 0), (6, 90, 2), [3.5, 65.5, 1.5], all_protected), [])

    def test_positive_level_and_observed_threshold_are_required(self):
        cells = {(0, 63, 0): block(0), (13, 63, 0): block(13), (14, 63, 0): block(14)}
        planned = batch.plan(cells, (0, 60, 0), (14, 90, 0), [.5, 65.5, .5], limit=1)
        self.assertEqual(planned[0]['predicted_coverage_count'], 3)
        # Only the first support is permitted for placement; an unsafe building
        # floor can receive predicted illumination but remains ineligible.
        cells[(13, 63, 0)]['state'] = 'Block{minecraft:oak_planks}'
        cells[(14, 63, 0)]['state'] = 'Block{minecraft:oak_planks}'
        planned = batch.plan(cells, (0, 60, 0), (14, 90, 0), [.5, 65.5, .5])
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0]['support'], [0, 63, 0])
        self.assertEqual(planned[0]['predicted_coverage_count'], 2)
        cells[(13, 63, 0)]['monster_spawn_block_light_limit'] = 1
        planned = batch.plan(cells, (0, 60, 0), (14, 90, 0), [.5, 65.5, .5])
        self.assertEqual(planned[0]['predicted_coverage_count'], 1)

    def test_batch_budget_is_bounded_and_does_not_pad_with_useless_targets(self):
        cells = {(x, 63, 0): block(x) for x in range(0, 281, 28)}
        bounds = (0, 60, 0), (280, 90, 0)
        planned = batch.plan(cells, *bounds, [.5, 65.5, .5])
        self.assertEqual(len(planned), 8)
        self.assertEqual({c['predicted_coverage_count'] for c in planned}, {1})
        self.assertEqual(len(batch.plan(cells, *bounds, [.5, 65.5, .5], limit=3)), 3)
        tiny = {(0, 63, 0): block(0)}
        self.assertEqual(len(batch.plan(tiny, (0, 60, 0), (0, 90, 0), [.5, 65.5, .5])), 1)
        for limit in (0, -1, 9, 64, True, 2.5, None):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                batch.plan(cells, *bounds, [.5, 65.5, .5], limit=limit)

    def test_bad_or_missing_observations_fail_closed(self):
        base = block(0)
        bad_rows = []
        for missing in ('pos', 'state', 'solid', 'fluid', 'block_entity', 'zombie_spawn_floor',
                        'zombie_block_light_risk', 'spawn_block_light', 'monster_spawn_block_light_limit'):
            bad_rows.append({k: v for k, v in base.items() if k != missing})
        bad_rows.extend(({**base, 'pos': [1, 63, 0]}, {**base, 'state': 'minecraft:grass_block'},
                         {**base, 'state': 'Block{minecraft:grass_block}junk'},
                         {**base, 'state': 'Block{minecraft:air}'}, {**base, 'spawn_block_light': True},
                         {**base, 'spawn_block_light': 16}, {**base, 'zombie_block_light_risk': 1},
                         {**base, 'zombie_spawn_floor': False}, {**base, 'spawn_block_light': 1}, None))
        for row in bad_rows:
            with self.subTest(row=row), self.assertRaises(lighting.LightingBlocked):
                batch.plan({(0, 63, 0): row}, (0, 60, 0), (2, 90, 2), [.5, 65.5, .5])
        for cells in (None, [], {(3, 63, 0): block(3)}, {(True, 63, 0): base}):
            with self.subTest(cells=cells), self.assertRaises(lighting.LightingBlocked):
                batch.plan(cells, (0, 60, 0), (2, 90, 2), [.5, 65.5, .5])
        self.assertEqual(batch.plan({}, (0, 60, 0), (2, 90, 2), [.5, 65.5, .5]), [])

    def test_invalid_start_bounds_and_masks_reject(self):
        cells = {(0, 63, 0): block(0)}
        for start in (None, [], [0, 65], [True, 65, 0], [0, math.nan, 0], [0, math.inf, 0]):
            with self.subTest(start=start), self.assertRaises(ValueError):
                batch.plan(cells, (0, 60, 0), (2, 90, 2), start)
        with self.assertRaisesRegex(ValueError, '50,000'):
            batch.plan(cells, (0, 60, 0), (100, 90, 100), [.5, 65.5, .5])
        with self.assertRaises(ValueError):
            batch.plan(cells, (0, 60, 0), (2, 90, 2), [.5, 65.5, .5],
                       protected=[{'min': [0, 60, 0], 'max': [-1, 90, 2]}])


if __name__ == '__main__':
    unittest.main()
