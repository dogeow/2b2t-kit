"""Offline geometry, conservation, pending receipts and material-loop regressions."""
from copy import deepcopy
from contextlib import contextmanager
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from unittest.mock import Mock
import zipfile

from material_jobs import MaterialJob
from material_jobs.protocol import JobBlocked
from projection_flat_backend import FlatMapBackend, accept_window, scene
from projection_flat_jobs_cli import main
from projection_flat_plan import FlatLayout, next_batch
from projection_material_plan import ProcessingCatalog
from material_jobs.projection_spatial_cache import native_content_hash
from test_material_jobs import FakeBackend

ITEM = 'minecraft:stone'


class FlatLoadingTest(unittest.TestCase):
    def test_registered_remote_cruise_keeps_high_trip_out_of_local_window_policy(self):
        job=FlatMapBackend.__new__(FlatMapBackend);job.profile={'remote_map_loading_cruise_y':160}
        selected={'min':[0,64,0],'max':[127,64,128]}
        remote=SimpleNamespace(status=lambda:{'pos':[-400,115,300]})
        local=SimpleNamespace(status=lambda:{'pos':[64,88,64]})
        self.assertEqual([64,160,64.5],job.projection_loading_target(remote,selected))
        self.assertEqual([64,88,64.5],job.projection_loading_target(local,selected))
        job.profile={'remote_map_loading_cruise_y':True}
        with self.assertRaises(JobBlocked):job.projection_loading_target(remote,selected)
    def test_native_unloaded_error_waits_for_same_selected_model(self):
        with tempfile.TemporaryDirectory()as d:
            job=FlatMapBackend.__new__(FlatMapBackend);job.out=Path(d);job.busy=False
            job.request={'projection_key':'ship'};job.audit=None;job.audit_dirty=True
            missing={'world_session':'w','phase':'error','detail':'等待图纸区块 1,2：UNLOADED',
                     'projection_selection':{'key':'ship'}}
            good={'world_session':'w','phase':'done','projection_audit':{'placement_key':'ship',
                  'loaded_chunks_verified':True,'loaded_server_chunks_verified':True,'kinds':{},'matched':10}}
            client=SimpleNamespace(world='w',request=Mock(side_effect=[missing,good]))
            job.ensure_client=lambda:client;job.checkpoint=Mock()
            with patch('projection_flat_backend.time.sleep'):result=job.refresh_audit()
            self.assertEqual(10,result['matched']);self.assertFalse(job.busy)
            self.assertEqual(2,client.request.call_count);job.checkpoint.assert_called_once()

    def test_unloaded_error_does_not_retry_changed_world_or_selection(self):
        for change in ({'world_session':'other'}, {'projection_selection':{'key':'other'}}):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as d:
                job=FlatMapBackend.__new__(FlatMapBackend);job.out=Path(d);job.busy=False
                job.request={'projection_key':'ship'};job.audit=None
                reply={'world_session':'w','phase':'error','detail':'等待图纸区块 1,2：UNLOADED',
                       'projection_selection':{'key':'ship'},**change}
                client=SimpleNamespace(world='w',request=Mock(return_value=reply))
                job.ensure_client=lambda:client;job.checkpoint=Mock()
                with self.assertRaises(JobBlocked):job.refresh_audit()
                self.assertIsNone(job.audit);self.assertFalse(job.busy)
                self.assertEqual(1,client.request.call_count)
                self.assertFalse((job.out/'projection-latest.json').exists())

    def test_other_native_error_keeps_its_actual_reason(self):
        with tempfile.TemporaryDirectory()as d:
            job=FlatMapBackend.__new__(FlatMapBackend);job.out=Path(d);job.busy=False
            job.request={'projection_key':'ship'};job.audit=None
            client=SimpleNamespace(world='w',request=Mock(return_value={'world_session':'w',
                    'phase':'error','detail':'图纸损坏','projection_selection':{'key':'ship'}}))
            job.ensure_client=lambda:client;job.checkpoint=Mock()
            with self.assertRaisesRegex(JobBlocked,'图纸损坏'):job.refresh_audit()
            self.assertEqual(1,client.request.call_count);self.assertFalse(job.busy)

    def test_server_chunk_arrival_is_waited_without_publishing_unloaded_cells(self):
        with tempfile.TemporaryDirectory()as d:
            job=FlatMapBackend.__new__(FlatMapBackend);job.out=Path(d);job.busy=False
            job.request={'projection_key':'ship'};job.audit={'matched':9};job.audit_dirty=True
            missing={'world_session':'w','projection_audit':{'placement_key':'ship',
                'loaded_chunks_verified':False,'loaded_server_chunks_verified':False,'kinds':{'unloaded':3}}}
            good={'world_session':'w','projection_audit':{'placement_key':'ship',
                'loaded_chunks_verified':True,'loaded_server_chunks_verified':True,'kinds':{},'matched':10,'total':18}}
            client=SimpleNamespace(world='w',request=Mock(side_effect=[missing,good]))
            job.ensure_client=lambda:client;job.checkpoint=Mock()
            with patch('projection_flat_backend.time.sleep'):
                result=job.refresh_audit()
            self.assertEqual(10,result['matched']);self.assertFalse(job.busy);self.assertFalse(job.audit_dirty)
            self.assertEqual(2,client.request.call_count);job.checkpoint.assert_called_once()

    def test_wrong_model_does_not_become_retry_or_cached_success(self):
        with tempfile.TemporaryDirectory()as d:
            job=FlatMapBackend.__new__(FlatMapBackend);job.out=Path(d);job.busy=False
            job.request={'projection_key':'ship'};job.audit=None
            client=SimpleNamespace(world='w',request=Mock(return_value={'world_session':'w','projection_audit':{'placement_key':'other'}}))
            job.ensure_client=lambda:client;job.checkpoint=Mock()
            with self.assertRaises(JobBlocked):job.refresh_audit()
            self.assertIsNone(job.audit);self.assertFalse((job.out/'projection-latest.json').exists())
            self.assertEqual(1,client.request.call_count)


