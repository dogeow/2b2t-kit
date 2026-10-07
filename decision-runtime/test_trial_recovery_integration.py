import tempfile
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from singleplayer_trial import TrialSkills, TrialWorld, short_term_goal
from singleplayer_trial_capabilities import capability_scene
from test_singleplayer_trial import registry, state
import test_singleplayer_trial as trial_tests
from test_trial_surface_recovery import Skills, one_step
from test_singleplayer_experience import state as experience_state, receipt
from singleplayer_experience import TrialExperienceStore
from singleplayer_trial_bridge import Paused


class RecoveryIntegrationTests(unittest.TestCase):
    def test_outer_wait_reason_survives_later_pause_status_without_repeated_journal_spam(self):
        with tempfile.TemporaryDirectory() as directory:
            worker, reg, root = trial_tests.WorkerTests().worker(directory)
            worker.registry = reg
            worker.command = 'pause'
            worker.bridge = SimpleNamespace(halted=True, active='own-scan', last='previous',
                                            revision=4, stop_owned=lambda: None)
            calls = []
            def interrupted():
                calls.append(True)
                if len(calls) == 2:
                    worker.stopping = True
                raise Paused('Owned scan observation interrupted')
            worker.cycle = interrupted
            worker.run(.1)
            events = [json.loads(v) for v in (root/'worker/journal.jsonl').read_text().splitlines()]
            waits = [v for v in events if v['event'] == 'worker_wait']
            self.assertEqual(1, len(waits))
            self.assertEqual('Owned scan observation interrupted', waits[0]['reason'])
            self.assertEqual('own-scan', waits[0]['active_request'])

    def test_confined_supported_player_with_stone_tools_gets_bounded_recovery_macro(self):
        with tempfile.TemporaryDirectory() as directory:
            reg = registry(directory)
            current = state(reg, on_ground=True, inventory=[
                {'item': 'minecraft:stone_pickaxe', 'count': 1},
                {'item': 'minecraft:stone_axe', 'count': 1},
                {'item': 'minecraft:furnace', 'count': 1}])
            bridge = SimpleNamespace(root=Path(directory), world=reg['world_name'],
                                     origin=current['pos'], state=current)
            skill = TrialSkills(bridge, directory)
            observed = Skills(one_step()).scan()
            options = skill.candidates(current, TrialWorld(list(observed.blocks.values()), observed.low, observed.high))
            self.assertIsNone(skill.explore_target)
            self.assertIn('recover_surface_access', options)
            self.assertIn('upward', short_term_goal(current, options))
            scene = capability_scene(options, current)
            row = next(v for v in scene['available'] if v['id'] == 'recover_surface_access')
            self.assertIn('surface remains unverified', row['verify'])
            self.assertNotIn('fly', row['via'])

    def test_recovery_does_not_appear_for_player_without_confirmed_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            reg = registry(directory)
            current = state(reg, on_ground=True)
            bridge = SimpleNamespace(root=Path(directory), world=reg['world_name'],
                                     origin=current['pos'], state=current)
            skill = TrialSkills(bridge, directory)
            observed = Skills(one_step()).scan()
            self.assertNotIn('recover_surface_access', skill.candidates(current,
                TrialWorld(list(observed.blocks.values()), observed.low, observed.high)))

    def test_experience_records_height_progress_without_claiming_surface_or_reusable_skill(self):
        with tempfile.TemporaryDirectory() as directory, TrialExperienceStore(directory) as store:
            before = experience_state(pos=[0, 57, 0])
            after = experience_state(time=2000, pos=[0, 61, 0])
            observed = store.record_attempt('trial-one', 'recover_surface_access', before, after,
                                            receipt(op='walk_path'))
            self.assertEqual('upward_movement_observed', observed['outcome'])
            self.assertFalse(observed['skill_verified'])
            self.assertEqual([], store.reusable_rules(before))
            flat = experience_state(time=3000, pos=[2, 57, 0])
            no_rise = store.record_attempt('trial-one', 'recover_surface_access', before, flat,
                                          receipt('flat', op='walk_path'))
            self.assertEqual('no_verified_effect', no_rise['outcome'])
