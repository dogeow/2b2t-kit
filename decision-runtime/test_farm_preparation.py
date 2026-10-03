import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from farm_preparation import (_Runner, _rows, PreparationWait, SCAN_SCOPE, assert_preparation_resolved, bucket_proved, journal_directory,
                              plan, preparation_lock, run, survey_rows, torch_candidates)
from test_potato_farm import FarmClient, row

SPEC = {'authorized': True, 'center': [0, 63, 0], 'radius': 1}

# Native timing/revision/cursor envelope and representative typed row copied
# from outputs/wheat-field-20261002/site-scan.json. The full scan was 17*7*13;
# this protocol fixture intentionally retains a row excerpt, not world state.
REAL_MULTIFRAME = {
    'phase': 'done', 'time': 1790938009512,
    'world_session': '4bc9f84b-c48f-45dc-8d8b-c7193ca0e64e', 'control_revision': 8,
    'scan_coherent': False, 'scan_started_at': 1790938009312, 'scan_ended_at': 1790938009512,
    'scan_start_tick': 78235, 'scan_end_tick': 78238, 'scan_elapsed_ticks': 3,
    'scan_start_revision': 8, 'scan_end_revision': 8, 'scan_cells_read': 1547, 'scan_total_cells': 1547,
    'scan_scope': 'loaded_client_cells_sampled_on_client_ticks_not_atomic_server_snapshot',
    'scan_entities': [],
    'scan_entity_scope': 'current_client_loaded_entities_intersecting_scan_AABB_sampled_at_scan_end_not_whole_herd',
    'blocks': [{'pos': [761024, 61, 797865], 'state': 'Block{minecraft:dirt}', 'solid': True,
                'replaceable': False, 'passable': False, 'fluid': False, 'block_entity': False,
                'block_light': 0, 'sky_light': 0, 'spawn_block_light': 0, 'spawn_sky_light': 0}]
}
REAL_SCAN_MIN, REAL_SCAN_MAX = [761024, 61, 797865], [761040, 67, 797877]


