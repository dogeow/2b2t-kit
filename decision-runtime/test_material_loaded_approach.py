"""Real corridor planning uses only current local scans; no game or network."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_client import Handoff
from material_jobs.acquisition import _resource_route_scope, _travel, Unavailable
from material_jobs.protocol import JobPaused


class LocalServerClient:
    world = 'world'
    task = 'same-material-owner'

    def __init__(self, out):
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.state = {'connected': True, 'world_session': self.world, 'health': 20,
                      'food': 20, 'guard_armed': True, 'guard_pve_only': True,
                      'flight': True, 'manual_movement': False, 'pos': [.5, 145, .5],
                      'air_only_navigation_protocol': 2, 'navigating': False,
                      'native_material_busy': False}
        self.actions = []
        self.rows = []
        self.last = None
        self.rev = 7
        self.native_inflight = None
        self.navigation_failure = None
        self.after_first_navigation = None
        self.scan_change = {}

    def status(self):
        return deepcopy(self.state)

    def request(self, op, **params):
        self.last = 'original-request-' + str(len(self.actions)+1)
        self.actions.append({'id': self.last, 'op': op, 'params': deepcopy(params),
                             'from': list(self.state['pos'])})
        if op == 'scan':
            low, high = params['min'], params['max']
            # A far column is not loaded merely because a client cache exists.
            if any(math.hypot(x-self.state['pos'][0], z-self.state['pos'][2]) > 48
                   for x in (low[0], high[0]) for z in (low[2], high[2])):
                raise AssertionError('Whole distant corridor was scanned before local approach')
            rows = [row for row in self.rows if all(low[i] <= row['pos'][i] <= high[i] for i in range(3))]
            cells = math.prod(high[i]-low[i]+1 for i in range(3))
            return {'id': self.last, 'world_session': self.world, 'phase': 'done', 'blocks': deepcopy(rows),
                    'control_revision':self.rev,'scan_start_revision':self.rev,'scan_end_revision':self.rev,
                    'scan_cells_read': cells, 'scan_total_cells': cells, **self.scan_change}
        if op != 'navigate':
            raise AssertionError('Approach cannot create a controller, mine, or change a mode: ' + op)
        if self.navigation_failure:
            self.native_inflight = {'request_id': self.last, 'op': op, 'params': deepcopy(params)}
            self.state['native_material_busy'] = True
            if self.navigation_failure == 'exception':
                raise RuntimeError('Original navigation outcome unknown')
            if self.navigation_failure == 'handoff':
                raise Handoff('Original navigation lost world scope after dispatch')
            return {'id': self.last, 'world_session': self.world, 'phase': 'waiting',
                    'detail': 'Original navigation outcome unknown'}
        self.state['pos'] = list(params['target'])
        if self.after_first_navigation and sum(row['op'] == 'navigate' for row in self.actions) == 1:
            self.state.update(self.after_first_navigation)
        return {'id': self.last, 'world_session': self.world, 'phase': 'done'}


class LoadedApproachTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        settled = patch('material_jobs.navigation.settled_state', side_effect=lambda c, *args: c.status())
        settled.start()
        self.addCleanup(settled.stop)

    def client(self, name='route'):
        return LocalServerClient(self.root / name)

    def moves(self, client):
        return [row for row in client.actions if row['op'] == 'navigate']

    def test_long_diagonal_loads_local_axis_legs_before_final_nearby_descent(self):
        c = self.client(); target = [240.5, 64, 240.5]; trace = []
        _travel(c, target, lambda: None, trace)
        self.assertEqual(target, c.status()['pos'])
        self.assertGreater(len(self.moves(c)), 10)
        for row in self.moves(c):
            start, end = row['from'], row['params']['target']
            self.assertLessEqual(math.dist(start, end), 32.000001)
            self.assertEqual(1, sum(abs(start[i]-end[i]) > .001 for i in range(3)))
            self.assertTrue(row['params']['air_only'])
            if end[1] < start[1]:
                self.assertLessEqual(math.hypot(start[0]-target[0], start[2]-target[2]), 32)
        for row in c.actions:
            if row['op'] == 'scan':
                self.assertLessEqual(row['params']['max'][0]-row['params']['min'][0], 33)
                self.assertLessEqual(row['params']['max'][2]-row['params']['min'][2], 33)
        native_ids = {row['request_id'] for row in trace if row.get('phase') == 'done'}
        self.assertEqual({row['id'] for row in self.moves(c)}, native_ids)
        self.assertTrue(all(row['final_target'] == target for row in trace if row.get('event')))

    def test_observed_tall_roof_keeps_new_cruise_height_and_splits_vertical_moves(self):
        c = self.client(); c.state['pos'][1] = 95
        c.rows = [{'pos': [24, y, 0], 'state':'Block{minecraft:stone}', 'solid': True, 'fluid': False,
                   'passable': False, 'block_entity': False}for y in range(95,171)]
        target = [240.5, 64, .5]
        _travel(c, target, lambda: None, [])
        moves = self.moves(c)
        first_horizontal = next(index for index, row in enumerate(moves)
                                if row['from'][0] != row['params']['target'][0])
        self.assertGreater(first_horizontal, 1)
        self.assertGreaterEqual(moves[first_horizontal]['from'][1], 173.1)
        self.assertTrue(all(math.dist(row['from'], row['params']['target']) <= 32.000001 for row in moves))
        self.assertTrue(all(row['params']['target'][1] >= 173.1 for row in moves[first_horizontal:]
                            if row['params']['target'][0] < target[0]-32))
        self.assertEqual(target, c.status()['pos'])

    def test_original_long_resource_scope_and_target_are_retained(self):
        c = self.client(); c.state['pos'][0] = -250.5
        region = {'item': 'minecraft:snow', 'min': [248, 64, 0], 'max': [253, 80, 5],
                  'source': 'natural_survey'}
        scope = _resource_route_scope({'search_origin': [0, 145, 0], 'search_radius': 256}, region)
        original = deepcopy(scope); target = [250.5, 67.1, .5]; trace = []
        _travel(c, target, lambda: None, trace, route_scope=scope)
        self.assertEqual(original, scope)
        self.assertEqual(target, c.status()['pos'])
        self.assertEqual(2, sum(row.get('event') == 'resource_route_segment_done' for row in trace))
        self.assertTrue(all(abs(row['params']['target'][0]) <= 272 for row in self.moves(c)))
        saved = json.loads((c.out / 'resource-route-segments-latest.json').read_text())
        self.assertEqual(('done', target), (saved['phase'], saved['final_target']))

    def test_distant_unapproved_route_still_refuses_before_scanning(self):
        c = self.client()
        with self.assertRaises(Unavailable):
            _travel(c, [500.5, 64, .5], lambda: None, [])
        self.assertFalse(c.actions)

    def test_approved_intermediate_segment_never_descends_below_observed_transit(self):
        c = self.client(); c.state['pos'][0] = -250.5
        c.rows = [{'pos': [-224, 170, 0], 'solid': True, 'fluid': False,
                   'passable': False, 'block_entity': False}]
        region = {'item': 'minecraft:snow', 'min': [248, 64, 0], 'max': [253, 80, 5],
                  'source': 'natural_survey'}
        scope = _resource_route_scope({'search_origin': [0, 145, 0], 'search_radius': 256}, region)
        target = [250.5, 67.1, .5]
        _travel(c, target, lambda: None, [], route_scope=scope)
        for row in self.moves(c):
            start, end = row['from'], row['params']['target']
            if end[1] < start[1]:
                self.assertLessEqual(math.hypot(start[0]-target[0], start[2]-target[2]), 32)
        self.assertEqual(target, c.status()['pos'])

    def test_unknown_native_receipt_or_exception_never_replays_or_scans_ahead(self):
        for failure in ('exception', 'handoff', 'waiting'):
            with self.subTest(failure=failure):
                c = self.client(failure); c.navigation_failure = failure; trace = []
                with self.assertRaises((RuntimeError, Handoff, Unavailable)):
                    _travel(c, [240.5, 64, .5], lambda: None, trace)
                self.assertEqual(1, len(self.moves(c)))
                rid = self.moves(c)[0]['id']
                self.assertEqual(rid, c.native_inflight['request_id'])
                self.assertTrue(any(row.get('request_id') == rid for row in trace))
                original_actions = deepcopy(c.actions)
                with self.assertRaises(Unavailable):
                    _travel(c, [240.5, 64, .5], lambda: None, trace)
                self.assertEqual(original_actions, c.actions)

    def test_partial_waiting_or_foreign_world_scan_is_never_a_clear_corridor(self):
        for changes in ({'phase': 'waiting'}, {'world_session': 'other'},
                        {'scan_cells_read': 0}, {'scan_total_cells': 0},
                        {'scan_cells_read': True}):
            with self.subTest(changes=changes):
                c = self.client('scan-' + next(iter(changes))); c.scan_change = changes
                with self.assertRaises(Unavailable):
                    _travel(c, [240.5, 64, .5], lambda: None, [])
                self.assertFalse(self.moves(c))

    def test_arrival_tolerance_drift_cannot_finish_or_descend_outside_original_search(self):
        class EdgeDrift(LocalServerClient):
            def request(self, op, **params):
                reply = super().request(op, **params)
                if op == 'navigate' and params['target'][0] == 272:
                    self.state['pos'][0] = 272.3
                return reply
        c = EdgeDrift(self.root / 'drift'); c.state['pos'][0] = -250.5
        region = {'item': 'minecraft:snow', 'min': [260, 64, 0], 'max': [266, 80, 5],
                  'source': 'natural_survey'}
        scope = _resource_route_scope({'search_origin': [0, 145, 0], 'search_radius': 256}, region)
        target = [272, 67.1, .5]; trace = []
        with self.assertRaises(Unavailable) as stopped:
            _travel(c, target, lambda: None, trace, route_scope=scope)
        self.assertEqual('route_uncertain', stopped.exception.code)
        self.assertEqual([272.3, 145, .5], c.status()['pos'])
        self.assertFalse(any(row['from'][0] > 272 for row in self.moves(c)))
        self.assertEqual(target, trace[-1]['final_target'])

    def test_lighting_preload_retains_roof_height_while_true_region_remains_distant(self):
        from types import SimpleNamespace
        from lighting_regions_cli import NativeBatch
        c = self.client('preload'); c.state['pos'][1] = 95
        c.rows = [{'pos': [24, y, 0], 'state':'Block{minecraft:stone}', 'solid': True, 'fluid': False,
                   'passable': False, 'block_entity': False}for y in range(95,171)]
        owner = SimpleNamespace(profile={'movement_bounds': {'min': [-10, -64, -10], 'max': [300, 300, 300]}},
                                book={'pending': {}}, save=lambda: None)
        def gate(state, client):
            self.assertIs(c, client)
            self.assertEqual(c.world, state['world_session'])
        owner.gate = gate
        NativeBatch(owner).preload_region(c, [240.5, 108, .5], c.out)
        self.assertLessEqual(abs(c.status()['pos'][0]-240.5), 16)
        self.assertGreaterEqual(c.status()['pos'][1], 175.1)
        self.assertTrue(all(row['params']['target'][1] >= row['from'][1] for row in self.moves(c)))
        self.assertTrue(all(math.dist(row['from'], row['params']['target']) <= 32.000001 for row in self.moves(c)))
        proof = json.loads((c.out / 'preload-route.json').read_text())
        self.assertTrue(proof['arrived_near'])

    def test_health_manual_world_and_busy_changes_stop_before_another_move(self):
        for change in ({'health': 18}, {'manual_movement': True}, {'world_session': 'other'},
                       {'connected': False}, {'native_material_busy': True}):
            with self.subTest(change=change):
                c = self.client(next(iter(change))); c.after_first_navigation = change
                trace = []
                with self.assertRaises(Unavailable):
                    _travel(c, [240.5, 64, .5], lambda: None, trace)
                self.assertEqual(1, len(self.moves(c)))
                self.assertTrue(any(row.get('request_id') == self.moves(c)[0]['id'] for row in trace))

    def test_checkpoint_pause_keeps_confirmed_native_id_and_original_destination(self):
        c = self.client(); trace = []; target = [240.5, 64, .5]
        def checkpoint():
            if self.moves(c):
                raise JobPaused('Real manual stop')
        with self.assertRaises(JobPaused):
            _travel(c, target, checkpoint, trace)
        self.assertEqual(1, len(self.moves(c)))
        self.assertTrue(any(row.get('request_id') == self.moves(c)[0]['id'] for row in trace))
        self.assertEqual(target, trace[-1]['final_target'])

    def test_no_clearance_above_roof_stops_at_next_loaded_leg(self):
        c = self.client(); c.rows = [{'pos': [100, y, 0], 'state':'Block{minecraft:stone}', 'solid': True, 'fluid': False,
                                     'passable': False, 'block_entity': False}for y in range(145,319)]
        with self.assertRaises(Unavailable) as stopped:
            _travel(c, [240.5, 64, .5], lambda: None, [])
        self.assertEqual('route_geometry_blocked', stopped.exception.code)
        self.assertLess(c.status()['pos'][0], 100)

    def test_finite_leg_and_time_limits_keep_original_target(self):
        c = self.client(); target = [240.5, 64, .5]; trace = []
        with patch('material_jobs.acquisition.MAX_LOADED_ROUTE_LEGS', 1):
            with self.assertRaises(Unavailable) as stopped:
                _travel(c, target, lambda: None, trace)
        self.assertEqual(1, sum(row.get('event') == 'loaded_chunk_approach_start' for row in trace))
        self.assertLessEqual(len(self.moves(c)), 2)
        self.assertEqual(target, stopped.exception.evidence['final_target'])
        fresh = self.client('expired')
        with patch('material_jobs.acquisition.MAX_LOADED_ROUTE_SECONDS', 0):
            with self.assertRaises(Unavailable):
                _travel(fresh, target, lambda: None, [])
        self.assertFalse(fresh.actions)

    def test_actual_short_vertical_arrivals_anchor_every_next_request(self):
        class ShortArrival(LocalServerClient):
            def request(self, op, **params):
                if op == 'navigate' and math.dist(self.state['pos'], params['target']) > 32:
                    raise AssertionError('Strict native owner rejected a precomputed long step')
                reply = super().request(op, **params)
                if op == 'navigate':
                    start = self.actions[-1]['from']; end = params['target']
                    axis = max(range(3), key=lambda i: abs(end[i]-start[i]))
                    self.state['pos'][axis] -= math.copysign(.19, end[axis]-start[axis])
                return reply
        c = ShortArrival(self.root / 'short-vertical'); target = [.5, 305, .5]
        trace = []; _travel(c, target, lambda: None, trace)
        self.assertLessEqual(math.dist(c.status()['pos'], target), .55)
        self.assertGreaterEqual(len(self.moves(c)), 6)
        self.assertTrue(all(math.dist(row['from'], row['params']['target']) <= 31.000001 for row in self.moves(c)))
        self.assertEqual({row['id'] for row in self.moves(c)},
                         {row['request_id'] for row in trace if row.get('phase') == 'done'})

    def test_actual_horizontal_drift_cannot_add_distance_to_next_native_move(self):
        class DriftingArrival(LocalServerClient):
            def request(self, op, **params):
                if op == 'navigate' and math.dist(self.state['pos'], params['target']) > 32:
                    raise AssertionError('Strict native owner rejected a drift-expanded step')
                reply = super().request(op, **params)
                if op == 'navigate':
                    start = self.actions[-1]['from']; end = params['target']
                    axis = max(range(3), key=lambda i: abs(end[i]-start[i]))
                    side = 0 if axis == 2 else 2
                    self.state['pos'][axis] -= math.copysign(.19, end[axis]-start[axis])
                    self.state['pos'][side] += .19
                return reply
        c = DriftingArrival(self.root / 'horizontal-drift'); c.state['pos'][1] = 90.1484486509
        c.rows = [{'pos': [24, 177, 0], 'solid': True, 'fluid': False,
                   'passable': False, 'block_entity': False}]
        target = [240.5, 64, 64.5]; trace = []
        _travel(c, target, lambda: None, trace, clearance_padding=2.32, obstacle_margin=5.1)
        self.assertLessEqual(math.dist(c.status()['pos'], target), .55)
        self.assertTrue(all(math.dist(row['from'], row['params']['target']) <= 31.000001 for row in self.moves(c)))
        self.assertTrue(all(row['params']['air_only'] for row in self.moves(c)))

    def test_region_client_can_keep_stricter_native_body_bounds(self):
        class RegionClient(LocalServerClient):
            def request(self, op, **params):
                if op == 'navigate' and params['target'][1]+1.8 > 110:
                    raise JobPaused('Region travel would leave authorized movement box')
                return super().request(op, **params)
        c = RegionClient(self.root / 'region'); c.state['pos'][1] = 95
        with self.assertRaisesRegex(JobPaused, 'authorized movement'):
            _travel(c, [240.5, 145, .5], lambda: None, [])
        self.assertFalse(self.moves(c))


if __name__ == '__main__':
    unittest.main()
