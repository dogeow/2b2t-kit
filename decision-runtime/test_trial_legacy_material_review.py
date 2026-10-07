"""A fresh native Start can defend while old material intent remains unknown."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from singleplayer_trial import TrialWorker
from singleplayer_trial_bridge import Paused
import test_singleplayer_trial as fixtures


class LegacyMaterialReviewTests(unittest.TestCase):
    def fixture(self, game, *, old_run='old-run'):
        registry = fixtures.registry(game)
        registry['run_id'] = 'new-run'
        root = Path(game).resolve() / 'config/twob2tkit/singleplayer-trial'
        automation = root.parent / 'automation'
        output = root / 'worker'
        (output / 'bootstrap').mkdir(parents=True)
        automation.mkdir()
        (root / 'registry.json').write_text(json.dumps(registry))
        (root / 'control.json').write_text(json.dumps({'id': 'native-user-start',
            'command': 'start', 'trial_id': registry['trial_id'], 'run_id': registry['run_id']}))
        current = fixtures.state(registry, world_session='new-user-session', chopping=False,
            navigating=False, borer_active=False, printing=False, guard_armed=False, guard_busy=False,
            guard_pve_only=False, safety_hold={'active': False, 'escaping': False}, last_request='trial-original')
        current['trial_identity']['process_alive'] = True
        pending = {'id': 'trial-original', 'op': 'chop', 'run_id': old_run,
            'world_id': registry['world_id'], 'trial_id': registry['trial_id'],
            'world_session': 'old-session', 'dimension': 'minecraft:overworld', 'arguments': {}}
        request = {**pending, 'local_trial': True, 'local_survival': True, 'server': 'singleplayer',
            'site': [9.5, 63.0, -73.67], 'item': 'minecraft:dark_oak_log', 'target_count': 8,
            'tree_limit': 1, 'seconds': 240, 'expected_revision': 17, 'expires_at': 1000}
        checkpoint = {'schema': 1, 'world_id': registry['world_id'], 'world_name': registry['world_name'],
            'trial_id': registry['trial_id'], 'source_run_id': old_run, 'game_version': '26.1.2',
            'stations': {'crafting_table': [2, 64, -70]}, 'owned': {'2,64,-70': 'crafting_table'},
            'unresolved_native': [pending]}
        files = {output / 'checkpoint.json': (json.dumps(checkpoint, indent=2) + '\n').encode(),
            output / 'journal.jsonl': b'{"event":"original_material_request","unchanged":true}\n',
            output / 'bootstrap/status.json': b'{"old_material_metadata":"keep every byte"}\n'}
        for path, content in files.items():
            path.write_bytes(content)
        original = (json.dumps(request, indent=3) + '\n').encode()
        (automation / 'request.json').write_bytes(original)
        dispatched = []
        handled = {'trial-original'}
        def reader(unused):
            current['time'] = int(time.time() * 1000)
            mailbox = json.loads((automation / 'request.json').read_text())
            if mailbox['id'] not in handled:
                handled.add(mailbox['id'])
                dispatched.append(copy.deepcopy(mailbox))
                if mailbox['op'] == 'guard':
                    current.update(guard_armed=True, guard_pve_only=True)
                elif mailbox['op'] == 'trial_respawn':
                    current.update(health=20, food=20, player_dead=False, screen='',
                                   world_session='new-respawn-session', guard_armed=False)
                    current['control_revision'] += 1
                else:
                    raise AssertionError('Legacy isolation dispatched material work: ' + mailbox['op'])
                current.update(id=mailbox['id'], last_request=mailbox['id'], op=mailbox['op'], phase='done')
            return copy.deepcopy(current)
        worker = TrialWorker(game, os.getpid(), reader=reader, model_factory=Mock(), sleeper=lambda _: None)
        self.addCleanup(worker.pool.shutdown, wait=True)
        if worker.experience:
            self.addCleanup(worker.experience.close)
        return worker, current, registry, pending, files, original, dispatched

    def preserved(self, files):
        for path, content in files.items():
            self.assertEqual(content, path.read_bytes(), str(path))

    def test_fresh_start_arms_only_new_guard_and_preserves_old_session_and_full_envelope(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, registry, pending, files, original, dispatched = self.fixture(game)
            worker.control()
            self.preserved(files)  # Even the first control event must use a new journal.
            worker.cycle()
            self.assertEqual(['guard'], [row['op'] for row in dispatched])
            self.assertEqual(registry['run_id'], dispatched[0]['run_id'])
            self.assertEqual('new-user-session', dispatched[0]['world_session'])
            self.assertEqual([pending], worker.legacy_pending)
            archive = worker.output / 'legacy-material-intents/trial-original.request.json'
            self.assertEqual(original, archive.read_bytes())
            worker.skills.observe = Mock(side_effect=AssertionError('No materials scanned'))
            worker.skills.execute = Mock(side_effect=AssertionError('No materials macro'))
            worker.decide = Mock(side_effect=AssertionError('No model call'))
            worker.cycle()
            self.assertEqual('waiting_material_review', worker.phase)
            worker.model_factory.assert_not_called()
            worker.decide.assert_not_called()
            status = json.loads((worker.output / 'status.json').read_text())
            self.assertFalse(status['material_macros_enabled'])
            self.assertEqual(str(worker.legacy_journal), status['journal_path'])
            self.assertEqual('old-session', status['legacy_pending'][0]['world_session'])
            self.assertTrue(worker.legacy_journal.is_file())
            self.preserved(files)

    def test_current_run_unknown_or_live_old_child_never_gains_legacy_permission(self):
        for kind in ('current-run', 'missing-run', 'missing-world', 'other-world', 'live-chop', 'live-navigation', 'resume'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as game:
                worker, current, registry, pending, files, original, dispatched = self.fixture(
                    game, old_run='new-run' if kind == 'current-run' else 'old-run')
                if kind in ('missing-run', 'missing-world', 'other-world'):
                    path = worker.output / 'checkpoint.json'
                    value = json.loads(path.read_text())
                    value['unresolved_native'][0]['run_id' if kind == 'missing-run' else 'world_id'] = (
                        '' if kind.startswith('missing-') else str(Path(game).resolve() / 'saves/Other'))
                    path.write_text(json.dumps(value))
                    files[path] = path.read_bytes()
                    (worker.automation / 'request.json').unlink()
                    # A absent old mailbox does not authorize its replay.
                    worker.reader = lambda _: copy.deepcopy(current)
                if kind == 'resume':
                    path = worker.root / 'control.json'
                    value = json.loads(path.read_text())
                    value['command'] = 'resume'
                    path.write_text(json.dumps(value))
                if kind.startswith('live-'):
                    current['chopping' if kind == 'live-chop' else 'navigating'] = True
                with self.assertRaises(Paused):
                    worker.cycle()
                self.assertEqual([], dispatched)
                self.assertEqual('pause', worker.command)
                self.preserved(files)

    def test_same_canonical_save_is_accepted_without_rewriting_historical_scope(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, registry, pending, files, original, dispatched = self.fixture(game)
            alias = str(Path(registry['world_id']).parent / '../saves/Trial')
            pending['world_id'] = alias
            path = worker.output / 'checkpoint.json'
            value = json.loads(path.read_text())
            value['unresolved_native'][0]['world_id'] = alias
            path.write_text(json.dumps(value))
            files[path] = path.read_bytes()
            mailbox = worker.automation / 'request.json'
            request = json.loads(mailbox.read_text())
            request['world_id'] = alias
            original = json.dumps(request, indent=3).encode()
            mailbox.write_bytes(original)
            worker.cycle()
            self.assertEqual(alias, worker.legacy_pending[0]['world_id'])
            self.assertEqual(registry['world_id'], dispatched[0]['world_id'])
            self.assertEqual(original, (worker.output / 'legacy-material-intents/trial-original.request.json').read_bytes())
            self.preserved(files)

    def test_player_inventory_interface_waits_without_closing_it_or_running_a_model(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, registry, pending, files, original, dispatched = self.fixture(game)
            worker.cycle()
            current['screen'] = 'InventoryScreen'
            worker.cycle()
            self.assertEqual('waiting_interface', worker.phase)
            self.assertEqual('InventoryScreen', current['screen'])
            self.assertEqual(['guard'], [row['op'] for row in dispatched])
            worker.model_factory.assert_not_called()
            self.preserved(files)

    def test_legacy_isolation_refuses_current_unknown_scope_change_and_evidence_change(self):
        for kind in ('current-unknown', 'session', 'checkpoint-change', 'old-confirmation'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as game:
                worker, current, registry, pending, files, original, dispatched = self.fixture(game)
                worker.cycle()
                if kind == 'current-unknown':
                    worker.bridge.pending_mutations['trial-new-unknown'] = {'op': 'slot_click'}
                elif kind == 'session':
                    current['world_session'] = 'foreign-new-session'
                elif kind == 'checkpoint-change':
                    path = worker.output / 'checkpoint.json'
                    path.write_bytes(path.read_bytes() + b' ')
                else:
                    (worker.automation / 'reply-trial-original.json').write_text(json.dumps({
                        **pending, 'phase': 'done', 'outcome_pending': False}))
                with self.assertRaises(Paused):
                    worker.cycle()
                self.assertEqual('pause', worker.command)
                self.assertEqual([pending], worker.legacy_pending)
                self.assertEqual(['guard'], [row['op'] for row in dispatched])
                if kind != 'checkpoint-change':
                    self.preserved(files)

    def test_death_and_acknowledged_respawn_keep_material_isolation_then_rearm_guard(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, registry, pending, files, original, dispatched = self.fixture(game)
            worker.cycle()
            current.update(health=0, player_dead=True, screen='DeathScreen', trial_deaths=1, phase='stopped')
            current['control_revision'] += 1
            with patch('singleplayer_trial.time.monotonic', return_value=100):
                worker.cycle()
            with patch('singleplayer_trial.time.monotonic', return_value=104):
                worker.cycle()
            worker.cycle()
            self.assertEqual(['guard', 'trial_respawn', 'guard'], [row['op'] for row in dispatched])
            self.assertEqual('waiting_material_review', worker.phase)
            self.assertEqual('new-respawn-session', worker.legacy_scope['world_session'])
            self.assertEqual('old-session', worker.legacy_pending[0]['world_session'])
            self.assertEqual([pending], worker.legacy_pending)
            worker.model_factory.assert_not_called()
            self.preserved(files)

    def test_existing_different_full_envelope_archive_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as game:
            worker, current, registry, pending, files, original, dispatched = self.fixture(game)
            archive = worker.output / 'legacy-material-intents/trial-original.request.json'
            archive.parent.mkdir()
            archive.write_bytes(b'different preserved evidence')
            with self.assertRaisesRegex(Paused, 'Different archived legacy envelope'):
                worker.cycle()
            self.assertEqual(b'different preserved evidence', archive.read_bytes())
            self.assertEqual([], dispatched)
            self.preserved(files)

    def test_slow_history_scan_reobserves_the_same_controller_before_guard_admission(self):
        import singleplayer_trial_hot_update as history
        original_scan = history.unresolved_mutations
        with tempfile.TemporaryDirectory() as game:
            worker, current, registry, pending, files, original, dispatched = self.fixture(game)
            clock = [time.time()]
            def delayed_scan(*args, **kwargs):
                rows = original_scan(*args, **kwargs)
                clock[0] += 8  # The first bridge frame is now genuinely older than 3s.
                return rows
            with patch('singleplayer_trial.time.time', side_effect=lambda: clock[0]), \
                 patch('singleplayer_trial_hot_update.unresolved_mutations', side_effect=delayed_scan):
                worker.cycle()
            self.assertEqual('waiting_material_review', worker.phase)
            self.assertEqual(['guard'], [row['op'] for row in dispatched])
            self.assertEqual(int(clock[0] * 1000), worker.bridge.state['time'])
            self.assertEqual([pending], worker.legacy_pending)
            self.preserved(files)

    def test_slow_history_scan_does_not_rebind_a_changed_revision_run_or_session(self):
        import singleplayer_trial_hot_update as history
        original_scan = history.unresolved_mutations
        for changed in ('revision', 'run', 'session'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as game:
                worker, current, registry, pending, files, original, dispatched = self.fixture(game)
                clock = [time.time()]
                def delayed_scan(*args, **kwargs):
                    rows = original_scan(*args, **kwargs)
                    clock[0] += 8
                    if changed == 'revision':
                        current['control_revision'] += 1
                    elif changed == 'run':
                        current['trial_identity']['run_id'] = 'foreign-run'
                    else:
                        current['world_session'] = 'foreign-session'
                    return rows
                with patch('singleplayer_trial.time.time', side_effect=lambda: clock[0]), \
                     patch('singleplayer_trial_hot_update.unresolved_mutations', side_effect=delayed_scan):
                    with self.assertRaises(Paused):
                        worker.cycle()
                self.assertEqual([], dispatched)
                self.preserved(files)


if __name__ == '__main__':
    unittest.main()
