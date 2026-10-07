import unittest

from singleplayer_trial_bridge import Paused
from survival_world import center
from trial_safety_preparation import prepare_small_shelter
from trial_safety_routing import enter_known_shelter, leave_known_shelter
from test_trial_safety_preparation import Skills, block


class RoutingSkills(Skills):
    def __init__(self):
        super().__init__()
        self.unknown_interaction = False;self.no_toggle = False;self.unknown_walk = False
        self.unconfirmed_result = False;self.scope_after_toggle = False
        prepare_small_shelter(self)
        for height, half in ((1, 'lower'), (2, 'upper')):
            self.rows[(0, height, 1)]['state'] = ('Block{minecraft:oak_door}[facing=north,half=' + half
                + ',hinge=left,open=false,powered=false]')
        self.clear_calls()

    def clear_calls(self):
        self.interactions.clear();self.walks.clear();self.events.clear();self.requests.clear()

    def interact(self, point, **arguments):
        actual = tuple(point)
        lower = list(self.small_shelter['door'])
        if self.no_toggle:self.interactions.append(actual)
        else:
            super().interact(lower, **arguments)
            self.interactions[-1] = actual
        if self.scope_after_toggle:self.state['world_session'] = 'another-session'
        if self.unknown_interaction:
            self.pending_mutations['door'] = {'op': 'interact'}
            raise Paused('Unknown native door interaction')
        return {'phase': 'waiting' if self.unconfirmed_result else 'done',
                'outcome_pending': self.unconfirmed_result}

    def walk(self, route):
        super().walk(route)
        if self.unknown_walk:raise Paused('Unknown native walking outcome')


