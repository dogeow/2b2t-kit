"""Fresh physical planning preserves the historical native chop unknown."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import test_singleplayer_trial as trial_fixtures
import test_trial_legacy_material_review as legacy_fixtures
from singleplayer_trial_bridge import Paused
from trial_material_rebaseline import (capture_baseline, recapture_after_respawn,
                                      record_review_refusal, submit_review, validate_review)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def full_inventory():
    rows = [{'slot': slot, 'item': 'minecraft:air', 'count': 0, 'max_stack': 64} for slot in range(36)]
    rows[0].update(item='minecraft:dark_oak_log', count=3)
    rows[1].update(item='minecraft:wooden_sword', count=1, max_stack=1, damage=4, max_damage=59)
    return rows


def clear_inventory_menu():
    return {'id': 0, 'type': 'InventoryMenu', 'cursor': {'item': 'minecraft:air', 'count': 0},
            'slots': [{'slot': slot, 'item': 'minecraft:air', 'count': 0} for slot in range(46)]}


class MaterialRebaselineTests(unittest.TestCase):
    def fixture(self, game):
        values = legacy_fixtures.LegacyMaterialReviewTests.fixture(self, game)
        worker, current, registry, pending, frozen, original, dispatched = values
        worker.cycle()  # Freeze the old envelope and arm only the fresh run's guard.
        current.update(inventory=full_inventory(), menu=clear_inventory_menu(),
                       on_ground=True, under_water=False, flight=False,
                       inventory_cursor_precondition_protocol=1,
                       inventory_isolation={'supported': True, 'active': True})
        now = int(time.time() * 1000)
        current['time'] = now
        worker.bridge.reader = lambda _: copy.deepcopy(current)
        root = worker.output / 'review-evidence'
        root.mkdir()
        archive = worker.output / 'legacy-material-intents/trial-original.request.json'
        frozen[archive] = archive.read_bytes()
        old_request = json.loads(archive.read_text())
        old_scope = {'world_id': registry['world_id'], 'world_session': pending['world_session'],
                     'dimension': pending['dimension']}
        identity = {'registered': True, 'world_id': registry['world_id'],
                    'trial_id': registry['trial_id'], 'run_id': pending['run_id'],
                    'process_alive': True}
        before = {**old_scope, 'time': 900, 'singleplayer_trial_protocol': 1,
                  'game_version': '26.1.2',
                  'server': 'singleplayer', 'connected': True, 'id': pending['id'],
                  'last_request': pending['id'], 'op': 'chop', 'phase': 'running',
                  'control_revision': old_request['expected_revision'] + 1,
                  'trial_identity': identity, 'chopping': True, 'navigating': False,
                  'borer_active': False, 'printing': False,
                  'movement_keys': {'forward': False, 'back': False, 'jump': False, 'sneak': False}}
        pause = {'protocol': 1, 'id': 'trial-api-pause-review', 'command': 'pause',
                 **old_scope, 'expected_revision': before['control_revision']}
        pause_reply = {'protocol': 1, 'id': pause['id'], 'phase': 'done',
                       'trial_identity': copy.deepcopy(identity)}
        stopped_identity = {**identity, 'run_id': '', 'process_alive': False}
        stopped = {**before, 'time': 1100, 'control_revision': 20,
                   'phase': 'stopped', 'chopping': False, 'trial_identity': stopped_identity,
                   'chopper_remaining': 0, 'chopper_platforms': 0}
        before_save = {**stopped, 'time': 1300, 'world_session': 'later-manual-session'}
        after_save = {**before_save, 'time': 1700, 'connected': False,
                      'trial_identity': {**stopped_identity, 'registered': False}}
        quit_reply = {'protocol': 1, 'id': 'trial-api-normal-quit', 'phase': 'done',
                      'trial_identity': copy.deepcopy(after_save['trial_identity'])}
        save_log = ('Saving players\nSaving worlds\n'
                    'ThreadedAnvilChunkStorage (world): All chunks are saved\n'
                    'ThreadedAnvilChunkStorage (DIM-1): All chunks are saved\n'
                    'ThreadedAnvilChunkStorage (DIM1): All chunks are saved\n'
                    'ThreadedAnvilChunkStorage: All dimensions are saved\n')
        backups = {'backup_before': b'previous normally saved world archive',
                   'backup_after': b'current normally saved world archive'}
        artifacts = {}
        for key, content in backups.items():
            path = root / (key + '.zip')
            path.write_bytes(content)
            artifacts[key] = {'path': str(path), 'sha256': sha256(path)}
        backup_diff = {'schema': 1, 'mode': 'read_only_saved_world_diff',
                       'request_id': pending['id'], 'world_id': registry['world_id'],
                       'run_id': pending['run_id'], 'request_world_session': pending['world_session'],
                       'worlds': [{'sha256': artifacts['backup_before']['sha256'], 'last_played_ms': 500},
                                  {'sha256': artifacts['backup_after']['sha256'], 'last_played_ms': 1500}],
                       'checked_blocks': 98_304,
                       'chunks': [{'checked_blocks': 98_304}]}
        docs = {'native_before_pause': before, 'native_pause_request': pause,
                'native_pause_reply': pause_reply, 'native_after_pause': stopped,
                'before_save': before_save, 'after_save': after_save,
                'normal_quit_reply': quit_reply,
                'backup_diff': backup_diff}
        for key, value in docs.items():
            path = root / (key + '.json')
            path.write_text(json.dumps(value) + '\n')
            artifacts[key] = {'path': str(path), 'sha256': sha256(path)}
        path = root / 'save_log.txt'
        path.write_text(save_log)
        normal_exit = {'schema': 1, 'source': 'operator_verified_native_quit_and_launcher_observation',
                       'exit_code': 0, 'exit_type': 'NORMAL', 'old_jvm_pid': 424243,
                       'old_jvm_alive_now': False, 'observed_at': 1800,
                       'save_log': {'path': str(path), 'sha256': sha256(path)}}
        path = root / 'normal_exit.json'
        path.write_text(json.dumps(normal_exit) + '\n')
        artifacts['normal_exit'] = {'path': str(path), 'sha256': sha256(path)}
        report = {'schema': 1, 'kind': 'operator_physical_review',
                  'decision': 'fresh_replan_allowed', 'historical_effects_unresolved': True,
                  'old_request_id': pending['id'], 'world_id': registry['world_id'],
                  'trial_id': registry['trial_id'], 'old_run_id': pending['run_id'],
                  'old_world_session': pending['world_session'], 'old_worker_pid': 424242,
                  'old_jvm_pid': 424243, 'artifacts': artifacts}
        report_path = root / 'operator-review.json'
        report_path.write_text(json.dumps(report) + '\n')
        freeze = {str(path): sha256(path) for path in (*frozen.keys(), archive)}
        request = {'schema': 1, 'id': 'rebaseline-1d0dcb01-4f41-4f99-b61f-86ac8834df0e',
                   'kind': 'fresh_material_replan', 'world_id': registry['world_id'],
                   'trial_id': registry['trial_id'], 'run_id': registry['run_id'],
                   'world_session': current['world_session'], 'dimension': current['dimension'],
                   'expected_revision': current['control_revision'], 'created_at': now,
                   'expires_at': now + 60_000,
                   'report': {'path': str(report_path), 'sha256': sha256(report_path)},
                   'frozen_legacy': freeze}
        return worker, current, registry, pending, frozen, request, report, now, dispatched

    def rewrite_report(self, request, report):
        path = Path(request['report']['path'])
        path.write_text(json.dumps(report) + '\n')
        request['report']['sha256'] = sha256(path)

    def rewrite_artifact(self, request, report, key, change):
        path = Path(report['artifacts'][key]['path'])
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value) + '\n')
        report['artifacts'][key]['sha256'] = sha256(path)
        self.rewrite_report(request, report)

    def preserved(self, frozen):
        legacy_fixtures.LegacyMaterialReviewTests.preserved(self, frozen)

    def verify(self, worker, state, request, now, pid_alive=None):
        return validate_review(worker, request, copy.deepcopy(state),
                               pid_alive=pid_alive or (lambda pid: False), now_ms=now)

    def scan_reply(self, worker, current, **changes):
        def scan(op, **arguments):
            self.assertEqual('scan', op)
            revision = current['control_revision']
            reply = trial_fixtures.native_scan_fields({'id': 'trial-baseline-scan', **arguments}, revision,
                                                      [trial_fixtures.row((2, 0, 0), 'crafting_table')])
            reply = {**copy.deepcopy(current), **reply, **changes}
            worker.bridge.state = reply
            return reply
        worker.bridge.request = Mock(side_effect=scan)

    def physical_baseline(self, worker, current, request, now):
        reviewed = self.verify(worker, current, request, now)
        terrain = trial_fixtures.terrain() + [trial_fixtures.row((2, 1, 0), 'crafting_table')]
        self.scan_reply(worker, current, blocks=terrain)
        baseline = capture_baseline(worker, reviewed, now_ms=now)
        worker.reader = lambda _: copy.deepcopy(current)
        return reviewed, baseline

    def acknowledged_respawn(self, worker, current, *, new_session='acknowledged-respawn-session'):
        current.update(health=20, food=20, player_dead=False, screen='',
                       world_session=new_session, control_revision=current['control_revision'] + 1,
                       id='trial-new-respawn', last_request='trial-new-respawn',
                       op='trial_respawn', phase='done')
        current['inventory'] = [{'slot': slot, 'item': 'minecraft:air', 'count': 0, 'max_stack': 64}
                                for slot in range(36)]
        worker.bridge.session = new_session
        worker.bridge.revision = current['control_revision']
        worker.bridge.last = current['id']
        worker.bridge.state = copy.deepcopy(current)
        receipt = {**copy.deepcopy(current), 'native': True, 'request_id': current['id']}
        worker.bridge.last_receipt = receipt
        return receipt

    def restarted_worker_evidence(self, worker):
        current_mailbox = json.loads((worker.automation / 'request.json').read_text())
        self.assertEqual('guard', current_mailbox['op'])
        self.assertEqual(worker.run_id, current_mailbox['run_id'])
        worker.legacy_evidence = None
        worker.protect_legacy_evidence()
        self.assertEqual(3, len(worker.legacy_evidence))
        archive = worker.output / 'legacy-material-intents/trial-original.request.json'
        self.assertNotIn(archive, worker.legacy_evidence)
        self.assertTrue(archive.is_file())
        return archive

    def test_explicit_review_accepts_fresh_replan_without_claiming_old_completion(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            pid_probe = Mock(return_value=False)
            verified = self.verify(worker, current, request, now, pid_probe)
            self.assertTrue(verified['report']['historical_effects_unresolved'])
            self.assertEqual('fresh_replan_allowed', verified['report']['decision'])
            self.assertEqual([pending], worker.legacy_pending)
            self.assertEqual({424242, 424243}, {call.args[0] for call in pid_probe.call_args_list})
            self.assertEqual(['guard'], [row['op'] for row in dispatched])
            self.preserved(frozen)

    def test_request_requires_exact_current_scope_and_fresh_bounded_ttl(self):
        changes = ({'world_id': '/tmp/other-save'}, {'trial_id': 'foreign-trial'},
                   {'run_id': 'old-run'}, {'world_session': 'old-session'},
                   {'dimension': 'minecraft:the_nether'}, {'expected_revision': 999},
                   {'schema': 2}, {'kind': 'resume_old_chop'}, {'id': '../outside'},
                   {'expected_revision': True})
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            for change in (*changes, {'expires_at': now - 1}, {'created_at': now + 1},
                           {'expires_at': now + 120_001}, {'expires_at': now}):
                with self.subTest(change=change), self.assertRaises(Paused):
                    self.verify(worker, current, {**request, **change}, now)
            self.preserved(frozen)

    def test_both_old_actor_and_old_jvm_must_be_dead_now(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            for active in (424242, 424243):
                with self.subTest(active=active), self.assertRaises(Paused):
                    self.verify(worker, current, request, now, lambda pid: pid == active)
            self.preserved(frozen)

    def test_review_requires_every_frozen_legacy_byte_and_report_hash(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            missing = copy.deepcopy(request)
            missing['frozen_legacy'].pop(next(iter(missing['frozen_legacy'])))
            wrong = copy.deepcopy(request)
            wrong['report']['sha256'] = '0' * 64
            for bad in (missing, wrong):
                with self.assertRaises(Paused): self.verify(worker, current, bad, now)
            path = next(iter(frozen))
            path.write_bytes(path.read_bytes() + b' changed')
            with self.assertRaises(Paused): self.verify(worker, current, request, now)
            self.assertEqual([pending], worker.legacy_pending)

    def test_hashes_do_not_substitute_for_matching_terminal_evidence(self):
        bad_artifacts = {
            'native_before_pause': lambda x: x.update(id='foreign-native-request'),
            'native_pause_request': lambda x: x.update(world_session='foreign-session'),
            'native_pause_reply': lambda x: x.update(phase='running'),
            'native_after_pause': lambda x: x.update(chopping=True),
            'before_save': lambda x: x['trial_identity'].update(process_alive=True),
            'after_save': lambda x: x.update(connected=True),
            'normal_quit_reply': lambda x: x.update(phase='waiting'),
            'normal_exit': lambda x: x.update(old_jvm_alive_now=True),
            'backup_diff': lambda x: x.update(request_id='foreign-native-request')}
        for key, change in bad_artifacts.items():
            with self.subTest(key=key), tempfile.TemporaryDirectory() as game:
                worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
                self.rewrite_artifact(request, report, key, change)
                with self.assertRaises(Paused): self.verify(worker, current, request, now)
                self.preserved(frozen)

    def test_operator_normal_exit_and_world_save_are_required(self):
        for kind in ('nonzero-exit', 'wrong-pid', 'save-incomplete', 'wrong-backup-hash'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as game:
                worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
                if kind in ('nonzero-exit', 'wrong-pid'):
                    key = 'exit_code' if kind == 'nonzero-exit' else 'old_jvm_pid'
                    self.rewrite_artifact(request, report, 'normal_exit', lambda value: value.update({key: 1}))
                elif kind == 'save-incomplete':
                    exit_path = Path(report['artifacts']['normal_exit']['path'])
                    exit_record = json.loads(exit_path.read_text())
                    path = Path(exit_record['save_log']['path'])
                    path.write_text('Saving players\nSaving worlds\n')
                    self.rewrite_artifact(request, report, 'normal_exit',
                        lambda value: value['save_log'].update(sha256=sha256(path)))
                else:
                    self.rewrite_artifact(request, report, 'backup_diff',
                        lambda value: value['worlds'][0].update(sha256='0' * 64))
                with self.assertRaises(Paused): self.verify(worker, current, request, now)
                self.preserved(frozen)

    def test_current_run_unknown_and_live_old_child_never_receive_material_permission(self):
        for kind in ('current-unknown', 'chop', 'navigation', 'borer', 'printer'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as game:
                worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
                if kind == 'current-unknown':
                    worker.bridge.pending_mutations['trial-current-unknown'] = {'op': 'slot_click'}
                else:
                    current[{'chop': 'chopping', 'navigation': 'navigating',
                             'borer': 'borer_active', 'printer': 'printing'}[kind]] = True
                with self.assertRaises(Paused): self.verify(worker, current, request, now)
                self.preserved(frozen)

    def test_fresh_baseline_contains_real_stock_and_complete_scan_without_old_trust(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            verified = self.verify(worker, current, request, now)
            self.scan_reply(worker, current)
            baseline = capture_baseline(worker, verified, now_ms=now)
            self.assertEqual('fresh_kit_physical_baseline', baseline['source'])
            self.assertEqual(request['id'], baseline['request_id'])
            self.assertTrue(baseline['historical_effects_unresolved'])
            self.assertEqual([pending], baseline['legacy_pending'])
            self.assertIn(pending['id'], baseline['forbidden_request_ids'])
            self.assertEqual(current['world_session'], baseline['world_session'])
            self.assertEqual(reg['run_id'], baseline['run_id'])
            self.assertEqual(current['inventory'], baseline['inventory'])
            self.assertFalse(baseline['old_action_replayed'])
            self.assertFalse(baseline['old_action_completed'])
            self.assertEqual(1, worker.bridge.request.call_count)
            self.assertEqual('scan', worker.bridge.request.call_args.args[0])
            self.assertFalse(baseline.get('owned'))
            self.assertFalse(baseline.get('stations'))
            self.assertEqual([pending], worker.legacy_pending)
            self.assertEqual(['guard'], [row['op'] for row in dispatched])
            worker.model_factory.assert_not_called()
            self.preserved(frozen)

    def test_partial_or_changed_revision_scan_cannot_become_a_physical_baseline(self):
        for kind in ('partial', 'revision', 'start-revision'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as game:
                worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
                verified = self.verify(worker, current, request, now)
                key = {'partial': 'scan_cells_read', 'revision': 'control_revision',
                       'start-revision': 'scan_start_revision'}[kind]
                self.scan_reply(worker, current, **{key: -1})
                with self.assertRaises(Paused): capture_baseline(worker, verified, now_ms=now)
                self.preserved(frozen)

    def test_malformed_positive_terrain_never_defines_an_air_baseline(self):
        rows = trial_fixtures.row((2, 0, 0), 'crafting_table')
        malformed = ([rows, copy.deepcopy(rows)], [{**rows, 'pos': [10000, 0, 0]}],
                     [{**rows, 'solid': 1}], [{**rows, 'pos': [2.5, 0, 0]}])
        for blocks in malformed:
            with self.subTest(blocks=blocks), tempfile.TemporaryDirectory() as game:
                worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
                verified = self.verify(worker, current, request, now)
                self.scan_reply(worker, current, blocks=blocks)
                with self.assertRaises(Paused): capture_baseline(worker, verified, now_ms=now)
                self.preserved(frozen)

    def test_operator_cli_writes_one_fresh_request_without_replaying_or_overwriting(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            with patch('decisions.status', return_value=copy.deepcopy(current)), \
                 patch('trial_material_rebaseline.time.time', return_value=now / 1000):
                submitted = submit_review(game, request['report']['path'], expires_seconds=60)
                path = worker.output / 'rebaseline-request.json'
                first_bytes = path.read_bytes()
                self.assertEqual(submitted, json.loads(first_bytes))
                self.verify(worker, current, submitted, now)
                with self.assertRaises(Paused):
                    submit_review(game, request['report']['path'], expires_seconds=60)
            self.assertEqual(first_bytes, path.read_bytes())
            self.assertEqual([pending], worker.legacy_pending)
            self.assertEqual(['guard'], [row['op'] for row in dispatched])
            self.preserved(frozen)

    def test_incomplete_inventory_or_occupied_sdk_cannot_become_baseline(self):
        for kind in ('missing-slot', 'duplicate-slot', 'cursor', 'grid', 'furnace'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as game:
                worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
                verified = self.verify(worker, current, request, now)
                if kind == 'missing-slot': current['inventory'].pop()
                elif kind == 'duplicate-slot': current['inventory'][-1]['slot'] = 0
                elif kind == 'cursor': current['menu']['cursor'].update(item='minecraft:diamond', count=1)
                elif kind == 'grid': current['menu']['slots'][1].update(item='minecraft:dark_oak_log', count=1)
                else:
                    current['menu']['type'] = 'FurnaceMenu'
                    current['menu']['slots'][0].update(item='minecraft:raw_iron', count=1)
                self.scan_reply(worker, current)
                with self.assertRaises(Paused): capture_baseline(worker, verified, now_ms=now)
                self.preserved(frozen)

    def test_fresh_request_does_not_survive_death_manual_takeover_or_changed_session(self):
        for change in ({'world_session': 'respawn-session'}, {'manual_movement': True},
                       {'health': 0, 'player_dead': True, 'screen': 'DeathScreen'},
                       {'control_revision': 999}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as game:
                worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
                verified = self.verify(worker, current, request, now)
                current.update(change)
                self.scan_reply(worker, current)
                with self.assertRaises(Paused): capture_baseline(worker, verified, now_ms=now)
                self.preserved(frozen)

    def test_worker_admission_archives_only_new_request_and_uses_separate_checkpoint(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            reviewed, baseline = self.physical_baseline(worker, current, request, now)
            path = worker.output / 'rebaseline-request.json'
            path.write_text(json.dumps(request, indent=2) + '\n')
            request_bytes = path.read_bytes()
            worker.skills.owned['2,64,-70'] = 'crafting_table'
            worker.skills.excluded.add((4, 64, -70))
            with patch('trial_material_rebaseline.validate_review', return_value=reviewed), \
                 patch('trial_material_rebaseline.capture_baseline', return_value=baseline):
                self.assertTrue(worker.accept_material_rebaseline(copy.deepcopy(current)))
            folder = worker.legacy_journal.parent / 'replanned-material' / baseline['newbaseline_id']
            self.assertEqual(baseline, json.loads((folder / 'baseline.json').read_text()))
            checkpoint = json.loads((folder / 'checkpoint.json').read_text())
            self.assertEqual([], checkpoint['unresolved_native'])
            self.assertEqual([pending], checkpoint['historical_unresolved_native'])
            self.assertEqual(reg['run_id'], checkpoint['source_run_id'])
            self.assertEqual(baseline['newbaseline_id'], checkpoint['material_baseline_id'])
            self.assertFalse(worker.skills.owned)
            self.assertFalse(worker.skills.excluded)
            self.assertEqual([2, 1, 0], worker.skills.stations['crafting_table'])
            self.assertNotEqual([2, 64, -70], worker.skills.stations['crafting_table'])
            self.assertFalse(path.exists())
            archived = worker.legacy_journal.parent / 'rebaseline-requests' / (request['id'] + '.json')
            self.assertEqual(request_bytes, archived.read_bytes())
            self.assertTrue(worker.material_replan_enabled())
            status = json.loads((worker.output / 'status.json').read_text())
            self.assertTrue(status['material_macros_enabled'])
            self.assertTrue(status['historical_effects_unresolved'])
            self.assertFalse(status['historical_replay_enabled'])
            self.assertEqual([pending], status['legacy_pending'])
            self.assertEqual(['guard'], [row['op'] for row in dispatched])
            self.assertNotIn(pending['id'], [row['id'] for row in dispatched])
            self.preserved(frozen)

    def test_cycle_admits_baseline_then_next_cycle_chooses_current_material_macro(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            reviewed, baseline = self.physical_baseline(worker, current, request, now)
            path = worker.output / 'rebaseline-request.json'
            path.write_text(json.dumps(request))
            old_skills = worker.skills
            old_skills.observe = Mock(side_effect=AssertionError('No unreviewed material scan'))
            old_skills.execute = Mock(side_effect=AssertionError('No unreviewed macro'))
            worker.decide = Mock(return_value={'choice': 'upgrade_stone_sword'})
            worker.attempt_record = Mock()
            with patch('trial_material_rebaseline.validate_review', return_value=reviewed), \
                 patch('trial_material_rebaseline.capture_baseline', return_value=baseline):
                worker.cycle()
            self.assertTrue(worker.material_replan_enabled())
            self.assertEqual(0, worker.steps)
            worker.decide.assert_not_called()
            old_skills.observe.assert_not_called()
            old_skills.execute.assert_not_called()
            worker.skills.observe = Mock(return_value=worker.skills.world)
            worker.skills.candidates = Mock(return_value={
                'wait': 'wait', 'upgrade_stone_sword': 'make a current stone sword'})
            worker.skills.execute = Mock(return_value=copy.deepcopy(current))
            worker.cycle()
            worker.decide.assert_called_once()
            worker.skills.execute.assert_called_once_with('upgrade_stone_sword')
            self.assertEqual(1, worker.steps)
            self.assertEqual([pending], worker.legacy_pending)
            self.assertEqual(['guard'], [row['op'] for row in dispatched])
            self.assertNotIn(pending['id'], [row['id'] for row in dispatched])
            self.preserved(frozen)

    def test_new_unknown_after_admission_stops_material_without_replaying_history(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            reviewed, baseline = self.physical_baseline(worker, current, request, now)
            worker.install_material_baseline(baseline)
            worker.skills.observe = Mock(side_effect=AssertionError('Unknown blocks materials'))
            worker.skills.execute = Mock(side_effect=AssertionError('Unknown blocks materials'))
            worker.bridge.pending_mutations['trial-new-click'] = {'op': 'slot_click'}
            with self.assertRaises(Paused): worker.cycle()
            self.assertFalse(worker.material_replan_enabled())
            self.assertEqual('pause', worker.command)
            self.assertEqual([pending], worker.legacy_pending)
            self.assertEqual(['guard'], [row['op'] for row in dispatched])
            worker.skills.observe.assert_not_called()
            worker.skills.execute.assert_not_called()
            self.preserved(frozen)

    def test_changed_admission_request_or_existing_archive_preserves_both_and_disables_materials(self):
        for kind in ('changed-request', 'existing-archive'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as game:
                worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
                reviewed, baseline = self.physical_baseline(worker, current, request, now)
                path = worker.output / 'rebaseline-request.json'
                path.write_text(json.dumps(request))
                archived = worker.legacy_journal.parent / 'rebaseline-requests' / (request['id'] + '.json')
                if kind == 'existing-archive':
                    archived.parent.mkdir(parents=True)
                    archived.write_bytes(b'preserved earlier independent review')
                def capture(*args, **kwargs):
                    if kind == 'changed-request': path.write_bytes(path.read_bytes() + b' ')
                    return baseline
                with patch('trial_material_rebaseline.validate_review', return_value=reviewed), \
                     patch('trial_material_rebaseline.capture_baseline', side_effect=capture):
                    self.assertFalse(worker.accept_material_rebaseline(copy.deepcopy(current)))
                self.assertFalse(worker.material_replan_enabled())
                self.assertTrue(path.is_file())
                if kind == 'existing-archive':
                    self.assertEqual(b'preserved earlier independent review', archived.read_bytes())
                self.assertEqual(['guard'], [row['op'] for row in dispatched])
                self.assertNotIn(pending['id'], [row['id'] for row in dispatched])
                self.preserved(frozen)

    def test_acknowledged_respawn_reobserves_empty_backpack_and_never_carries_old_stock(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            reviewed, baseline = self.physical_baseline(worker, current, request, now)
            before_bytes = json.dumps(baseline, sort_keys=True)
            receipt = self.acknowledged_respawn(worker, current)
            self.scan_reply(worker, current)
            with patch('trial_material_rebaseline.time.time', return_value=now / 1000):
                renewed = recapture_after_respawn(worker, baseline, receipt)
            self.assertEqual('acknowledged_same_run_normal_respawn', renewed['renewal_source'])
            self.assertEqual(baseline['newbaseline_id'], renewed['previous_baseline_id'])
            self.assertNotEqual(baseline['newbaseline_id'], renewed['newbaseline_id'])
            self.assertEqual(current['world_session'], renewed['world_session'])
            self.assertEqual(current['inventory'], renewed['inventory'])
            self.assertTrue(all(row['count'] == 0 for row in renewed['inventory']))
            self.assertEqual(receipt, renewed['native_respawn_receipt'])
            self.assertEqual(baseline['review']['request']['report'], renewed['review']['request']['report'])
            self.assertNotEqual(baseline['request_id'], renewed['request_id'])
            self.assertEqual(before_bytes, json.dumps(baseline, sort_keys=True))
            self.assertEqual([pending], renewed['legacy_pending'])
            self.assertFalse(renewed['old_action_replayed'])
            self.assertFalse(renewed['old_action_completed'])
            self.assertEqual(1, worker.bridge.request.call_count)
            self.assertEqual('scan', worker.bridge.request.call_args.args[0])
            self.assertEqual(['guard'], [row['op'] for row in dispatched])
            self.preserved(frozen)

    def test_respawn_renewal_requires_exact_current_native_receipt_and_no_unknown(self):
        cases = ('non-native', 'not-done', 'wrong-op', 'wrong-request-id', 'wrong-native-id',
                 'foreign-run', 'foreign-session', 'revision', 'current-unknown',
                 'halted', 'active', 'manual-reopen', 'no-receipt')
        for kind in cases:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as game:
                worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
                reviewed, baseline = self.physical_baseline(worker, current, request, now)
                receipt = self.acknowledged_respawn(worker, current)
                if kind == 'non-native': receipt['native'] = False
                elif kind == 'not-done': receipt['phase'] = 'waiting'
                elif kind == 'wrong-op': receipt['op'] = 'guard'
                elif kind == 'wrong-request-id': receipt['request_id'] = 'trial-other-respawn'
                elif kind == 'wrong-native-id': receipt['id'] = 'trial-other-native'
                elif kind == 'foreign-run': receipt['trial_identity']['run_id'] = 'foreign-run'
                elif kind == 'foreign-session': receipt['world_session'] = 'foreign-session'
                elif kind == 'revision': receipt['control_revision'] += 1
                elif kind == 'current-unknown':
                    worker.bridge.pending_mutations['trial-current-unknown'] = {'op': 'mine_block'}
                elif kind == 'halted': worker.bridge.halted = True
                elif kind == 'active': worker.bridge.active = 'trial-still-running'
                elif kind == 'manual-reopen':
                    current['world_session'] = 'manual-reopen-session'
                    worker.bridge.session = current['world_session']
                else: receipt = None
                worker.bridge.request = Mock(side_effect=AssertionError('Rejected renewal cannot scan or mutate'))
                with patch('trial_material_rebaseline.time.time', return_value=now / 1000), \
                     self.assertRaises(Paused):
                    recapture_after_respawn(worker, baseline, receipt)
                worker.bridge.request.assert_not_called()
                self.preserved(frozen)

    def test_acknowledged_respawn_may_keep_world_session_but_still_requires_new_physical_facts(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            reviewed, baseline = self.physical_baseline(worker, current, request, now)
            receipt = self.acknowledged_respawn(worker, current, new_session=current['world_session'])
            self.scan_reply(worker, current)
            with patch('trial_material_rebaseline.time.time', return_value=now / 1000):
                renewed = recapture_after_respawn(worker, baseline, receipt)
            self.assertEqual(baseline['world_session'], renewed['world_session'])
            self.assertNotEqual(baseline['control_revision'], renewed['control_revision'])
            self.assertNotEqual(baseline['newbaseline_id'], renewed['newbaseline_id'])
            self.assertTrue(all(row['count'] == 0 for row in renewed['inventory']))
            self.assertEqual(1, worker.bridge.request.call_count)
            self.assertEqual([pending], renewed['legacy_pending'])
            self.preserved(frozen)

    def test_changed_immutable_report_after_respawn_never_inherits_old_authorization(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            reviewed, baseline = self.physical_baseline(worker, current, request, now)
            receipt = self.acknowledged_respawn(worker, current)
            report_path = Path(request['report']['path'])
            report_path.write_bytes(report_path.read_bytes() + b' ')
            worker.bridge.request = Mock(side_effect=AssertionError('Changed review cannot scan'))
            with patch('trial_material_rebaseline.time.time', return_value=now / 1000), \
                 self.assertRaises(Paused):
                recapture_after_respawn(worker, baseline, receipt)
            worker.bridge.request.assert_not_called()
            self.assertEqual([pending], worker.legacy_pending)
            self.preserved(frozen)

    def test_worker_acknowledged_respawn_installs_new_baseline_and_preserves_both_histories(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            reviewed, baseline = self.physical_baseline(worker, current, request, now)
            worker.install_material_baseline(baseline)
            first_folder = worker.legacy_journal.parent / 'replanned-material' / baseline['newbaseline_id']
            first_baseline_bytes = (first_folder / 'baseline.json').read_bytes()
            worker.seen_death_epoch = 1
            worker.death_seen_at = 90
            current.update(health=0, player_dead=True, screen='DeathScreen', trial_deaths=1,
                           phase='stopped')
            def native(op, **arguments):
                if op == 'trial_respawn':
                    receipt = self.acknowledged_respawn(worker, current)
                    dispatched.append({'id': receipt['id'], 'op': op, 'run_id': reg['run_id']})
                    return copy.deepcopy(current)
                self.assertEqual('scan', op)
                revision = current['control_revision']
                reply = trial_fixtures.native_scan_fields(
                    {'id': 'trial-fresh-respawn-scan', **arguments}, revision, trial_fixtures.terrain())
                current.update(reply, op=op)
                worker.bridge.last = reply['id']
                worker.bridge.state = copy.deepcopy(current)
                worker.bridge.last_receipt = {**copy.deepcopy(current), 'native': True,
                                             'request_id': reply['id']}
                dispatched.append({'id': reply['id'], 'op': op, 'run_id': reg['run_id']})
                return copy.deepcopy(current)
            worker.bridge.request = Mock(side_effect=native)
            with patch('singleplayer_trial.time.monotonic', return_value=104), \
                 patch('trial_material_rebaseline.time.time', return_value=now / 1000):
                worker.death_recovery(copy.deepcopy(current))
            renewed = worker.material_rebaseline
            self.assertIsNotNone(renewed)
            self.assertTrue(worker.material_replan_enabled())
            self.assertNotEqual(baseline['newbaseline_id'], renewed['newbaseline_id'])
            self.assertEqual(baseline['newbaseline_id'], renewed['previous_baseline_id'])
            self.assertEqual(current['world_session'], worker.legacy_scope['world_session'])
            self.assertEqual('old-session', worker.legacy_pending[0]['world_session'])
            self.assertTrue(all(row['count'] == 0 for row in renewed['inventory']))
            self.assertEqual({}, worker.skills.stations)
            self.assertEqual({}, worker.skills.owned)
            self.assertEqual(first_baseline_bytes, (first_folder / 'baseline.json').read_bytes())
            new_folder = worker.legacy_journal.parent / 'replanned-material' / renewed['newbaseline_id']
            self.assertEqual(renewed, json.loads((new_folder / 'baseline.json').read_text()))
            checkpoint = json.loads((new_folder / 'checkpoint.json').read_text())
            self.assertEqual([], checkpoint['unresolved_native'])
            self.assertEqual([pending], checkpoint['historical_unresolved_native'])
            self.assertEqual(['guard', 'trial_respawn', 'scan'], [row['op'] for row in dispatched])
            self.assertNotIn(pending['id'], [row['id'] for row in dispatched])
            worker.model_factory.assert_not_called()
            self.preserved(frozen)

    def test_worker_failed_respawn_rebaseline_keeps_guard_only_and_does_not_inherit_stock(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            reviewed, baseline = self.physical_baseline(worker, current, request, now)
            worker.install_material_baseline(baseline)
            worker.seen_death_epoch = 1
            worker.death_seen_at = 90
            current.update(health=0, player_dead=True, screen='DeathScreen', trial_deaths=1,
                           phase='stopped')
            def respawn(op, **arguments):
                self.assertEqual('trial_respawn', op)
                receipt = self.acknowledged_respawn(worker, current)
                dispatched.append({'id': receipt['id'], 'op': op, 'run_id': reg['run_id']})
                return copy.deepcopy(current)
            worker.bridge.request = Mock(side_effect=respawn)
            with patch('singleplayer_trial.time.monotonic', return_value=104), \
                 patch('trial_material_rebaseline.recapture_after_respawn', side_effect=Paused('Incomplete new scan')):
                worker.death_recovery(copy.deepcopy(current))
            self.assertIsNone(worker.material_rebaseline)
            self.assertFalse(worker.material_replan_enabled())
            self.assertEqual('waiting_material_review', worker.phase)
            self.assertEqual({}, worker.skills.stations)
            self.assertEqual({}, worker.skills.owned)
            self.assertEqual([pending], worker.legacy_pending)
            self.assertEqual(['guard', 'trial_respawn'], [row['op'] for row in dispatched])
            self.assertNotIn(pending['id'], [row['id'] for row in dispatched])
            self.preserved(frozen)

    def test_restart_guard_mailbox_uses_existing_old_archive_in_exact_canonical_frozen_set(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            archive = self.restarted_worker_evidence(worker)
            self.verify(worker, current, request, now)
            self.assertEqual(4, len(worker.legacy_evidence))
            self.assertEqual(sha256(archive), worker.legacy_evidence[archive])
            self.assertEqual(request['frozen_legacy'],
                             {str(path): value for path, value in worker.legacy_evidence.items()})
            self.assertEqual([pending], worker.legacy_pending)
            self.assertEqual(['guard'], [row['op'] for row in dispatched])
            self.assertNotIn(pending['id'], [row['id'] for row in dispatched])
            self.preserved(frozen)

    def test_restart_canonical_set_rejects_missing_root_missing_archive_or_arbitrary_extra(self):
        for kind in ('missing-root', 'missing-archive', 'arbitrary-extra', 'report-invalid'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as game:
                worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
                archive = self.restarted_worker_evidence(worker)
                if kind == 'missing-root':
                    request['frozen_legacy'].pop(str(next(iter(worker.legacy_evidence))))
                elif kind == 'missing-archive': request['frozen_legacy'].pop(str(archive))
                elif kind == 'arbitrary-extra':
                    extra = worker.output / 'unrelated.json'
                    extra.write_bytes(b'other unrelated evidence')
                    request['frozen_legacy'][str(extra)] = sha256(extra)
                else: request['report']['sha256'] = '0' * 64
                with self.assertRaises(Paused): self.verify(worker, current, request, now)
                self.assertEqual(3, len(worker.legacy_evidence))
                self.assertNotIn(archive, worker.legacy_evidence)
                self.preserved(frozen)

    def test_restart_archive_scope_and_hash_are_checked_before_in_memory_freeze_extension(self):
        for kind in ('wrong-scope', 'wrong-hash'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as game:
                worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
                archive = self.restarted_worker_evidence(worker)
                if kind == 'wrong-scope':
                    original = json.loads(archive.read_text())
                    original['world_session'] = 'foreign-historical-session'
                    archive.write_text(json.dumps(original))
                    request['frozen_legacy'][str(archive)] = sha256(archive)
                else: archive.write_bytes(archive.read_bytes() + b' ')
                with self.assertRaises(Paused): self.verify(worker, current, request, now)
                self.assertEqual(3, len(worker.legacy_evidence))
                self.assertNotIn(archive, worker.legacy_evidence)
                self.assertEqual([pending], worker.legacy_pending)
                self.preserved({path: content for path, content in frozen.items() if path != archive})

    def test_refusal_receipt_binds_exact_new_request_and_prevents_repeated_review(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            request['expected_revision'] += 100
            path = worker.output / 'rebaseline-request.json'
            path.write_text(json.dumps(request, indent=2) + '\n')
            content = path.read_bytes()
            with patch('trial_material_rebaseline.validate_review', wraps=validate_review) as verify, \
                 patch('trial_material_rebaseline.capture_baseline') as capture:
                self.assertFalse(worker.accept_material_rebaseline(copy.deepcopy(current)))
                verify.assert_called_once()
                capture.assert_not_called()
            receipt_path = worker.output / 'rebaseline-receipts' / (request['id'] + '.json')
            receipt_bytes = receipt_path.read_bytes()
            receipt = json.loads(receipt_bytes)
            self.assertEqual('rejected', receipt['phase'])
            self.assertEqual('kit_worker_physical_review_refusal', receipt['source'])
            self.assertEqual(hashlib.sha256(content).hexdigest(), receipt['request_sha256'])
            self.assertFalse(receipt['request_admitted'])
            self.assertFalse(receipt['material_macros_executed'])
            self.assertFalse(receipt['old_action_replayed'])
            self.assertTrue(receipt['historical_effects_unresolved'])
            self.assertFalse((worker.automation / ('reply-' + request['id'] + '.json')).exists())
            with patch('trial_material_rebaseline.validate_review') as verify, \
                 patch('trial_material_rebaseline.capture_baseline') as capture:
                self.assertFalse(worker.accept_material_rebaseline(copy.deepcopy(current)))
                verify.assert_not_called()
                capture.assert_not_called()
            same = record_review_refusal(worker, request, content, 'Do not overwrite the first refusal')
            self.assertEqual(receipt, same)
            self.assertEqual(receipt_bytes, receipt_path.read_bytes())
            self.assertEqual(content, path.read_bytes())
            self.assertEqual([pending], worker.legacy_pending)
            self.preserved(frozen)

    def test_cli_reissues_only_exact_terminally_rejected_new_review_and_preserves_all_old_bytes(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            request['expected_revision'] += 100
            path = worker.output / 'rebaseline-request.json'
            path.write_text(json.dumps(request, indent=2) + '\n')
            content = path.read_bytes()
            self.assertFalse(worker.accept_material_rebaseline(copy.deepcopy(current)))
            receipt_path = worker.output / 'rebaseline-receipts' / (request['id'] + '.json')
            receipt_bytes = receipt_path.read_bytes()
            with patch('decisions.status', return_value=copy.deepcopy(current)), \
                 patch('trial_material_rebaseline.time.time', return_value=now / 1000):
                submitted = submit_review(game, request['report']['path'], expires_seconds=60)
            archive = worker.output / 'rejected-rebaseline-requests' / (request['id'] + '.json')
            self.assertEqual(content, archive.read_bytes())
            self.assertEqual(receipt_bytes, receipt_path.read_bytes())
            self.assertEqual(submitted, json.loads(path.read_text()))
            self.assertNotEqual(request['id'], submitted['id'])
            self.assertNotEqual(pending['id'], submitted['id'])
            self.assertEqual(current['control_revision'], submitted['expected_revision'])
            self.assertEqual(now, submitted['created_at'])
            self.assertEqual(now + 60_000, submitted['expires_at'])
            self.verify(worker, current, submitted, now)
            self.assertEqual([pending], worker.legacy_pending)
            self.assertEqual(['guard'], [row['op'] for row in dispatched])
            self.preserved(frozen)

    def test_cli_does_not_replace_unknown_mismatched_or_admitted_review(self):
        kinds = ('no-receipt', 'wrong-hash', 'accepted', 'unknown', 'wrong-id', 'wrong-scope',
                 'admitted', 'executed', 'wrong-source')
        for kind in kinds:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as game:
                worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
                path = worker.output / 'rebaseline-request.json'
                path.write_text(json.dumps(request))
                content = path.read_bytes()
                if kind != 'no-receipt':
                    receipt = record_review_refusal(worker, request, content, 'Verified refusal')
                    if kind == 'wrong-hash': receipt['request_sha256'] = '0' * 64
                    elif kind in ('accepted', 'unknown'): receipt['phase'] = kind
                    elif kind == 'wrong-id': receipt['id'] = 'rebaseline-other-request'
                    elif kind == 'wrong-scope': receipt['world_session'] = 'foreign-session'
                    elif kind == 'admitted': receipt['request_admitted'] = True
                    elif kind == 'executed': receipt['material_macros_executed'] = True
                    else: receipt['source'] = 'model_invented_refusal'
                    receipt_path = worker.output / 'rebaseline-receipts' / (request['id'] + '.json')
                    receipt_path.write_text(json.dumps(receipt))
                    receipt_bytes = receipt_path.read_bytes()
                with patch('decisions.status', return_value=copy.deepcopy(current)), \
                     patch('trial_material_rebaseline.time.time', return_value=now / 1000), \
                     self.assertRaises(Paused):
                    submit_review(game, request['report']['path'], expires_seconds=60)
                self.assertEqual(content, path.read_bytes())
                self.assertFalse((worker.output / 'rejected-rebaseline-requests' / (request['id'] + '.json')).exists())
                if kind != 'no-receipt': self.assertEqual(receipt_bytes, receipt_path.read_bytes())
                self.preserved(frozen)

    def test_cli_never_overwrites_an_existing_rejected_request_archive(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, reg, pending, frozen, request, report, now, dispatched = self.fixture(game)
            path = worker.output / 'rebaseline-request.json'
            path.write_text(json.dumps(request))
            content = path.read_bytes()
            record_review_refusal(worker, request, content, 'Verified refusal')
            archive = worker.output / 'rejected-rebaseline-requests' / (request['id'] + '.json')
            archive.parent.mkdir()
            archive.write_bytes(b'earlier preserved different request')
            with patch('decisions.status', return_value=copy.deepcopy(current)), \
                 self.assertRaises(Paused):
                submit_review(game, request['report']['path'], expires_seconds=60)
            self.assertEqual(content, path.read_bytes())
            self.assertEqual(b'earlier preserved different request', archive.read_bytes())
            self.preserved(frozen)


if __name__ == '__main__':
    unittest.main()
