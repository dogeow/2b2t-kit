"""Projection pipelines keep their original backend identity and guarded fetch scope."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import material_jobs_backend as native
from material_jobs import MaterialJob
from material_jobs import pipeline_dispatch as dispatch
from material_jobs.protocol import JobBlocked, JobPaused
from projection_material_plan import ProcessingCatalog
from test_mud_pipeline import Client, Backend as MudFixtureBackend, fixture


class BackendPipelineContextTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        jar = self.root / 'recipes.jar'
        fixture(jar)
        self.client = Client({'minecraft:mud': 4, 'minecraft:wheat': 4})
        self.selection = {'key': 'ship', 'min': [20, 64, 20], 'max': [27, 64, 27]}
        self.request = {'schema': 1, 'id': 'pipeline-context', 'mode': 'projection',
                        'targets': {'minecraft:mud_bricks': 16512}, 'projection_key': 'ship',
                        'context': {'server': 'simpcraft.com', 'dimension': 'minecraft:overworld',
                                    'world_session': 'world', 'expected_revision': 1, 'start_pos': [0, 64, 0]},
                        'target_stack_sizes': {'minecraft:mud_bricks': 64}, 'created_at': 1000}
        self.original_request = copy.deepcopy(self.request)
        self.backend = native.Backend.__new__(native.Backend)
        self.backend.request = self.request
        self.backend.root = self.root / 'automation'
        self.backend.out = self.root / 'job'
        self.backend.profile = {'recipe_jar': str(jar), 'depots': [],
                                'protected_regions': [{'min': [0, 50, 0], 'max': [10, 80, 10]}]}
        self.backend.catalog = ProcessingCatalog(jar)
        self.backend.client = self.client
        self.backend.checkpoint = Mock()
        self.original_checkpoint = self.backend.checkpoint
        self.backend.ensure_client = Mock(return_value=self.client)
        self.backend.sequence = 0
        self.backend.busy = False
        self.backend.prepare_travel = Mock()
        self.backend.stage_near_base = Mock()
        self.backend.fetch_packed = Mock(return_value=None)
        self.backend.finished_supply_pass = Mock(side_effect=AssertionError('Finished projection stock is unrelated'))
        self.fresh = patch.object(native, 'read_fresh', side_effect=self.frame)
        self.fresh.start()
        self.addCleanup(self.fresh.stop)
        self.recorded = patch('material_jobs.pipeline_experience.record_outcome')
        self.recorded_mock = self.recorded.start()
        self.addCleanup(self.recorded.stop)

    def frame(self, *args, **kwargs):
        return {**self.client.status(), 'projection_selection': copy.deepcopy(self.selection),
                'control_revision': 1, 'target_stack_sizes': self.request['target_stack_sizes']}

    def pipeline(self, checkpoint=None):
        return self.backend.run_pipeline('minecraft:mud_bricks', 4, self.root / 'pipeline',
                                         target_scope='absolute_backpack_total', checkpoint=checkpoint)

    def assert_restored(self):
        self.assertIs(self.request, self.backend.request)
        self.assertEqual(self.original_request, self.request)
        self.assertIs(self.client, self.backend.client)
        self.assertIs(self.original_checkpoint, self.backend.checkpoint)
        self.assertFalse(hasattr(self.backend, 'resource_pipeline_context'))

    def test_actual_wrapper_uses_explicit_resource_fetch_without_request_mode_mutation(self):
        callback = Mock()
        original_fetch = native.Backend.fetch

        def family(client, profile, item, target, out, checkpoint):
            self.assertIs(self.client, client)
            self.assertIs(self.backend, client.material_backend)
            self.assertIs(self.backend, client.mud_backend)
            self.assertIs(self.request, self.backend.request)
            self.assertEqual('projection', self.backend.request['mode'])
            self.assertEqual('ship', self.backend.resource_pipeline_context['projection_key'])
            result = original_fetch(self.backend, {'minecraft:glass': 3})
            self.assertEqual({'minecraft:glass': 3}, result['missing'])
            checkpoint()
            return {'phase': 'waiting', 'code': 'WAIT_SOURCE'}

        with patch.object(dispatch.mud_pipeline, 'run', side_effect=family):
            result = self.pipeline(checkpoint=callback)
        self.assertEqual('WAIT_SOURCE', result['code'])
        self.backend.finished_supply_pass.assert_not_called()
        self.backend.fetch_packed.assert_called_once_with({'minecraft:glass': 3})
        callback.assert_called()
        self.original_checkpoint.assert_not_called()
        self.assert_restored()

    def test_context_and_checkpoint_restore_after_original_exception(self):
        failure = JobPaused('Manual takeover')

        def family(*args):
            self.assertTrue(self.backend.resource_pipeline_context)
            self.assertIs(self.request, self.backend.request)
            raise failure

        with patch.object(dispatch.mud_pipeline, 'run', side_effect=family):
            with self.assertRaises(JobPaused) as raised:
                self.pipeline()
        self.assertIs(failure, raised.exception)
        self.assertIs(failure, self.recorded_mock.call_args.kwargs['error'])
        self.assert_restored()

    def test_changed_projection_at_entry_refuses_before_owned_client_or_fetch(self):
        self.selection['key'] = 'other'
        with patch.object(dispatch.mud_pipeline, 'run') as family:
            with self.assertRaises(JobBlocked):
                self.pipeline()
        family.assert_not_called()
        self.backend.ensure_client.assert_not_called()
        self.backend.prepare_travel.assert_not_called()
        self.assert_restored()

    def test_changed_key_or_bounds_inside_pipeline_refuses_before_resource_fetch(self):
        for field, value in (('key', 'other'), ('min', [21, 64, 20])):
            with self.subTest(field=field):
                self.selection = {'key': 'ship', 'min': [20, 64, 20], 'max': [27, 64, 27]}

                def family(*args):
                    self.selection[field] = value
                    return self.backend.fetch({'minecraft:glass': 3})

                with patch.object(dispatch.mud_pipeline, 'run', side_effect=family):
                    with self.assertRaises(JobBlocked):
                        self.pipeline()
                self.backend.prepare_travel.assert_not_called()
                self.assert_restored()

    def test_scope_changes_are_checked_even_without_worker_checkpoint(self):
        def family(*args):
            self.selection['key'] = 'other'
            return {'phase': 'done'}

        with patch.object(dispatch.mud_pipeline, 'run', side_effect=family):
            with self.assertRaises(JobBlocked):
                self.pipeline()
        self.assert_restored()

    def test_request_change_in_callback_is_rejected_before_worker_entry(self):
        def change_request():
            self.request['projection_key'] = 'other'

        with patch.object(dispatch.mud_pipeline, 'run') as worker:
            with self.assertRaises(JobBlocked):
                self.pipeline(checkpoint=change_request)
        worker.assert_not_called()
        self.assertIs(self.request, self.backend.request)
        self.assertIs(self.original_checkpoint, self.backend.checkpoint)
        self.assertFalse(hasattr(self.backend, 'resource_pipeline_context'))

    def test_world_change_during_worker_refuses_before_resource_action(self):
        original_frame = self.frame

        def family(*args):
            with patch.object(native, 'read_fresh', side_effect=lambda *a, **kw: {
                    **original_frame(), 'world_session': 'different-world'}):
                return self.backend.fetch({'minecraft:glass': 3})

        with patch.object(dispatch.mud_pipeline, 'run', side_effect=family):
            with self.assertRaises(JobBlocked):
                self.pipeline()
        self.backend.prepare_travel.assert_not_called()
        self.assert_restored()

    def test_nested_resource_pipeline_is_rejected_without_rebinding_identity(self):
        def family(*args):
            return self.pipeline()

        with patch.object(dispatch.mud_pipeline, 'run', side_effect=family) as worker:
            with self.assertRaises(JobBlocked):
                self.pipeline()
        self.assertEqual(1, worker.call_count)
        self.assert_restored()

    def test_actual_mud_worker_accepts_only_the_wrapper_resource_context(self):
        fixture_backend = MudFixtureBackend(self.client, self.backend.profile)
        self.backend.crafting_catalog = fixture_backend.crafting_catalog
        self.backend.craft = fixture_backend.craft
        result = self.pipeline()
        self.assertEqual(('done', 'absolute_backpack_total'), (result['phase'], result['target_scope']))
        self.assertEqual(4, self.client.count('minecraft:mud_bricks'))
        self.assertEqual(0, self.client.count('minecraft:mud'))
        self.assertEqual(0, self.client.count('minecraft:wheat'))
        self.backend.finished_supply_pass.assert_not_called()
        self.assert_restored()
        # Direct projection invocation without its scoped wrapper still refuses.
        result = dispatch.mud_pipeline.run(self.client, self.backend.profile, 'minecraft:mud_bricks', 4,
                                           self.root / 'direct', lambda: None)
        self.assertEqual('WAIT_BACKEND', result['code'])

    def test_item_and_explicit_depot_contracts_do_not_enable_projection_resource_override(self):
        for mode, item, scope, module in (
                ('item', 'minecraft:mud_bricks', 'absolute_backpack_total', dispatch.mud_pipeline),
                ('projection', 'minecraft:raw_iron_block', 'approved_depot_total', dispatch.mineral_pipeline)):
            with self.subTest(mode=mode, scope=scope):
                self.request['mode'] = mode

                def family(*args):
                    self.assertFalse(hasattr(self.backend, 'resource_pipeline_context'))
                    self.assertIs(self.original_checkpoint, self.backend.checkpoint)
                    return {'phase': 'waiting', 'code': 'WAIT_SOURCE'}

                with patch.object(module, 'run', side_effect=family):
                    result = self.backend.run_pipeline(item, 4, self.root / mode, target_scope=scope)
                self.assertEqual('WAIT_SOURCE', result['code'])
        self.request['mode'] = 'projection'
        self.assert_restored()

    def test_native_engine_keeps_original_inflight_when_projection_changes_in_wrapper(self):
        self.backend.observe = lambda: {**self.frame(), 'projection_audit': {
            'placement_key': 'ship', 'loaded_chunks_verified': True,
            'matched': 0, 'total': 4, 'replacement_items': {'minecraft:mud_bricks': 4}}}
        self.backend.finish = Mock()
        job = MaterialJob(self.request, self.backend.out, self.backend)
        self.backend.checkpoint = job.checkpoint
        original_checkpoint = self.backend.checkpoint

        def family(*args):
            self.selection['key'] = 'other'
            return {'phase': 'done'}

        with patch.object(dispatch.mud_pipeline, 'run', side_effect=family) as worker:
            result = job.run()
        self.assertEqual('blocked', result['state'])
        worker.assert_called_once()
        pending = json.loads((job.out / 'inflight.json').read_text())
        self.assertEqual('run_pipeline', pending['operation'])
        self.assertEqual(['minecraft:mud_bricks', 4, 'absolute_backpack_total'], pending['args'][:3])
        self.assertIs(self.request, self.backend.request)
        self.assertEqual(self.original_request, self.request)
        self.assertIs(original_checkpoint, self.backend.checkpoint)
        self.assertFalse(hasattr(self.backend, 'resource_pipeline_context'))


if __name__ == '__main__':
    unittest.main()
