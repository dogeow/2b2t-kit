"""Offline inventory/warehouse conservation tests; no live client or RPC."""
import copy
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from material_plan import MaterialPlanner
from projection_material_plan import ProcessingCatalog
from recipe_catalog import RecipeCatalog
from material_jobs import mineral_pipeline as pipeline
from material_jobs.protocol import JobBlocked, JobPaused


def fixture_jar(path):
    recipes = {
        'raw_iron_block': ('###', '###', '###', {'#': 'minecraft:raw_iron'}, 'raw_iron_block', 1),
        'stone_bricks': ('##', '##', {'#': 'minecraft:stone'}, 'stone_bricks', 4),
        'stone_brick_slab': ('###', {'#': 'minecraft:stone_bricks'}, 'stone_brick_slab', 6),
        'chiseled_stone_bricks': ('#', '#', {'#': 'minecraft:stone_brick_slab'}, 'chiseled_stone_bricks', 1),
        'lodestone': ('SSS', 'SIS', 'SSS', {'S': 'minecraft:chiseled_stone_bricks',
                                          'I': 'minecraft:iron_ingot'}, 'lodestone', 1),
    }
    with zipfile.ZipFile(path, 'w') as jar:
        for name, spec in recipes.items():
            pattern, key, output, count = list(spec[:-3]), spec[-3], spec[-2], spec[-1]
            jar.writestr('data/minecraft/recipe/' + name + '.json', json.dumps({
                'type': 'minecraft:crafting_shaped', 'pattern': pattern, 'key': key,
                'result': {'id': 'minecraft:' + output, 'count': count}}))
        for output, source in [('stone', 'cobblestone'), ('deepslate', 'cobbled_deepslate'),
                               ('iron_ingot', 'raw_iron')]:
            jar.writestr('data/minecraft/recipe/' + output + '.json', json.dumps({
                'type': 'minecraft:smelting', 'ingredient': 'minecraft:' + source,
                'result': {'id': 'minecraft:' + output}, 'cookingtime': 200}))


class Client:
    world = 'world'
    def __init__(self):
        self.held, self.depot, self.packed = Counter(), Counter(), Counter()
        self.last = None; self.manual = False; self.busy = False; self.room = 1_000_000
    def status(self):
        rows = []
        for item, total in self.held.items():
            for start in range(0, total, 64):
                rows.append({'slot': len(rows), 'item': item, 'count': min(64, total-start), 'max_stack': 64})
        if len(rows) > 36:
            raise AssertionError('Test would exceed actual inventory capacity')
        while len(rows) < 36:
            rows.append({'slot': len(rows), 'item': 'minecraft:air', 'count': 0, 'max_stack': 1})
        return {'connected': True, 'world_session': self.world, 'server': 'test',
                'dimension': 'minecraft:overworld', 'manual_movement': self.manual,
                'inventory': rows, 'control_revision': 1, 'borer_active': self.busy}


class Backend:
    def __init__(self, client, jar):
        self.client = client; client.mineral_backend = self
        self.profile = {'depots': [[1, 64, 1]], 'resource_regions': [],
                        'mineral_pipeline_max_actions': 4096}
        self.catalog, self.crafting = ProcessingCatalog(jar), RecipeCatalog(jar)
        self.warehouse_hint = {}; self.calls = []; self.acquire_reply = None
        self.extra_raw = 0; self.fail_acquire = False; self.bad_craft = False
        self.backpack_stop = False; self.room_fails = False
    def ensure_client(self):
        return self.client
    def prepare_travel(self):
        self.calls.append(('prepare_travel',))
    def stage_near_base(self, depots):
        self.calls.append(('stage_near_base', copy.deepcopy(depots)))
    def fetch(self, targets):
        self.calls.append(('fetch', copy.deepcopy(targets)))
        for item, target in targets.items():
            count = min(max(0, target-self.client.held[item]), self.client.depot[item])
            self.client.depot[item] -= count; self.client.held[item] += count
        return {'phase': 'waiting'}
    def fetch_packed(self, targets):
        self.calls.append(('fetch_packed', copy.deepcopy(targets)))
        for item, target in targets.items():
            count = min(max(0, target-self.client.held[item]), self.client.packed[item])
            self.client.packed[item] -= count; self.client.held[item] += count
    def acquire(self, item, desired):
        self.calls.append(('acquire', item, desired))
        if self.fail_acquire:
            raise JobPaused('Interrupted after native intent')
        if self.backpack_stop:
            self.backpack_stop = False
            self.client.held['minecraft:cobblestone'] = 64
            return {'phase': 'waiting', 'code': 'quarry_backpack_reserve'}
        if self.acquire_reply:
            return copy.deepcopy(self.acquire_reply)
        self.client.held[item] = max(self.client.held[item], desired)
        if item == pipeline.RAW:
            self.client.held[item] += self.extra_raw
        return {'phase': 'done'}
    def make_room(self, targets, keep):
        self.calls.append(('make_room', copy.deepcopy(targets), list(keep)))
        if not self.room_fails and 'minecraft:cobblestone' not in keep:
            amount = self.client.held['minecraft:cobblestone']
            self.client.depot['minecraft:cobblestone'] += amount
            self.client.held['minecraft:cobblestone'] = 0
        return {'phase': 'done'}
    def craft(self, targets):
        self.calls.append(('craft', copy.deepcopy(targets)))
        if self.bad_craft:
            self.client.held[pipeline.IRON] = targets[pipeline.IRON]
            return {'phase': 'done'}
        plan = MaterialPlanner(self.crafting).plan(targets, dict(self.client.held))
        if plan['missing_supplies']:
            raise AssertionError(plan['missing_supplies'])
        for step in plan['steps']:
            if step['kind'] != 'craft':
                continue
            for item, count in step['ingredients'].items():
                self.client.held[item] -= count
            self.client.held[step['item']] += step['produced']
        return {'phase': 'done'}
    def smelt(self, recipe, desired):
        self.calls.append(('smelt', recipe['item'], desired))
        amount = desired-self.client.held[recipe['item']]
        coal = (amount+7)//8
        needs = {item: value for item, value in ((recipe['source'], amount), ('minecraft:coal', coal))
                 if self.client.held[item] < value}
        if needs:
            return {'phase': 'waiting', 'requirements': needs}
        self.client.held[recipe['source']] -= amount
        self.client.held['minecraft:coal'] -= coal
        self.client.held[recipe['item']] += amount
        return {'phase': 'done'}


