import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import singleplayer_experience as experience


def state(**changes):
    result = {
        'server': 'singleplayer', 'connected': True,
        'world_session': 'world-a', 'world_id': '/game/saves/Trial World One',
        'world_name': 'Trial World One', 'time': 1000,
        'game_version': '26.1.2', 'kit_version': '2026.10.7.2',
        'runtime_version': '1.7.83', 'game_mode': 'survival',
        'difficulty': 'normal', 'dimension': 'minecraft:overworld',
        'health': 20, 'food': 20, 'player_dead': False, 'trial_deaths': 0,
        'pos': [12345, 64, 67890],
        'inventory': [{'item': 'minecraft:oak_log', 'count': 0}],
    }
    result.update(changes)
    return result


def receipt(request_id='request-one', **changes):
    value = {'native': True, 'request_id': request_id, 'id': request_id,
             'world_session': 'world-a', 'phase': 'done', 'op': 'chop'}
    value.update(changes)
    return value


class SingleplayerExperienceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'experience'
        self.store = experience.TrialExperienceStore(self.root)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def record_logs(self, request_id='request-one', **kwargs):
        return self.store.record_attempt('trial-one', 'gather_starting_wood', state(),
            state(time=2000, inventory=[{'item': 'minecraft:oak_log', 'count': 4}]),
            receipt(request_id), **kwargs)

    def test_model_success_or_completion_claim_is_not_evidence(self):
        candidate = {'category': 'gathering', 'lesson': 'verify_inventory_after_gathering', 'confidence': 'high'}
        result = self.store.record_attempt('trial-one', 'gather_starting_wood', state(),
            state(time=2000), receipt(result_macro='confirmed', dragon_defeated=True), candidate)
        self.assertEqual(result['outcome'], 'no_verified_effect')
        self.assertFalse(result['skill_verified'])
        self.assertEqual(self.store.reusable_rules(state()), [])
        proposal = json.loads(self.store.db.execute('SELECT proposal FROM attempts').fetchone()[0])
        self.assertFalse(proposal['supported_by_observation'])
        self.assertEqual(proposal['status'], 'proposal_only')

    def test_three_distinct_native_observations_export_fixed_rule_for_new_world(self):
        for index in range(3):
            self.assertEqual(self.record_logs('request-' + str(index))['outcome'], 'inventory_progress')
        second = state(world_session='world-b', world_id='/game/saves/Trial World Two',
                       world_name='Trial World Two', pos=[-7, 80, 8])
        rules = self.store.reusable_rules(second)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]['rule'], 'verify_inventory_after_gathering')
        self.assertEqual(rules[0]['observed_attempts'], 3)
        self.assertTrue(rules[0]['advisory_only'])
        self.assertFalse(rules[0]['replay_allowed'])
        exported = json.dumps(rules)
        for prohibited in ('world-a', 'world-b', 'request-', '12345', '67890', '/game/saves', 'world_session', 'pos'):
            self.assertNotIn(prohibited, exported)

    def test_repeated_observation_of_one_receipt_does_not_create_three_successes(self):
        for time_ms in (2000, 2100, 2200):
            self.store.record_attempt('trial-one', 'gather_starting_wood', state(),
                state(time=time_ms, inventory=[{'item': 'minecraft:oak_log', 'count': 4}]), receipt())
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 1)
        self.assertEqual(self.store.reusable_rules(state()), [])

    def test_death_before_respawn_is_observed_without_a_completed_receipt(self):
        result = self.store.record_attempt('trial-one', 'explore_nearby', state(),
            state(time=2000, health=0, player_dead=True, trial_deaths=1))
        self.assertEqual(result['outcome'], 'death_observed')
        self.assertEqual(self.store.reusable_rules(state())[0]['rule'], 'death_requires_new_observation')
        # A death already followed by automatic respawn remains visible in the native counter.
        result = self.store.record_attempt('trial-two', 'explore_nearby', state(),
            state(time=3000, health=20, trial_deaths=1))
        self.assertEqual(result['outcome'], 'death_observed')

    def test_explicit_native_stall_and_error_are_diagnostic_rules(self):
        self.store.record_attempt('trial-one', 'explore_nearby', state(), state(time=2000),
            receipt('stuck-request', phase='waiting', code='navigation_stuck'))
        self.store.record_attempt('trial-one', 'craft_stone_tools', state(), state(time=3000),
            receipt('failed-request', phase='error', code='missing_material'))
        self.assertEqual({row['rule'] for row in self.store.reusable_rules(state())},
                         {'rescan_after_stall', 'rescan_before_retry'})

    def test_waiting_timer_alone_cannot_be_failure_or_progress(self):
        result = self.store.record_attempt('trial-one', 'explore_nearby', state(),
            state(time=2000, pos=[12365, 64, 67890]),
            receipt(phase='waiting', detail='time ran out'))
        self.assertEqual(result['outcome'], 'unconfirmed')
        self.assertEqual(self.store.reusable_rules(state()), [])

    def test_scope_order_and_multiplayer_are_rejected_without_recording(self):
        for changed in ({'server': 'example.test'}, {'world_session': 'new-world'},
                        {'world_id': '/game/saves/Other World'}, {'time': 999},
                        {'time': 2_000_000}, {'kit_version': 'new-version'},
                        {'connected': False}):
            with self.subTest(changed=changed):
                result = self.store.record_attempt('trial-one', 'observe', state(),
                    state(**{'time': 2000, **changed}), receipt())
                self.assertEqual(result['status'], 'unconfirmed')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)

    def test_wrong_request_world_or_missing_native_flag_never_adds_positive_evidence(self):
        for change in ({'id': 'different'}, {'world_session': 'different'}, {'native': False}):
            result = self.store.record_attempt('trial-one', 'gather_starting_wood', state(),
                state(time=2000, inventory=[{'item': 'minecraft:oak_log', 'count': 4}]), receipt(**change))
            self.assertEqual(result['outcome'], 'unconfirmed')

    def test_rule_reuse_requires_compatible_versions_mode_difficulty_dimension(self):
        for index in range(3):
            self.record_logs('request-' + str(index))
        for changed in ({'game_version': '26.2'}, {'runtime_version': '1.8'},
                        {'kit_version': '2026.11.1'}, {'game_mode': 'creative'},
                        {'difficulty': 'hard'}, {'dimension': 'minecraft:the_nether'},
                        {'server': 'example.test'}, {'game_version': None}):
            with self.subTest(changed=changed):
                self.assertEqual(self.store.reusable_rules(state(**changed)), [])

    def test_missing_game_version_can_be_recorded_but_not_reused(self):
        before = state(game_version=None)
        self.store.record_attempt('trial-one', 'explore_nearby', before,
            state(time=2000, game_version=None, player_dead=True, health=0, trial_deaths=1))
        self.assertEqual(self.store.reusable_rules(before), [])

    def test_arbitrary_code_coordinates_paths_and_free_form_proposals_are_rejected(self):
        for proposal in ({'lesson': 'run_shell', 'category': 'preparation', 'confidence': 'high'},
                         {'lesson': 'rescan_after_stall', 'category': 'navigation', 'confidence': 'high', 'code': 'os.system(...)'},
                         {'lesson': 'rescan_after_stall', 'category': 'navigation', 'confidence': 'high', 'pos': [1, 2, 3]},
                         {'lesson': 'rescan_after_stall', 'category': 'navigation', 'confidence': 'high', 'note': '/game/saves/secret'},
                         {'lesson': 'rescan_after_stall', 'category': 'combat', 'confidence': 'high'}):
            with self.subTest(proposal=proposal), self.assertRaises(ValueError):
                self.record_logs(proposal=proposal)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)

    def test_model_choice_is_stored_candidate_only_even_when_observation_supports_it(self):
        result = self.record_logs(proposal={'lesson': 'verify_inventory_after_gathering',
            'category': 'gathering', 'confidence': 'medium'})
        self.assertEqual(result['proposal_status'], 'proposal_only')
        self.assertFalse(result['skill_verified'])
        candidate = json.loads(self.store.db.execute('SELECT proposal FROM attempts').fetchone()[0])
        self.assertTrue(candidate['supported_by_observation'])
        self.assertEqual(self.store.reusable_rules(state()), [])

    def test_database_payload_contains_no_world_coordinates_or_request_ids(self):
        self.record_logs()
        rows = self.store.db.execute('SELECT * FROM attempts').fetchall()
        text = json.dumps(rows)
        for secret in ('/game/saves', 'Trial World One', 'world-a', 'request-one', '12345', '67890', 'trial-one'):
            self.assertNotIn(secret, text)

    def test_tool_progress_uses_tool_gain_not_consumed_planks(self):
        before = state(inventory=[{'item': 'minecraft:oak_planks', 'count': 16}])
        after = state(time=2000, inventory=[{'item': 'minecraft:oak_planks', 'count': 10}])
        result = self.store.record_attempt('trial-one', 'craft_wooden_tools', before, after, receipt())
        self.assertEqual(result['outcome'], 'no_verified_effect')
        after['inventory'].append({'item': 'minecraft:wooden_pickaxe', 'count': 1})
        result = self.store.record_attempt('trial-one', 'craft_wooden_tools', before, after, receipt('other'))
        self.assertEqual(result['outcome'], 'tool_progress')

    def test_motion_is_observed_not_declared_goal_completion(self):
        result = self.store.record_attempt('trial-one', 'explore_nearby', state(),
            state(time=2000, pos=[12360, 64, 67890]), receipt())
        self.assertEqual(result['outcome'], 'movement_observed')
        self.assertFalse(result['skill_verified'])

    def test_store_is_bounded_and_optional_writer_does_not_wait_long_on_busy_database(self):
        with patch.object(experience, 'MAX_EVENTS', 2):
            for index in range(4):
                self.record_logs('request-' + str(index))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 2)
        competing = sqlite3.connect(self.root / 'singleplayer-experiences.sqlite3')
        try:
            competing.execute('BEGIN IMMEDIATE')
            with self.assertRaises(sqlite3.OperationalError):
                self.record_logs('busy-request')
        finally:
            competing.rollback()
            competing.close()

    def test_symlink_store_is_rejected_and_schema_only_offers_known_rules(self):
        link = Path(self.temp.name) / 'link'
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            experience.TrialExperienceStore(link)
        criteria = experience.proposal_question()['lesson']['criteria']
        self.assertEqual(set(criteria), set(experience.RULES) | {'no_lesson'})


if __name__ == '__main__':
    unittest.main()
