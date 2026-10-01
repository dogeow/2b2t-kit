"""Dispatch scope/client tests; all family game operations are spies."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from material_jobs import pipeline_dispatch as dispatch
from material_jobs.protocol import JobBlocked, JobPaused
from material_jobs_backend import Backend


class PipelineDispatchTests(unittest.TestCase):
    def setUp(self):
        self.client = SimpleNamespace()
        self.backend = SimpleNamespace(client=self.client, profile={'schema': 1})
        self.backend.ensure_client = Mock(return_value=self.client)
        self.checkpoint = Mock()
        self.out = Path('/unused/offline-order')

    def call(self, item, scope, target=64):
        return dispatch.run(self.backend, item, target, self.out, self.checkpoint, scope)

    def test_each_family_receives_the_same_owned_client_and_backend(self):
        cases = (
            ('minecraft:raw_iron_block', 'approved_depot_total', dispatch.mineral_pipeline, 'mineral_backend'),
            ('minecraft:dark_oak_planks', 'approved_depot_total', dispatch.wood_pipeline, 'wood_backend'),
            ('minecraft:cyan_terracotta', 'absolute_backpack', dispatch.colored_pipeline, 'colored_backend'),
            ('minecraft:dripstone_block', 'absolute_backpack', dispatch.natural_block_pipeline, 'natural_backend'),
            ('minecraft:mud_bricks', 'absolute_backpack_total', dispatch.mud_pipeline, 'mud_backend'),
            ('minecraft:stripped_cherry_wood', 'approved_depot_total', dispatch.stripped_wood_pipeline, 'stripped_wood_backend'),
        )
        for item, scope, module, binding in cases:
            with self.subTest(item=item), patch.object(module, 'run') as family:
                receipt = {'phase': 'waiting', 'code': 'WAIT_SOURCE', 'item': item, 'pending': {'id': 'original'}}
                family.return_value = receipt
                result = self.call(item, scope)
                self.assertIs(receipt, result)
                self.assertIs(self.backend, self.client.material_backend)
                self.assertIs(self.backend, getattr(self.client, binding))
                family.assert_called_once_with(self.client, self.backend.profile, item, 64,
                                               self.out, self.checkpoint)
        self.assertEqual(6, self.backend.ensure_client.call_count)

    def test_family_item_sets_are_the_actual_module_contracts(self):
        self.assertEqual(dispatch.mineral_pipeline.ITEMS, dispatch.FAMILIES[0][1])
        self.assertEqual(set(dispatch.wood_pipeline.LOGS) | set(dispatch.wood_pipeline.PLANKS),
                         set(dispatch.FAMILIES[1][1]))
        self.assertEqual(dispatch.colored_pipeline.OUTPUTS, dispatch.FAMILIES[2][1])
        self.assertEqual(dispatch.natural_block_pipeline.OUTPUTS, dispatch.FAMILIES[3][1])
        self.assertEqual(dispatch.natural_block_pipeline.TARGET_SCOPE, dispatch.FAMILIES[3][2])
        self.assertEqual(dispatch.mud_pipeline.ITEMS, dispatch.FAMILIES[4][1])
        self.assertEqual(dispatch.mud_pipeline.TARGET_SCOPE, dispatch.FAMILIES[4][2])
        self.assertEqual(dispatch.mud_pipeline.MAX_TARGET_COUNT, dispatch.FAMILIES[4][4])
        self.assertEqual(dispatch.stripped_wood_pipeline.OUTPUTS, dispatch.FAMILIES[5][1])
        self.assertEqual(dispatch.stripped_wood_pipeline.TARGET_SCOPE, dispatch.FAMILIES[5][2])
        self.assertEqual(dispatch.stripped_wood_pipeline.MAX_TARGET_COUNT, dispatch.FAMILIES[5][4])
        for index, family in enumerate(dispatch.FAMILIES):
            self.assertFalse(set(family[1]) & set().union(*(set(r[1]) for r in dispatch.FAMILIES[index+1:])))

    def test_unsupported_output_rejects_before_controller_or_checkpoint(self):
        for item in ('minecraft:raw_iron', 'minecraft:air', 'minecraft:diamond_block', ''):
            with self.subTest(item=item), self.assertRaises(ValueError):
                self.call(item, 'approved_depot_total')
        self.backend.ensure_client.assert_not_called(); self.checkpoint.assert_not_called()

    def test_wrong_scope_cannot_start_any_family(self):
        cases = [('minecraft:tuff', 'absolute_backpack'),
                 ('minecraft:oak_planks', 'absolute_backpack'),
                 ('minecraft:black_concrete', 'approved_depot_total'),
                 ('minecraft:mushroom_stem', 'approved_depot_total'),
                 ('minecraft:mud_bricks', 'absolute_backpack'),
                 ('minecraft:stripped_cherry_wood', 'absolute_backpack'),
                 ('minecraft:stone', None)]
        with (patch.object(dispatch.mineral_pipeline, 'run') as mineral,
              patch.object(dispatch.wood_pipeline, 'run') as wood,
              patch.object(dispatch.colored_pipeline, 'run') as colored,
              patch.object(dispatch.natural_block_pipeline, 'run') as natural,
              patch.object(dispatch.mud_pipeline, 'run') as mud,
              patch.object(dispatch.stripped_wood_pipeline, 'run') as stripped):
            for item, scope in cases:
                with self.subTest(item=item), self.assertRaises(ValueError):
                    self.call(item, scope)
            mineral.assert_not_called(); wood.assert_not_called(); colored.assert_not_called()
            natural.assert_not_called(); mud.assert_not_called(); stripped.assert_not_called()
        self.backend.ensure_client.assert_not_called(); self.checkpoint.assert_not_called()

    def test_missing_scope_is_not_implicitly_inferred(self):
        with self.assertRaises(TypeError):
            dispatch.run(self.backend, 'minecraft:stone', 64, self.out, self.checkpoint)
        self.backend.ensure_client.assert_not_called()

    def test_invalid_or_family_oversize_counts_reject_before_controller(self):
        cases = [('minecraft:stone', 'approved_depot_total', 1_000_001),
                 ('minecraft:oak_log', 'approved_depot_total', 100_001),
                 ('minecraft:red_concrete', 'absolute_backpack', 2305),
                 ('minecraft:dripstone_block', 'absolute_backpack', 2305),
                 ('minecraft:mud', 'absolute_backpack_total', 2305),
                 ('minecraft:stripped_cherry_wood', 'approved_depot_total', 100001),
                 ('minecraft:stone', 'approved_depot_total', True),
                 ('minecraft:stone', 'approved_depot_total', 0)]
        for item, scope, target in cases:
            with self.subTest(item=item, target=target), self.assertRaises(ValueError):
                self.call(item, scope, target)
        self.backend.ensure_client.assert_not_called(); self.checkpoint.assert_not_called()

    def test_every_registered_output_can_be_described_without_controller(self):
        for module, items, scope, _, maximum in dispatch.FAMILIES:
            for item in items:
                with self.subTest(item=item):
                    result = dispatch.describe(item)
                    self.assertEqual({'item': item,
                                      'family': module.__name__.rsplit('.', 1)[-1].removesuffix('_pipeline'),
                                      'target_scope': scope, 'max_target_count': maximum}, result)
        self.backend.ensure_client.assert_not_called(); self.checkpoint.assert_not_called()

    def test_describe_rejects_unsupported_or_invalid_item_without_client(self):
        for item in ('minecraft:air', 'minecraft:raw_iron', None, [], 123):
            with self.subTest(item=item), self.assertRaises(ValueError):
                dispatch.describe(item)
        self.backend.ensure_client.assert_not_called(); self.checkpoint.assert_not_called()

    def test_describe_returns_detached_metadata_not_mutable_registry(self):
        result = dispatch.describe('minecraft:mud_bricks')
        result['target_scope'] = 'approved_depot_total'
        self.assertEqual('absolute_backpack_total', dispatch.describe('minecraft:mud_bricks')['target_scope'])

    def test_foreign_client_return_is_rejected_before_binding_or_family_action(self):
        self.backend.ensure_client.return_value = SimpleNamespace()
        with patch.object(dispatch.mineral_pipeline, 'run') as family:
            with self.assertRaises(JobBlocked):
                self.call('minecraft:stone', 'approved_depot_total')
            family.assert_not_called()
        self.assertFalse(hasattr(self.client, 'material_backend'))

    def test_player_checkpoint_pause_precedes_acquiring_controller(self):
        self.checkpoint.side_effect = JobPaused('manual takeover')
        with self.assertRaises(JobPaused):
            self.call('minecraft:stone', 'approved_depot_total')
        self.backend.ensure_client.assert_not_called()

    def test_family_exception_is_not_rewritten_as_a_success(self):
        with patch.object(dispatch.wood_pipeline, 'run', side_effect=JobPaused('original pending')):
            with self.assertRaisesRegex(JobPaused, 'original pending'):
                self.call('minecraft:spruce_planks', 'approved_depot_total')

    def test_existing_backend_public_hook_passes_explicit_scope_and_own_checkpoint(self):
        backend = Backend.__new__(Backend); backend.checkpoint = self.checkpoint
        receipt = {'phase': 'waiting', 'code': 'WAIT_RECONCILE'}
        with patch.object(dispatch, 'run', return_value=receipt) as route:
            actual = backend.run_pipeline('minecraft:green_terracotta', 128, self.out,
                                          target_scope='absolute_backpack')
            self.assertIs(receipt, actual)
            route.assert_called_once_with(backend, 'minecraft:green_terracotta', 128,
                                          self.out, self.checkpoint, 'absolute_backpack')


if __name__ == '__main__':
    unittest.main()