class SafetyRoutingTests(unittest.TestCase):
    def test_night_entry_uses_real_open_route_then_verified_closed_door(self):
        skills = RoutingSkills();skills.state['pos'] = [.5, 1, 3.5]
        result = enter_known_shelter(skills)
        self.assertEqual(result['pos'], [.5, 1, .5])
        self.assertEqual(len(skills.interactions), 2)
        self.assertEqual(skills.interactions, [(0, 2, 1), (0, 2, 1)])
        self.assertEqual(skills.walks[-1], [(0, 1, 2), (0, 1, 1), (0, 1, 0)])
        self.assertIn('open=false', skills.rows[(0, 1, 1)]['state'])
        self.assertIn('open=false', skills.rows[(0, 2, 1)]['state'])
        self.assertEqual(skills.events[-1][0], 'known_shelter_entered')
        self.assertFalse(skills.events[-1][1]['flight_used'])

    def test_day_leave_reaches_nearest_ground_outside_footprint_and_closes_door(self):
        skills = RoutingSkills()
        result = leave_known_shelter(skills)
        self.assertEqual(result['pos'], [.5, 1, 2.5])
        self.assertEqual(skills.walks[-1], [(0, 1, 1), (0, 1, 2)])
        self.assertEqual(len(skills.interactions), 2)
        self.assertIn('open=false', skills.rows[(0, 1, 1)]['state'])
        self.assertEqual(skills.events[-1][0], 'known_shelter_left')

    def test_already_inside_closed_shelter_needs_no_movement_or_toggle(self):
        skills = RoutingSkills();result = enter_known_shelter(skills)
        self.assertEqual(result['pos'], [.5, 1, .5])
        self.assertEqual(skills.interactions, []);self.assertEqual(skills.walks, [])

    def test_already_outside_closed_shelter_does_not_open_it_again(self):
        skills = RoutingSkills();skills.state['pos'] = [.5, 1, 3.5]
        leave_known_shelter(skills)
        self.assertEqual(skills.interactions, []);self.assertEqual(skills.walks, [])

    def test_open_door_is_not_toggled_closed_before_entry(self):
        skills = RoutingSkills();skills.state['pos'] = [.5, 1, 3.5]
        for height in (1, 2):
            value = skills.rows[(0, height, 1)]
            value['state'] = value['state'].replace('open=false', 'open=true')
        enter_known_shelter(skills)
        self.assertEqual(len(skills.interactions), 1)
        self.assertEqual(skills.state['pos'], [.5, 1, .5])

    def test_other_world_dimension_or_unverified_record_refuses_before_actions(self):
        for field, value in (('world_id', '/tmp/other-trial'), ('dimension', 'minecraft:the_nether'), ('verified', False)):
            with self.subTest(field=field):
                skills = RoutingSkills();skills.small_shelter[field] = value
                with self.assertRaises(Paused):leave_known_shelter(skills)
                self.assertEqual(skills.interactions, []);self.assertEqual(skills.walks, [])

    def test_partial_geometry_and_missing_outside_support_refuse_without_actions(self):
        for target in ((-1, 1, 0), (0, 3, 0), (0, 0, 2)):
            with self.subTest(target=target):
                skills = RoutingSkills();skills.rows.pop(target)
                with self.assertRaises(Paused):leave_known_shelter(skills)
                self.assertEqual(skills.interactions, []);self.assertEqual(skills.walks, [])

    def test_lava_outside_the_door_has_no_route_or_toggle(self):
        skills = RoutingSkills();skills.rows[(0, 1, 2)] = block((0, 1, 2), 'lava', fluid=True)
        with self.assertRaises(Paused):leave_known_shelter(skills)
        self.assertEqual(skills.interactions, []);self.assertEqual(skills.walks, [])

    def test_far_record_outside_current_fresh_scan_is_not_remotely_approached(self):
        skills = RoutingSkills();skills.state['pos'] = [.5, 1, 30.5]
        with self.assertRaises(Paused):enter_known_shelter(skills)
        self.assertEqual(skills.interactions, []);self.assertEqual(skills.walks, [])

    def test_inconsistent_halves_powered_and_wrong_axis_doors_refuse_without_actions(self):
        for old, new in (('open=false', 'open=true'), ('hinge=left', 'hinge=right'),
                         ('powered=false', 'powered=true'), ('facing=north', 'facing=east')):
            with self.subTest(new=new):
                skills = RoutingSkills()
                for height in (1, 2) if 'facing' in old or 'powered' in old else (2,):
                    value = skills.rows[(0, height, 1)]
                    value['state'] = value['state'].replace(old, new)
                with self.assertRaises(Paused):leave_known_shelter(skills)
                self.assertEqual(skills.interactions, []);self.assertEqual(skills.walks, [])

    def test_unknown_toggle_is_not_replayed_by_another_route_call(self):
        skills = RoutingSkills();skills.unknown_interaction = True
        with self.assertRaises(Paused):leave_known_shelter(skills)
        self.assertTrue(skills.halted);self.assertEqual(len(skills.interactions), 1)
        with self.assertRaises(Paused):leave_known_shelter(skills)
        self.assertEqual(len(skills.interactions), 1)

    def test_callback_without_fresh_toggle_confirmation_is_not_replayed(self):
        skills = RoutingSkills();skills.no_toggle = True
        with self.assertRaisesRegex(Paused, 'confirmation'):leave_known_shelter(skills)
        self.assertTrue(skills.halted);self.assertEqual(len(skills.interactions), 1)
        with self.assertRaises(Paused):leave_known_shelter(skills)
        self.assertEqual(len(skills.interactions), 1)

    def test_explicit_unknown_native_reply_never_authorizes_walk_after_opening(self):
        skills = RoutingSkills();skills.unconfirmed_result = True
        with self.assertRaises(Paused):leave_known_shelter(skills)
        self.assertTrue(skills.halted);self.assertEqual(skills.walks, [])

    def test_session_changed_by_interaction_cannot_walk_old_route(self):
        skills = RoutingSkills();skills.scope_after_toggle = True
        with self.assertRaises(Paused):leave_known_shelter(skills)
        self.assertTrue(skills.halted);self.assertEqual(skills.walks, [])

    def test_unknown_walk_arrival_does_not_repeat_waypoints_or_close_door(self):
        skills = RoutingSkills();skills.unknown_walk = True
        with self.assertRaises(Paused):leave_known_shelter(skills)
        self.assertTrue(skills.halted);self.assertEqual(len(skills.walks), 1)
        self.assertEqual(len(skills.interactions), 1)
        with self.assertRaises(Paused):leave_known_shelter(skills)
        self.assertEqual(len(skills.walks), 1);self.assertEqual(len(skills.interactions), 1)

    def test_falling_player_cannot_start_a_shelter_route(self):
        skills = RoutingSkills();skills.state['on_ground'] = False
        with self.assertRaises(Paused):leave_known_shelter(skills)
        self.assertEqual(skills.interactions, []);self.assertEqual(skills.walks, [])


if __name__ == '__main__':unittest.main()
