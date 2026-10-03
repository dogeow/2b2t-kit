"""Pure lighting flight routes stay low and inside fully observed AIR."""
from copy import deepcopy
import math
import unittest

from lighting_air_route import plan


STONE = {'state': 'Block{minecraft:stone}'}


def flat_cells(low, high, ground=0):
    return {(x, ground, z): STONE
            for x in range(low[0], high[0] + 1)
            for z in range(low[2], high[2] + 1)}


class AirRouteTest(unittest.TestCase):
    def assert_safe(self, route, cells, low, high, start, target):
        self.assertIsNotNone(route)
        self.assertEqual(route[0], list(start))
        self.assertEqual(route[-1], list(target))
        for waypoint in route:
            self.assertEqual(len(waypoint), 3)
            self.assertTrue(all(math.isfinite(value) for value in waypoint))
        for a, b in zip(route, route[1:]):
            self.assertEqual(sum(a[i] != b[i] for i in range(3)), 1)
            minimum = [math.floor(min(a[i], b[i]) - (.35 if i != 1 else 0))
                       for i in range(3)]
            maximum = [math.floor(max(a[i], b[i]) + (.35 if i != 1 else 1.8))
                       for i in range(3)]
            self.assertTrue(all(low[i] <= minimum[i] <= maximum[i] <= high[i]
                                for i in range(3)))
            self.assertFalse(any((x, y, z) in cells
                                 for x in range(minimum[0], maximum[0] + 1)
                                 for y in range(minimum[1], maximum[1] + 1)
                                 for z in range(minimum[2], maximum[2] + 1)))

    def test_flat_land_has_no_gratuitous_ascent_or_descent(self):
        low, high = (0, 0, -2), (12, 15, 2)
        cells = flat_cells(low, high)
        start, target = (.5, 2.5, .5), (12.5, 2.5, .5)
        route = plan(cells, start, target, low, high)
        self.assert_safe(route, cells, low, high, start, target)
        self.assertEqual(route, [list(start), list(target)])

    def test_high_start_descends_before_flat_horizontal_travel(self):
        low, high = (-2, 0, -2), (12, 20, 2)
        cells = flat_cells(low, high)
        start, target = (.5, 16.5, .5), (12.5, 2.5, .5)
        route = plan(cells, start, target, low, high)
        self.assert_safe(route, cells, low, high, start, target)
        self.assertEqual(route, [list(start), [.5, 2.5, .5], list(target)])

    def test_high_start_at_scope_edge_uses_one_observed_step_before_descent(self):
        low, high = (0, 0, -2), (12, 20, 2)
        cells = flat_cells(low, high)
        start, target = (.5, 16.5, .5), (12.5, 2.5, .5)
        route = plan(cells, start, target, low, high)
        self.assert_safe(route, cells, low, high, start, target)
        self.assertEqual(route, [list(start), [1.5, 16.5, .5],
                                 [1.5, 2.5, .5], list(target)])

    def test_integer_high_start_snaps_down_and_has_no_half_block_ascent(self):
        low, high = (-2, 0, -2), (12, 20, 2)
        cells = flat_cells(low, high)
        start, target = (.5, 16, .5), (12.5, 2.5, .5)
        route = plan(cells, start, target, low, high)
        self.assert_safe(route, cells, low, high, start, target)
        self.assertEqual(route, [list(start), [.5, 2.5, .5], list(target)])

    def test_integer_pose_can_snap_down_when_upper_center_touches_a_ceiling(self):
        low, high = (-2, 0, -2), (6, 10, 2)
        cells = {(0, 4, 0): STONE}
        start, target = (.5, 2, .5), (6.5, 1.5, .5)
        route = plan(cells, start, target, low, high)
        self.assert_safe(route, cells, low, high, start, target)
        self.assertEqual(route, [list(start), [.5, 1.5, .5], list(target)])

    def test_wall_forces_local_rise_two_cells_before_obstacle(self):
        low, high = (0, 0, -1), (12, 12, 1)
        cells = flat_cells(low, high)
        cells.update({(6, y, z): STONE for y in range(1, 5) for z in range(-1, 2)})
        start, target = (.5, 2.5, .5), (12.5, 2.5, .5)
        route = plan(cells, start, target, low, high)
        self.assert_safe(route, cells, low, high, start, target)
        rising = [(a, b) for a, b in zip(route, route[1:]) if b[1] > a[1]]
        self.assertTrue(rising)
        self.assertEqual(rising[0][0], [4.5, 2.5, .5])
        self.assertEqual(max(p[1] for p in route), 5.5)
        self.assertEqual(route[-2], [8.5, 2.5, .5])

    def test_observed_short_detour_can_stay_low(self):
        low, high = (0, 0, -4), (12, 12, 4)
        cells = flat_cells(low, high)
        cells.update({(6, y, 0): STONE for y in range(1, 9)})
        start, target = (.5, 2.5, .5), (12.5, 2.5, .5)
        route = plan(cells, start, target, low, high)
        self.assert_safe(route, cells, low, high, start, target)
        self.assertTrue(any(p[2] != .5 for p in route))
        self.assertTrue(all(p[1] == 2.5 for p in route))

    def test_no_descent_through_a_roof_sealing_the_observed_box(self):
        low, high = (0, 0, -2), (8, 12, 2)
        cells = flat_cells(low, high)
        cells.update({(x, 5, z): STONE for x in range(9) for z in range(-2, 3)})
        self.assertIsNone(plan(cells, (.5, 8.5, .5), (8.5, 2.5, .5), low, high))

    def test_roof_requires_an_observed_side_descent_before_returning_under_it(self):
        low, high = (-4, 0, -4), (8, 12, 4)
        cells = flat_cells(low, high)
        cells.update({(x, 5, z): STONE for x in range(1, 7) for z in range(-1, 2)})
        start, target = (3.5, 8.5, .5), (3.5, 2.5, .5)
        route = plan(cells, start, target, low, high)
        self.assert_safe(route, cells, low, high, start, target)
        self.assertTrue(any(p[0] < 1 or p[0] > 7 or abs(p[2]) > 1.5 for p in route))

    def test_upper_third_body_cell_obstructs_a_centered_endpoint(self):
        low, high = (0, 0, -2), (6, 10, 2)
        cells = {(6, 4, 0): STONE}
        self.assertIsNone(plan(cells, (.5, 2.5, .5), (6.5, 2.5, .5), low, high))

    def test_width_crossing_a_cell_boundary_obstructs_exact_endpoint(self):
        low, high = (-2, 0, -2), (6, 10, 2)
        cells = {(-1, 2, 0): STONE}
        self.assertIsNone(plan(cells, (.2, 2.5, .5), (6.5, 2.5, .5), low, high))

    def test_any_present_row_is_occupied_including_passable_or_air_claims(self):
        low, high = (0, 0, -2), (6, 10, 2)
        for row in ({'state': 'Block{minecraft:air}'}, {'passable': True}, {}, None):
            with self.subTest(row=row):
                self.assertIsNone(plan({(6, 3, 0): row}, (.5, 2.5, .5),
                                       (6.5, 2.5, .5), low, high))

    def test_exact_endpoints_do_not_require_intermediate_horizontal_padding(self):
        low, high = (-1, 0, -2), (6, 10, 2)
        cells = {(0, y, 0): STONE for y in range(2, 5)}
        cells.update({(5, y, 0): STONE for y in range(2, 5)})
        start, target = (1.5, 2.5, .5), (4.5, 2.5, .5)
        route = plan(cells, start, target, low, high)
        self.assert_safe(route, cells, low, high, start, target)
        self.assertEqual(route, [list(start), list(target)])

    def test_off_center_alignment_checks_axis_legs_and_preserves_exact_poses(self):
        low, high = (-1, 0, -1), (7, 10, 3)
        # A diagonal bounding box would include this cell. First align X/Z,
        # then Y, so the real swept body remains entirely clear.
        cells = {(0, 4, 0): STONE}
        start, target = (1.1, 2.1, 1.1), (5.8, 2.3, 1.7)
        route = plan(cells, start, target, low, high)
        self.assert_safe(route, cells, low, high, start, target)
        self.assertIn([1.5, 2.5, 1.5], route)
        self.assertIn([5.5, 2.5, 1.5], route)

    def test_same_cell_offsets_still_have_only_checked_axis_transitions(self):
        low, high = (-2, 0, -2), (2, 8, 2)
        start, target = (.2, 2.1, .8), (.7, 2.4, .3)
        route = plan({}, start, target, low, high)
        self.assert_safe(route, {}, low, high, start, target)

    def test_same_exact_pose_returns_the_single_actual_waypoint(self):
        low, high = (-2, 0, -2), (2, 8, 2)
        pose = (.5, 2.5, .5)
        self.assertEqual(plan({}, pose, pose, low, high), [list(pose)])

    def test_same_off_center_pose_needs_no_alignment_or_extra_body_space(self):
        low, high = (-2, 0, -2), (2, 8, 2)
        pose = (.5, 2.1, .5)
        self.assertEqual(plan({(0, 4, 0): STONE}, pose, pose, low, high), [list(pose)])

    def test_body_outside_complete_scope_is_unknown_even_if_cells_are_empty(self):
        low, high = (0, 0, -2), (6, 10, 2)
        for start, target in (((.2, 2.5, .5), (6.5, 2.5, .5)),
                              ((.5, 2.5, .5), (6.8, 2.5, .5)),
                              ((.5, 2.5, .5), (6.5, 9.5, .5)),
                              ((-.5, 2.5, .5), (6.5, 2.5, .5))):
            with self.subTest(start=start, target=target):
                self.assertIsNone(plan({}, start, target, low, high))

    def test_unknown_outside_scope_cannot_supply_intermediate_padding(self):
        self.assertIsNone(plan({}, (.5, 2.5, .5), (6.5, 2.5, .5),
                               (0, 0, 0), (6, 10, 0)))

    def test_small_expansion_budget_stops_before_long_route(self):
        low, high = (0, 0, -2), (12, 10, 2)
        start, target = (.5, 2.5, .5), (12.5, 2.5, .5)
        self.assertIsNone(plan({}, start, target, low, high, max_expansions=2))
        self.assertIsNotNone(plan({}, start, target, low, high, max_expansions=13))

    def test_nonpositive_or_malformed_budgets_are_rejected(self):
        for budget in (0, -1, True, 1.5, None, '32'):
            with self.subTest(budget=budget):
                self.assertIsNone(plan({}, (.5, 2.5, .5), (6.5, 2.5, .5),
                                       (0, 0, -2), (6, 10, 2), budget))

    def test_malformed_nonfinite_coordinates_or_scope_are_rejected(self):
        valid = [{}, (.5, 2.5, .5), (6.5, 2.5, .5), (0, 0, -2), (6, 10, 2)]
        cases = ((1, [math.nan, 2.5, .5]), (2, [6.5, math.inf, .5]),
                 (1, [True, 2.5, .5]), (1, [0, 2]), (2, '6,2,0'),
                 (3, [0.0, 0, -2]), (3, [7, 0, -2]), (4, [6, 1, 2]),
                 (0, []), (0, {(7, 2, 0): STONE}), (0, {(True, 2, 0): STONE}),
                 (0, {('x', 2, 0): STONE}))
        for index, value in cases:
            with self.subTest(index=index, value=value):
                arguments = list(valid)
                arguments[index] = value
                self.assertIsNone(plan(*arguments))

    def test_planning_does_not_mutate_observation_or_inputs(self):
        low, high = [-2, 0, -2], [6, 10, 2]
        cells = flat_cells(low, high)
        start, target = [.5, 2.5, .5], [6.5, 2.5, .5]
        before = deepcopy((cells, start, target, low, high))
        self.assertIsNotNone(plan(cells, start, target, low, high))
        self.assertEqual((cells, start, target, low, high), before)


if __name__ == '__main__':
    unittest.main()