def model(width=6, depth=3, origin=(0, 64, 0)):
    x, y, z = origin
    rows = [{'pos': [x + a, y, z + b], 'state': 'Block{' + ITEM + '}', 'item': ITEM}
            for b in range(depth) for a in range(width)]
    return {'model_schema': 1, 'placement_key': 'ship', 'content_hash': native_content_hash(rows),
            'bounds': {'min': list(origin), 'max': [x + width - 1, y, z + depth - 1]},
            'total': len(rows), 'expected': rows, 'loaded_chunks_verified': True,
            'loaded_server_chunks_verified': True}


CONFIG = {'schema': 1, 'content_hash': model()['content_hash']}


def layout_for(m, config=CONFIG):
    return FlatLayout(m, {**config, 'content_hash': m['content_hash']})


def inventory(count=0, free=4):
    rows = [{'slot': i, 'item': 'minecraft:diamond_sword', 'count': 1, 'max_stack': 1,
             'durability': 1000} for i in range(43)]
    for i in range(free):
        rows[9 + i] = {'slot': 9 + i, 'item': 'minecraft:air', 'count': 0, 'max_stack': 1}
    if count:
        rows[5] = {'slot': 5, 'item': ITEM, 'count': count, 'max_stack': 64}
    return rows


def state(count=0, free=4):
    return {'pos': [.5, 66.75, .5], 'projection_selection': {'key': 'ship'},
            'flight':True, 'on_ground':False,
            'inventory': inventory(count, free), 'projection_air_seed_protocol': 1,
            'target_stack_sizes': {ITEM: 64}}


def audit(layout, actual):
    mismatches = [{'pos': list(p), 'expected': row['state'], 'actual': 'Block{minecraft:air}',
                   'kind': 'missing', 'fluid': False, 'adjacent_fluid': False,
                   'block_entity': False, 'neighbors_loaded': True}
                  for p, row in layout.expected.items() if p not in actual]
    return {'audit_schema': 2, 'placement_key': layout.key, 'total': len(layout.expected),
            'matched': len(actual), 'mismatches': mismatches, 'observed_at': 1000,
            'loaded_chunks_verified': True, 'loaded_server_chunks_verified': True,
            'kinds': {'missing': len(mismatches)}, 'enclosed_air_conflicts': []}