class PreparationClient(FarmClient):
    def __init__(self, root, water=True, light=9):
        super().__init__()
        self.root = Path(root); self.last = ''; self.out = self.root / 'control'
        self.extra['bucket_water_protocol'] = 1
        self.bad_bucket = False; self.unknown = None; self.no_torch_change = False; self.multiframe = False
        self.light_after_torch = 9
        if not water:
            self.rows[(0, 63, 0)] = row([0, 63, 0], 'Block{minecraft:dirt}')
        for r in self.rows.values(): r['spawn_block_light'] = light
        for slot, item, count in [(11, 'torch', 4), (12, 'water_bucket', 1),
                                  (13, 'bucket', 1), (14, 'diamond_shovel', 1)]:
            self.inv[slot].update(item='minecraft:' + item, count=count)

    def request(self, op, **params):
        self.last = 'native-' + str(len(self.calls) + 1)
        if op == self.unknown:
            self.calls.append((op, copy.deepcopy(params)))
            return {**self.status(), 'id': self.last, 'phase': 'waiting'}
        if op in ('scan', 'select_item'):
            if op == 'scan' and self.multiframe: self.time += 200
            result = super().request(op, **params)
            result.update(id=self.last, phase='done')
            if op == 'scan':
                volume = math.prod(b-a+1 for a, b in zip(params['min'], params['max']))
                elapsed = 3 if self.multiframe else 0; duration = 200 if self.multiframe else 0
                end = result['time']; tick = end // 50; revision = result['control_revision']
                result.update(scan_coherent=not self.multiframe, scan_scope=SCAN_SCOPE,
                    scan_started_at=end-duration, scan_ended_at=end, scan_start_tick=tick-elapsed,
                    scan_end_tick=tick, scan_elapsed_ticks=elapsed, scan_start_revision=revision,
                    scan_end_revision=revision, scan_cells_read=volume, scan_total_cells=volume)
            return result
        self.calls.append((op, copy.deepcopy(params)))
        if op == 'navigate':
            self.extra['pos'] = params['target'][:]
            return {**self.status(), 'id': self.last, 'phase': 'done',
                    'material_air_navigation': {'phase': 'confirmed', 'outcome': 'done',
                                                'stable_ticks': 8, 'restored_ticks': 8}}
        pos = tuple(params['pos']); hand = self.inv[self.selected]
        if op == 'mine_block':
            assert self.rows[pos]['state'] == params['expected_state']
            self.rows.pop(pos)
            return {**self.status(), 'id': self.last, 'phase': 'done',
                    'server_confirmed': True, 'outcome_pending': False,
                    'confirmation_scope': 'single_target_server_block_update_and_native_sequence_ack',
                    'server_update_seen': True, 'server_observed_state': 'Block{minecraft:air}',
                    'native_sequence': 3, 'server_ack_sequence': 3, 'mining_target': list(pos)}
        if op in ('bucket_fill', 'bucket_place'):
            before = self.status()
            hand.update(item='minecraft:water_bucket' if op == 'bucket_fill' else 'minecraft:bucket', count=1)
            if op == 'bucket_place':
                self.rows[pos] = row(pos, 'Block{minecraft:water}[level=0]', False, True)
            after = self.status()
            counts = lambda s, item: sum(r['count'] for r in s['inventory'] if r['slot'] < 36 and r['item'] == item)
            proof = {'request_id': self.last, 'world_session': self.world, 'operation': op,
                     'pos': list(pos), 'use_count': 1, 'confirmed': not self.bad_bucket,
                     'unknown_outcome': self.bad_bucket, 'server_block_update_seen': True,
                     'server_block_confirmed': True, 'server_inventory_update_seen': True,
                     'server_inventory_confirmed': True, 'automatic_retry_allowed': False,
                     'server_observed_state': self.rows.get(pos, {}).get('state', 'Block{minecraft:air}'),
                     'expected_state_before': params['expected_state'],
                     'confirmation_scope': 'post_single_normal_use_current_connection_target_block_and_selected_bucket_slot_server_packets_plus_vanilla_prediction_settled_and_exact_inventory_delta_after_8_ticks'}
            for name, item in [('empty_buckets', 'minecraft:bucket'), ('water_buckets', 'minecraft:water_bucket')]:
                proof[name + '_before'] = counts(before, item); proof[name + '_after'] = counts(after, item)
            return {**after, 'id': self.last, 'phase': 'done', 'bucket_water': proof}
        if op == 'interact':
            assert hand['item'] == 'minecraft:torch'
            target = (pos[0], pos[1] + 1, pos[2])
            if not self.no_torch_change:
                self.rows[target] = row(target, 'Block{minecraft:torch}', False)
                hand['count'] -= 1
                if not hand['count']: hand['item'] = 'minecraft:air'
                for r in self.rows.values(): r['spawn_block_light'] = self.light_after_torch
            return {**self.status(), 'id': self.last, 'phase': 'done'}
        raise AssertionError(op)

    def mutations(self): return [op for op, _ in self.calls if op != 'scan']

    def checked(self, op, **params):
        reply = self.request(op, **params)
        if reply['phase'] != 'done': raise RuntimeError('unknown native outcome')
        return reply