def audit(client, depots, items):
    return {'complete': True, 'world_session': client.world,
            'counts': {item: client.depot[item] for item in items}}


def exchange(client, depots, deposit):
    remaining = {}
    for item, keep in deposit.items():
        amount = min(max(0, client.held[item]-keep), client.room)
        client.held[item] -= amount; client.depot[item] += amount
        client.room -= amount
        if client.held[item] > keep:
            remaining[item] = client.held[item]-keep
    return {'complete': not remaining, 'remaining_deposit': remaining}


class MineralPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); jar = self.root/'recipes.jar'; fixture_jar(jar)
        self.client = Client(); self.backend = Backend(self.client, jar)
        for name, value in [('audit', audit), ('exchange', exchange)]:
            patcher = patch.object(pipeline, name, value); patcher.start(); self.addCleanup(patcher.stop)
    def run_order(self, item='raw_iron_block', target=64):
        return pipeline.run(self.client, self.backend.profile, 'minecraft:'+item, target,
                            self.root/'order', lambda: None)
    def journal(self):
        return json.loads((self.root/'order/mineral-pipeline.json').read_text())
    def test_full_3173_order_uses_49_packs_and_exact_tail(self):
        result = self.run_order(target=3173)
        self.assertEqual('done', result['phase'])
        self.assertEqual(3173, self.client.depot[pipeline.IRON])
        inputs = [call[2] for call in self.backend.calls if call[:2] == ('acquire', pipeline.RAW)]
        self.assertEqual([576]*49 + [333], inputs)
        self.assertEqual(0, self.client.held[pipeline.RAW])
        self.assertEqual(0, result['ai_calls'])
    def test_fortune_excess_and_existing_raw_are_real_remainders(self):
        self.client.held[pipeline.RAW] = 2; self.backend.extra_raw = 2
        self.run_order(target=65)
        self.assertEqual(65, self.client.depot[pipeline.IRON])
        self.assertEqual(2, self.client.held[pipeline.RAW])
        self.assertEqual(2, self.journal()['raw_remainder'])
    def test_existing_finished_stock_is_not_newly_mined_or_overproduced(self):
        self.client.depot[pipeline.IRON] = 60; self.client.held[pipeline.IRON] = 7
        self.run_order(target=64)
        self.assertEqual(64, self.client.depot[pipeline.IRON])
        self.assertEqual(3, self.client.held[pipeline.IRON])
        self.assertFalse(any(c[0] in ('acquire', 'craft') for c in self.backend.calls))
    def test_partial_deposit_resumes_without_recrafting(self):
        self.client.room = 10
        first = self.run_order(target=20)
        self.assertEqual(('waiting', 'WAIT_DEPOT', 10),
                         (first['phase'], first['code'], first['deposited']))
        crafts = sum(c[0] == 'craft' for c in self.backend.calls)
        self.client.room = 100
        second = self.run_order(target=20)
        self.assertEqual('done', second['phase'])
        self.assertEqual(crafts, sum(c[0] == 'craft' for c in self.backend.calls))
        self.assertEqual(20, self.client.depot[pipeline.IRON])
    def test_unknown_deposit_cannot_be_claimed_or_replayed(self):
        with patch.object(pipeline, 'exchange', return_value={'complete': True, 'remaining_deposit': {}}):
            with self.assertRaises(JobBlocked):
                self.run_order()
        self.assertEqual('deposit_verification', self.journal()['pending']['kind'])
        self.backend.calls.clear()
        self.assertEqual('WAIT_RECEIPT', self.run_order()['code'])
        self.assertEqual([], self.backend.calls)
    def test_post_transfer_audit_mismatch_keeps_reconciliation_marker(self):
        def dishonest(c, depots, items):
            value = audit(c, depots, items)
            if c.depot[pipeline.IRON]:
                value['counts'][pipeline.IRON] += 1
            return value
        with patch.object(pipeline, 'audit', dishonest):
            with self.assertRaises(JobBlocked):
                self.run_order()
        self.assertEqual('WAIT_RECEIPT', self.run_order()['code'])
    def test_carried_change_during_post_transfer_audit_never_credits_batch(self):
        def changed(c, depots, items):
            result = audit(c, depots, items)
            if c.depot[pipeline.IRON]:
                c.held[pipeline.IRON] += 1
            return result
        with patch.object(pipeline, 'audit', changed):
            with self.assertRaises(JobBlocked):
                self.run_order()
        self.assertEqual(0, self.journal()['deposited'])
        self.assertEqual('WAIT_RECEIPT', self.run_order()['code'])
    def test_unknown_backend_phase_keeps_pending_even_with_enough_inventory(self):
        def unknown(item, desired):
            self.client.held[item] = desired
            return {'phase': 'unknown'}
        with patch.object(self.backend, 'acquire', unknown):
            with self.assertRaises(JobBlocked):
                self.run_order()
        self.assertEqual('acquire', self.journal()['pending']['kind'])
        self.assertEqual('WAIT_RECEIPT', self.run_order()['code'])
    def test_native_interruption_keeps_pending_and_does_not_replay(self):
        self.backend.fail_acquire = True
        with self.assertRaises(JobPaused):
            self.run_order()
        self.assertEqual('acquire', self.journal()['pending']['kind'])
        count = len(self.backend.calls)
        self.assertEqual('WAIT_RECEIPT', self.run_order()['code'])
        self.assertEqual(count, len(self.backend.calls))
    def test_nine_to_one_violation_blocks_even_if_finished_count_looks_right(self):
        self.backend.bad_craft = True
        with self.assertRaises(JobBlocked):
            self.run_order()
        self.assertEqual('craft_verification', self.journal()['pending']['kind'])
        self.assertEqual(0, self.client.depot[pipeline.IRON])
        self.assertEqual('WAIT_RECEIPT', self.run_order()['code'])
    def test_budget_wait_is_known_and_resumable(self):
        self.backend.profile['mineral_pipeline_max_actions'] = 12
        result = self.run_order(target=130)
        self.assertEqual('WAIT_BUDGET', result['code'])
        self.assertIsNone(self.journal()['pending'])
        for _ in range(20):
            result = self.run_order(target=130)
            if result['phase'] == 'done':
                break
        self.assertEqual('done', result['phase'])
        self.assertEqual(130, self.client.depot[pipeline.IRON])
    def test_time_budget_stops_before_new_intent_and_can_resume(self):
        self.backend.profile['mineral_pipeline_max_seconds'] = 2
        with patch.object(pipeline.time, 'monotonic', side_effect=range(1000)):
            self.assertEqual('WAIT_BUDGET', self.run_order(target=1)['code'])
        self.assertIsNone(self.journal()['pending'])
        self.assertEqual('done', self.run_order(target=1)['phase'])
    def test_busy_native_work_pauses_before_any_backend_action(self):
        self.client.busy = True
        with self.assertRaises(JobPaused):
            self.run_order()
        self.assertEqual([], self.backend.calls)
    def test_corrupt_journal_does_not_move_or_produce(self):
        order = self.root/'order'; order.mkdir()
        (order/'mineral-pipeline.json').write_text('[1,2,3]')
        with self.assertRaises(JobBlocked):
            self.run_order()
        self.assertEqual([], self.backend.calls)
    def test_current_depot_change_is_not_extra_progress(self):
        self.client.room = 10; self.run_order(target=20)
        self.client.depot[pipeline.IRON] += 1; self.backend.calls.clear()
        self.assertEqual('WAIT_STOCK_CHANGED', self.run_order(target=20)['code'])
        self.assertFalse(any(c[0] in ('acquire', 'craft') for c in self.backend.calls))
    def test_source_missing_yields_wait_without_fabricated_regions_or_stock(self):
        self.backend.acquire_reply = {'phase': 'waiting', 'code': 'no_safe_candidate'}
        self.assertEqual('WAIT_SOURCE', self.run_order()['code'])
        self.assertEqual([], self.backend.profile['resource_regions'])
        self.assertEqual(0, self.client.depot[pipeline.IRON])
    def test_original_route_hold_is_preserved(self):
        self.backend.acquire_reply = {'phase': 'waiting', 'code': 'guard_displaced'}
        self.assertEqual('guard_displaced', self.run_order()['code'])
        self.assertFalse(any(c[0] == 'craft' for c in self.backend.calls))
    def test_verified_backpack_stop_unloads_only_byproducts_then_continues(self):
        self.backend.backpack_stop = True
        self.assertEqual('done', self.run_order()['phase'])
        rooms = [call for call in self.backend.calls if call[0] == 'make_room']
        self.assertEqual(1, len(rooms))
        self.assertIn(pipeline.RAW, rooms[0][2])
        self.assertIn(pipeline.IRON, rooms[0][2])
        self.assertEqual(64, self.client.depot['minecraft:cobblestone'])
    def test_failed_capacity_cleanup_never_restarts_native_quarry(self):
        self.backend.backpack_stop = self.backend.room_fails = True
        self.assertEqual('WAIT_CAPACITY', self.run_order()['code'])
        self.assertEqual(1, sum(call[0] == 'acquire' for call in self.backend.calls))
    def test_diorite_and_tuff_direct_batches_use_real_acquire(self):
        for item in ('diorite', 'tuff'):
            with self.subTest(item=item):
                self.root = Path(self.tmp.name)/item; self.root.mkdir()
                self.backend.calls.clear()
                self.assertEqual('done', self.run_order(item, 300)['phase'])
                self.assertEqual([128, 128, 44], [c[2] for c in self.backend.calls if c[:2] == ('acquire', 'minecraft:'+item)])
                self.assertFalse(any(c[0] in ('craft', 'smelt') for c in self.backend.calls))
    def test_stone_uses_owned_cobblestone_and_actual_fuel_requirements(self):
        self.client.depot.update({'minecraft:cobblestone': 200, 'minecraft:coal': 25})
        self.assertEqual('done', self.run_order('stone', 200)['phase'])
        self.assertEqual(200, self.client.depot['minecraft:stone'])
        self.assertEqual(0, self.client.depot['minecraft:cobblestone'])
        self.assertFalse(any(c[0] == 'acquire' for c in self.backend.calls))
    def test_deepslate_mines_only_missing_cobbled_input_then_smelts(self):
        self.client.depot.update({'minecraft:cobbled_deepslate': 3, 'minecraft:coal': 40})
        self.assertEqual('done', self.run_order('deepslate', 243)['phase'])
        self.assertEqual(243, self.client.depot['minecraft:deepslate'])
        self.assertEqual([128, 115], [c[2] for c in self.backend.calls if c[:2] == ('acquire', 'minecraft:cobbled_deepslate')])
    def test_lodestone_fetches_existing_ingots_before_mining_raw(self):
        self.client.depot.update({'minecraft:iron_ingot': 39, 'minecraft:cobblestone': 300,
                                  'minecraft:stone_bricks': 43, 'minecraft:coal': 40})
        self.assertEqual('done', self.run_order('lodestone', 36)['phase'])
        self.assertEqual(36, self.client.depot['minecraft:lodestone'])
        self.assertEqual(3, self.client.depot['minecraft:iron_ingot'])
        self.assertFalse(any(c[:2] == ('acquire', pipeline.RAW) for c in self.backend.calls))
    def test_manual_takeover_and_new_world_are_never_automatically_resumed(self):
        self.client.manual = True
        with self.assertRaises(JobPaused):
            self.run_order()
        self.assertEqual([], self.backend.calls)
        self.client.manual = False; self.client.room = 10; self.run_order(target=20)
        self.client.world = 'new-world'; self.backend.calls.clear()
        with self.assertRaises(JobPaused):
            self.run_order(target=20)
        self.assertEqual([], self.backend.calls)
    def test_new_target_requires_new_order_and_existing_controller_binding(self):
        self.client.room = 10; self.run_order(target=20)
        with self.assertRaises(JobPaused):
            self.run_order(target=21)
        self.backend.client = Client()
        with self.assertRaises(JobBlocked):
            self.run_order(target=20)
    def test_bound_backend_can_be_passed_directly(self):
        result = pipeline.run(self.backend, self.backend.profile, pipeline.IRON, 1,
                              self.root/'order', lambda: None)
        self.assertEqual('done', result['phase'])


if __name__ == '__main__':
    unittest.main()