class FlatPlanningTests(unittest.TestCase):
    def setUp(self):
        self.layout = FlatLayout(model(), CONFIG)

    def test_nearest_supported_connected_window_and_stack_reserve(self):
        actual = {(0, 64, 0): 'Block{minecraft:stone}'}
        before = deepcopy((actual, state(6)))
        result = next_batch(self.layout, actual, state(6))
        self.assertEqual(result['operation'], 'print')
        self.assertEqual(len(result['positions']), 4)
        self.assertEqual(result['retained_after'], 2)
        observed = set(actual)
        for p in map(tuple, result['positions']):
            x, y, z = p
            self.assertTrue(observed & {(x - 1, y, z), (x + 1, y, z), (x, y, z - 1), (x, y, z + 1)})
            observed.add(p)
        self.assertEqual((actual, state(6)), before)

    def test_isolated_map_gets_one_seed_and_replans_to_supported_print(self):
        first = next_batch(self.layout, {}, state(12))
        self.assertEqual((first['operation'], len(first['positions'])), ('air_seed', 1))
        actual = {tuple(first['positions'][0]): 'Block{minecraft:stone}'}
        second = next_batch(self.layout, actual, state(11))
        self.assertEqual(second['operation'], 'print')

    def test_pending_missing_cell_cannot_be_bridge_or_mutation(self):
        layout = layout_for(model(3, 1), {**CONFIG, 'excluded_positions': [[1, 64, 0]]})
        actual = {(0, 64, 0): 'Block{minecraft:stone}'}
        result = next_batch(layout, actual, state(8))
        self.assertEqual(result['operation'], 'air_seed')
        self.assertEqual(result['positions'], [[2, 64, 0]])
        actual[(1, 64, 0)] = 'Block{minecraft:stone}'
        self.assertEqual(next_batch(layout, actual, state(8))['operation'], 'print')

    def test_offhand_packed_and_named_stacks_never_fund_print(self):
        s = state()
        s['inventory'][40] = {'slot': 40, 'item': ITEM, 'count': 64, 'max_stack': 64}
        s['inventory'][0] = {'slot': 0, 'item': 'minecraft:shulker_box', 'count': 1, 'max_stack': 1,
                             'contains': [{'item': ITEM, 'count': 64, 'max_stack': 64}]}
        result = next_batch(self.layout, {}, s)
        self.assertEqual(result['operation'], 'supply')
        self.assertEqual(result['requirements'], {ITEM: 20})
        s['inventory'][5] = {'slot': 5, 'item': ITEM, 'count': 64, 'max_stack': 64, 'custom_name': 'keep'}
        self.assertEqual(next_batch(self.layout, {}, s)['phase'], 'blocked')

    def test_capacity_limits_one_load_without_dumping_other_inventory(self):
        layout = layout_for(model(128, 1))
        result = next_batch(layout, {}, state(free=1))
        self.assertEqual(result['requirements'], {ITEM: 64})
        self.assertEqual(result['load_plan']['construction_cells'], 62)
        self.assertEqual(next_batch(layout, {}, state(free=0))['phase'], 'blocked')

    def test_world_coordinates_come_from_model_and_per_job_policy(self):
        layout = layout_for(model(origin=(450, 90, -70)))
        s = state(8); s['pos'] = [450.5, 92.75, -69.5]
        result = next_batch(layout, {}, s)
        self.assertEqual(result['positions'], [[450, 90, -70]])
        self.assertEqual(result['station'], [450.5, 92.75, -69.5])

    def test_actual_limits_and_budget_are_not_guessed(self):
        s = state(); s['target_stack_sizes'] = {}
        self.assertEqual(next_batch(self.layout, {}, s)['phase'], 'blocked')
        s = state(10)
        for cap in (1, 2, 3):
            actual = {(0, 64, 0): 'Block{minecraft:stone}'}
            self.assertEqual(len(next_batch(self.layout, actual, s, cell_budget=cap)['positions']), cap)

    def test_one_reachable_four_by_four_window_replaces_smaller_subwindows(self):
        layout = layout_for(model(4, 4))
        actual = {(0, 64, 0): 'Block{minecraft:stone}'}
        result = next_batch(layout, actual, state(64))
        self.assertEqual(len(result['positions']), 15)
        self.assertEqual(result['station'], [2.0, 66.75, 2.0])
        # Far corner top face remains within ordinary survival reach.
        eye = [2.0, 66.75 + 1.62, 2.0]
        self.assertLess(math.dist(eye, [.5, 65, .5]), 4.5)

    def test_models_and_audits_must_be_complete_and_exact(self):
        for mutate in (lambda m: m['expected'].pop(), lambda m: m.update(content_hash='b' * 64),
                       lambda m: m.update(loaded_server_chunks_verified=False),
                       lambda m: m['expected'][1].update(pos=[0, 64, 0])):
            m = model(); mutate(m)
            with self.assertRaises(ValueError): FlatLayout(m, CONFIG)
        a = audit(self.layout, {})
        self.assertEqual(self.layout.observed(a), {})
        for mutate in (lambda a: a['mismatches'].pop(), lambda a: a.update(matched=True),
                       lambda a: a['mismatches'][0].update(adjacent_fluid=True),
                       lambda a: a['mismatches'][0].update(actual='Block{minecraft:chest}')):
            bad = deepcopy(a); mutate(bad)
            with self.assertRaises(ValueError): self.layout.observed(bad)

    def test_stateful_targets_require_existing_dedicated_adapter(self):
        m = model(1, 1)
        m['expected'][0].update(item='minecraft:stripped_cherry_wood', state='Block{minecraft:stripped_cherry_wood}[axis=y]')
        m['content_hash'] = native_content_hash(m['expected'])
        layout = layout_for(m)
        s = state(8); s['inventory'][5]['item'] = 'minecraft:stripped_cherry_wood'
        self.assertEqual(next_batch(layout, {}, s)['phase'], 'blocked')


