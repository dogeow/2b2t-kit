import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from singleplayer_trial import TrialWorld, TrialWorker, LABELS
from singleplayer_trial_bridge import Paused
from survival_world import cell, center
from trial_safety_preparation import _layout, prepare_small_shelter
from trial_shelter_access import observe_partial_shelter
from trial_surface_recovery import plan_upward
import test_trial_safety_preparation as preparation


class FarSkills(preparation.Skills):
    def __init__(self):
        super().__init__({'dirt': 23, 'oak_door': 1})
        self.rows.update({(x, 0, 0): preparation.block((x, 0, 0)) for x in range(24)})
        self.state['pos'] = [23.5, 1, .5]
        self.small_shelter = {'schema': 1, 'world_id': self.state['world_id'],
            'dimension': self.state['dimension'], **_layout((0, 1, 0)),
            'door_item': 'oak_door', 'verified': False}
        self.rows[(-1, 1, -1)] = preparation.block((-1, 1, -1), 'dirt')
        self.inv['dirt'] -= 1
        self.rejected_routes = set()
        self.original_plan = copy.deepcopy(self.small_shelter)


class ShelterAccessTests(unittest.TestCase):
    def test_partial_outside_local_scan_returns_by_bounded_normal_corridor_before_building(self):
        skills = FarSkills()
        self.assertFalse(skills.scan().known((-1, 1, -1)))
        world = observe_partial_shelter(skills, skills.small_shelter)
        self.assertTrue(world.known((-1, 1, -1)))
        self.assertEqual('dirt', world.name((-1, 1, -1)))
        self.assertEqual(skills.original_plan, skills.small_shelter)
        self.assertTrue(skills.walks)
        self.assertFalse(skills.placements)
        scans = [args for op, args in skills.requests if op == 'scan']
        self.assertEqual(1, len(scans))
        volume = 1
        for low, high in zip(scans[0]['min'], scans[0]['max']): volume *= high - low + 1
        self.assertLessEqual(volume, 30_000)
        self.assertTrue(any(event == 'partial_shelter_return_verified' for event, unused in skills.events))

    def test_complete_saved_plan_can_resume_after_return_without_replacing_owned_wall(self):
        skills = FarSkills()
        result = prepare_small_shelter(skills)
        self.assertTrue(result['verified'])
        self.assertEqual(22, sum(item == 'dirt' for item, unused in skills.placements))
        self.assertNotIn(('dirt', (-1, 1, -1)), skills.placements)
        self.assertEqual(skills.original_plan['layout'], result['layout'])

    def test_partial_scan_changed_scope_and_over_budget_never_walk_or_modify_plan(self):
        for change in ('partial', 'session', 'too_far'):
            with self.subTest(change=change):
                skills = FarSkills()
                if change == 'partial': skills.partial_scan = True
                elif change == 'session':
                    original = skills.request
                    def request(op, **args):
                        result = original(op, **args)
                        result['world_session'] = 'other'
                        return result
                    skills.request = request
                else: skills.state['pos'] = [500.5, 1, .5]
                with self.assertRaises(Paused): observe_partial_shelter(skills, skills.small_shelter)
                self.assertFalse(skills.walks)
                self.assertFalse(skills.placements)
                self.assertEqual(skills.original_plan, skills.small_shelter)

    def test_known_real_changed_block_remains_preserved_instead_of_treated_as_missing_air(self):
        skills = FarSkills()
        skills.rows[(-1, 1, -1)] = preparation.block((-1, 1, -1), 'chest', block_entity=True)
        with self.assertRaisesRegex(Paused, 'unexpected current block'): prepare_small_shelter(skills)
        self.assertFalse(skills.placements)
        self.assertEqual('Block{minecraft:chest}', skills.rows[(-1, 1, -1)]['state'])

    def test_exhausted_partial_shelter_does_not_fall_back_to_roaming_exploration(self):
        with tempfile.TemporaryDirectory() as game:
            worker = TrialWorker(Path(game), 12345)
            skills = FarSkills()
            skills.world = skills.scan()
            skills.exploration = Mock(return_value=((24, 1, 0), [(24, 1, 0)]))
            worker.skills = skills
            worker.bridge = skills.b
            worker.failures['prepare_small_shelter'] = 3
            try:
                result = worker.actionable_candidates({'wait': 'Wait', 'prepare_small_shelter': LABELS['prepare_small_shelter']},
                                                      skills.read(), skills.world)
                self.assertEqual({'wait': 'Wait'}, result)
                skills.exploration.assert_not_called()
            finally:
                worker.pool.shutdown(wait=True)

    def test_actual_pit_pose_needs_normal_centering_then_existing_safe_headroom_plan(self):
        data = json.loads((Path(__file__).parent / 'fixtures/trial_shelter_return_pit_20261007.json').read_text())
        world = TrialWorld(data['blocks'], data['min'], data['max'])
        self.assertIsNone(plan_upward(world, data))
        source = cell(data['pos'])
        route = world.route(world.paths(data['pos']), source)
        self.assertEqual([source], route)
        planned = plan_upward(world, {**data, 'pos': center(source)})
        self.assertIsNotNone(planned)
        self.assertEqual((11, 58, -68), planned['target'])
        self.assertEqual((11, 57, -68), planned['support'])
        self.assertNotIn(planned['support'], planned['needed'])
        self.assertNotIn((12, 56, -68), planned['needed'])

    def test_no_return_graph_below_house_uses_one_bounded_ascent_and_retains_plan(self):
        skills = FarSkills()
        # A complete known pit floor deliberately has no ramp up to the house.
        skills.state['pos'] = [23.75, -3, .5]
        skills.rows[(23, -4, 0)] = preparation.block((23, -4, 0))
        skills.rows.pop((23, 0, 0))
        def recover(actor, **args):
            self.assertEqual(4, args['max_rises'])
            self.assertEqual(8, args['max_mined'])
            self.assertTrue(set(map(tuple, actor.small_shelter['floor'])) <= actor.excluded)
            actor.state['pos'] = [23.5, 0, .5]
            return {'actual_rise': 3, 'phase': 'progress', 'surface_confirmed': False}
        with patch('trial_surface_recovery.recover_upward', side_effect=recover) as used:
            with self.assertRaisesRegex(Paused, 'bounded ascent advanced'):
                observe_partial_shelter(skills, skills.small_shelter)
        self.assertEqual(1, used.call_count)
        self.assertTrue(skills.walks)  # Real normal centering precedes the skill.
        self.assertFalse(skills.placements)
        self.assertEqual(skills.original_plan, skills.small_shelter)


if __name__ == '__main__': unittest.main()
