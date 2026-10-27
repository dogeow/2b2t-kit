import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from live_service import process


class LiveServiceTest(unittest.TestCase):
    def test_failed_attempts_count_toward_rate_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for i in range(2):
                (root / str(i)).write_text(json.dumps(dict(kind='live_reflection', state='failed',
                                                         started_at=int(time.time()*1000)-1000)))
            path = root / 'pending'
            path.write_text(json.dumps(dict(kind='live_reflection', state='pending')))
            with patch('live_service.reflect_live') as model:
                self.assertFalse(process(path))
                model.assert_not_called()
            self.assertEqual(json.loads(path.read_text())['state'], 'pending')

    def test_unknown_problem_does_not_call_model_or_retry_game(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'problem'
            path.write_text(json.dumps(dict(state='pending', kind='unhandled_native_failure')))
            with patch('live_service.reflect_live') as model:
                self.assertFalse(process(path))
                model.assert_not_called()
            self.assertEqual(json.loads(path.read_text())['state'], 'needs_codex_fix')
