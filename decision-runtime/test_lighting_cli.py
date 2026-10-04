"""Planning and later-frame evidence checks; never uses a game."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import lighting_cli as lighting
from potato_farm import ENTITY_SCOPE, ENTITY_SCOPE_AT_SCAN_END

LOW, HIGH = (0, 60, 0), (4, 90, 4)


def grass(x=2, y=63, z=2, **changes):
    return {**{'pos': [x, y, z], 'state': 'Block{minecraft:grass_block}[snowy=false]',
               'solid': True, 'fluid': False, 'block_entity': False, 'spawn_block_light': 0,
               'monster_spawn_block_light_limit': 0, 'zombie_spawn_floor': True,
               'zombie_block_light_risk': True}, **changes}


def inventory(count):
    return [{'slot': i, 'item': lighting.TORCH if i == 0 else 'minecraft:air',
             'count': count if i == 0 else 0} for i in range(36)]


def snapshot(count=8, tick=100):
    return {'world_session': 'world-a', 'time': tick, 'connected': True,
            'control_revision': 7, 'manual_movement': False, 'guard_armed': True,
            'guard_pve_only': True, 'flight': True, 'health': 20, 'food': 20,
            'recent_hurt_at': 0, 'inventory': inventory(count), 'entities': [],
            'hand': {'item': lighting.TORCH, 'count': count},
            'pos': [2.5, 65.5, 2.5]}


class FakeClient:
    def __init__(self, root, unknown=False):
        self.root = Path(root)
        self.world, self.task, self.rev = 'world-a', 'task-a', 7
        self.tick, self.interacted, self.unknown, self.interactions = 100, False, unknown, 0
        self.heartbeat = type('Heartbeat', (), {'id': 'owner-a'})()
        self.finished = 0
        self.progress = []

    def start_progress(self, title, total, done=0, phase='准备中'):
        self.progress.append({'title': title, 'total': total, 'done': done, 'phase': phase})

    def set_progress(self, *, done=None, phase=None):
        self.progress.append({'done': done, 'phase': phase})

    def request(self, op, **params):
        if op == 'snapshot':
            self.tick += 1
            return snapshot(7 if self.interacted and not self.unknown else 8, self.tick)
        if op == 'scan':
            if params['min'] == [2, 64, 2] and params['max'] == [2, 64, 2]:
                rows = [] if self.unknown else [{'pos': [2, 64, 2], 'state': 'Block{minecraft:torch}'}]
            elif params['min'][1] >= 66:
                rows = []
            else:
                rows = [grass()]
            return {'world_session': self.world, 'phase': 'done', 'blocks': rows, 'scan_entities': [],
                    'scan_entity_scope': ENTITY_SCOPE_AT_SCAN_END}
        raise AssertionError('Unexpected request ' + op)

    def checked(self, op, **params):
        if op == 'interact':
            self.interacted = True
            self.interactions += 1
        elif op not in ('select_item', 'material_job_park'):
            raise AssertionError('Unexpected operation ' + op)
        return {'phase': 'done', 'id': 'request-a'}

    def finish(self):
        self.finished += 1


class ObservedClient(FakeClient):
    def __init__(self, root, states):
        super().__init__(root)
        self.states, self.operations = list(states), []
        self.park_target = [2.5, 88, 2.5]

    def observe(self):
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]

    def request(self, op, **params):
        self.operations.append(op)
        return self.observe() if op == 'snapshot' else super().request(op, **params)

    def raw(self):
        self.operations.append('raw')
        return self.observe()

    def park_near(self, state):
        return lighting.math.dist(state['pos'], self.park_target) <= 2


def parking_frame(*, kind='parking', revision=8, tick=105):
    return {**snapshot(tick=tick), 'pos': [2.5, 88, 2.5], 'control_revision': revision,
            'supervision_lease': {'id': 'owner-a', 'kind': kind, 'world_session': 'world-a',
                                  'job_session': 'task-a', 'revision': revision,
                                  'remote_finish': 'guard', 'park_target': [2.5, 88, 2.5]},
            'supervision_safety': {'lease': 'owner-a', 'job_session': 'task-a',
                                   'action': 'KEEP_PVE_GUARD', 'cause': 'controller_finished',
                                   'time': tick}}


class LightingPlanningTests(unittest.TestCase):
    def test_native_volume_cap_uses_inclusive_cells(self):
        lighting.bounds([0, 0, 0], [49, 19, 49])
        with self.assertRaisesRegex(ValueError, '50,000'):
            lighting.bounds([0, 0, 0], [49, 20, 49])

    def test_helper_budget_rejects_boolean_zero_or_unbounded_runs(self):
        for value in (True, 0, 65, 1.5):
            with self.assertRaises(ValueError):
                lighting.plan({'blocks': [grass()]}, LOW, HIGH, value)

    def test_actual_dark_safe_floor_and_full_roof_required(self):
        cells = {(2, 63, 2): grass()}
        self.assertEqual(len(lighting.candidates(cells, LOW, HIGH)), 1)
        for change in ({'spawn_block_light': 1}, {'block_entity': True}, {'solid': False},
                       {'fluid': True}, {'spawn_block_light': None}, {'state': 'Block{minecraft:farmland}'}):
            self.assertEqual(lighting.candidates({(2, 63, 2): grass(**change)}, LOW, HIGH), [])
        cells[(2, 80, 2)] = {'state': 'Block{minecraft:oak_leaves}', 'pos': [2, 80, 2]}
        self.assertEqual(lighting.candidates(cells, LOW, HIGH), [])

    def test_explicit_safe_ground_allows_dirt_stone_and_stable_beach_sand(self):
        for name in ('dirt', 'stone', 'cobblestone', 'stone_bricks', 'sand', 'red_sand'):
            with self.subTest(name=name):
                rows = {(2, 63, 2): grass(state=f'Block{{minecraft:{name}}}')}
                self.assertEqual(len(lighting.candidates(rows, LOW, HIGH)), 1)
        for name in ('farmland', 'dirt_path', 'oak_planks', 'chest', 'water',
                     'potatoes', 'magma_block', 'soul_sand', 'unknown'):
            with self.subTest(name=name):
                self.assertEqual(lighting.candidates(
                    {(2, 63, 2): grass(state=f'Block{{minecraft:{name}}}')}, LOW, HIGH), [])
        for changes in ({'fluid': True}, {'block_entity': True}, {'solid': False}):
            self.assertEqual(lighting.candidates(
                {(2, 63, 2): grass(state='Block{minecraft:sand}', **changes)}, LOW, HIGH), [])
        self.assertEqual(lighting.candidates({(2, 63, 2): grass(), (2, 64, 2): {
            'pos': [2, 64, 2], 'state': 'Block{minecraft:short_grass}'}}, LOW, HIGH), [])

    def test_live_scan_requires_known_bounded_entity_scope_and_list(self):
        base = {'phase': 'done', 'world_session': 'world-a', 'blocks': [grass()], 'scan_entities': []}
        for scope in (ENTITY_SCOPE, ENTITY_SCOPE_AT_SCAN_END):
            self.assertEqual(len(lighting.scan_cells({**base, 'scan_entity_scope': scope}, LOW, HIGH, 'world-a')), 1)
        for scope in (None, '', 'all_server_entities', [], True):
            with self.subTest(scope=scope), self.assertRaisesRegex(lighting.LightingBlocked, 'entity scope'):
                lighting.scan_cells({**base, 'scan_entity_scope': scope}, LOW, HIGH, 'world-a')
        with self.assertRaisesRegex(lighting.LightingBlocked, 'entity scope'):
            lighting.scan_cells({**base, 'scan_entity_scope': ENTITY_SCOPE_AT_SCAN_END,
                                 'scan_entities': None}, LOW, HIGH, 'world-a')

    def test_live_scan_rejects_pending_even_with_valid_scope(self):
        base = {'world_session': 'world-a', 'blocks': [grass()], 'scan_entities': [],
                'scan_entity_scope': ENTITY_SCOPE_AT_SCAN_END}
        for phase in (None, 'running', 'waiting'):
            with self.assertRaisesRegex(lighting.LightingBlocked, 'Complete'):
                lighting.scan_cells({**base, 'phase': phase}, LOW, HIGH, 'world-a')

    def test_large_movement_authorization_is_not_one_native_scan(self):
        movement = {'min': [-1000, 60, -1000], 'max': [1000, 142, 1000]}
        self.assertEqual(lighting.validate_movement_bounds(movement, LOW, HIGH),
                         ((-1000, 60, -1000), (1000, 142, 1000)))
        with self.assertRaisesRegex(ValueError, '50,000'):
            lighting.bounds(movement['min'], movement['max'])
        for bad in ({'min': [1, 60, 0], 'max': [4, 90, 4]},
                    {'min': [0, 60, 0], 'max': [4, 320, 4]},
                    {'min': [False, 60, 0], 'max': [4, 90, 4]}):
            with self.assertRaises(ValueError):
                lighting.validate_movement_bounds(bad, LOW, HIGH)

    def test_explicit_movement_box_allows_actual_guard_drift_without_expanding_targets(self):
        class PositionClient(FakeClient):
            def __init__(self, root):
                super().__init__(root)
                self.pos, self.scans, self.moves = [-.1, 65.5, 2.5], [], []
            def request(self, op, **params):
                if op == 'snapshot':
                    self.tick += 1
                    return {**snapshot(tick=self.tick), 'pos': self.pos}
                if op == 'scan':
                    self.scans.append(params)
                    return {'phase': 'done', 'world_session': self.world, 'blocks': [],
                            'scan_entity_scope': ENTITY_SCOPE_AT_SCAN_END, 'scan_entities': []}
                return super().request(op, **params)
            def checked(self, op, **params):
                if op == 'navigate':
                    self.moves.append(params)
                    self.pos = params['target']
                    return {'phase': 'done'}
                return super().checked(op, **params)
        with tempfile.TemporaryDirectory() as folder:
            client = PositionClient(folder)
            default = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
            with self.assertRaisesRegex(lighting.LightingBlocked, 'movement bounds'):
                default.move([2.5, 65.5, 2.5])
            self.assertEqual(client.moves, [])
            self.assertEqual(client.scans, [])
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot(),
                                          movement_bounds={'min': [-2, 60, -2], 'max': [6, 90, 6]})
            runner.move([2.5, 65.5, 2.5])
            self.assertEqual(len(client.moves), 1)
            self.assertTrue(client.moves[0]['air_only'])
            self.assertEqual(client.scans[0]['min'], [-1, 65, 2])
            candidate = {'support': [5, 63, 2], 'target': [5, 64, 2],
                         'support_state': 'Block{minecraft:sand}'}
            with self.assertRaisesRegex(lighting.LightingBlocked, 'inconsistent placement'):
                runner.place(candidate, 0)
            self.assertEqual(client.interactions, 0)
            self.assertEqual(runner.report['bounds']['max'], list(HIGH))
            self.assertEqual(runner.report['movement_bounds']['max'], [6, 90, 6])

    def test_protected_support_or_target_never_becomes_candidate(self):
        cells = {(2, 63, 2): grass()}
        for y in (63, 64):
            protected = lighting.protection_boxes([{'min': [2, y, 2], 'max': [2, y, 2]}])
            self.assertEqual(lighting.candidates(cells, LOW, HIGH, protected=protected), [])
            self.assertEqual(lighting.risk_counts(cells, protected)['protected_dark_floor'], 1)
            self.assertEqual(lighting.risk_counts(cells, protected)['unprotected_dark_floor'], 0)
        protected = [{'min': [3, 60, 2], 'max': [3, 90, 2]}]
        self.assertEqual(len(lighting.candidates(cells, LOW, HIGH, protected=protected)), 1)

    def test_masks_validate_without_native_scan_volume_restriction(self):
        lighting.protection_boxes([{'min': [0, -64, 0], 'max': [1000, 319, 1000]}])
        for value in ({'min': [0, 1, 0], 'max': [0, 0, 0]},
                      {'min': [True, 60, 0], 'max': [4, 90, 4]},
                      {'min': [0, 60, 0], 'max': [4, 320, 4]},
                      {'min': [0, 60, 0], 'max': [4, 90, 4], 'name': 'ignored'}):
            with self.assertRaises(ValueError):
                lighting.protection_boxes([value])

    def test_duplicate_and_outside_scan_rows_fail_closed(self):
        for rows in ([grass(), grass()], [grass(x=6)]):
            with self.assertRaises(lighting.LightingBlocked):
                lighting.scan_cells({'blocks': rows}, LOW, HIGH)

    def test_route_compression_preserves_turns_and_avoids_body_obstacle(self):
        cells = {(2, 66, 1): {'state': 'Block{minecraft:stone}'}}
        route = lighting.cardinal_route(cells, [1.5, 65.5, 1.5], [3, 63, 1], 65.5, LOW, HIGH)
        self.assertIsNotNone(route)
        self.assertNotIn((2, 1), route)
        compressed = lighting.compress_route(route)
        self.assertLess(len(compressed), len(route))
        self.assertEqual((compressed[0], compressed[-1]), (route[0], route[-1]))
        self.assertEqual(lighting.compress_route([(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]),
                         [(0, 0), (2, 0), (2, 2)])

    def test_exact_inventory_requires_all_distinct_backpack_slots(self):
        self.assertEqual(lighting.stock(snapshot()), 8)
        for rows in (inventory(8)[:-1], inventory(8) + [inventory(8)[0]]):
            with self.assertRaises(lighting.LightingBlocked):
                lighting.stock({'inventory': rows})

    def test_proof_rejects_same_frame_wrong_world_or_nonexact_delta(self):
        target = [2, 64, 2]
        reply = {'phase': 'done', 'world_session': 'world-a', 'blocks': [{'pos': target, 'state': 'Block{minecraft:torch}'}],
                 'scan_entity_scope': ENTITY_SCOPE_AT_SCAN_END, 'scan_entities': []}
        self.assertTrue(lighting.later_torch_frame(reply, snapshot(7, 101), target, 'world-a', 8, 100))
        self.assertFalse(lighting.later_torch_frame(reply, snapshot(7, 100), target, 'world-a', 8, 100))
        self.assertFalse(lighting.later_torch_frame(reply, snapshot(6, 101), target, 'world-a', 8, 100))
        with self.assertRaises(lighting.LightingBlocked):
            lighting.later_torch_frame(reply, snapshot(7, 101), target, 'world-b', 8, 100)

    def test_offline_cli_never_loads_client_or_game_state(self):
        with tempfile.TemporaryDirectory() as folder:
            scan = Path(folder) / 'saved.json'
            scan.write_text(json.dumps({'blocks': [grass()]}))
            with patch.dict('sys.modules', {'material_client': None}), patch('builtins.print'):
                status = lighting.main(['--min', '0', '60', '0', '--max', '4', '90', '4',
                                        '--max-torches', '2', '--out', folder, '--plan-only', '--scan', str(scan)])
            self.assertEqual(status, 0)
            report = json.loads((Path(folder) / 'plan.json').read_text())
            self.assertFalse(report['cave_routes_completed'])
            self.assertEqual(len(report['candidates']), 1)

    def test_cli_masks_filter_saved_plan_and_report_excluded_darkness(self):
        with tempfile.TemporaryDirectory() as folder:
            scan = Path(folder) / 'saved.json'
            scan.write_text(json.dumps({'blocks': [grass()]}))
            protected = Path(folder) / 'protected.json'
            protected.write_text(json.dumps([{'min': [0, 60, 0], 'max': [1, 90, 1]}]))
            with patch.dict('sys.modules', {'material_client': None}), patch('builtins.print'):
                status = lighting.main(['--min', '0', '60', '0', '--max', '4', '90', '4',
                                        '--out', folder, '--plan-only', '--scan', str(scan),
                                        '--protect-file', str(protected),
                                        '--protect-box', '2', '64', '2', '2', '64', '2'])
            self.assertEqual(status, 0)
            report = json.loads((Path(folder) / 'plan.json').read_text())
            self.assertEqual(report['candidates'], [])
            self.assertEqual(report['counts']['zombie_block_light_risk'], 1)
            self.assertEqual(report['counts']['protected_dark_floor'], 1)
            self.assertEqual(len(report['protected_boxes']), 2)

    def test_runtime_rechecks_mask_even_for_stale_external_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            client = FakeClient(folder)
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot(),
                                          protected=[{'min': [2, 64, 2], 'max': [2, 64, 2]}])
            candidate = lighting.candidates({(2, 63, 2): grass()}, LOW, HIGH)[0]
            with self.assertRaisesRegex(lighting.LightingBlocked, 'Protected'):
                runner.place(candidate, 0)
            self.assertEqual(client.interactions, 0)
            self.assertFalse(runner.intent_path(candidate['target']).exists())

    def test_external_candidate_outside_job_bounds_never_dispatches(self):
        with tempfile.TemporaryDirectory() as folder:
            client = FakeClient(folder)
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
            candidate = {'support': [6, 63, 2], 'target': [6, 64, 2],
                         'support_state': 'Block{minecraft:grass_block}[snowy=false]'}
            with self.assertRaisesRegex(lighting.LightingBlocked, 'Protected or inconsistent'):
                runner.place(candidate, 0)
            self.assertEqual(client.interactions, 0)

    def test_runtime_rejects_roof_above_survey_ceiling_before_interaction(self):
        class RoofClient(FakeClient):
            def request(self, op, **params):
                reply = super().request(op, **params)
                if op == 'scan' and params['max'][1] == 319:
                    reply['blocks'].append({'pos': [2, 120, 2], 'state': 'Block{minecraft:stone}'})
                return reply
        with tempfile.TemporaryDirectory() as folder:
            client = RoofClient(folder)
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
            candidate = lighting.candidates({(2, 63, 2): grass()}, LOW, HIGH)[0]
            with self.assertRaisesRegex(lighting.LightingBlocked, 'roof column changed'):
                runner.place(candidate, 0)
            self.assertEqual(client.interactions, 0)

    def test_runtime_rechecks_real_light_and_safe_support_before_interaction(self):
        class RelitClient(FakeClient):
            def request(self, op, **params):
                reply = super().request(op, **params)
                if op == 'scan' and params['max'][1] == 319:
                    reply['blocks'][0]['spawn_block_light'] = 10
                    reply['blocks'][0]['zombie_block_light_risk'] = False
                return reply
        with tempfile.TemporaryDirectory() as folder:
            client = RelitClient(folder)
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
            candidate = lighting.candidates({(2, 63, 2): grass()}, LOW, HIGH)[0]
            with self.assertRaises(lighting.LightingBlocked):
                runner.place(candidate, 0)
            self.assertEqual(client.interactions, 0)

    def test_two_later_frames_verify_one_interaction(self):
        with tempfile.TemporaryDirectory() as folder:
            client = FakeClient(folder)
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
            candidate = lighting.candidates({(2, 63, 2): grass()}, LOW, HIGH)[0]
            with patch('lighting_cli.time.sleep'):
                runner.place(candidate, 0)
            self.assertEqual(client.interactions, 1)
            self.assertEqual(runner.report['placed'][0]['later_verified_frames'], 2)
            self.assertEqual(runner.report['progress']['placed_verified'], 1)
            self.assertEqual(runner.report['progress']['placement_limit'], 1)
            self.assertEqual(client.progress[0]['title'], '岛屿补光')
            self.assertEqual(client.progress[0]['total'], 1)
            self.assertEqual(client.progress[-1]['done'], 1)
            self.assertIn('no_dedicated_ack', runner.report['evidence_scope'])
            self.assertEqual(json.loads(runner.intent_path(candidate['target']).read_text())['state'], 'verified')

    def test_guard_displacement_reapproaches_before_any_interaction(self):
        class DisplacedClient(FakeClient):
            def __init__(self, root):
                super().__init__(root)
                self.pos = [4.36, 67.14, 2.86]
                self.order = []
            def request(self, op, **params):
                if op == 'snapshot':
                    self.tick += 1
                    return {**snapshot(7 if self.interacted else 8, self.tick), 'pos': self.pos}
                if op == 'scan':
                    rows = [grass()]
                    if self.interacted:
                        rows += [{'pos': [2, 64, 2], 'state': 'Block{minecraft:torch}'}]
                    rows = [row for row in rows if all(params['min'][i] <= row['pos'][i] <= params['max'][i]
                                                      for i in range(3))]
                    return {'phase': 'done', 'world_session': self.world, 'blocks': rows,
                            'scan_entity_scope': ENTITY_SCOPE_AT_SCAN_END, 'scan_entities': []}
                return super().request(op, **params)
            def checked(self, op, **params):
                self.order.append(op)
                if op == 'navigate':
                    self.pos = params['target']
                    return {'phase': 'done', 'id': 'position-reapproach'}
                if op == 'interact':
                    self.asserted_dispatch_pos = list(self.pos)
                return super().checked(op, **params)
        with tempfile.TemporaryDirectory() as folder:
            client = DisplacedClient(folder)
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
            candidate = lighting.candidates({(2, 63, 2): grass()}, LOW, HIGH)[0]
            with patch('lighting_cli.time.sleep'):
                runner.place(candidate, 0)
            self.assertEqual(client.order, ['navigate', 'select_item', 'interact'])
            self.assertEqual(client.asserted_dispatch_pos, [2.5, 65.5, 2.5])
            self.assertEqual(client.interactions, 1)
            self.assertEqual(runner.report['station_reapproaches'][0]['route'], 'fresh_clear_sweep')

    def test_repeated_station_changes_never_create_intent_or_click_old_target(self):
        with tempfile.TemporaryDirectory() as folder:
            client = FakeClient(folder)
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
            candidate = lighting.candidates({(2, 63, 2): grass()}, LOW, HIGH)[0]
            displaced = {**snapshot(), 'pos': [4.2, 67.5, 2.5]}
            with patch.object(runner, 'wait_for_guard', return_value=displaced), \
                    patch.object(runner, 'approach_station') as approach:
                with self.assertRaisesRegex(lighting.LightingBlocked, 'repeatedly changed'):
                    runner.place(candidate, 0)
            self.assertEqual(approach.call_count, 3)
            self.assertEqual(client.interactions, 0)
            self.assertFalse(runner.intent_path(candidate['target']).exists())

    def test_movement_to_old_station_requires_fresh_clear_sweep(self):
        class BlockedRun(lighting.LightingRun):
            def move(self, target):
                raise lighting.LightingBlocked('Fresh movement body sweep is occupied')
        with tempfile.TemporaryDirectory() as folder:
            client = FakeClient(folder)
            runner = BlockedRun(client, LOW, HIGH, 1, folder, snapshot())
            candidate = lighting.candidates({(2, 63, 2): grass()}, LOW, HIGH)[0]
            displaced = {**snapshot(), 'pos': [4.2, 67.5, 2.5]}
            with (
                patch.object(runner, 'wait_for_guard', return_value=displaced),
                patch.object(runner, 'scan', return_value={'blocks': [
                    {'pos': [3, 66, 2], 'state': 'Block{minecraft:stone}'}], 'scan_entities': [],
                    'phase':'done','world_session':client.world,'scan_entity_scope':ENTITY_SCOPE_AT_SCAN_END}),
            ):
                with self.assertRaisesRegex(lighting.LightingBlocked, 'movement body sweep'):
                    runner.place(candidate, 0)
            self.assertEqual(client.interactions, 0)
            self.assertFalse(runner.intent_path(candidate['target']).exists())

    def test_unknown_interaction_persists_and_blocks_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            client = FakeClient(folder, unknown=True)
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
            candidate = lighting.candidates({(2, 63, 2): grass()}, LOW, HIGH)[0]
            with patch('lighting_cli.time.monotonic', side_effect=[0, 0, 0, 0, 7]), patch('lighting_cli.time.sleep'):
                with self.assertRaisesRegex(lighting.LightingBlocked, 'will never repeat'):
                    runner.place(candidate, 0)
            self.assertEqual(client.interactions, 1)
            self.assertEqual(json.loads(runner.intent_path(candidate['target']).read_text())['state'], 'interaction_intent')
            with self.assertRaisesRegex(lighting.LightingBlocked, 'Unresolved prior'):
                lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot()).reject_unknown_intents()
            self.assertEqual(client.interactions, 1)

    def test_batch_uses_one_initial_scan_and_low_route_not_fixed_high_transit(self):
        class PlannedRun(lighting.LightingRun):
            def __init__(self,client,folder):
                super().__init__(client,LOW,HIGH,2,folder,snapshot())
                self.actual_pos=[2.5,70,2.5];self.moves=[];self.whole_scans=0
            def fresh(self,work=True):return {**snapshot(),'pos':self.actual_pos}
            def scan(self,low,high,name=None):
                self.whole_scans+=1
                return {'phase':'done','world_session':self.c.world,'blocks':[grass(),grass(x=3,y=64,z=3)],
                    'scan_entity_scope':ENTITY_SCOPE_AT_SCAN_END,'scan_entities':[]}
            def move(self,target):self.moves.append(list(target));self.actual_pos=list(target)
            def place(self,candidate,index):
                self.report['placed'].append({'target':candidate['target']})
                return {'world_session':self.c.world,'blocks':[{'pos':candidate['target'],'state':'Block{minecraft:torch}'}]}
        with tempfile.TemporaryDirectory() as folder:
            runner=PlannedRun(FakeClient(folder),folder);runner.work()
            self.assertEqual(2,runner.whole_scans)
            self.assertEqual(1,len(runner.report['placed']))
            self.assertTrue(runner.moves);self.assertLessEqual(max(p[1] for p in runner.moves),70)
            self.assertTrue(json.loads((Path(folder)/'batch-plan.json').read_text())['prediction_only'])

    def test_guard_defense_waits_without_work_input_and_then_resumes(self):
        busy = {**snapshot(tick=100), 'guard_busy': True,
                'entities': [{'hostile': True, 'health': 20}]}
        calm = {**snapshot(tick=101), 'guard_busy': False,
                'entities': [{'hostile': True, 'health': 0}]}
        with tempfile.TemporaryDirectory() as folder:
            client = ObservedClient(folder, [busy, calm])
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
            with patch('lighting_cli.time.sleep'):
                observed = runner.wait_for_guard()
            self.assertEqual(observed, calm)
            self.assertEqual(client.operations, ['snapshot', 'snapshot'])
            self.assertEqual(client.interactions, 0)
            self.assertEqual(client.finished, 0)
            self.assertEqual(runner.report['guard_waits'][0]['outcome'], 'existing_guard_settled')
            self.assertFalse(runner.report['guard_waits'][0]['input_dispatched'])

    def test_guard_wait_is_bounded_and_does_not_finish_or_logout(self):
        busy = {**snapshot(tick=100), 'guard_busy': True}
        with tempfile.TemporaryDirectory() as folder:
            client = ObservedClient(folder, [busy])
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
            with patch('lighting_cli.time.monotonic', side_effect=[0, 61]), patch('lighting_cli.time.sleep'):
                with self.assertRaisesRegex(lighting.LightingBlocked, 'stayed busy'):
                    runner.wait_for_guard()
            self.assertEqual(client.operations, ['snapshot'])
            self.assertEqual(client.interactions, 0)
            self.assertEqual(client.finished, 0)
            self.assertEqual(runner.report['guard_waits'][0]['outcome'], 'bounded_wait_unresolved')

    def test_normal_thirty_second_combat_waits_until_dead_without_lighting_input(self):
        hostile={'type':'minecraft:drowned','hostile':True,'health':20,'alive':True}
        first={**snapshot(tick=100),'entities':[hostile]}
        second={**snapshot(tick=101),'entities':[hostile]}
        dead={**snapshot(tick=102),'entities':[{**hostile,'health':0}]}
        with tempfile.TemporaryDirectory() as folder:
            client=ObservedClient(folder,[first,second,dead])
            runner=lighting.LightingRun(client,LOW,HIGH,1,folder,snapshot())
            with patch('lighting_cli.time.monotonic',side_effect=[0,21,33]),patch('lighting_cli.time.sleep'):
                observed=runner.wait_for_guard()
            self.assertEqual(dead,observed)
            self.assertEqual(['snapshot','snapshot','snapshot'],client.operations)
            self.assertEqual(0,client.interactions);self.assertEqual(0,client.finished)

    def test_guard_wait_preserves_manual_health_and_world_stop_priority(self):
        for change in ({'manual_movement': True}, {'world_session': 'world-b'},
                       {'health': 19}, {'safety_hold': {'active': True}}, {'control_revision': 8}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                client = ObservedClient(folder, [{**snapshot(), **change, 'guard_busy': True}])
                runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
                with self.assertRaises(lighting.LightingBlocked):
                    runner.wait_for_guard()
                self.assertEqual(client.operations, ['snapshot'])
                self.assertEqual(client.interactions, 0)

    def test_late_owned_parking_transition_is_observed_without_replay(self):
        pending = parking_frame(kind='materials', revision=8, tick=101)
        pending['supervision_lease']['revision'] = 7
        done = parking_frame(tick=102)
        with tempfile.TemporaryDirectory() as folder:
            client = ObservedClient(folder, [pending, done])
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
            with patch('lighting_cli.time.sleep'):
                runner.confirm_final_park(7, 100)
            self.assertTrue(runner.report['park_native_confirmed'])
            self.assertEqual(client.operations, ['raw', 'raw'])
            self.assertEqual(client.finished, 0)
            frames = json.loads((Path(folder) / 'final-parking-observations.json').read_text())
            self.assertEqual([frame['kind'] for frame in frames], ['materials', 'parking'])

    def test_owned_final_parking_requires_exact_identity_native_keep_and_freshness(self):
        with tempfile.TemporaryDirectory() as folder:
            client = ObservedClient(folder, [parking_frame()])
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
            self.assertTrue(runner.owned_final_park(parking_frame(), 7, 100))
            for change in ({'connected': False}, {'world_session': 'world-b'},
                           {'manual_movement': True}, {'health': 17}, {'flight': False},
                           {'guard_armed': False}, {'guard_pve_only': False}, {'under_water': True},
                           {'safety_hold': {'active': True}}, {'time': 99}, {'control_revision': 9}):
                with self.subTest(change=change):
                    self.assertFalse(runner.owned_final_park({**parking_frame(), **change}, 7, 100))
            for key, value in (('id', 'foreign'), ('job_session', 'foreign'), ('world_session', 'world-b'),
                               ('kind', 'materials'), ('revision', 7), ('remote_finish', 'logout'),
                               ('park_target', [8.5, 88, 2.5]), ('park_target', [2.5, float('nan'), 2.5])):
                frame = parking_frame(); frame['supervision_lease'][key] = value
                with self.subTest(lease_field=key, value=value):
                    self.assertFalse(runner.owned_final_park(frame, 7, 100))
            for key, value in (('action', 'LOGOUT'), ('cause', 'timeout'), ('lease', 'foreign'),
                               ('job_session', 'foreign'), ('time', 99)):
                frame = parking_frame(); frame['supervision_safety'][key] = value
                with self.subTest(safety_field=key, value=value):
                    self.assertFalse(runner.owned_final_park(frame, 7, 100))

    def test_foreign_parking_stops_observation_immediately(self):
        foreign = parking_frame(); foreign['supervision_lease']['id'] = 'foreign'
        with tempfile.TemporaryDirectory() as folder:
            client = ObservedClient(folder, [foreign, parking_frame()])
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
            with self.assertRaisesRegex(lighting.LightingBlocked, 'cleanup was not replayed'):
                runner.confirm_final_park(7, 100)
            self.assertEqual(client.operations, ['raw'])
            self.assertFalse(runner.report['park_native_confirmed'])

    def test_late_parking_timeout_keeps_failure_and_never_replays_finish(self):
        pending = parking_frame(kind='materials')
        with tempfile.TemporaryDirectory() as folder:
            client = ObservedClient(folder, [pending])
            runner = lighting.LightingRun(client, LOW, HIGH, 1, folder, snapshot())
            with patch('lighting_cli.time.monotonic', side_effect=[0, 5]), patch('lighting_cli.time.sleep'):
                with self.assertRaisesRegex(lighting.LightingBlocked, 'receipt unavailable'):
                    runner.confirm_final_park(7, 100)
            self.assertEqual(client.operations, ['raw'])
            self.assertEqual(client.finished, 0)
            self.assertFalse(runner.report['park_native_confirmed'])

    def test_unverified_park_lease_never_releases_client(self):
        class Ascending(FakeClient):
            def __init__(self, root):
                super().__init__(root);self.pos=[2.5,65.5,2.5];self.rises=0
            def request(self,op,**params):
                if op=='snapshot':
                    self.tick+=1;return {**snapshot(tick=self.tick),'pos':list(self.pos),
                        'entities':[{'type':'minecraft:spider','hostile':True,'health':16}] if self.pos[1]<85 else []}
                return super().request(op,**params)
            def _finish_vertical(self,state):
                self.rises+=1;self.pos[1]=min(self.park_target[1],self.pos[1]+48)
        with tempfile.TemporaryDirectory() as folder:
            client=Ascending(folder)
            runner=lighting.LightingRun(client,LOW,HIGH,1,folder,snapshot())
            with patch.object(runner,'wait_for_guard',side_effect=AssertionError('Escape must not wait for enemies')):
                with self.assertRaisesRegex(lighting.LightingBlocked,'Native park lease unproven'):
                    runner.park()
            self.assertGreater(client.rises,0);self.assertEqual(client.finished,0)


if __name__ == '__main__':
    unittest.main()
