"""Real caretaker CLI/registry/journal contract used by the native production page; no game IO."""
import contextlib
import fcntl
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from farm_caretaker import Caretaker
from farm_caretaker_cli import main
from test_farm_caretaker import profile, state


class NativeUiContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.game = Path(self.temp.name)
        self.root = self.game / 'config/twob2tkit/automation'
        self.root.mkdir(parents=True)
        self.profile_file = self.game / 'config/twob2tkit/farm-caretaker-profile.json'
        self.profile_file.write_text(json.dumps(profile()))

    def invoke(self, action):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(['--game-dir', str(self.game), '--profile', str(self.profile_file), action])
        return code, json.loads(output.getvalue())

    def test_real_status_registers_same_default_journal_without_observing_or_starting_game(self):
        with patch.object(Caretaker, '_observe', side_effect=AssertionError('Status must not observe the game')):
            code, result = self.invoke('status')
        self.assertEqual(0, code)
        self.assertFalse(result["worker_running"])
        self.assertEqual((False, False, 'NOT_STARTED', None),
                         (result['enabled'], result['paused'], result['reason'], result['pending']))
        self.assertEqual((300, 20, 4, 8), tuple(result['profile'][key] for key in
                                              ('interval_seconds', 'adult_keep', 'potato_reserve', 'cooked_food_reserve')))
        caretaker = Caretaker(self.root, profile())
        registry = json.loads((caretaker.path.parent.parent / 'registry.json').read_text())
        self.assertEqual(str(caretaker.out), registry['directory'])
        self.assertEqual(24, (2 * registry['profile']['potato_fields'][0]['radius'] + 1) ** 2 - 1)

    def test_pause_stop_wire_matches_native_atomic_control_and_never_rewrites_unknown_journal(self):
        self.invoke('status')
        caretaker = Caretaker(self.root, profile())
        original = caretaker.status()
        original['pending'] = {'stage': 'harvest_store', 'directory': 'original-cycle'}
        caretaker.path.write_text(json.dumps(original))
        before = caretaker.path.read_bytes()
        for action in ('pause', 'stop'):
            with patch.object(Caretaker, '_observe', side_effect=AssertionError('Control submission must not observe game')):
                code, result = self.invoke(action)
            self.assertEqual((0, 'submitted', action), (code, result['phase'], result['action']))
            control = json.loads(caretaker.control.read_text())
            self.assertEqual(caretaker.key, control['key'])
            self.assertEqual(action, control['action'])
            self.assertEqual(before, caretaker.path.read_bytes())

    def test_actual_worker_flock_rejects_duplicate_before_any_observation_or_backend_acquisition(self):
        self.invoke('status')
        caretaker = Caretaker(self.root, profile())
        with caretaker.lock_path.open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(Caretaker, '_observe', side_effect=AssertionError('Status must not observe game')):
                probe_code, probe = self.invoke('status')
            self.assertEqual(0, probe_code)
            self.assertTrue(probe['worker_running'])
            with patch.object(Caretaker, '_observe', side_effect=AssertionError('Duplicate must never observe game')):
                code, result = self.invoke('run')
        self.assertEqual((2, 'waiting'), (code, result['phase']))
        self.assertIn('Another local caretaker worker', result['detail'])
        self.assertFalse(json.loads(caretaker.path.read_text())['enabled'])

    def test_explicit_run_cannot_bypass_real_persisted_safety_hold(self):
        self.invoke('status')
        current = state()
        current['time'] = int(time.time() * 1000)
        (self.root / 'status.json').write_text(json.dumps(current))
        (self.root / 'safety-hold.json').write_text(json.dumps({'active': True}))
        with patch('farm_caretaker.NativeStages', side_effect=AssertionError('Safety lock must prevent native backend acquisition')) as backend:
            code, result = self.invoke('run')
        self.assertEqual((2, 'waiting', 'WAIT_CONTROL'), (code, result['phase'], result['code']))
        backend.assert_not_called()
        self.assertTrue(json.loads((self.root / 'safety-hold.json').read_text())['active'])

    def test_explicit_resume_keeps_original_pending_directory_and_cannot_replay(self):
        self.invoke('status')
        caretaker = Caretaker(self.root, profile())
        book = caretaker.status()
        book['pending'] = {'stage': 'surplus', 'directory': 'cycle-000007/surplus'}
        caretaker.path.write_text(json.dumps(book))
        with patch.object(Caretaker, '_observe', side_effect=AssertionError('Unknown pending must reject before observing game')):
            code, result = self.invoke('resume')
        self.assertEqual((2, 'waiting'), (code, result['phase']))
        self.assertIn('original pending cycle cannot be replayed', result['detail'])
        self.assertEqual(book['pending'], json.loads(caretaker.path.read_text())['pending'])


if __name__ == '__main__':
    unittest.main()
