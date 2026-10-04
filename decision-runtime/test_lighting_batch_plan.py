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


def plant(pos, state='Block{minecraft:short_grass}'):
    return {**block(*pos, dark=False, state=state), 'solid': False, 'passable': True}


class LightingBatchPlanTests(unittest.TestCase):
    def under_roof(self):
        dark=(760824,62,797823);neighbor=(760821,62,797824)
        cells={dark:block(*dark,state='Block{minecraft:sand}'),
               neighbor:{**block(*neighbor,state='Block{minecraft:sand}'),
                         'spawn_block_light':3,'zombie_block_light_risk':False},
               (760824,65,797823):block(760824,65,797823,dark=False,state='Block{minecraft:stone}')}
        return cells,(760819,60,797820),(760827,90,797828),dark,neighbor

    def test_actual_underroof_dark_sand_is_reached_from_safe_lit_exterior_neighbor(self):
        cells,low,high,dark,neighbor=self.under_roof();original=copy.deepcopy(cells)
        self.assertEqual(lighting.candidates(cells,low,high),[])
        planned=batch.plan(cells,low,high,[neighbor[0]+.5,64.5,neighbor[2]+.5])
        self.assertEqual(1,len(planned));self.assertEqual(list(neighbor),planned[0]['support'])
        self.assertEqual(1,planned[0]['predicted_coverage_count'])
        self.assertEqual('safe_neighbor_of_observed_dark_floor',planned[0]['placement_basis'])
        self.assertTrue(planned[0]['prediction_only']);self.assertEqual(original,cells)
        self.assertEqual(batch.plan(cells,low,high,[neighbor[0]+.5,64.5,neighbor[2]+.5],residual=False),[])

    def test_lit_neighbor_is_useless_without_air_light_path(self):
        cells,low,high,dark,neighbor=self.under_roof()
        for y in range(low[1],high[1]+1):
            for z in range(low[2],high[2]+1):
                cells[(760822,y,z)]=block(760822,y,z,dark=False,state='Block{minecraft:stone}')
        self.assertEqual(batch.plan(cells,low,high,[neighbor[0]+.5,64.5,neighbor[2]+.5]),[])

    def test_verified_plants_at_dark_spawn_space_receive_neighbor_light(self):
        for state in ('Block{minecraft:short_grass}', 'Block{minecraft:dandelion}'):
            cells, low, high, dark, neighbor = self.under_roof()
            spawn = (dark[0], dark[1] + 1, dark[2])
            cells[spawn] = plant(spawn, state)
            original = copy.deepcopy(cells)
            with self.subTest(state=state):
                planned = batch.plan(cells, low, high, [neighbor[0]+.5, 64.5, neighbor[2]+.5])
                self.assertEqual(len(planned), 1)
                self.assertEqual(planned[0]['support'], list(neighbor))
                self.assertEqual(planned[0]['predicted_coverage_count'], 1)
                self.assertNotIn(tuple(planned[0]['target']), cells)
                self.assertEqual(cells, original)

    def test_plants_transmit_in_both_directions_with_one_level_attenuation(self):
        cells = {(3, 64, 0): plant((3, 64, 0)),
                 (9, 64, 0): plant((9, 64, 0), 'Block{minecraft:dandelion}')}
        grid = batch._LightGrid(cells, (0, 64, 0), (14, 64, 0), [])
        risks = {grid.index((13, 64, 0)): (1, 0), grid.index((14, 64, 0)): (2, 0)}
        self.assertEqual(grid.coverage((0, 64, 0), risks), 1)
        self.assertEqual(grid.coverage((13, 64, 0), {grid.index((0, 64, 0)): (1, 0)}), 1)
        self.assertEqual(grid.coverage((0, 64, 0), {grid.index((13, 64, 0)): (1, 1)}), 0)

    def test_passable_or_unverified_plant_states_do_not_transmit(self):
        other_states = ('Block{minecraft:fern}', 'Block{minecraft:poppy}',
                        'Block{minecraft:tall_grass}[half=lower]',
                        'Block{minecraft:short_grass}[unverified=true]',
                        'Block{example:short_grass}', 'Block{minecraft:glass}',
                        'Block{minecraft:water}')
        bad_rows = [plant((1, 64, 0), state) for state in other_states]
        for state in ('Block{minecraft:short_grass}', 'Block{minecraft:dandelion}'):
            for flag, value in (('fluid', True), ('block_entity', True),
                                ('solid', True), ('passable', False)):
                bad_rows.append({**plant((1, 64, 0), state), flag: value})
            bad_rows.append({key: value for key, value in plant((1, 64, 0), state).items()
                             if key != 'passable'})
        for row in bad_rows:
            with self.subTest(row=row):
                grid = batch._LightGrid({(1, 64, 0): row}, (0, 64, 0), (2, 64, 0), [])
                self.assertEqual(grid.coverage((0, 64, 0), {grid.index((2, 64, 0)): (1, 0)}), 0)

    def test_plant_bridge_in_protected_area_stays_outside_prediction_domain(self):
        cells = {(1, 64, 0): plant((1, 64, 0))}
        grid = batch._LightGrid(cells, (0, 64, 0), (2, 64, 0),
                               [{'min': [1, 64, 0], 'max': [1, 64, 0]}])
        self.assertEqual(grid.coverage((0, 64, 0), {grid.index((2, 64, 0)): (1, 0)}), 0)

    def test_transmitting_plants_are_not_air_for_candidate_clearance_or_placement(self):
        for state in ('Block{minecraft:short_grass}', 'Block{minecraft:dandelion}'):
            for height in (62, 63, 65, 84):
                cells, low, high, dark, neighbor = self.under_roof()
                cells[(neighbor[0], height, neighbor[2])] = plant((neighbor[0], height, neighbor[2]), state)
                original = copy.deepcopy(cells)
                with self.subTest(state=state, height=height):
                    self.assertEqual(batch.plan(cells, low, high,
                                               [neighbor[0]+.5, 64.5, neighbor[2]+.5]), [])
                    self.assertEqual(cells, original)

    def test_neighbor_support_target_and_dark_target_masks_are_preserved(self):
        cells,low,high,dark,neighbor=self.under_roof()
        for protected_pos in (neighbor,(neighbor[0],neighbor[1]+1,neighbor[2]),dark):
            protected=[{'min':list(protected_pos),'max':list(protected_pos)}]
            self.assertEqual(batch.plan(cells,low,high,[neighbor[0]+.5,64.5,neighbor[2]+.5],protected),[])

    def test_no_safe_roof_free_neighbor_means_no_placement_prediction(self):
        for change in ('building','roof','fluid','no_dark'):
            cells,low,high,dark,neighbor=self.under_roof()
            if change=='building':cells[neighbor]['state']='Block{minecraft:oak_planks}'
            elif change=='roof':cells[(neighbor[0],68,neighbor[2])]=block(neighbor[0],68,neighbor[2],dark=False,state='Block{minecraft:oak_leaves}')
            elif change=='fluid':cells[neighbor]['fluid']=True
            else:cells[dark].update(spawn_block_light=1,zombie_block_light_risk=False)
            with self.subTest(change=change):
                self.assertEqual(batch.plan(cells,low,high,[neighbor[0]+.5,64.5,neighbor[2]+.5]),[])

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
