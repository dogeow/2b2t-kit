"""Offline carried-output adapters over the existing mineral/wood fixtures.

No client, RPC, acquisition worker or real profile is created by these tests.
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from material_jobs import mineral_pipeline as mineral
from material_jobs import pipeline_dispatch as dispatch
from material_jobs import wood_pipeline as wood
from material_jobs.protocol import JobBlocked, JobPaused, fingerprint
from test_mineral_pipeline import Backend as MineralBackend, Client as MineralClient, fixture_jar
from test_material_wood_pipeline import Backend as WoodBackend, Client as WoodClient


SCOPE = 'absolute_backpack_total'


def projection_context(backend, item, target):
    request = {'id': 'carried-projection-job', 'mode': 'projection', 'projection_key': 'map-art',
               'targets': {item: 3173},
               'context': {'world_session': backend.client.world}}
    backend.request = request
    backend.resource_pipeline_context = {
        'projection_key': 'map-art', 'world_session': backend.client.world,
        'target_scope': SCOPE, 'item': item, 'target_count': target,
        'request_id': request['id'], 'request_fingerprint': fingerprint(request),
        'selection_bounds': {'min': [20, 64, 20], 'max': [27, 64, 27]}}
    return request


class CarriedDispatchTests(unittest.TestCase):
    def setUp(self):
        self.client = SimpleNamespace()
        self.backend = SimpleNamespace(client=self.client, profile={'schema': 1})
        self.backend.ensure_client = Mock(return_value=self.client)
        self.checkpoint = Mock()
        self.out = Path('/unused/offline-carried')

    def test_description_preserves_depot_contract_and_advertises_only_supported_carried_outputs(self):
        supported = {mineral.IRON, *wood.PLANKS}
        for item in mineral.ITEMS | set(wood.LOGS) | set(wood.PLANKS):
            with self.subTest(item=item):
                described = dispatch.describe(item)
                self.assertEqual('approved_depot_total', described['target_scope'])
                if item in supported:
                    self.assertEqual(SCOPE, described['carried_target_scope'])
                else:
                    self.assertNotIn('carried_target_scope', described)
        self.backend.ensure_client.assert_not_called()
        self.checkpoint.assert_not_called()

    def test_carried_scope_routes_same_owned_client_profile_and_checkpoint_to_adapter(self):
        for item, family, binding in (
                (mineral.IRON, mineral, 'mineral_backend'),
                *((item, wood, 'wood_backend') for item in wood.PLANKS)):
            with self.subTest(item=item), patch.object(family, 'run_carried') as carried, \
                    patch.object(family, 'run') as depot:
                receipt = {'phase': 'waiting', 'code': 'WAIT_SOURCE', 'target_scope': SCOPE}
                carried.return_value = receipt
                actual = dispatch.run(self.backend, item, 64, self.out, self.checkpoint, SCOPE)
                self.assertIs(receipt, actual)
                self.assertIs(self.backend, self.client.material_backend)
                self.assertIs(self.backend, getattr(self.client, binding))
                carried.assert_called_once_with(self.client, self.backend.profile, item, 64,
                                                self.out, self.checkpoint)
                depot.assert_not_called()

    def test_explicit_depot_scope_keeps_existing_family_entry_point(self):
        for item, family in ((mineral.IRON, mineral), ('minecraft:oak_planks', wood)):
            with self.subTest(item=item), patch.object(family, 'run') as depot, \
                    patch.object(family, 'run_carried') as carried:
                receipt = {'phase': 'done'}
                depot.return_value = receipt
                self.assertIs(receipt, dispatch.run(self.backend, item, 64, self.out,
                                                     self.checkpoint, 'approved_depot_total'))
                depot.assert_called_once_with(self.client, self.backend.profile, item, 64,
                                              self.out, self.checkpoint)
                carried.assert_not_called()

    def test_other_minerals_and_raw_logs_cannot_request_carried_adapter(self):
        for item in (mineral.ITEMS - {mineral.IRON}) | set(wood.LOGS):
            with self.subTest(item=item), self.assertRaises(ValueError):
                dispatch.run(self.backend, item, 64, self.out, self.checkpoint, SCOPE)
        self.backend.ensure_client.assert_not_called()
        self.checkpoint.assert_not_called()

    def test_carried_invalid_counts_are_rejected_before_controller(self):
        for item in (mineral.IRON, 'minecraft:oak_planks'):
            for count in (0, True, 2305):
                with self.subTest(item=item, count=count), self.assertRaises(ValueError):
                    dispatch.run(self.backend, item, count, self.out, self.checkpoint, SCOPE)
        self.backend.ensure_client.assert_not_called()
        self.checkpoint.assert_not_called()


class CarriedFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.audit_spies = {}
        self.deposit_spies = {}
        for family in (mineral, wood):
            audit = patch.object(family, 'audit', side_effect=AssertionError('Carried output must not audit final depots'))
            deposit = patch.object(family, 'exchange', side_effect=AssertionError('Carried output must not be deposited'))
            self.audit_spies[family] = audit.start()
            self.deposit_spies[family] = deposit.start()
            self.addCleanup(audit.stop)
            self.addCleanup(deposit.stop)

    def mineral(self, stock=None):
        jar = self.root / 'recipes.jar'
        fixture_jar(jar)
        client = MineralClient()
        client.held.update(stock or {})
        backend = MineralBackend(client, jar)
        backend.request = {'mode': 'item'}
        return client, backend

    def wood(self, stock=None, species='oak'):
        client = WoodClient(self.root, stock)
        profile = {'server': 'example', 'dimension': 'minecraft:overworld',
                   'depots': [[1, 64, 2]], 'resource_regions': []}
        backend = WoodBackend(client, profile, species)
        backend.ensure_client = lambda: client
        client.wood_backend = backend
        return client, backend

    def run_carried(self, family, client, backend, item, target, name='order', checkpoint=None):
        if backend.request.get('mode') == 'item':
            projection_context(backend, item, target)
        return family.run_carried(client, backend.profile, item, target,
                                  self.root / name, checkpoint or (lambda: None))

    def no_final_deposit(self, family):
        self.audit_spies[family].assert_not_called()
        self.deposit_spies[family].assert_not_called()

    def journal(self, name='order'):
        paths = list((self.root / name).glob('*pipeline*.json'))
        self.assertEqual(1, len(paths), 'One persistent adapter journal is required')
        return paths[0], json.loads(paths[0].read_text())

    def uncertain(self, operation):
        try:
            result = operation()
        except (JobBlocked, JobPaused):
            return None
        self.assertEqual('waiting', result['phase'])
        self.assertIn(result['code'].lower(), ('wait_receipt', 'wait_reconcile'))
        return result


class CarriedContextJournalTests(CarriedFixture):
    def cases(self):
        client, backend = self.mineral({mineral.RAW: 18})
        yield mineral, client, backend, mineral.IRON, 2, 'mineral'
        client, backend = self.wood({'minecraft:oak_log': 2})
        yield wood, client, backend, 'minecraft:oak_planks', 5, 'wood'

    def refused(self, operation):
        try:
            result = operation()
        except (JobBlocked, JobPaused):
            return
        self.assertEqual('waiting', result['phase'])

    def test_item_mode_cannot_borrow_carried_projection_scope(self):
        for family, client, backend, item, target, name in self.cases():
            with self.subTest(family=name):
                projection_context(backend, item, target)
                backend.request['mode'] = 'item'
                backend.resource_pipeline_context['request_fingerprint'] = fingerprint(backend.request)
                self.refused(lambda: family.run_carried(client, backend.profile, item, target,
                                                       self.root / name, lambda: None))
                self.assertEqual([], backend.calls)
                self.no_final_deposit(family)

    def test_completed_journal_cannot_move_to_another_original_projection_request(self):
        for family, client, backend, item, target, name in self.cases():
            with self.subTest(family=name):
                self.assertEqual('done', self.run_carried(family, client, backend, item, target, name)['phase'])
                path, _ = self.journal(name)
                before = path.read_bytes()
                backend.calls.clear()
                backend.request['id'] = 'replacement-projection-job'
                backend.resource_pipeline_context.update(
                    request_id=backend.request['id'], request_fingerprint=fingerprint(backend.request))
                self.refused(lambda: self.run_carried(family, client, backend, item, target, name))
                self.assertEqual([], backend.calls)
                self.assertEqual(before, path.read_bytes())
                self.no_final_deposit(family)

    def test_completed_journal_cannot_move_to_changed_projection_bounds(self):
        for family, client, backend, item, target, name in self.cases():
            with self.subTest(family=name):
                self.assertEqual('done', self.run_carried(family, client, backend, item, target, name)['phase'])
                path, _ = self.journal(name)
                before = path.read_bytes()
                backend.calls.clear()
                backend.resource_pipeline_context['selection_bounds']['min'][0] += 1
                self.refused(lambda: self.run_carried(family, client, backend, item, target, name))
                self.assertEqual([], backend.calls)
                self.assertEqual(before, path.read_bytes())
                self.no_final_deposit(family)

    def test_interruption_before_craft_conservation_is_verified_preserves_native_pending(self):
        for family, client, backend, item, target, name in self.cases():
            with self.subTest(family=name):
                craft = backend.craft
                progress = {'returned': False, 'checks': 0}
                def execute(targets):
                    result = craft(targets)
                    progress['returned'] = True
                    return result
                def checkpoint():
                    if progress['returned']:
                        progress['checks'] += 1
                        if progress['checks'] == 2:
                            raise JobPaused('Interrupted before conservation verification')
                backend.craft = execute
                with self.assertRaises(JobPaused):
                    self.run_carried(family, client, backend, item, target, name, checkpoint)
                path, journal = self.journal(name)
                self.assertTrue(journal['pending'])
                self.assertGreaterEqual(client.held[item], target)
                before, calls = path.read_bytes(), copy.deepcopy(backend.calls)
                self.uncertain(lambda: self.run_carried(family, client, backend, item, target, name))
                self.assertEqual(calls, backend.calls)
                self.assertEqual(before, path.read_bytes())
                self.no_final_deposit(family)


class MineralCarriedTests(CarriedFixture):
    def test_target_counts_backpack_stock_and_keeps_new_finished_material_carried(self):
        client, backend = self.mineral({mineral.IRON: 7, mineral.RAW: 38})
        client.depot[mineral.IRON] = 1000
        result = self.run_carried(mineral, client, backend, mineral.IRON, 11)
        self.assertEqual(('done', SCOPE), (result['phase'], result['target_scope']))
        self.assertEqual(11, client.held[mineral.IRON])
        self.assertEqual(2, client.held[mineral.RAW])
        self.assertEqual(1000, client.depot[mineral.IRON])
        self.assertIn(('craft', {mineral.IRON: 11}), backend.calls)
        self.assertFalse(any(call[0] == 'acquire' for call in backend.calls))
        self.no_final_deposit(mineral)

    def test_enough_existing_backpack_stock_does_not_fetch_or_manufacture(self):
        client, backend = self.mineral({mineral.IRON: 12})
        result = self.run_carried(mineral, client, backend, mineral.IRON, 8)
        self.assertEqual('done', result['phase'])
        self.assertEqual(12, client.held[mineral.IRON])
        self.assertFalse(any(call[0] in ('fetch', 'fetch_packed', 'acquire', 'craft') for call in backend.calls))
        self.no_final_deposit(mineral)

    def test_one_call_produces_at_most_64_blocks_and_retains_fortune_raw_surplus(self):
        client, backend = self.mineral()
        backend.extra_raw = 2
        result = self.run_carried(mineral, client, backend, mineral.IRON, 130)
        self.assertEqual('waiting', result['phase'])
        self.assertEqual(64, client.held[mineral.IRON])
        self.assertEqual(2, client.held[mineral.RAW])
        self.assertEqual([576], [call[2] for call in backend.calls if call[:2] == ('acquire', mineral.RAW)])
        self.assertEqual([('craft', {mineral.IRON: 64})], [call for call in backend.calls if call[0] == 'craft'])
        self.assertFalse(client.depot[mineral.IRON])
        self.no_final_deposit(mineral)

    def test_known_batches_resume_to_absolute_target_without_deposit(self):
        client, backend = self.mineral()
        phases = [self.run_carried(mineral, client, backend, mineral.IRON, 130)['phase'] for _ in range(3)]
        self.assertEqual(['waiting', 'waiting', 'done'], phases)
        self.assertEqual(130, client.held[mineral.IRON])
        self.assertEqual([576, 576, 18], [call[2] for call in backend.calls if call[:2] == ('acquire', mineral.RAW)])
        self.no_final_deposit(mineral)

    def test_exact_projection_context_reuses_original_request_client_and_profile(self):
        client, backend = self.mineral({mineral.RAW: 18})
        request = projection_context(backend, mineral.IRON, 2)
        before_request, before_profile = copy.deepcopy(request), copy.deepcopy(backend.profile)
        result = self.run_carried(mineral, client, backend, mineral.IRON, 2)
        self.assertEqual('done', result['phase'])
        self.assertIs(request, backend.request)
        self.assertIs(client, backend.client)
        self.assertEqual(before_request, request)
        self.assertEqual(before_profile, backend.profile)
        self.no_final_deposit(mineral)

    def test_projection_context_requires_every_exact_contract_field_before_actions(self):
        client, backend = self.mineral({mineral.RAW: 18})
        for field, wrong in (('projection_key', 'other'), ('world_session', 'other-world'),
                             ('item', 'minecraft:stone'), ('target_count', 3),
                             ('target_scope', 'approved_depot_total'), ('request_id', 'other-job'),
                             ('request_fingerprint', 'different-fingerprint'),
                             ('selection_bounds', {'min': [30, 64, 20], 'max': [27, 64, 27]})):
            with self.subTest(field=field):
                projection_context(backend, mineral.IRON, 2)
                backend.resource_pipeline_context[field] = wrong
                backend.calls.clear()
                self.uncertain_or_refused(lambda: self.run_carried(mineral, client, backend, mineral.IRON, 2, field))
                self.assertEqual([], backend.calls)
        projection_context(backend, mineral.IRON, 2)
        del backend.resource_pipeline_context
        self.uncertain_or_refused(lambda: self.run_carried(mineral, client, backend, mineral.IRON, 2, 'missing'))
        self.assertEqual([], backend.calls)
        self.no_final_deposit(mineral)

    def test_unknown_craft_receipt_cannot_complete_or_replay_despite_correct_conservation(self):
        client, backend = self.mineral({mineral.RAW: 18})
        craft = backend.craft
        def unknown(targets):
            craft(targets)
            return {'phase': 'waiting'}
        backend.craft = unknown
        action = lambda: self.run_carried(mineral, client, backend, mineral.IRON, 2)
        self.uncertain(action)
        path, journal = self.journal()
        self.assertTrue(journal['pending'])
        self.assertEqual(2, client.held[mineral.IRON])
        self.assertEqual(0, client.held[mineral.RAW])
        before, calls = path.read_bytes(), copy.deepcopy(backend.calls)
        self.uncertain(action)
        self.assertEqual(calls, backend.calls)
        self.assertEqual(before, path.read_bytes())
        self.no_final_deposit(mineral)

    def uncertain_or_refused(self, operation):
        try:
            result = operation()
        except (JobBlocked, JobPaused):
            return
        self.assertEqual('waiting', result['phase'])

    def test_wrong_nine_to_one_delta_retains_pending_even_when_finished_target_is_present(self):
        client, backend = self.mineral({mineral.RAW: 18})
        backend.bad_craft = True
        action = lambda: self.run_carried(mineral, client, backend, mineral.IRON, 2)
        self.uncertain(action)
        path, journal = self.journal()
        self.assertTrue(journal['pending'])
        self.assertEqual(2, client.held[mineral.IRON])
        self.assertEqual(18, client.held[mineral.RAW])
        before = path.read_bytes()
        calls = copy.deepcopy(backend.calls)
        self.uncertain(action)
        self.assertEqual(calls, backend.calls)
        self.assertEqual(before, path.read_bytes())
        self.no_final_deposit(mineral)

    def test_observed_craft_overshoot_cannot_bypass_the_64_block_batch_bound(self):
        client, backend = self.mineral({mineral.RAW: 585})
        def oversized(targets):
            backend.calls.append(('oversized_craft', targets))
            client.held[mineral.RAW] -= 585
            client.held[mineral.IRON] += 65
            return {'phase': 'done'}
        backend.craft = oversized
        action = lambda: self.run_carried(mineral, client, backend, mineral.IRON, 1)
        self.uncertain(action)
        path, journal = self.journal()
        self.assertTrue(journal['pending'])
        before, calls = path.read_bytes(), copy.deepcopy(backend.calls)
        self.uncertain(action)
        self.assertEqual(calls, backend.calls)
        self.assertEqual(before, path.read_bytes())
        self.no_final_deposit(mineral)

    def test_unknown_native_acquire_cannot_replay_after_inventory_becomes_sufficient(self):
        client, backend = self.mineral()
        def unknown(item, desired):
            backend.calls.append(('unknown_acquire', item, desired))
            client.held[item] = desired
            return {'phase': 'unknown'}
        backend.acquire = unknown
        action = lambda: self.run_carried(mineral, client, backend, mineral.IRON, 64)
        self.uncertain(action)
        path, journal = self.journal()
        self.assertEqual('acquire', journal['pending']['kind'])
        client.held[mineral.IRON] = 64
        before, calls = path.read_bytes(), copy.deepcopy(backend.calls)
        self.uncertain(action)
        self.assertEqual(calls, backend.calls)
        self.assertEqual(before, path.read_bytes())
        self.no_final_deposit(mineral)

    def test_native_route_hold_retains_pending_before_any_later_craft(self):
        client, backend = self.mineral()
        def held(item, desired):
            backend.calls.append(('held_acquire', item, desired))
            client.held[item] = desired
            return {'phase': 'waiting', 'code': 'route_uncertain'}
        backend.acquire = held
        action = lambda: self.run_carried(mineral, client, backend, mineral.IRON, 2)
        try:
            first = action()
        except (JobBlocked, JobPaused):
            pass
        else:
            self.assertEqual('waiting', first['phase'])
        path, journal = self.journal()
        self.assertTrue(journal['pending'])
        self.assertFalse(any(call[0] == 'craft' for call in backend.calls))
        client.held[mineral.IRON] = 2
        before, calls = path.read_bytes(), copy.deepcopy(backend.calls)
        self.uncertain(action)
        self.assertEqual(calls, backend.calls)
        self.assertEqual(before, path.read_bytes())
        self.no_final_deposit(mineral)


class WoodCarriedTests(CarriedFixture):
    def test_all_five_families_keep_planks_carried_with_absolute_craft_targets(self):
        for species in wood.SPECIES:
            with self.subTest(species=species):
                raw, output = 'minecraft:' + species + '_log', 'minecraft:' + species + '_planks'
                client, backend = self.wood({raw: 16, output: 3}, species)
                client.depot[output] = 1000
                result = self.run_carried(wood, client, backend, output, 51, species)
                self.assertEqual(('done', SCOPE), (result['phase'], result['target_scope']))
                self.assertEqual(51, client.held[output])
                self.assertEqual(4, client.held[raw])
                self.assertEqual(1000, client.depot[output])
                self.assertIn(('craft', {output: 51}), backend.calls)
        self.no_final_deposit(wood)

    def test_rounding_surplus_stays_carried_and_four_to_one_is_conserved(self):
        raw, output = 'minecraft:oak_log', 'minecraft:oak_planks'
        client, backend = self.wood({raw: 2, output: 3})
        result = self.run_carried(wood, client, backend, output, 8)
        self.assertEqual('done', result['phase'])
        self.assertEqual(11, client.held[output])
        self.assertEqual(0, client.held[raw])
        self.assertIn(('craft', {output: 11}), backend.calls)
        self.assertEqual(0, client.depot.get(output, 0))
        self.no_final_deposit(wood)

    def test_small_existing_log_stock_is_used_before_new_fetch_or_harvest(self):
        raw, output = 'minecraft:oak_log', 'minecraft:oak_planks'
        client, backend = self.wood({raw: 3})
        with patch('material_jobs.acquisition.acquire') as acquire:
            result = self.run_carried(wood, client, backend, output, 100)
        self.assertEqual('waiting', result['phase'])
        self.assertEqual(12, client.held[output])
        self.assertEqual(0, client.held[raw])
        self.assertFalse(any(call[0] == 'fetch' for call in backend.calls))
        acquire.assert_not_called()
        self.no_final_deposit(wood)

    def test_enough_existing_planks_do_not_fetch_craft_or_deposit(self):
        output = 'minecraft:oak_planks'
        client, backend = self.wood({output: 12})
        result = self.run_carried(wood, client, backend, output, 8)
        self.assertEqual('done', result['phase'])
        self.assertEqual(12, client.held[output])
        self.assertFalse(any(call[0] in ('fetch', 'craft') for call in backend.calls))
        self.no_final_deposit(wood)

    def test_known_acquisition_reuses_client_profile_and_limits_new_logs_and_planks(self):
        raw, output = 'minecraft:oak_log', 'minecraft:oak_planks'
        client, backend = self.wood()
        region = {'item': raw, 'min': [0, 48, 0], 'max': [5, 100, 5], 'source': 'natural_survey'}
        backend.profile['resource_regions'] = [region]
        request = projection_context(backend, output, 130)
        before = copy.deepcopy(backend.profile)
        regrowth = {'planted': True, 'growth_confirmed': False, 'stage': 'sapling_kept_no_bone_meal'}
        def acquire(c, item, target, profile, directory, checkpoint):
            self.assertIs(client, c)
            self.assertEqual(raw, item)
            self.assertEqual(16, target)
            self.assertEqual([region], profile['resource_regions'])
            c.held[item] = 17
            return {'phase': 'done', 'gained': 17, 'regrowth': regrowth}
        with patch('material_jobs.equipment.prepare', return_value={'phase': 'done'}), \
                patch('material_jobs.acquisition.acquire', side_effect=acquire) as harvested:
            result = self.run_carried(wood, client, backend, output, 130)
        self.assertEqual('waiting', result['phase'])
        self.assertEqual(64, client.held[output])
        self.assertEqual(1, client.held[raw])
        harvested.assert_called_once()
        self.assertIs(request, backend.request)
        self.assertEqual(before, backend.profile)
        _, journal = self.journal()
        self.assertIn('sapling_kept_no_bone_meal', json.dumps(journal))
        self.no_final_deposit(wood)

    def test_exact_projection_context_preserves_original_request_identity(self):
        raw, output = 'minecraft:oak_log', 'minecraft:oak_planks'
        client, backend = self.wood({raw: 2})
        request = projection_context(backend, output, 5)
        before_request, before_profile = copy.deepcopy(request), copy.deepcopy(backend.profile)
        result = self.run_carried(wood, client, backend, output, 5)
        self.assertEqual('done', result['phase'])
        self.assertEqual(8, client.held[output])
        self.assertIs(client, backend.client)
        self.assertIs(request, backend.request)
        self.assertEqual(before_request, request)
        self.assertEqual(before_profile, backend.profile)
        self.no_final_deposit(wood)

    def test_projection_context_requires_every_exact_contract_field_before_actions(self):
        output = 'minecraft:oak_planks'
        client, backend = self.wood({'minecraft:oak_log': 2})
        for field, wrong in (('projection_key', 'other'), ('world_session', 'other-world'),
                             ('item', 'minecraft:cherry_planks'), ('target_count', 6),
                             ('target_scope', 'approved_depot_total'), ('request_id', 'other-job'),
                             ('request_fingerprint', 'different-fingerprint'),
                             ('selection_bounds', {'min': [30, 64, 20], 'max': [27, 64, 27]})):
            with self.subTest(field=field):
                projection_context(backend, output, 5)
                backend.resource_pipeline_context[field] = wrong
                backend.calls.clear()
                try:
                    result = self.run_carried(wood, client, backend, output, 5, field)
                except (JobBlocked, JobPaused):
                    pass
                else:
                    self.assertEqual('waiting', result['phase'])
                self.assertEqual([], backend.calls)
        projection_context(backend, output, 5)
        del backend.resource_pipeline_context
        try:
            result = self.run_carried(wood, client, backend, output, 5, 'missing')
        except (JobBlocked, JobPaused):
            pass
        else:
            self.assertEqual('waiting', result['phase'])
        self.assertEqual([], backend.calls)
        self.no_final_deposit(wood)

    def test_unknown_craft_retains_pending_even_when_inventory_reaches_target(self):
        raw, output = 'minecraft:oak_log', 'minecraft:oak_planks'
        client, backend = self.wood({raw: 16})
        craft = backend.craft
        def uncertain(targets):
            craft(targets)
            return {'phase': 'waiting'}
        backend.craft = uncertain
        action = lambda: self.run_carried(wood, client, backend, output, 64)
        self.uncertain(action)
        path, journal = self.journal()
        self.assertEqual('craft', journal['pending']['kind'])
        self.assertEqual(64, client.held[output])
        before, calls = path.read_bytes(), copy.deepcopy(backend.calls)
        self.uncertain(action)
        self.assertEqual(calls, backend.calls)
        self.assertEqual(before, path.read_bytes())
        self.no_final_deposit(wood)

    def test_wrong_four_to_one_input_loss_retains_pending_and_never_recrafts(self):
        raw, output = 'minecraft:oak_log', 'minecraft:oak_planks'
        client, backend = self.wood({raw: 16})
        def wrong(targets):
            backend.calls.append(('wrong_craft', targets))
            client.held[output] = 64
            client.held[raw] = 1
            return {'phase': 'done'}
        backend.craft = wrong
        action = lambda: self.run_carried(wood, client, backend, output, 64)
        self.uncertain(action)
        path, journal = self.journal()
        self.assertEqual('craft', journal['pending']['kind'])
        before, calls = path.read_bytes(), copy.deepcopy(backend.calls)
        self.uncertain(action)
        self.assertEqual(calls, backend.calls)
        self.assertEqual(before, path.read_bytes())
        self.no_final_deposit(wood)

    def test_unknown_native_harvest_cannot_replay_after_finished_stock_arrives(self):
        raw, output = 'minecraft:oak_log', 'minecraft:oak_planks'
        client, backend = self.wood()
        backend.profile['resource_regions'] = [{'item': raw, 'min': [0, 48, 0], 'max': [5, 100, 5]}]
        def unknown(c, item, target, *args):
            c.held[item] = target
            return {'phase': 'waiting', 'code': 'route_uncertain'}
        action = lambda: self.run_carried(wood, client, backend, output, 64)
        with patch('material_jobs.equipment.prepare', return_value={'phase': 'done'}), \
                patch('material_jobs.acquisition.acquire', side_effect=unknown) as harvested:
            self.uncertain(action)
            path, journal = self.journal()
            self.assertEqual('acquire', journal['pending']['kind'])
            client.held[output] = 64
            before, calls = path.read_bytes(), copy.deepcopy(backend.calls)
            self.uncertain(action)
        harvested.assert_called_once()
        self.assertEqual(calls, backend.calls)
        self.assertEqual(before, path.read_bytes())
        self.no_final_deposit(wood)


if __name__ == '__main__':
    unittest.main()
