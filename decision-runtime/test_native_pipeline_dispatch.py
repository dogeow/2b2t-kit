"""Native MaterialJob entry dispatches bounded carried targets on one backend."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from material_jobs import MaterialJob
from material_jobs import pipeline_dispatch as dispatch
from material_jobs.protocol import JobPaused
from projection_material_plan import ProcessingCatalog
from test_material_jobs import FakeBackend


class NativePipelineBackend(FakeBackend):
    def __init__(self, catalog, **kwargs):
        super().__init__(catalog, **kwargs)
        self.client = SimpleNamespace()
        self.profile = {'schema': 1}
        self.pipeline_reply = None
        self.pipeline_gain = None
        self.pipeline_error = None
        self.pipeline_targets = []
        self.stack_sizes.update({
            'minecraft:dripstone_block': 64, 'minecraft:mushroom_stem': 64,
            'minecraft:mud_bricks': 64, 'minecraft:raw_iron_block': 64,
            'minecraft:oak_planks': 64, 'minecraft:stripped_cherry_wood': 64})

    def ensure_client(self):
        return self.client

    def run_pipeline(self, item, target, out, *, target_scope, checkpoint):
        self.calls.append(('run_pipeline', item, target, target_scope))
        self.pipeline_targets.append((item, target, Path(out)))
        checkpoint()
        if self.pipeline_error:
            raise self.pipeline_error
        if self.pipeline_gain is None:
            self.held[item] = target
        else:
            self.held[item] += self.pipeline_gain
        return self.pipeline_reply or {'phase': 'done', 'target_scope': target_scope}


class NativePipelineDispatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        jar = self.root / 'recipes.jar'
        with zipfile.ZipFile(jar, 'w') as archive:
            archive.writestr('data/minecraft/recipe/white_concrete_powder.json', json.dumps({
                'type': 'minecraft:crafting_shapeless',
                'ingredients': ['minecraft:sand'] * 4 + ['minecraft:gravel'] * 4 + ['minecraft:white_dye'],
                'result': {'id': 'minecraft:white_concrete_powder', 'count': 8}}))
        self.catalog = ProcessingCatalog(jar)

    def request(self, item, count, *, projection=False):
        return {'schema': 1, 'id': 'native-pipeline',
                'mode': 'projection' if projection else 'item',
                'targets': {item: count}, 'projection_key': 'ship' if projection else None,
                'context': {'server': 'example.test', 'dimension': 'minecraft:overworld',
                            'world_session': 'world', 'expected_revision': 1, 'start_pos': [0, 64, 0]},
                'created_at': 1000}

    def job(self, backend, item, count, *, projection=False, name='job'):
        return MaterialJob(self.request(item, count, projection=projection), self.root / name, backend)

    def test_native_item_dispatches_each_carried_family_with_its_exact_scope(self):
        for item, scope in (('minecraft:white_concrete', 'absolute_backpack'),
                            ('minecraft:dripstone_block', 'absolute_backpack'),
                            ('minecraft:mud_bricks', 'absolute_backpack_total')):
            with self.subTest(item=item):
                backend = NativePipelineBackend(self.catalog)
                result = self.job(backend, item, 16, name=item.split(':')[1]).run()
                self.assertEqual('completed', result['state'])
                calls = [call for call in backend.calls if call[0] == 'run_pipeline']
                self.assertEqual([('run_pipeline', item, 16, scope)], calls)
                self.assertFalse(any(call[0] in ('acquire', 'craft', 'smelt', 'harden') for call in backend.calls))
                self.assertEqual(0, result['ai_calls'])

    def test_projection_uses_current_remaining_counts_and_bounded_actual_backpack_targets(self):
        item = 'minecraft:dripstone_block'
        backend = NativePipelineBackend(self.catalog, held={item: 10}, projection={item: 300})
        # Request totals are deliberately stale: only the current audit is a
        # production source. Existing carried blocks are included exactly once.
        result = self.job(backend, item, 16512, projection=True).run()
        self.assertEqual('completed', result['state'])
        self.assertEqual(300, backend.matched)
        self.assertEqual([138, 128, 34], [target for _, target, _ in backend.pipeline_targets])
        self.assertEqual(0, backend.held[item])
        self.assertEqual(len(backend.pipeline_targets), len({out for _, _, out in backend.pipeline_targets}))

    def test_projection_mineral_and_planks_use_explicit_carried_scope_with_current_targets(self):
        for item in ('minecraft:raw_iron_block','minecraft:oak_planks'):
            with self.subTest(item=item):
                backend=NativePipelineBackend(self.catalog,held={item:10},projection={item:300})
                result=self.job(backend,item,16512,projection=True,name=item.split(':')[1]).run()
                self.assertEqual('completed',result['state'])
                self.assertEqual(300,backend.matched)
                self.assertEqual([138,128,34],[target for _,target,_ in backend.pipeline_targets])
                self.assertTrue(all(call[3]=='absolute_backpack_total'
                                    for call in backend.calls if call[0]=='run_pipeline'))
                self.assertFalse(any(call[0] in ('acquire','craft','smelt') for call in backend.calls))

    def test_projection_carried_receipt_unknown_cannot_be_overridden_by_enough_inventory(self):
        for item in ('minecraft:raw_iron_block','minecraft:oak_planks'):
            with self.subTest(item=item):
                backend=NativePipelineBackend(self.catalog,projection={item:4})
                backend.pipeline_reply={'phase':'waiting','code':'WAIT_RECEIPT','pending':{'kind':'native'}}
                job=self.job(backend,item,4,projection=True,name=item.split(':')[1])
                result=job.run()
                self.assertEqual('blocked',result['state'])
                self.assertTrue((job.out/'inflight.json').exists())
                result=self.job(backend,item,4,projection=True,name=item.split(':')[1]).run()
                self.assertEqual('blocked',result['state'])
                self.assertEqual(1,len(backend.pipeline_targets))

    def test_done_receipt_needs_actual_carried_output_and_keeps_unknown_intent(self):
        backend = NativePipelineBackend(self.catalog)
        backend.pipeline_gain = 0
        job = self.job(backend, 'minecraft:dripstone_block', 4)
        result = job.run()
        self.assertEqual('blocked', result['state'])
        self.assertTrue((job.out / 'inflight.json').is_file())
        self.assertEqual(1, len(backend.pipeline_targets))
        self.assertEqual(0, backend.held['minecraft:dripstone_block'])

    def test_unknown_receipt_cannot_be_overridden_by_finished_inventory_or_replayed(self):
        backend = NativePipelineBackend(self.catalog)
        backend.pipeline_reply = {'phase': 'waiting', 'code': 'WAIT_RECONCILE', 'detail': 'Unconfirmed owned cell'}
        job = self.job(backend, 'minecraft:mud_bricks', 4)
        result = job.run()
        self.assertEqual('blocked', result['state'])
        self.assertTrue((job.out / 'inflight.json').is_file())
        resumed = self.job(backend, 'minecraft:mud_bricks', 4)
        result = resumed.run()
        self.assertEqual('blocked', result['state'])
        self.assertEqual(1, len(backend.pipeline_targets))
        self.assertTrue((job.out / 'inflight.json').is_file())

    def test_pending_or_wrong_scope_receipt_cannot_complete_even_with_enough_stock(self):
        for receipt in ({'phase': 'waiting', 'code': 'WAIT_SOURCE', 'pending': {'kind': 'mine'}},
                        {'phase': 'done', 'target_scope': 'approved_depot_total'}):
            with self.subTest(receipt=receipt):
                backend = NativePipelineBackend(self.catalog)
                backend.pipeline_reply = receipt
                job = self.job(backend, 'minecraft:mushroom_stem', 4, name=str(len(receipt)))
                result = job.run()
                self.assertEqual('blocked', result['state'])
                self.assertTrue((job.out / 'inflight.json').is_file())
                self.assertEqual(1, len(backend.pipeline_targets))

    def test_safe_partial_batches_continue_without_dispatching_raw_requirements(self):
        item = 'minecraft:dripstone_block'
        backend = NativePipelineBackend(self.catalog)
        backend.pipeline_gain = 4
        backend.pipeline_reply = {'phase': 'waiting', 'code': 'SOURCE_BATCH',
                                  'requirements': {'minecraft:unsupported_source': 1}}
        result = self.job(backend, item, 12).run()
        self.assertEqual('completed', result['state'])
        self.assertEqual([12, 12, 12], [target for _, target, _ in backend.pipeline_targets])
        self.assertFalse(any(call[0] == 'acquire' for call in backend.calls))
        self.assertEqual({'minecraft:unsupported_source': 1}, result['pipeline_requirements'])

    def test_missing_source_wait_is_bounded_and_never_claims_completion(self):
        backend = NativePipelineBackend(self.catalog)
        backend.pipeline_gain = 0
        backend.pipeline_reply = {'phase': 'waiting', 'code': 'WAIT_SOURCE', 'requirements': {'minecraft:mud': 4}}
        result = self.job(backend, 'minecraft:mud_bricks', 4).run()
        self.assertEqual('blocked', result['state'])
        self.assertEqual(2, len(backend.pipeline_targets))
        self.assertFalse(any(call[0] == 'acquire' for call in backend.calls))

    def test_pause_during_pipeline_preserves_intent_and_does_not_replay(self):
        backend = NativePipelineBackend(self.catalog)
        backend.pipeline_error = JobPaused('Manual takeover during owned work')
        job = self.job(backend, 'minecraft:dripstone_block', 4)
        result = job.run()
        self.assertEqual('paused', result['state'])
        self.assertTrue((job.out / 'inflight.json').is_file())
        self.assertEqual(1, backend.finish_count)
        backend.pipeline_error = None
        result = self.job(backend, 'minecraft:dripstone_block', 4).run()
        self.assertEqual('blocked', result['state'])
        self.assertEqual(1, len(backend.pipeline_targets))

    def test_standard_item_semantics_do_not_implicitly_create_depot_orders(self):
        for item in ('minecraft:raw_iron_block', 'minecraft:oak_planks', 'minecraft:stripped_cherry_wood'):
            with self.subTest(item=item):
                backend = NativePipelineBackend(self.catalog)
                result = self.job(backend, item, 4, name=item.split(':')[1]).run()
                self.assertEqual('completed', result['state'])
                self.assertEqual([], backend.pipeline_targets)
                self.assertTrue(any(call[0] == 'acquire' for call in backend.calls))
        backend = NativePipelineBackend(self.catalog)
        result = self.job(backend, 'minecraft:raw_iron_block', 3173, name='large-depot').run()
        self.assertEqual('blocked', result['state'])
        self.assertEqual([], backend.calls)

    def test_nonspecialized_material_and_older_backend_keep_generic_path(self):
        for backend, item in ((NativePipelineBackend(self.catalog), 'minecraft:dirt'),
                              (FakeBackend(self.catalog), 'minecraft:white_concrete')):
            with self.subTest(item=item):
                backend.stack_sizes[item] = 64
                result = self.job(backend, item, 4, name=item.split(':')[1]).run()
                self.assertEqual('completed', result['state'])
                self.assertFalse(any(call[0] == 'run_pipeline' for call in backend.calls))
                self.assertTrue(any(call[0] == 'acquire' for call in backend.calls))

    def test_native_entry_reuses_dispatch_owned_client_without_creating_another_backend(self):
        item = 'minecraft:mushroom_stem'
        backend = NativePipelineBackend(self.catalog)
        original = backend.client
        seen = []

        def family(client, profile, output, target, out, checkpoint):
            seen.append(client)
            self.assertIs(original, client)
            self.assertIs(backend, client.material_backend)
            self.assertIs(backend, client.natural_backend)
            self.assertIs(backend.profile, profile)
            checkpoint()
            backend.held[output] = target
            return {'phase': 'done', 'target_scope': 'absolute_backpack'}

        def real_dispatch(output, target, out, *, target_scope, checkpoint):
            return dispatch.run(backend, output, target, out, checkpoint, target_scope)

        backend.run_pipeline = real_dispatch
        with patch.object(dispatch.natural_block_pipeline, 'run', side_effect=family):
            result = self.job(backend, item, 10).run()
        self.assertEqual('completed', result['state'])
        self.assertEqual([original], seen)
        self.assertIs(original, backend.client)


if __name__ == '__main__':
    unittest.main()
