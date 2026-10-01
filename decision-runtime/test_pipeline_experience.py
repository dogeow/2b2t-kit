import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from experience_recording import close_recorders, record_lesson
from material_jobs.pipeline_experience import record_outcome
from material_jobs.protocol import JobPaused
from material_jobs_backend import Backend


class PipelineExperienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.addCleanup(close_recorders)
        self.root = Path(self.tmp.name)
        self.backend = SimpleNamespace(root=self.root / 'automation')
        self.out = self.root / 'job'

    def record(self, **kw):
        return record_outcome(self.backend, 'minecraft:mud_bricks', 64,
                              'absolute_backpack_total', self.out, **kw)

    def test_reported_done_is_only_a_lesson_and_never_a_verified_skill(self):
        for _ in range(2):
            self.assertEqual('lesson', self.record(result={'phase': 'done'})['status'])
        from experience_recording import MANAGERS
        memory = MANAGERS[str((self.root / 'skill-memory').resolve())]
        self.assertEqual({'skills': {}, 'episodes': 0, 'lessons': 2}, memory.summary())
        self.assertEqual('reported_done', memory.recent_lessons('投影建造')[0]['experience']['outcome'])

    def test_pending_and_scope_are_retained_without_raw_receipt_or_secrets(self):
        self.record(result={'phase': 'waiting', 'code': 'WAIT_RECONCILE',
                            'pending': {'password': 'private'}, 'detail': 'credential-secret'})
        data = (self.out / 'pipeline-experiences.jsonl').read_text()
        event = json.loads(data)
        self.assertTrue(event['pending_present']); self.assertFalse(event['automatic_retry_allowed'])
        self.assertEqual('absolute_backpack_total', event['target_scope'])
        self.assertNotIn('private', data); self.assertNotIn('credential-secret', data)

    def test_takeover_is_interruption_and_original_error_text_is_not_logged(self):
        self.record(error=JobPaused('private manual context'))
        event = json.loads((self.out / 'pipeline-experiences.jsonl').read_text())
        self.assertEqual('interrupted', event['outcome'])
        self.assertEqual('JobPaused', event['error_type']); self.assertNotIn('private', str(event))

    def test_recorder_failure_does_not_raise_or_call_any_controller(self):
        with patch('experience_recording.record_lesson', side_effect=OSError('disk full')):
            self.assertEqual('recording_failed', self.record(result={'phase': 'done'})['status'])
        self.assertFalse(hasattr(self.backend, 'client'))

    def test_imported_lessons_deduplicate_and_never_promote_skills(self):
        event = {'kind': 'operating_lesson', 'topic': 'unknown_receipt',
                 'acceptance': 'diagnostic_only'}
        store = self.root / 'isolated'
        first = record_lesson(event, store); second = record_lesson(event, store)
        self.assertEqual(first['id'], second['id'])
        from experience_recording import MANAGERS
        self.assertEqual(1, MANAGERS[str(store.resolve())].summary()['lessons'])

    def test_backend_hook_keeps_exact_receipt_and_original_exception(self):
        backend = Backend.__new__(Backend); backend.checkpoint = Mock(); backend.root = self.backend.root
        receipt = {'phase': 'waiting', 'code': 'WAIT_SOURCE'}
        with patch('material_jobs.pipeline_dispatch.run', return_value=receipt), \
             patch('material_jobs.pipeline_experience.record_outcome') as recorded:
            actual = backend.run_pipeline('minecraft:mud_bricks', 64, self.out,
                                          target_scope='absolute_backpack_total')
            self.assertIs(receipt, actual); self.assertIs(receipt, recorded.call_args.kwargs['result'])
        failure = JobPaused('exact original')
        with patch('material_jobs.pipeline_dispatch.run', side_effect=failure), \
             patch('material_jobs.pipeline_experience.record_outcome') as recorded:
            with self.assertRaises(JobPaused) as raised:
                backend.run_pipeline('minecraft:mud_bricks', 64, self.out,
                                     target_scope='absolute_backpack_total')
            self.assertIs(failure, raised.exception); self.assertIs(failure, recorded.call_args.kwargs['error'])

    def test_existing_backend_enables_native_learning_and_shared_profile_store(self):
        import material_jobs_backend as module
        backend = Backend.__new__(Backend)
        backend.root = self.backend.root; backend.out = self.out
        backend.profile = {'skill_memory_state': str(self.root / 'existing-observer')}
        backend.request = {'context': {}}; backend.client = None
        backend.sequence = 0; backend.busy = False
        frame = {'server': 'test', 'pos': [0, 140, 0]}
        client = SimpleNamespace()
        with patch.object(module, 'read_fresh', return_value=frame), \
             patch.object(module, 'require_unlocked'), patch.object(module, 'require_scope'), \
             patch.object(module, 'JobClient', return_value=client) as create:
            self.assertIs(client, backend.ensure_client())
            self.assertTrue(create.call_args.kwargs['record_experience'])
            self.assertEqual(self.root / 'existing-observer', create.call_args.kwargs['experience_state'])
            backend.ensure_client(); create.assert_called_once()

    def test_busy_optional_database_has_bounded_wait(self):
        import sqlite3, time
        store = self.root / 'busy'
        record_lesson({'kind': 'setup'}, store); close_recorders()
        lock = sqlite3.connect(store / 'skills.sqlite3')
        try:
            lock.execute('BEGIN IMMEDIATE')
            started = time.monotonic()
            with self.assertRaises(sqlite3.OperationalError):
                record_lesson({'kind': 'new'}, store)
            self.assertLess(time.monotonic() - started, .6)
        finally:
            lock.rollback(); lock.close()

    def test_invalid_contract_is_not_recorded_as_a_game_failure(self):
        backend = Backend.__new__(Backend); backend.checkpoint = Mock()
        with patch('material_jobs.pipeline_experience.record_outcome') as recorded:
            with self.assertRaises(ValueError):
                backend.run_pipeline('minecraft:stone', 64, self.out, target_scope='wrong')
            recorded.assert_not_called()


if __name__ == '__main__':
    unittest.main()
