"""Access recovery receipts tested without connecting to Minecraft."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_jobs.construction_access_journal import AccessJournal, AccessJournalError, journal_path


class AccessJournalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scope = {'server': 'example.test', 'dimension': 'minecraft:overworld',
                      'placement_key': 'ship', 'model_hash': 'abc123', 'world_session': 'world-1'}
        self.plan = {'blocks': [{'pos': [10, 64, 20], 'expected': 'Block{minecraft:white_concrete}',
                               'item': 'minecraft:white_concrete'},
                              {'pos': [10, 65, 20], 'expected': 'Block{minecraft:white_concrete}',
                               'item': 'minecraft:white_concrete'}],
                     'outside': [9.5, 64, 20.5], 'inside': [11.5, 64, 20.5], 'axis': 'x'}
        self.path = journal_path(self.root, self.scope)
        self.journal = AccessJournal(self.path, self.scope, self.plan)

    def observed(self, world='world-1', states=None):
        states = states or ['Block{minecraft:white_concrete}'] * 2
        return {'fresh': True, 'exact': True, 'world_session': world,
                'blocks': [{'pos': block['pos'], 'state': state, 'fluid': False, 'container': False}
                           for block, state in zip(self.plan['blocks'], states)]}

    def validate(self, journal=None, world='world-1'):
        (journal or self.journal).revalidate(world, self.observed(world))

    def proof(self, world='world-1', states=None):
        return {'world_session': world, 'observations': self.observed(world, states),
                'inventory': {'before': {'minecraft:white_concrete': 4},
                              'after': {'minecraft:white_concrete': 2}}}

    def test_scope_mismatch_preserves_original_and_pending(self):
        self.validate()
        self.journal.intent('break', pos=[10, 65, 20])
        original = self.path.read_bytes()
        for key in ('server', 'dimension', 'placement_key', 'model_hash'):
            with self.subTest(key=key), self.assertRaises(AccessJournalError):
                AccessJournal(self.path, {**self.scope, key: 'different'}, self.plan)
            self.assertEqual(original, self.path.read_bytes())

    def test_new_world_revalidates_without_changing_original_operation_scope(self):
        self.validate()
        original = self.journal.intent('break', pos=[10, 65, 20])
        resumed = AccessJournal(self.path, {**self.scope, 'world_session': 'world-2'})
        self.validate(resumed, 'world-2')
        self.assertEqual(original, resumed.pending)
        self.assertEqual(['world-1', 'world-2'], [e['world_session'] for e in resumed.data['epochs']])
        resumed.confirm('break', **self.proof('world-2', ['Block{minecraft:white_concrete}', 'Block{minecraft:air}']))
        self.assertEqual('world-1', resumed.data['operations'][0]['world_session'])
        self.assertEqual('world-2', resumed.data['operations'][0]['evidence']['world_session'])

    def test_disconnect_preserves_pending_and_allows_request_id_receipt(self):
        self.validate()
        pending = self.journal.intent('break', pos=[10, 65, 20])
        resumed = AccessJournal(self.path, self.scope)
        resumed.record_request('request-after-timeout', error='disconnected')
        self.assertEqual(pending['id'], resumed.pending['id'])
        self.assertEqual('request-after-timeout', resumed.pending['request_records'][0]['request_id'])
        self.assertEqual([], resumed.data['operations'])
        with self.assertRaises(AccessJournalError):
            resumed.confirm('break', **self.proof())
        self.validate(resumed)
        with self.assertRaises(AccessJournalError):
            resumed.intent('break', pos=[10, 65, 20])

    def test_abnormal_block_revalidation_is_recorded_and_stops_new_actions(self):
        self.validate()
        self.journal.intent('break')
        original = self.journal.pending
        for state in ('Block{minecraft:stone}', 'Block{minecraft:water}',
                      'Block{minecraft:chest}', 'unknown', None):
            with self.subTest(state=state):
                observations = self.observed('world-2')
                observations['blocks'][0]['state'] = state
                with self.assertRaises(AccessJournalError):
                    self.journal.revalidate('world-2', observations)
                self.assertFalse(self.journal.data['epochs'][-1]['accepted'])
                self.assertEqual(original, self.journal.pending)
                with self.assertRaises(AccessJournalError):
                    self.journal.confirm('break', **self.proof('world-2'))

    def test_freshness_full_coverage_and_hazard_flags_are_mandatory(self):
        variants = []
        for key, value in [('fresh', False), ('exact', False), ('world_session', 'old')]:
            obs = self.observed(); obs[key] = value; variants.append(obs)
        for key, value in [('fluid', True), ('container', True), ('fluid', None)]:
            obs = self.observed(); obs['blocks'][0][key] = value; variants.append(obs)
        obs = self.observed(); obs['blocks'].pop(); variants.append(obs)
        obs = self.observed(); obs['blocks'][1] = obs['blocks'][0]; variants.append(obs)
        for obs in variants:
            with self.subTest(obs=obs), self.assertRaises(AccessJournalError):
                self.journal.revalidate('world-1', obs)
        with self.assertRaises(AccessJournalError):
            self.journal.intent('break')

    def test_confirm_requires_caller_proof_and_correct_pending_kind(self):
        self.validate()
        self.journal.intent('break')
        for proof in ({}, {'world_session': 'world-1'},
                      {'world_session': 'world-1', 'observations': self.observed()},
                      {**self.proof(), 'inventory': {}}):
            with self.subTest(proof=proof), self.assertRaises(AccessJournalError):
                self.journal.confirm('break', **proof)
        with self.assertRaises(AccessJournalError):
            self.journal.confirm('restore', **self.proof())
        self.assertIsNotNone(self.journal.pending)
        self.journal.confirm('break', **self.proof(states=['Block{minecraft:air}'] * 2))
        self.assertIsNone(self.journal.pending)
        self.assertEqual(1, len(self.journal.data['operations']))

    def test_restored_is_terminal_and_never_reopened_on_load(self):
        self.validate()
        self.journal.checkpoint('restored', **self.proof())
        resumed = AccessJournal(self.path, self.scope, self.plan)
        self.assertTrue(resumed.restored)
        self.validate(resumed, 'world-2')
        for action in (lambda: resumed.intent('break'),
                       lambda: resumed.checkpoint('planned'),
                       lambda: resumed.confirm('break', **self.proof('world-2'))):
            with self.assertRaises(AccessJournalError):
                action()
        new = AccessJournal(journal_path(self.root, self.scope, 'transaction-2'), self.scope, self.plan)
        self.assertFalse(new.restored)
        self.assertNotEqual(resumed.data['transaction_id'], new.data['transaction_id'])

    def test_restored_requires_no_pending_and_both_original_states(self):
        self.validate()
        self.journal.intent('restore')
        with self.assertRaises(AccessJournalError):
            self.journal.checkpoint('restored', **self.proof())
        self.journal.confirm('restore', **self.proof())
        with self.assertRaises(AccessJournalError):
            self.journal.checkpoint('restored', **self.proof(states=['Block{minecraft:air}'] * 2))
        self.assertFalse(self.journal.restored)

    def test_each_mutation_preserves_prior_record_in_atomic_backup(self):
        initial = json.loads(self.path.read_text())
        self.validate()
        backup = self.path.with_name('access.json.backups') / '00000000.json'
        self.assertEqual(initial, json.loads(backup.read_text()))
        before = self.journal.data
        self.journal.intent('break')
        self.assertEqual(before, json.loads((backup.parent / '00000001.json').read_text()))

    def test_write_failure_preserves_memory_file_and_pending(self):
        self.validate()
        self.journal.intent('break')
        before = self.journal.data
        with patch('kit_runtime.journal.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.journal.confirm('break', **self.proof())
        self.assertEqual(before, self.journal.data)
        self.assertEqual(before, json.loads(self.path.read_text()))

    def test_stale_handle_cannot_overwrite_another_pending_intent(self):
        other = AccessJournal(self.path, self.scope)
        self.validate()
        self.journal.intent('break')
        before = self.path.read_bytes()
        with self.assertRaises(AccessJournalError):
            other.checkpoint('planned')
        self.assertEqual(before, self.path.read_bytes())

    def test_existing_plan_cannot_be_replaced_and_views_are_detached(self):
        changed = deepcopy(self.plan); changed['blocks'][0]['pos'][0] += 1
        before = self.path.read_bytes()
        with self.assertRaises(AccessJournalError):
            AccessJournal(self.path, self.scope, changed)
        self.assertEqual(before, self.path.read_bytes())
        view = self.journal.data; view['plan']['blocks'].clear()
        self.assertEqual(2, len(self.journal.data['plan']['blocks']))

    def test_path_stable_across_world_sessions_but_scoped_and_safe(self):
        self.assertEqual(self.path, journal_path(self.root, {**self.scope, 'world_session': 'world-2'}))
        for key in ('server', 'dimension', 'placement_key', 'model_hash'):
            self.assertNotEqual(self.path, journal_path(self.root, {**self.scope, key: '../different'}))
        with self.assertRaises(AccessJournalError):
            journal_path(self.root, self.scope, '../escape')

    def test_credentials_are_rejected_before_mutation(self):
        self.validate()
        before = self.path.read_bytes()
        with self.assertRaises(AccessJournalError):
            self.journal.intent('break', request={'authorization': 'secret'})
        self.assertEqual(before, self.path.read_bytes())


if __name__ == '__main__':
    unittest.main()