class FlatReceiptTests(unittest.TestCase):
    def setUp(self):
        self.layout = layout_for(model(3, 1))
        self.before = {(0, 64, 0): 'Block{minecraft:stone}'}
        self.plan = next_batch(self.layout, self.before, state(4))
        self.after = dict(self.before, **{})
        self.after.update({tuple(p): 'Block{minecraft:stone}' for p in self.plan['positions']})
        self.receipt = {'phase': 'done', 'professional_printer': {'server_confirmed': 2,
                        'failure': '', 'travel_pending': 0, 'owned': False, 'enabled': False,
                        'waiting_for_server': False}}

    def test_ack_stock_and_exact_cells_must_agree(self):
        self.assertEqual(len(accept_window(self.plan, self.before, self.after, 4, 2, self.receipt, self.layout.expected)), 2)
        cases = [(4, 3, self.receipt), (4, 2, {'phase': 'waiting'}),
                 (4, 2, {'phase': 'done', 'professional_printer': {**self.receipt['professional_printer'], 'travel_pending': 1}})]
        for before, after, receipt in cases:
            with self.assertRaises(JobBlocked): accept_window(self.plan, self.before, self.after, before, after, receipt, self.layout.expected)
        changed = dict(self.after); changed.pop((0, 64, 0))
        with self.assertRaises(JobBlocked): accept_window(self.plan, self.before, changed, 4, 2, self.receipt, self.layout.expected)

    def test_scan_completeness_and_registered_light_rules(self):
        low, high = [0, 64, 0], [2, 65, 0]
        base = {'pos': [0, 64, 0], 'state': 'Block{minecraft:stone}', 'solid': True, 'fluid': False, 'block_entity': False}
        light = {'pos': [0, 65, 0], 'state': 'Block{minecraft:torch}', 'solid': False,
                 'passable': True, 'fluid': False, 'block_entity': False}
        r = {'phase': 'done', 'world_session': 'world', 'scan_cells_read': 6, 'scan_total_cells': 6,
             'control_revision': 1, 'scan_start_revision': 1, 'scan_end_revision': 1, 'blocks': [base, light]}
        with self.assertRaises(JobBlocked): scene(self.layout, r, low, high, 'world', 1)
        layout = layout_for(model(3, 1), {**CONFIG, 'registered_lights': [[0, 65, 0]]})
        self.assertEqual(scene(layout, r, low, high, 'world', 1), self.before)
        for mutate in (lambda r: r.update(scan_cells_read=5), lambda r: r.update(scan_end_revision=2),
                       lambda r: r['blocks'].append(deepcopy(base)),
                       lambda r: r['blocks'][0].update(state='Block{minecraft:dirt}')):
            bad = deepcopy(r); mutate(bad)
            with self.assertRaises(JobBlocked): scene(layout, bad, low, high, 'world', 1)

    def test_existing_standing_map_lights_are_read_only_and_require_exact_support(self):
        layout = layout_for(model(1, 1), {**CONFIG, 'reuse_existing_map_lights': True})
        base = {'pos': [0, 64, 0], 'state': 'Block{minecraft:stone}',
                'solid': True, 'fluid': False, 'block_entity': False}
        light = {'pos': [0, 65, 0], 'state': 'Block{minecraft:torch}',
                 'solid': False, 'passable': True, 'fluid': False, 'block_entity': False}
        reply = {'phase': 'done', 'world_session': 'world', 'scan_cells_read': 2, 'scan_total_cells': 2,
                 'control_revision': 1, 'scan_start_revision': 1, 'scan_end_revision': 1, 'blocks': [base, light]}
        self.assertEqual(scene(layout, reply, [0, 64, 0], [0, 65, 0], 'world', 1), self.before)
        self.assertFalse(layout.config['registered_lights'])
        for mutate in (lambda r: r['blocks'].pop(0), lambda r: r.update(scan_end_revision=2),
                       lambda r: r['blocks'][1].update(fluid=True),
                       lambda r: r['blocks'][1].update(state='Block{minecraft:chest}')):
            bad = deepcopy(reply); mutate(bad)
            with self.assertRaises(JobBlocked): scene(layout, bad, [0, 64, 0], [0, 65, 0], 'world', 1)

    def test_stopped_navigation_without_material_action_allows_healthy_parking(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FlatMapBackend.__new__(FlatMapBackend); backend.out = Path(tmp)
            target = backend.out / '0001-build/window-0000'; target.mkdir(parents=True)
            journal = target / 'flat-window.json'
            original = {'complete': False, 'pending': 'navigate', 'world_session': 'world'}
            journal.write_text(json.dumps(original))
            with patch('material_jobs_backend.Backend.finish', return_value={'parked': True}) as finish:
                self.assertEqual(backend.finish(), {'parked': True}); finish.assert_called_once()
            self.assertEqual(json.loads(journal.read_text()), original)
            (target / 'mask-receipt.json').write_text('{}')
            with patch('material_jobs_backend.Backend.finish') as finish:
                with self.assertRaises(JobBlocked): backend.finish()
                finish.assert_not_called()

    def test_air_seed_needs_real_projected_state_and_exact_native_counts(self):
        p = next_batch(self.layout, {}, state(4))
        target = tuple(p['positions'][0])
        after = {target: self.layout.expected[target]['state']}
        ack = {'phase': 'done', 'projection_air_seed': {'target': list(target), 'server_confirmed': True,
               'projection_matches': True, 'requires_stripping': False, 'use_count': 1,
               'expected_state': after[target], 'projected_state': after[target],
               'inventory_before': 4, 'inventory_after': 3}}
        self.assertEqual(accept_window(p, {}, after, 4, 3, ack, self.layout.expected), {target})
        for key, value in [('use_count', True), ('projection_matches', False), ('requires_stripping', True),
                           ('projected_state', 'Block{minecraft:dirt}'), ('inventory_after', 4)]:
            bad = deepcopy(ack); bad['projection_air_seed'][key] = value
            with self.assertRaises(JobBlocked): accept_window(p, {}, after, 4, 3, bad, self.layout.expected)

    def test_preflight_yields_to_manual_input_and_other_native_owner(self):
        backend = FlatMapBackend.__new__(FlatMapBackend); backend.checkpoint = lambda: None
        backend.request = {'target_stack_sizes': {ITEM: 64}}
        s = state(4)
        s.update(connected=True, world_session='world', control_revision=1, health=20, food=20,
                 manual_movement=False, screen='', guard_busy=False, under_water=False,
                 safety_hold={'active': False}, flight=True, guard_armed=True, guard_pve_only=True,
                 supervision_lease={'kind': 'materials', 'id': 'lease', 'job_session': 'task',
                                    'world_session': 'world', 'revision': 1},
                 professional_printer={'owned': False, 'enabled': False, 'waiting_for_server': False,
                                       'travel_pending': 0, 'rotate': True, 'in_air': False, 'air_place': False})
        client = SimpleNamespace(world='world', task='task', rev=1, heartbeat=SimpleNamespace(id='lease'), status=lambda: s)
        self.assertEqual(backend._safe_flat(client, self.layout)['world_session'], 'world')
        for key, value in [('manual_movement', True), ('health', 18), ('guard_busy', True), ('screen', 'inventory')]:
            bad = deepcopy(s); bad[key] = value; client.status = lambda: bad
            with self.assertRaises(JobBlocked): backend._safe_flat(client, self.layout)
        bad = deepcopy(s); bad['supervision_lease']['id'] = 'other'; client.status = lambda: bad
        with self.assertRaises(JobBlocked): backend._safe_flat(client, self.layout)

    def test_unknown_original_window_blocks_recovery_without_new_controller(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FlatMapBackend.__new__(FlatMapBackend); backend.out = Path(tmp)
            target = backend.out / '0001-build/window-0000'; target.mkdir(parents=True)
            journal = target / 'flat-window.json'
            original = {'complete': False, 'pending': 'professional_print', 'world_session': 'old-world'}
            journal.write_text(json.dumps(original))
            with patch.object(backend, 'ensure_client', side_effect=AssertionError('must not create client')):
                result = backend.recover({'operation': 'build'})
            self.assertFalse(result['safe_to_replan'])
            self.assertEqual(json.loads(journal.read_text()), original)
            with patch('material_jobs_backend.Backend.finish', side_effect=AssertionError('must not move or clear')):
                with self.assertRaises(JobBlocked): backend.finish()
            self.assertEqual(json.loads(journal.read_text()), original)

    def test_pending_native_window_retains_journal_and_never_clears_mask(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FlatMapBackend.__new__(FlatMapBackend)
            s = state(4); s.update(selected_slot=5, hand={'item': ITEM}, pos=self.plan['station'])
            s['projection_batch'] = {'active': False}
            calls = []
            def request(op, **kw):
                calls.append(op)
                if op == 'projection_batch_set':
                    return {'projection_batch': {'active': True, 'count': 2, 'placement_key': 'ship',
                            'task_session': 'task', 'min_feet_y': 65}}
                return {'phase': 'waiting', 'professional_printer': {'travel_pending': 1}}
            client = SimpleNamespace(world='world', task='task', request=request, checked=request, status=lambda: s)
            backend.checkpoint = lambda: None
            backend._safe_flat = lambda c, layout: s
            backend._scan_flat = lambda *args: (self.before, [0, 64, 0], [2, 68, 0])
            target = Path(tmp) / 'window'
            with patch('material_jobs.acquisition._travel'):
                with self.assertRaises(JobBlocked): backend._window(client, self.layout, self.before, self.plan, target)
            record = json.loads((target / 'flat-window.json').read_text())
            self.assertEqual(record['pending'], 'professional_print')
            self.assertFalse(record['complete'])
            self.assertNotIn('projection_batch_clear', calls)
            self.assertEqual(calls.count('professional_print'), 1)

    def test_cruise_arrival_cannot_dispatch_material_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FlatMapBackend.__new__(FlatMapBackend)
            s = state(4); s['pos'] = [self.plan['station'][0], 140, self.plan['station'][2]]
            calls = []
            client = SimpleNamespace(world='world', task='task', checked=lambda *a, **k: calls.append(a), status=lambda: s)
            backend.checkpoint = lambda: None
            backend._safe_flat = lambda c, layout: s
            target = Path(tmp) / 'window'
            with patch('material_jobs.acquisition._travel') as travel:
                with self.assertRaises(JobBlocked): backend._window(client, self.layout, self.before, self.plan, target)
            self.assertFalse(travel.call_args.kwargs['keep_cruise'])
            self.assertEqual(calls, [])
            self.assertEqual(json.loads((target/'flat-window.json').read_text())['pending'], 'navigate')

    def test_high_start_descends_before_print_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FlatMapBackend.__new__(FlatMapBackend)
            s = state(4); s.update(selected_slot=5, hand={'item': ITEM}, projection_batch={'active': False})
            s['pos'] = [self.plan['station'][0], 140, self.plan['station'][2]]
            calls = []
            def request(op, **kw):
                self.assertLessEqual(abs(s['pos'][1]-self.plan['station'][1]), .75)
                calls.append(op)
                if op == 'projection_batch_set':
                    return {'projection_batch': {'active': True, 'count': 2, 'placement_key': 'ship',
                            'task_session': 'task', 'min_feet_y': 65}}
                return {'phase': 'waiting', 'professional_printer': {'travel_pending': 1}}
            client = SimpleNamespace(world='world', task='task', request=request, checked=request, status=lambda: s)
            backend.checkpoint = lambda: None
            backend._safe_flat = lambda c, layout: s
            backend._scan_flat = lambda *args: (self.before, [0, 64, 0], [2, 68, 0])
            def native_travel(c, target, checkpoint, trace, *, keep_cruise):
                # Match the existing travel primitive's final-descent semantics.
                s['pos'] = [target[0], max(s['pos'][1], target[1]) if keep_cruise else target[1], target[2]]
            with patch('material_jobs.acquisition._travel', side_effect=native_travel):
                with self.assertRaises(JobBlocked): backend._window(client, self.layout, self.before, self.plan, Path(tmp)/'window')
            self.assertEqual(calls.count('professional_print'), 1)
            self.assertEqual(s['pos'], self.plan['station'])


class SimulatedFlatBackend(FakeBackend):
    """Actual existing scheduler, with only game I/O replaced by in-memory stock."""
    def __init__(self, catalog):
        super().__init__(catalog, projection={ITEM: 20})
        self.layout = layout_for(model(20, 1))
        self.actual = {}

    def observe(self):
        s = super().observe()
        for row in s['inventory']:
            if row['count'] == 0:
                row['max_stack'] = 1
        s['inventory'] += [{'slot': n, 'item': 'minecraft:air', 'count': 0, 'max_stack': 1} for n in range(36, 43)]
        s.update(pos=[.5, 66.75, .5], projection_selection={'key': 'ship'}, projection_air_seed_protocol=1,
                 target_stack_sizes=self.stack_sizes, projection_audit=audit(self.layout, self.actual))
        s['projection_audit']['replacement_items'] = dict(+self.projection)
        return s

    def build(self, key):
        gained = 0
        while True:
            p = next_batch(self.layout, self.actual, self.observe())
            if p['phase'] != 'ready':
                self.calls.append(('flat_build', key, gained))
                return {'phase': p['phase'], 'requirements': p.get('requirements', {}), 'placed': gained}
            for pos in p['positions']:
                self.actual[tuple(pos)] = self.layout.expected[tuple(pos)]['state']
                self.held[p['item']] -= 1
                self.projection[p['item']] -= 1
                self.matched += 1
                gained += 1


class FlatIntegrationTests(unittest.TestCase):
    def test_vertical_deepslate_carried_stack_is_ready_and_uses_axis_placement(self):
        m=model(100,1)
        for row in m['expected']:
            row.update(item='minecraft:deepslate',state='Block{minecraft:deepslate}[axis=y]')
        m['content_hash']=native_content_hash(m['expected']);layout=layout_for(m)
        backend=FlatMapBackend.__new__(FlatMapBackend)
        backend.profile={'minimum_projection_trip_stack':64}
        backend.request={'projection_key':'ship','flat_map':{**CONFIG,'content_hash':m['content_hash']}}
        s=state(64);s['inventory'][5]['item']='minecraft:deepslate'
        s['target_stack_sizes']={'minecraft:deepslate':64};s['projection_audit']=audit(layout,{})
        self.assertFalse(backend.has_ready_projection_output(s))
        self.assertEqual('blocked',next_batch(layout,{},s)['phase'])
        s['projection_air_seed_axis_protocol']=1
        self.assertTrue(backend.has_ready_projection_output(s))
        first=next_batch(layout,{},s)
        self.assertEqual('air_seed',first['operation']);self.assertEqual('minecraft:deepslate',first['item'])
        actual={tuple(first['positions'][0]):'Block{minecraft:deepslate}[axis=y]'}
        s['inventory'][5]['count']=63
        self.assertEqual('print',next_batch(layout,actual,s)['operation'])
        for props in ('axis=x','axis=z','axis=y,waterlogged=false'):
            altered=deepcopy(m)
            for row in altered['expected']:row['state']='Block{minecraft:deepslate}['+props+']'
            altered['content_hash']=native_content_hash(altered['expected'])
            self.assertFalse(layout_for(altered).fillable)

    def test_registered_whole_trip_uses_stack_or_exact_tail_before_returning(self):
        m=model(100,1);layout=layout_for(m);backend=FlatMapBackend.__new__(FlatMapBackend)
        backend.profile={'minimum_projection_trip_stack':64}
        backend.request={'projection_key':'ship','flat_map':{**CONFIG,'content_hash':m['content_hash']}}
        s=state(7);s['projection_audit']=audit(layout,{})
        self.assertFalse(backend.has_ready_projection_output(s))
        s['inventory'][5]['count']=64;self.assertTrue(backend.has_ready_projection_output(s))
        s['inventory'][5]['count']=32;s['inventory'][6]={'slot':6,'item':ITEM,'count':32,'max_stack':64}
        self.assertTrue(backend.has_ready_projection_output(s))
        m=model(5,1);layout=layout_for(m);backend.request['flat_map']['content_hash']=m['content_hash']
        s=state(7);s['projection_audit']=audit(layout,{})
        self.assertTrue(backend.has_ready_projection_output(s))

    def test_small_plain_carried_output_is_ready_without_supplying_a_full_batch(self):
        m=model(3,1); layout=layout_for(m)
        backend=FlatMapBackend.__new__(FlatMapBackend)
        backend.request={'projection_key':'ship','flat_map':{**CONFIG,'content_hash':m['content_hash']}}
        snapshot=state(3); snapshot['projection_audit']=audit(layout,{})
        self.assertTrue(backend.has_ready_projection_output(snapshot))
        for change in ('reserve','metadata','wet','retained','unloaded'):
            s=deepcopy(snapshot); backend.request['flat_map']={**CONFIG,'content_hash':m['content_hash']}
            if change=='reserve':s['inventory'][5]['count']=2
            elif change=='metadata':s['inventory'][5]['custom_name']='protected'
            elif change=='wet':
                for row in s['projection_audit']['mismatches']:row['adjacent_fluid']=True
            elif change=='retained':backend.request['flat_map']['excluded_positions']=[list(p)for p in layout.expected]
            else:s['projection_audit']['loaded_server_chunks_verified']=False
            self.assertFalse(backend.has_ready_projection_output(s),change)

    def test_scheduler_builds_ready_carried_output_before_advice_or_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            request={'schema':1,'id':'carried-first','mode':'projection','targets':{},'projection_key':'ship','created_at':1000,
                     'context':{'server':'example.test','dimension':'minecraft:overworld','world_session':'world','expected_revision':1,'start_pos':[0,64,0]}}
            backend=SimpleNamespace(has_ready_projection_output=lambda s:True,projection_jev_enabled=True,
                                    advise_projection_supply=lambda *a:(_ for _ in ()).throw(AssertionError('must build before advice')))
            job=MaterialJob(request,Path(tmp),backend);job.held={ITEM:3};job.snapshot=state(3)
            with patch.object(job,'_build_batch') as build:
                self.assertIsNone(job._projection_batch({ITEM:128}))
            build.assert_called_once_with()

    def test_real_backend_build_returns_supply_without_any_placement(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = model(3, 1); layout = layout_for(m)
            calls = []
            def request(op, **params):
                calls.append(op)
                self.assertEqual(op, 'projection_model')
                return {'world_session': 'world', 'projection_model': m}
            current = state(2)
            current['projection_selection'].update(min=[0,64,0], max=[2,64,0])
            client = SimpleNamespace(world='world', request=request, status=lambda: current)
            backend = FlatMapBackend.__new__(FlatMapBackend)
            backend.request = {'flat_map': {**CONFIG, 'content_hash': m['content_hash']}}
            @contextmanager
            def action(name):
                self.assertEqual(name, 'build')
                yield client, Path(tmp)
            backend.action = action; backend.prepare_travel = lambda: None
            backend.refresh_audit = lambda: audit(layout, {})
            backend._safe_flat = lambda c, l: state(2)
            receipt = backend.build('ship')
            self.assertEqual((receipt['phase'], receipt['placed'], receipt['requirements']), ('waiting', 0, {ITEM: 5}))
            self.assertEqual(calls, ['projection_model'])

    def test_depot_return_loads_model_before_build_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = model(3,1); layout = layout_for(m)
            current = state(2); current['pos'] = [0.5,100,160.5]
            current['projection_selection'].update(min=[0,64,0], max=[2,64,0])
            calls = []
            def request(op, **params):
                calls.append(op)
                self.assertEqual(op, 'projection_model')
                self.assertLess(math.dist(current['pos'], [1.5,100,.5]), 1)
                return {'world_session':'world', 'projection_model':m}
            client = SimpleNamespace(world='world', request=request, status=lambda: current)
            backend = FlatMapBackend.__new__(FlatMapBackend)
            backend.request = {'flat_map':{**CONFIG,'content_hash':m['content_hash']}}
            backend.checkpoint = lambda: None
            @contextmanager
            def action(name):
                yield client, Path(tmp)
            backend.action = action; backend.prepare_travel = lambda: None
            backend.refresh_audit = lambda: audit(layout,{})
            backend._safe_flat = lambda c,l: current
            def travel(c,target,checkpoint,trace,*,keep_cruise):
                self.assertTrue(keep_cruise);current['pos']=target;calls.append('return_to_model')
            with patch('material_jobs.acquisition._travel',side_effect=travel), \
                    patch('material_jobs.navigation.lift_for_travel',return_value=current):
                result=backend.build('ship')
            self.assertEqual(result['phase'],'waiting')
            self.assertEqual(calls,['return_to_model','projection_model'])

    def test_remote_quarry_return_segments_before_loading_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = model(3,1); layout = layout_for(m)
            current = state(2); current['pos'] = [-400.5,100,400.5]
            current['projection_selection'].update(min=[0,64,0], max=[2,64,0])
            calls = []
            def request(op, **params):
                calls.append(op)
                self.assertEqual(op, 'projection_model')
                self.assertLess(math.dist(current['pos'], [1.5,100,.5]), 1)
                return {'world_session':'world', 'projection_model':m}
            client = SimpleNamespace(world='world', request=request, status=lambda: current)
            backend = FlatMapBackend.__new__(FlatMapBackend)
            backend.request = {'flat_map':{**CONFIG,'content_hash':m['content_hash']}}
            backend.checkpoint = lambda: None
            @contextmanager
            def action(name):
                yield client, Path(tmp)
            backend.action = action; backend.prepare_travel = lambda: None
            backend.refresh_audit = lambda: audit(layout,{})
            backend._safe_flat = lambda c,l: current
            def travel(c,target,checkpoint,trace,*,keep_cruise):
                self.assertTrue(keep_cruise)
                self.assertLessEqual(math.hypot(current['pos'][0]-target[0],current['pos'][2]-target[2]),256.00001)
                current['pos']=target;calls.append('return_to_model')
            with patch('material_jobs.acquisition._travel',side_effect=travel), \
                    patch('material_jobs.navigation.lift_for_travel',return_value=current):
                result=backend.build('ship')
            self.assertEqual(result['phase'],'waiting')
            self.assertEqual(calls,['return_to_model','return_to_model','return_to_model','projection_model'])

    def test_uncertain_return_keeps_segment_without_a_second_navigation(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'projection-loading'
            current = state(4); current['pos'] = [-400.5,100,400.5]
            backend = FlatMapBackend.__new__(FlatMapBackend)
            backend.checkpoint = lambda: None
            client = SimpleNamespace(status=lambda:current)
            with patch('material_jobs.acquisition._travel', side_effect=RuntimeError('native outcome unknown')) as travel, \
                    patch('material_jobs.navigation.lift_for_travel',return_value=current):
                with self.assertRaisesRegex(RuntimeError, 'outcome unknown'):
                    backend.travel_to_projection(client,[1.5,100,.5],'ship',out)
            travel.assert_called_once()
            trace=json.loads((out/'model-loading-travel.json').read_text())
            self.assertEqual(trace[0]['final_target'],[1.5,100,.5])
            self.assertEqual(trace[0]['segment'],1)

    def test_flat_initial_loading_uses_center_with_current_safe_height(self):
        backend=FlatMapBackend.__new__(FlatMapBackend)
        client=SimpleNamespace(status=lambda:{'pos':[0,145,500]})
        self.assertEqual([64.,145,64.], backend.projection_loading_target(
            client,{'min':[0,64,0],'max':[127,64,127]}))

    def test_existing_scheduler_mines_smelts_places_resupplies_and_finishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); jar = root / 'recipes.jar'
            with zipfile.ZipFile(jar, 'w') as archive:
                archive.writestr('data/minecraft/recipe/stone.json', json.dumps({
                    'type': 'minecraft:smelting', 'ingredient': 'minecraft:cobblestone',
                    'result': {'id': ITEM}, 'cookingtime': 200}))
            backend = SimulatedFlatBackend(ProcessingCatalog(jar))
            request = {'schema': 1, 'id': 'flat-test', 'mode': 'projection', 'targets': {},
                       'projection_key': 'ship', 'created_at': 1000,
                       'context': {'server': 'example.test', 'dimension': 'minecraft:overworld',
                                   'world_session': 'world', 'expected_revision': 1, 'start_pos': [0, 64, 0]}}
            result = MaterialJob(request, root / 'job', backend).run()
            self.assertEqual(result['state'], 'completed', result)
            self.assertEqual((result['done'], result['total'], backend.held[ITEM]), (20, 20, 2))
            self.assertTrue(any(c[0] == 'acquire' for c in backend.calls))
            self.assertTrue(any(c[0] == 'smelt' for c in backend.calls))
            self.assertTrue(any(c[0] == 'flat_build' for c in backend.calls))
            self.assertEqual(result['ai_calls'], 0)

    def test_default_cli_only_plans_offline_and_keeps_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); layout = FlatLayout(model(), CONFIG)
            data = {'model': model(), 'audit': audit(layout, {}), 'snapshot': state(8), 'policy': CONFIG}
            argv = []
            for key, value in data.items():
                path = root / (key + '.json'); path.write_text(json.dumps(value))
                argv.extend(['--' + key, str(path)])
            out = root / 'plan.json'; argv.extend(['--out', str(out)])
            with patch('projection_flat_backend.create_backend', side_effect=AssertionError('no live backend')):
                self.assertEqual(main(argv), 0)
            self.assertTrue(json.loads(out.read_text())['planning_only'])
            original = out.read_bytes()
            with self.assertRaises(FileExistsError): main(argv)
            self.assertEqual(out.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
