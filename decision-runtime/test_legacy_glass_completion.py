import copy
import json
from pathlib import Path
import tempfile
import unittest

from legacy_glass_completion import resolved_legacy_glass
from material_jobs.projection_clearance import pending_positions


class LegacyGlassCompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.batch = self.root / 'depot-0123456789ab'
        self.batch.mkdir()
        (self.batch / 'control').mkdir()
        self.scope = dict(server='example.org', dimension='minecraft:overworld', projection_key='original', pos=[1, 62, 3])
        self.plan = dict(targets=[dict(pos=[1, 62, 3], expected='Block{minecraft:glass}'),
                                  dict(pos=[2, 62, 3], expected='Block{minecraft:glass}')],
                         mining_sent=False, stock_before=3, world_session='old-world')
        self.worker = dict(active=False, phase='terminal', safe_return_verified=True,
                           world_session='old-world', task_session='old-task',
                           result=dict(planned=2, verified_glass_placed=1, glass_remaining=2,
                                       other_blocks_unchanged=True, health=20))
        self.audit = dict(audit_schema=2, loaded_chunks_verified=True, loaded_server_chunks_verified=True,
                          server='example.org', dimension='minecraft:overworld', placement_key='original',
                          observed_at=1000, mismatches=[dict(pos=[2, 62, 3])])
        self.event = dict(op='material_job_pause', phase='done', params=dict(release=True, task_session='old-task'),
                          world_session='old-world', health_after=20, inventory_delta={}, time=2)
        self.record = dict(preserve_original_claims=True, inventory_credit=0,
                           pending=dict(legacy_records=[dict(target=[1, 62, 3], claim_not_cleared=False,
                           queue_settled_and_scene_conserved=True, reason='Fresh scoped native Mod glass batch',
                           world_session='old-world', proof=str(self.batch / 'selected-glass-targets.json'))]))
        self.write()

    def write(self):
        for name, value in [('selected-glass-targets.json', self.plan), ('worker.json', self.worker),
                            ('native-glass-result.json', self.audit)]:
            (self.batch / name).write_text(json.dumps(value))
        (self.batch / 'control/events.jsonl').write_text(json.dumps(self.event) + '\n')

    def resolved(self):
        return resolved_legacy_glass(self.record, self.scope, {})

    def test_conserved_terminal_batch_resolves_only_completed_target(self):
        self.assertTrue(self.resolved())
        self.scope['pos'] = self.record['pending']['legacy_records'][0]['target'] = [2, 62, 3]
        self.assertFalse(self.resolved())

    def test_unresolved_and_untyped_flags_stay_protected(self):
        legacy = self.record['pending']['legacy_records'][0]
        for value in [True, None, 0, 'false']:
            with self.subTest(value=value):
                legacy['claim_not_cleared'] = value
                self.assertFalse(self.resolved())

    def test_native_claim_and_mixed_records_stay_protected(self):
        second = copy.deepcopy(self.record['pending']['legacy_records'][0])
        second['native_claim_not_cleared'] = True
        self.record['pending']['legacy_records'].append(second)
        self.assertFalse(self.resolved())

    def test_untyped_native_claim_cannot_be_treated_as_cleared(self):
        legacy = self.record['pending']['legacy_records'][0]
        for value in [True, None, 0, 'true']:
            with self.subTest(value=value):
                legacy['native_claim_not_cleared'] = value
                self.assertFalse(self.resolved())

    def test_nonlegacy_pending_is_never_resolved(self):
        self.record['pending']['request_id'] = 'unconfirmed-native'
        self.assertFalse(self.resolved())

    def test_quantity_conservation_is_required(self):
        self.worker['result']['glass_remaining'] = 1
        self.write()
        self.assertFalse(self.resolved())

    def test_batch_must_be_terminal_and_released_by_its_owner(self):
        for field, value in [('active', True), ('phase', 'running'), ('safe_return_verified', False)]:
            with self.subTest(field=field):
                before = self.worker[field]
                self.worker[field] = value
                self.write()
                self.assertFalse(self.resolved())
                self.worker[field] = before
        self.event['params']['task_session'] = 'another-task'
        self.write()
        self.assertFalse(self.resolved())

    def test_native_release_must_follow_the_audit(self):
        self.event['time'] = .5
        self.write()
        self.assertFalse(self.resolved())

    def test_scope_and_original_world_are_exact(self):
        for field in ['server', 'dimension', 'projection_key']:
            with self.subTest(field=field):
                original = self.scope[field]
                self.scope[field] = 'different'
                self.assertFalse(self.resolved())
                self.scope[field] = original
        self.record['pending']['legacy_records'][0]['world_session'] = 'wrong-world'
        self.assertFalse(self.resolved())

    def test_missing_or_corrupt_proof_is_protected(self):
        (self.batch / 'native-glass-result.json').write_text('{')
        self.assertFalse(self.resolved())
        (self.batch / 'native-glass-result.json').unlink()
        self.assertFalse(self.resolved())

    def test_symlinked_proof_is_not_followed(self):
        path = self.batch / 'worker.json'
        original = path.read_text()
        path.unlink()
        other = self.root / 'other.json'
        other.write_text(original)
        path.symlink_to(other)
        self.assertFalse(self.resolved())

    def test_inventory_credit_and_other_block_changes_cannot_be_hidden(self):
        self.record['inventory_credit'] = 1
        self.assertFalse(self.resolved())
        self.record['inventory_credit'] = 0
        self.worker['result']['other_blocks_unchanged'] = False
        self.write()
        self.assertFalse(self.resolved())

    def test_duplicate_targets_cannot_fake_conservation(self):
        self.plan['targets'][1] = copy.deepcopy(self.plan['targets'][0])
        self.write()
        self.assertFalse(self.resolved())

    def test_integration_preserves_original_files_and_unknown_targets(self):
        directory = self.root / 'projection-terrain-intents'
        directory.mkdir()
        record = {**self.record, 'scope': self.scope}
        path = directory / 'known.json'
        path.write_text(json.dumps(record))
        before = path.read_bytes()
        unknown = dict(scope={**self.scope, 'pos': [9, 62, 3]}, pending=dict(request_id='unknown'))
        (directory / 'unknown.json').write_text(json.dumps(unknown))
        self.assertEqual({(9, 62, 3)}, pending_positions(self.root, 'original', self.scope))
        self.assertEqual(before, path.read_bytes())
        self.worker['active'] = True
        self.write()
        self.assertEqual({(1, 62, 3), (9, 62, 3)}, pending_positions(self.root, 'original', self.scope))


if __name__ == '__main__':
    unittest.main()