class PreparationTest(unittest.TestCase):
    def test_actual_multiframe_envelope_is_complete_despite_non_atomic_sampling(self):
        result = _rows(copy.deepcopy(REAL_MULTIFRAME), REAL_SCAN_MIN, REAL_SCAN_MAX)
        self.assertEqual({(761024, 61, 797865)}, set(result))
        protected = copy.deepcopy(REAL_MULTIFRAME)
        protected['blocks'].append({'pos': [761036, 64, 797871], 'state': 'Block{minecraft:barrel}[facing=east,open=false]',
                                    'solid': True, 'passable': False, 'fluid': False, 'block_entity': True})
        with self.assertRaises(PreparationWait) as error: _rows(protected, REAL_SCAN_MIN, REAL_SCAN_MAX)
        self.assertEqual('WAIT_CONTAINER', error.exception.code)

    def test_multiframe_scan_rejects_incomplete_cross_revision_and_invalid_timing(self):
        invalid = [('scan_cells_read', 1546), ('scan_total_cells', 1546), ('scan_cells_read', True),
                   ('scan_start_revision', 7), ('scan_end_revision', 9), ('control_revision', 9),
                   ('scan_scope', 'atomic_server_snapshot'), ('scan_started_at', 0),
                   ('scan_started_at', 1790938009513), ('scan_ended_at', 1790938040000),
                   ('scan_elapsed_ticks', 2), ('scan_end_tick', 78234), ('scan_coherent', True),
                   ('time', 1790938009300), ('unloaded_chunks', 1)]
        for key, value in invalid:
            with self.subTest(key=key):
                reply = copy.deepcopy(REAL_MULTIFRAME); reply[key] = value
                with self.assertRaises(PreparationWait) as error: _rows(reply, REAL_SCAN_MIN, REAL_SCAN_MAX)
                self.assertEqual('WAIT_SCAN', error.exception.code)
        reply = copy.deepcopy(REAL_MULTIFRAME); reply.pop('scan_total_cells')
        with self.assertRaises(PreparationWait): _rows(reply, REAL_SCAN_MIN, REAL_SCAN_MAX)

    def test_complete_multiframe_field_still_requires_two_distinct_final_audits(self):
        with tempfile.TemporaryDirectory() as d:
            c = PreparationClient(d); c.multiframe = True
            result = run(c, {**SPEC, 'radius': 2}, Path(d) / 'proof', no_move=True)
            self.assertEqual('done', result['phase']); self.assertFalse(result['server_verified'])
            book = json.loads(Path(result['journal']).read_text())
            self.assertEqual(2, len(book['final_observed_times']))
            self.assertLess(*book['final_observed_times']); self.assertEqual([], c.mutations())

    def test_complete_scan_from_another_world_is_still_rejected_by_live_gate(self):
        with tempfile.TemporaryDirectory() as d:
            c = PreparationClient(d); native = c.request
            def request(op, **params):
                reply = native(op, **params)
                if op == 'scan': reply['world_session'] = 'foreign'
                return reply
            with patch.object(c, 'request', side_effect=request):
                result = run(c, SPEC, Path(d) / 'proof', no_move=True)
            self.assertEqual('WAIT_CONTROL', result['code']); self.assertEqual([], c.mutations())

    def test_explicit_small_plan_reuses_planting_cells(self):
        self.assertEqual(8, len(plan(SPEC)['cells']))
        for bad in ({}, {**SPEC, 'radius': 3}, {**SPEC, 'radius': True}, {**SPEC, 'center': [0.5, 63, 0]}):
            with self.assertRaises(ValueError): plan(bad)

    def test_registry_is_shared_by_crops_and_output_cannot_bypass_pending(self):
        with tempfile.TemporaryDirectory() as d:
            state = {'server': 'Example.COM:25565', 'dimension': 'minecraft:overworld', 'world_session': 'w'}
            directory, path = journal_directory(Path(d), state, SPEC)
            path.write_text('{"pending":{"op":"bucket_fill"}}')
            self.assertEqual((directory, path), journal_directory(Path(d), state, {**SPEC, 'crop': 'wheat'}))
            with self.assertRaises(PreparationWait): journal_directory(Path(d), state, SPEC, Path(d) / 'different')
            with self.assertRaises(PreparationWait): journal_directory(Path(d), {**state, 'world_session': 'new'}, SPEC)
            with self.assertRaises(PreparationWait): journal_directory(Path(d), state, {**SPEC, 'radius': 2})

    def test_prepared_source_needs_no_bucket_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            c = PreparationClient(d); c.inv[12].update(item='minecraft:air', count=0)
            result = run(c, SPEC, Path(d) / 'proof', no_move=True)
            self.assertEqual('done', result['phase']); self.assertEqual([], c.mutations())
            self.assertFalse(result['server_verified'])

    def test_one_center_soil_and_short_grass_only_are_mined(self):
        with tempfile.TemporaryDirectory() as d:
            c = PreparationClient(d, water=False)
            c.rows[(1, 64, 0)] = row([1, 64, 0], 'Block{minecraft:short_grass}', False)
            result = run(c, SPEC, Path(d) / 'proof', no_move=True)
            self.assertEqual('done', result['phase'])
            mined = [p['pos'] for op, p in c.calls if op == 'mine_block']
            self.assertEqual([[1, 64, 0], [0, 63, 0]], mined)
            self.assertEqual(1, c.mutations().count('bucket_place'))
            self.assertNotIn('bucket_fill', c.mutations())

    def test_bucket_done_without_exact_native_proof_retains_intent_and_never_repeats(self):
        with tempfile.TemporaryDirectory() as d:
            c = PreparationClient(d, water=False); c.bad_bucket = True
            result = run(c, SPEC, Path(d) / 'proof', no_move=True)
            self.assertEqual('WAIT_RECONCILE', result['code'])
            book = json.loads(Path(result['journal']).read_text()); self.assertEqual('bucket_place', book['pending']['op'])
            before = copy.deepcopy(c.calls)
            self.assertEqual('WAIT_RECONCILE', run(c, SPEC, Path(d) / 'proof', no_move=True)['code'])
            self.assertEqual(before, c.calls)

    def test_explicit_water_source_is_filled_once_before_center_excavation(self):
        with tempfile.TemporaryDirectory() as d:
            c = PreparationClient(d, water=False); c.inv[12].update(item='minecraft:air', count=0)
            source = [0, 63, 3]; c.rows[tuple(source)] = row(source, 'Block{minecraft:water}[level=0]', False, True)
            result = run(c, {**SPEC, 'water_source': source}, Path(d) / 'proof', no_move=True)
            self.assertEqual('done', result['phase']); self.assertEqual(1, c.mutations().count('bucket_fill'))
            self.assertLess(c.mutations().index('bucket_fill'), c.mutations().index('mine_block'))

    def test_missing_explicit_source_never_digs_or_searches_for_water(self):
        with tempfile.TemporaryDirectory() as d:
            c = PreparationClient(d, water=False); c.inv[12].update(item='minecraft:air', count=0)
            result = run(c, SPEC, Path(d) / 'proof', no_move=True)
            self.assertEqual('WAIT_WATER_SOURCE', result['code']); self.assertEqual([], c.mutations())

    def test_scan_rejects_containers_crops_flowing_water_entities_and_missing_headroom(self):
        for kind in ('container', 'crop', 'fluid', 'entity', 'head', 'wall', 'detail', 'unloaded'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                c = PreparationClient(d)
                if kind == 'container': c.rows[(2, 63, 0)]['block_entity'] = True
                elif kind == 'crop': c.rows[(1, 64, 0)] = row([1, 64, 0], 'Block{minecraft:wheat}[age=0]', False)
                elif kind == 'fluid': c.rows[(1, 64, 0)] = row([1, 64, 0], 'Block{minecraft:water}[level=1]', False, True)
                elif kind == 'entity': c.entities = [{'id': 1}]
                elif kind == 'head': c.rows[(1, 65, 0)] = row([1, 65, 0], 'Block{minecraft:stone}')
                elif kind == 'wall': c.rows.pop((1, 63, 0))
                elif kind == 'detail': c.rows[(1, 63, 0)].pop('solid')
                data = c.request('scan', min=plan(SPEC)['scan_min'], max=plan(SPEC)['scan_max'], details=True)
                if kind == 'unloaded': data['unloaded_chunks'] = 1
                with self.assertRaises(PreparationWait): survey_rows(data, plan(SPEC))

    def test_torch_support_can_be_one_lower_and_stays_outside_crop_cells(self):
        with tempfile.TemporaryDirectory() as d:
            c = PreparationClient(d, light=0); c.rows.pop((-2, 63, 0))
            data = c.request('scan', min=plan(SPEC)['scan_min'], max=plan(SPEC)['scan_max'], details=True)
            candidates = torch_candidates(survey_rows(data, plan(SPEC)), plan(SPEC))
            self.assertIn([-2, 62, 0], [p['support'] for p in candidates])
            result = run(c, SPEC, Path(d) / 'proof', no_move=True)
            self.assertEqual('done', result['phase']); self.assertEqual(1, result['torches_placed'])

    def test_geometry_never_substitutes_for_measured_crop_light(self):
        with tempfile.TemporaryDirectory() as d:
            c = PreparationClient(d, light=0); c.light_after_torch = 0
            result = run(c, SPEC, Path(d) / 'proof', no_move=True)
            self.assertEqual('WAIT_LIGHT', result['code']); self.assertEqual(4, result['torches_placed'])
            self.assertFalse(json.loads(Path(result['journal']).read_text()).get('pending'))

    def test_unknown_torch_keeps_intent_before_any_future_retry(self):
        with tempfile.TemporaryDirectory() as d:
            c = PreparationClient(d, light=0); c.no_torch_change = True
            result = run(c, SPEC, Path(d) / 'proof', no_move=True)
            self.assertEqual('WAIT_RECONCILE', result['code'])
            self.assertEqual('interact', json.loads(Path(result['journal']).read_text())['pending']['op'])

    def test_unknown_selection_mining_and_navigation_are_not_replayed(self):
        for op in ('select_item', 'mine_block', 'navigate'):
            with self.subTest(op=op), tempfile.TemporaryDirectory() as d:
                c = PreparationClient(d, water=False); c.unknown = op; c.extra['air_only_navigation_protocol'] = 2
                result = run(c, SPEC, Path(d) / 'proof', no_move=op != 'navigate')
                self.assertEqual('WAIT_RECONCILE', result['code'])
                self.assertEqual(op, json.loads(Path(result['journal']).read_text())['pending']['op'])
                calls = copy.deepcopy(c.calls)
                run(c, SPEC, Path(d) / 'proof', no_move=op != 'navigate')
                self.assertEqual(calls, c.calls)

    def test_air_route_is_scanned_and_only_normal_stable_navigation_is_used(self):
        with tempfile.TemporaryDirectory() as d:
            c = PreparationClient(d, water=False); c.extra['air_only_navigation_protocol'] = 2
            result = run(c, SPEC, Path(d) / 'proof')
            self.assertEqual('done', result['phase'])
            paths = [p for op, p in c.calls if op == 'navigate']
            self.assertTrue(paths); self.assertTrue(all(p['air_only'] is True and p['arrival'] == .25 for p in paths))

    def test_high_waiting_position_reuses_travel_and_unknown_descent_intent_is_not_replayed(self):
        center = [761029, 64, 797869]; target = [761029.5, 65.6, 797869.5]
        for unknown in (False, True):
            with self.subTest(unknown=unknown), tempfile.TemporaryDirectory() as d:
                c = PreparationClient(d); c.extra['pos'] = [761029.4574863483, 145, 797869.4468230433]
                c.extra['air_only_navigation_protocol'] = 2
                if unknown: c.unknown = 'navigate'
                path = Path(d) / 'journal.json'; book = {'actions': [], 'pending': None}
                runner = _Runner(c, plan({'authorized': True, 'center': center, 'radius': 2}),
                                 path, book, lambda: None, False, 4)
                native_checked = c.checked
                def checked(op, **params):
                    saved = json.loads(path.read_text())
                    self.assertEqual('navigate', saved['pending']['op'])
                    self.assertEqual(target, saved['pending']['params']['target'])
                    self.assertEqual(145, saved['pending']['before']['pos'][1])
                    return native_checked(op, **params)
                def travel(proxy, actual_target, checkpoint, trace, **margins):
                    self.assertEqual(target, actual_target)
                    self.assertEqual({'clearance_padding': 2.32, 'obstacle_margin': 5.1}, margins)
                    proxy.status(); checkpoint()
                    proxy.request('scan', min=[761029, 65, 797869], max=[761029, 147, 797869], details=True)
                    proxy.request('navigate', target=actual_target, arrival=.25, seconds=90, air_only=True)
                    trace.append({'target': actual_target, 'phase': 'done'})
                with patch('farm_preparation._travel', side_effect=travel) as delegated, patch.object(c, 'checked', side_effect=checked):
                    if unknown:
                        with self.assertRaises(PreparationWait): runner.go(center)
                        with self.assertRaises(PreparationWait): runner.go(center)
                        self.assertEqual('navigate', book['pending']['op'])
                    else:
                        runner.go(center); self.assertIsNone(book['pending'])
                        self.assertEqual('navigate', book['actions'][-1]['op'])
                    self.assertTrue(delegated.called)
                self.assertEqual(1, c.mutations().count('navigate'))

    def test_existing_crop_pending_cannot_be_bypassed_by_preparation_output(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); registry = root / 'farms' / 'crop' / 'registry.json'; registry.parent.mkdir(parents=True)
            planting = root / 'original'; planting.mkdir(); (planting / 'wheat-farm-id.json').write_text('{"pending":{"operation":"plant"}}')
            registry.write_text(json.dumps({'scope': {'server': 'server', 'dimension': 'minecraft:overworld',
                                                      'layout': {'center': SPEC['center'], 'crop': 'wheat'}}, 'directory': str(planting)}))
            with self.assertRaises(PreparationWait):
                journal_directory(root, {'server': 'server:25565', 'dimension': 'minecraft:overworld', 'world_session': 'w'}, SPEC)

    def test_unknown_cleanup_or_changed_source_blocks_before_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            c = PreparationClient(d); directory, path = journal_directory(c.root, {**c.status(), 'server': c.server}, SPEC, Path(d) / 'proof')
            path.write_text(json.dumps({'schema': 1, 'scope': {'server': 'server', 'dimension': 'minecraft:overworld', 'center': SPEC['center'], 'radius': 1},
                                       'world_session': c.world, 'water_source': None, 'actions': [], 'pending': None, 'cleanup_pending': {'op': 'pause'}}))
            self.assertEqual('WAIT_RECONCILE', run(c, SPEC, directory, no_move=True)['code'])
            self.assertEqual([], c.calls)
            with self.assertRaises(PreparationWait): run(c, {**SPEC, 'water_source': [0, 63, 3]}, directory, no_move=True)

    def test_bucket_proof_rejects_each_missing_or_foreign_confirmation(self):
        with tempfile.TemporaryDirectory() as d:
            c = PreparationClient(d, water=False); c.selected = 12; before = c.status()
            params = {'pos': [0, 63, 0], 'expected_state': 'Block{minecraft:air}'}
            reply = c.request('bucket_place', **params); after = c.status()
            self.assertTrue(bucket_proved('bucket_place', reply, c.world, c.last, params, before, after))
            for key, value in [('request_id', 'foreign'), ('world_session', 'old'), ('use_count', True),
                               ('confirmed', False), ('server_inventory_confirmed', False), ('server_block_confirmed', False),
                               ('empty_buckets_after', 99), ('operation', 'bucket_fill'), ('pos', [1, 63, 0])]:
                broken = copy.deepcopy(reply); broken['bucket_water'][key] = value
                with self.subTest(key=key): self.assertFalse(bucket_proved('bucket_place', broken, c.world, c.last, params, before, after))

    def test_missing_light_detail_stops_before_world_or_inventory_mutations(self):
        with tempfile.TemporaryDirectory() as d:
            c = PreparationClient(d, water=False); c.rows[(1, 63, 0)].pop('spawn_block_light')
            result = run(c, SPEC, Path(d) / 'proof', no_move=True)
            self.assertEqual('WAIT_SCAN', result['code']); self.assertEqual([], c.mutations())

    def test_known_water_or_torch_loss_never_restarts_confirmed_work(self):
        for kind in ('water', 'torch'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                c = PreparationClient(d, water=kind != 'water', light=0 if kind == 'torch' else 9)
                first = run(c, SPEC, Path(d) / 'proof', no_move=True); self.assertEqual('done', first['phase'])
                if kind == 'water': c.rows[(0, 63, 0)] = row([0, 63, 0], 'Block{minecraft:dirt}')
                else:
                    torch = next(p for p, r in c.rows.items() if r['state'] == 'Block{minecraft:torch}'); c.rows.pop(torch)
                before = c.mutations()[:]
                result = run(c, SPEC, Path(d) / 'proof', no_move=True)
                self.assertEqual('WAIT_RECONCILE', result['code']); self.assertEqual(before, c.mutations())

    def test_other_entrypoint_readonly_hook_blocks_pending_and_active_preparation(self):
        with tempfile.TemporaryDirectory() as d:
            state = {'server': 'server:25565', 'dimension': 'minecraft:overworld', 'world_session': 'w'}
            root = Path(d); directory, path = journal_directory(root, state, SPEC)
            path.write_text(json.dumps({'scope': {'server': 'server', 'dimension': 'minecraft:overworld', 'center': SPEC['center'], 'radius': 1},
                                       'world_session': 'w', 'pending': {'op': 'bucket_place'}}))
            with self.assertRaises(PreparationWait): assert_preparation_resolved(root, state, {**SPEC, 'crop': 'wheat'})
            with preparation_lock(root, state, SPEC):
                with self.assertRaises(PreparationWait): assert_preparation_resolved(root, state, SPEC)
            path.write_text(json.dumps({'scope': {'server': 'server', 'dimension': 'minecraft:overworld', 'center': SPEC['center'], 'radius': 1},
                                       'world_session': 'w', 'pending': None}))
            with preparation_lock(root, state, SPEC):
                assert_preparation_resolved(root, state, SPEC)


if __name__ == '__main__': unittest.main()
