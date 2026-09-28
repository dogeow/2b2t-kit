import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import projection_dry_paving as paving
from projection_dry_paving import PavingBlocked, PavingPending, SITE, pave_batch


POS = [760984, 63, 797828]  # Current audit: grass occupying a rear stone-brick path cell.
OLD = 'Block{minecraft:grass_block}[snowy=false]'
WANTED = 'Block{minecraft:stone_bricks}'
SUPPORT = 'Block{minecraft:dirt}'


def test_site(pos=POS):
    key = 'test-full-yard-eight-regions'
    return key, {**SITE, 'name': 'test-full-yard', 'total': 1,
                 'bounds': {'min': [pos[0]-1, 61, pos[2]-1],
                            'max': [pos[0]+1, 70, pos[2]+1]},
                 'placement_key_sha256': hashlib.sha256(key.encode()).hexdigest()}


class FakeClient:
    def __init__(self, root, *, pos=POS, expected=WANTED, actual=OLD):
        self.root = Path(root)
        self.out = self.root / 'events'
        self.out.mkdir(parents=True)
        self.world = 'world-1'
        self.task = 'materials-test'
        self.pos = list(pos)
        self.key, self.site = test_site(pos)
        self.expected = expected
        self.actual = actual
        self.entities = []
        self.player_feet = [pos[0] + 2.5, 64.02, pos[2] + .5]
        self.pickup_inside = False
        self.pickup_offset = (0, 0)
        self.pickup_feet_y = 63.95
        self.approach_inside = False
        self.approach_pose = None
        self.block_after_vertical_selection = False
        self.direct_scan_drift = False
        self.animal_after_pickup = False
        self.navigation_refused = False
        self.navigation_params = []
        self.vertical_settle_y = None
        self.low_settle_y = None
        self.air_obstacles = set()
        self.neighbor = None
        self.extra = None
        self.fluid = False
        self.model_hash = 'verified-model-hash'
        self.uncertain_mine = False
        self.refuse_mine = False
        self.uncertain_place = False
        self.block_after_mine = False
        self.animal_after_mine = False
        self.operations = []
        self.interact_params = None
        self.mine_params = None
        self.items = {'minecraft:stone_bricks': 2, 'minecraft:dirt': 0}
        self.hand = 'minecraft:diamond_shovel'
        self.host_protocol = 1
        self.dimension = 'minecraft:overworld'

    def _inventory(self):
        return [{'slot': 0, 'item': 'minecraft:stone_bricks', 'count': self.items['minecraft:stone_bricks'], 'max_stack': 64},
                {'slot': 1, 'item': 'minecraft:diamond_shovel', 'count': 1, 'durability': 100},
                {'slot': 2, 'item': 'minecraft:dirt', 'count': self.items['minecraft:dirt'], 'max_stack': 64},
                {'slot': 3, 'item': 'minecraft:air', 'count': 0, 'max_stack': 1}]

    def status(self):
        snapshot = copy.deepcopy({'time': 10000, 'connected': True, 'world_session': self.world,
                              'dry_paving_protocol': self.host_protocol,
                              'server': 'simpcraft.com:25565', 'dimension': self.dimension,
                              'screen': '', 'manual_movement': False, 'health': 20, 'food': 20,
                              'game_mode': 'survival',
                              'guard_armed': True, 'guard_pve_only': True, 'guard_busy': False,
                              'flight': True, 'under_water': False, 'air_return_active': False,
                              'safety_hold': {'active': False},
                              'supervision_lease': {'kind': 'materials', 'job_session': self.task},
                              'projection_selection': {'key': self.key, **self.site['bounds']},
                              'pos': self.player_feet,
                              'entities': self.entities, 'inventory': self._inventory(),
                              'hand': {'item': self.hand, 'durability': 100}})
        if self.host_protocol is None:
            snapshot.pop('dry_paving_protocol')
        return snapshot

    def _audit(self):
        matched = int(self.actual == self.expected)
        mismatch = [] if matched else [{'pos': self.pos, 'expected': self.expected,
                                        'actual': self.actual,
                                        'kind': 'missing' if self.actual == 'Block{minecraft:air}' else 'occupied',
                                        'block_entity': False, 'fluid': False,
                                        'adjacent_fluid': False, 'neighbors_loaded': True}]
        return {'audit_schema': 2, 'observed_at': 10000, 'server': 'simpcraft.com',
                'dimension': self.dimension, 'loaded_chunks_verified': True,
                'enclosed_air_conflicts': [], 'name': self.site['name'],
                'placement_key': self.key, 'matched': matched, 'total': 1,
                'mismatches': mismatch}

    def _scan(self, low, high):
        x, _, z = self.pos
        rows = [{'pos': [x, 62, z], 'state': SUPPORT, 'solid': True,
                 'fluid': False, 'block_entity': False, 'passable': False}]
        if self.actual != 'Block{minecraft:air}':
            rows.append({'pos': self.pos, 'state': self.actual, 'solid': True,
                         'fluid': False, 'block_entity': False, 'passable': False})
        if self.extra is not None:
            rows.append(self.extra)
        if self.neighbor is not None:
            rows.append(self.neighbor)
        if self.fluid:
            rows.append({'pos': [x+1, 62, z], 'state': 'Block{minecraft:water}[level=0]',
                         'solid': False, 'fluid': True, 'block_entity': False, 'passable': False})
        for point in self.air_obstacles:
            rows.append({'pos': list(point), 'state': 'Block{minecraft:stone}',
                         'solid': True, 'fluid': False, 'block_entity': False,
                         'passable': False})
        return [r for r in rows if all(low[i] <= r['pos'][i] <= high[i] for i in range(3))]

    def request(self, op, **params):
        self.operations.append(op)
        if op == 'projection_model':
            return {'phase': 'done', 'world_session': self.world,
                    'projection_model': {'placement_key': self.key, 'bounds': self.site['bounds'],
                                         'loaded_chunks_verified': True, 'total': 1,
                                         'content_hash': self.model_hash, 'observed_at': 10000,
                                         'expected': [{'pos': self.pos, 'state': self.expected}]}}
        if op == 'projection_audit':
            return {'phase': 'done', 'world_session': self.world, 'projection_audit': self._audit()}
        if op == 'scan':
            if (self.direct_scan_drift and self.actual == 'Block{minecraft:air}'
                    and self.hand == 'minecraft:stone_bricks'
                    and params['min'] == [self.pos[0], self.pos[1]+1, self.pos[2]]
                    and params['max'] == [self.pos[0], self.pos[1]+3, self.pos[2]]):
                self.player_feet[1] = 64.0
            return {'phase': 'done', 'world_session': self.world,
                    'blocks': self._scan(params['min'], params['max'])}
        if op == 'select_item':
            self.hand = params['item']
            if (self.block_after_vertical_selection and self.actual == 'Block{minecraft:air}'
                    and self.navigation_params):
                self.air_obstacles.add((self.pos[0], self.pos[1]+3, self.pos[2]))
            return {'phase': 'done'}
        if op == 'approach_block':
            if self.block_after_mine and self.actual == 'Block{minecraft:air}':
                return {'phase': 'waiting', 'detail': 'No visible collision-free depot approach'}
            if (self.actual == 'Block{minecraft:air}'
                    and math.dist(self.player_feet,
                                  [self.pos[0]+.5, self.pos[1]+.5, self.pos[2]+.5]) > 12):
                self.player_feet = [self.pos[0]+2.5, 64.02, self.pos[2]+.5]
            if self.approach_pose is not None and self.actual == 'Block{minecraft:air}':
                self.player_feet = list(self.approach_pose)
            elif self.approach_inside and self.actual == 'Block{minecraft:air}':
                self.player_feet = [self.pos[0]+.5, 63.95, self.pos[2]+.5]
            return {'phase': 'done'}
        if op == 'navigate':
            self.navigation_params.append(params)
            if self.navigation_refused:
                return {'phase': 'waiting'}
            self.player_feet = list(params['target'])
            if (self.vertical_settle_y is not None
                    and params['target'][1] == self.pos[1] + 1.45):
                self.player_feet[1] = self.vertical_settle_y
            if (self.low_settle_y is not None
                    and params['target'][1] == self.pos[1] + 1.2):
                self.player_feet[1] = self.low_settle_y
            return {'phase': 'done'}
        if op == 'mine_block':
            self.mine_params = params
            if self.refuse_mine:
                return {'phase': 'waiting', 'detail': 'Dry paving neighbor changed'}
            self.actual = 'Block{minecraft:air}'
            self.entities = [{'type': 'minecraft:item', 'uuid': 'owned-drop',
                              'pos': [self.pos[0]+.5, 63.5, self.pos[2]+.5],
                              'stack': {'item': 'minecraft:dirt', 'count': 1}}]
            if self.animal_after_mine:
                self.entities.append({'type': 'minecraft:cow', 'uuid': 'arrived-after-mining',
                                      'pos': [self.pos[0]+1.5, 63.5, self.pos[2]+.5]})
            return {'phase': 'waiting' if self.uncertain_mine else 'done'}
        if op == 'collect_item':
            self.entities = []
            self.items['minecraft:dirt'] += 1
            if self.pickup_inside:
                self.player_feet = [self.pos[0]+.5+self.pickup_offset[0], self.pickup_feet_y,
                                    self.pos[2]+.5+self.pickup_offset[1]]
            if self.animal_after_pickup:
                self.entities = [{'type': 'minecraft:cow', 'uuid': 'nearby-private-identity',
                                  'pos': [self.pos[0]+2.5, 63.5, self.pos[2]+.5]}]
            return {'phase': 'done'}
        if op == 'interact':
            self.interact_params = params
            if self.uncertain_place:
                return {'phase': 'waiting'}
            self.actual = self.expected
            self.items['minecraft:stone_bricks'] -= 1
            return {'phase': 'done'}
        raise AssertionError(op)

    def checked(self, op, **params):
        reply = self.request(op, **params)
        if reply.get('phase') != 'done':
            raise RuntimeError(op + ' not confirmed')
        return reply


class DryPavingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = FakeClient(self.temp.name)

    def run_one(self):
        with patch.object(paving, 'SITE', self.client.site):
            return pave_batch(self.client, [self.client.pos], settle=lambda _: None)

    def journal(self):
        files = list(self.client.root.glob('dry-paving-v1/*/*.json'))
        self.assertEqual(len(files), 1)
        return json.loads(files[0].read_text())

    def test_old_or_invalid_host_protocol_blocks_before_any_game_request(self):
        for protocol in (None, 0, False, '1', 2):
            with self.subTest(protocol=protocol):
                self.client.host_protocol = protocol
                with self.assertRaisesRegex(PavingBlocked, 'active Kit mod'):
                    self.run_one()
                self.assertEqual(self.client.operations, [])
                self.assertEqual(list(Path(self.temp.name).glob('dry-paving-v1/*/*.json')), [])

    def test_exact_cell_mine_collect_place_and_second_run_is_read_only(self):
        self.assertEqual(self.run_one()[0]['result'], 'placed')
        self.assertEqual(self.client.actual, WANTED)
        self.assertEqual(self.client.items['minecraft:stone_bricks'], 1)
        self.assertEqual(self.client.items['minecraft:dirt'], 1)
        self.assertEqual(self.journal()['phase'], 'complete')
        self.assertEqual(self.run_one()[0]['result'], 'already_complete')
        self.assertEqual(self.client.operations.count('mine_block'), 1)
        self.assertEqual(self.client.operations.count('interact'), 1)
        self.assertIs(self.client.mine_params['dry_paving_guard'], True)
        self.assertIs(self.client.interact_params['dry_paving_guard'], True)

    def test_native_mining_guard_refusal_keeps_intent_and_never_replays(self):
        self.client.refuse_mine = True
        with self.assertRaises(PavingPending):
            self.run_one()
        self.assertEqual(self.client.actual, OLD)
        self.assertEqual(self.journal()['phase'], 'mine_intent')
        with self.assertRaises(PavingPending):
            self.run_one()
        self.assertEqual(self.client.operations.count('mine_block'), 1)

    def test_uncertain_mine_stays_pending_even_when_world_looks_like_air(self):
        self.client.uncertain_mine = True
        with self.assertRaises(PavingPending):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'mine_intent')
        with self.assertRaises(PavingPending):
            self.run_one()
        self.assertEqual(self.client.operations.count('mine_block'), 1)
        self.assertEqual(self.client.operations.count('interact'), 0)

    def test_uncertain_place_is_not_clicked_again(self):
        self.client.uncertain_place = True
        with self.assertRaises(PavingPending):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'place_intent')
        with self.assertRaises(PavingPending):
            self.run_one()
        self.assertEqual(self.client.operations.count('mine_block'), 1)
        self.assertEqual(self.client.operations.count('interact'), 1)

    def test_recovered_drop_can_resume_placement_without_remining(self):
        self.client.block_after_mine = True
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.client.block_after_mine = False
        self.assertEqual(self.run_one()[0]['result'], 'placed')
        self.assertEqual(self.client.operations.count('mine_block'), 1)

    def test_recovered_air_cell_rebinds_after_reconnect_once_without_remining(self):
        self.client.block_after_mine = True
        with self.assertRaises(PavingBlocked):
            self.run_one()
        old = self.journal()
        self.assertEqual(old['phase'], 'recovered')
        self.client.world = 'world-2'
        self.client.block_after_mine = False
        self.assertEqual(self.run_one()[0]['result'], 'placed')
        record = self.journal()
        self.assertEqual(record['world_session'], 'world-2')
        rebounds = [r for r in record['receipts'] if r.get('event') == 'world_session_rebind']
        self.assertEqual(len(rebounds), 1)
        self.assertEqual(rebounds[0]['previous_world_session'], old['world_session'])
        self.assertEqual(rebounds[0]['current_world_session'], 'world-2')
        self.assertIs(rebounds[0]['observed_air'], True)
        self.assertEqual(self.client.operations.count('mine_block'), 1)
        self.assertEqual(self.client.operations.count('interact'), 1)

    def test_recovered_reconnect_pre_approaches_from_high_park_before_rebind(self):
        self.client.block_after_mine = True
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.client.world = 'world-2'
        self.client.block_after_mine = False
        self.client.player_feet = [POS[0]+15.5, 120.0, POS[2]+23.5]
        start = len(self.client.operations)
        self.assertEqual(self.run_one()[0]['result'], 'placed')
        resumed = self.client.operations[start:]
        self.assertLess(resumed.index('approach_block'), resumed.index('select_item'))
        self.assertEqual(self.client.operations.count('mine_block'), 1)
        self.assertEqual(len([r for r in self.journal()['receipts']
                              if r.get('event') == 'world_session_rebind']), 1)

    def test_recovered_reconnect_changed_model_or_cell_remains_pending(self):
        for change in ('model', 'target'):
            with self.subTest(change=change):
                self.client = FakeClient(Path(self.temp.name) / change)
                self.client.block_after_mine = True
                with self.assertRaises(PavingBlocked):
                    self.run_one()
                self.client.world = 'world-2'
                self.client.block_after_mine = False
                if change == 'model':
                    self.client.model_hash = 'changed-model-hash'
                else:
                    self.client.actual = OLD
                with self.assertRaises(PavingPending):
                    self.run_one()
                self.assertEqual(self.journal()['world_session'], 'world-1')
                self.assertEqual(self.journal()['phase'], 'recovered')
                self.assertEqual(self.client.operations.count('mine_block'), 1)
                self.assertNotIn('interact', self.client.operations)

    def test_recovered_reconnect_changed_dimension_or_nearby_entity_holds(self):
        for change in ('dimension', 'entity'):
            with self.subTest(change=change):
                self.client = FakeClient(Path(self.temp.name) / change)
                self.client.block_after_mine = True
                with self.assertRaises(PavingBlocked):
                    self.run_one()
                self.client.world = 'world-2'
                self.client.block_after_mine = False
                if change == 'dimension':
                    self.client.dimension = 'minecraft:the_nether'
                else:
                    self.client.entities = [{'type': 'minecraft:cow', 'uuid': 'nearby',
                                             'pos': [POS[0]+1.5, 63.5, POS[2]+.5]}]
                with self.assertRaises(PavingBlocked):
                    self.run_one()
                self.assertEqual(self.journal()['world_session'], 'world-1')
                self.assertNotIn('interact', self.client.operations)

    def test_recovered_reconnect_unsettled_native_request_holds_journal(self):
        self.client.block_after_mine = True
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.client.world = 'world-2'
        self.client.block_after_mine = False
        (self.client.root / 'request.json').write_text(json.dumps({
            'id': 'unconfirmed-native-request', 'world_session': 'world-2'}))
        with self.assertRaisesRegex(PavingPending, 'Native request completion is unverified'):
            self.run_one()
        self.assertEqual(self.journal()['world_session'], 'world-1')
        self.assertNotIn('interact', self.client.operations)

    def test_recovered_reconnect_requires_original_mine_and_pickup_receipts(self):
        self.client.block_after_mine = True
        with self.assertRaises(PavingBlocked):
            self.run_one()
        path = next(self.client.root.glob('dry-paving-v1/*/*.json'))
        record = json.loads(path.read_text())
        record['receipts'] = [r for r in record['receipts'] if r['phase'] != 'mined']
        path.write_text(json.dumps(record))
        self.client.world = 'world-2'
        self.client.block_after_mine = False
        with self.assertRaisesRegex(PavingPending, 'confirmed excavation and pickup'):
            self.run_one()
        self.assertEqual(self.journal()['world_session'], 'world-1')
        self.assertEqual(self.client.operations.count('mine_block'), 1)
        self.assertNotIn('interact', self.client.operations)

    def test_inflight_mine_or_place_intent_does_not_rebind_on_reconnect(self):
        for action in ('mine', 'place'):
            with self.subTest(action=action):
                self.client = FakeClient(Path(self.temp.name) / action)
                if action == 'mine':
                    self.client.uncertain_mine = True
                else:
                    self.client.uncertain_place = True
                with self.assertRaises(PavingPending):
                    self.run_one()
                old = self.journal()
                self.client.world = 'world-2'
                with self.assertRaises(PavingPending):
                    self.run_one()
                self.assertEqual(self.journal(), old)
                self.assertEqual(self.client.operations.count('mine_block'), 1)
                self.assertEqual(self.client.operations.count('interact'), int(action == 'place'))

    def test_high_park_recovered_cell_approaches_before_entity_coverage_check(self):
        self.client.block_after_mine = True
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.client.block_after_mine = False
        self.client.player_feet = [self.client.pos[0]+15.5, 120.0,
                                   self.client.pos[2]+23.5]
        start = len(self.client.operations)
        self.assertEqual(self.run_one()[0]['result'], 'placed')
        resumed = self.client.operations[start:]
        self.assertLess(resumed.index('approach_block'), resumed.index('select_item'))
        self.assertEqual(self.client.operations.count('mine_block'), 1)
        self.assertEqual(self.client.operations.count('interact'), 1)

    def test_high_park_pre_approach_failure_keeps_recovered_journal(self):
        self.client.block_after_mine = True
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.client.player_feet = [self.client.pos[0]+15.5, 120.0,
                                   self.client.pos[2]+23.5]
        start = len(self.client.operations)
        with self.assertRaisesRegex(PavingBlocked, 'No verified dry support-face approach'):
            self.run_one()
        resumed = self.client.operations[start:]
        self.assertIn('approach_block', resumed)
        self.assertNotIn('select_item', resumed)
        self.assertNotIn('interact', resumed)
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.assertEqual(self.client.operations.count('mine_block'), 1)

    def test_post_pickup_body_overlap_stays_recovered_until_safe_approach(self):
        self.client.pickup_inside = True
        self.client.pickup_offset = (.2, 0)
        self.client.approach_inside = True
        with self.assertRaisesRegex(PavingBlocked, 'Player body overlaps'):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.assertNotIn('place_intent', [row['phase'] for row in self.journal()['receipts']])
        self.assertNotIn('interact', self.client.operations)
        moves = [op for op in self.client.operations if op == 'navigate']
        self.assertGreaterEqual(len(moves), 1)
        self.assertTrue(all(row['air_only'] is True and row['arrival'] == .2
                            for row in self.client.navigation_params))
        self.client.approach_inside = False
        self.assertEqual(self.run_one()[0]['result'], 'placed')
        self.assertEqual(self.client.operations.count('mine_block'), 1)
        self.assertEqual(self.client.operations.count('interact'), 1)

    def test_live_west_approach_gap_passes_before_native_exact_body_guard(self):
        pos = [761004, 63, 797829]
        self.client = FakeClient(Path(self.temp.name) / 'west-gap', pos=pos)
        self.client.block_after_mine = True
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.client.block_after_mine = False
        self.client.player_feet = [761002.5195225418, 64.0, 797829.5002699184]
        self.client.approach_pose = [761003.4985609235, 64.0, 797829.5000003378]
        self.assertTrue(paving._player_body_clear(
            {'pos': self.client.approach_pose}, tuple(pos)))
        self.assertFalse(paving._player_body_clear(
            {'pos': [pos[0] - .2, 64.0, pos[2] + .5]}, tuple(pos)))
        self.assertEqual(self.run_one()[0]['result'], 'placed')
        self.assertEqual(self.client.navigation_params, [])
        self.assertEqual(self.client.operations.count('mine_block'), 1)
        self.assertEqual(self.client.operations.count('interact'), 1)

    def test_corner_overlap_exits_north_of_protected_house_buffer(self):
        pos = [761004, 63, 797829]
        self.client = FakeClient(Path(self.temp.name) / 'corner', pos=pos)
        self.client.block_after_mine = True
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.client.block_after_mine = False
        self.client.player_feet = [pos[0] + 1.2500004, 64.0, pos[2] + 1.2527]
        self.assertFalse(paving._player_body_clear(self.client.status(), tuple(pos)))
        self.assertTrue(paving._protected((pos[0], pos[1], pos[2] + 2), self.client.site))
        self.assertEqual(self.run_one()[0]['result'], 'placed')
        targets = [row['target'] for row in self.client.navigation_params]
        self.assertEqual(len(targets), 4)
        self.assertEqual(targets[1][0], pos[0] + 1.2500004)
        self.assertEqual(targets[1][2], pos[2] - 1.5)
        self.assertEqual(targets[-1][0], pos[0] + .5)
        self.assertEqual(targets[-1][2], pos[2] - 1.5)
        self.assertTrue(all(target[2] <= pos[2] + 1.2527 for target in targets))
        self.assertEqual(self.client.operations.count('mine_block'), 1)

    def test_corner_starting_column_obstruction_stays_recovered(self):
        pos = [761004, 63, 797829]
        self.client = FakeClient(Path(self.temp.name) / 'corner-obstructed', pos=pos)
        self.client.block_after_mine = True
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.client.block_after_mine = False
        self.client.player_feet = [pos[0] + 1.2500004, 64.0, pos[2] + 1.2527]
        self.client.air_obstacles = {(pos[0]+1, 64, pos[2]+1)}
        with self.assertRaisesRegex(PavingBlocked, 'No freshly scanned dry axis route'):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.assertNotIn('navigate', self.client.operations)
        self.assertNotIn('interact', self.client.operations)

    def test_corner_never_uses_protected_south_when_other_routes_close(self):
        pos = [761004, 63, 797829]
        self.client = FakeClient(Path(self.temp.name) / 'corner-protected', pos=pos)
        self.client.block_after_mine = True
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.client.block_after_mine = False
        self.client.player_feet = [pos[0] + 1.2500004, 64.0, pos[2] + 1.2527]
        self.client.air_obstacles = {(pos[0]+1, 64, pos[2])}
        with self.assertRaisesRegex(PavingBlocked, 'No freshly scanned dry axis route'):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.assertNotIn('navigate', self.client.operations)
        self.assertNotIn('interact', self.client.operations)

    def test_recovered_cell_waits_for_nearby_animal_and_logs_anonymous_evidence(self):
        self.client.pickup_inside = True
        self.client.animal_after_pickup = True
        with self.assertRaisesRegex(PavingBlocked, 'animal, player, or unowned drop'):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.assertNotIn('interact', self.client.operations)
        evidence = (self.client.out / 'paving-blockers.jsonl').read_text()
        blocker = json.loads(evidence.splitlines()[-1])
        self.assertEqual(blocker['journal_phase'], 'recovered')
        self.assertEqual(blocker['nearby'],
                         [{'type': 'minecraft:cow', 'distance_blocks': 2.0}])
        self.assertIs(blocker['player_body_clear'], False)
        self.assertNotIn('nearby-private-identity', evidence)
        self.client.entities = []
        self.assertEqual(self.run_one()[0]['result'], 'placed')
        self.assertEqual(self.client.operations.count('mine_block'), 1)

    def test_unconfirmed_safe_navigation_never_writes_placement_intent(self):
        self.client.pickup_inside = True
        self.client.navigation_refused = True
        with self.assertRaisesRegex(PavingBlocked, 'reposition did not finish'):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.assertNotIn('interact', self.client.operations)

    def test_no_scanned_clear_corridor_leaves_recovered_cell_untouched(self):
        self.client.pickup_inside = True
        x, y, z = self.client.pos
        self.client.air_obstacles = {(x-1, y+1, z), (x+1, y+1, z),
                                     (x, y+1, z-1), (x, y+1, z+1),
                                     (x, y+3, z)}
        with self.assertRaisesRegex(PavingBlocked, 'No freshly scanned dry axis route'):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.assertNotIn('navigate', self.client.operations)
        self.assertNotIn('interact', self.client.operations)

    def test_edge_cell_uses_verified_vertical_pose_when_horizontal_ring_is_blocked(self):
        pos = [761021, 63, 797829]
        self.client = FakeClient(Path(self.temp.name) / 'edge-vertical', pos=pos)
        self.client.pickup_inside = True
        x, y, z = pos
        self.client.air_obstacles = {(x-1, y+1, z), (x+1, y+1, z),
                                     (x, y+1, z-1), (x, y+1, z+1)}
        self.assertEqual(self.run_one()[0]['result'], 'placed')
        self.assertEqual(len(self.client.navigation_params), 1)
        waypoint = self.client.navigation_params[0]['target']
        self.assertEqual(waypoint, [x+.5, y+1.45, z+.5])
        self.assertIs(self.client.navigation_params[0]['air_only'], True)
        self.assertEqual(self.client.operations.count('approach_block'), 1)
        self.assertEqual(self.client.operations.count('mine_block'), 1)
        self.assertEqual(self.client.operations.count('interact'), 1)

    def test_live_vertical_settle_skips_approach_that_would_descend_into_hole(self):
        pos = [761019, 63, 797829]
        self.client = FakeClient(Path(self.temp.name) / 'vertical-live-pose', pos=pos)
        self.client.pickup_inside = True
        self.client.vertical_settle_y = 64.31018418550967
        self.client.approach_inside = True
        self.assertEqual(self.run_one()[0]['result'], 'placed')
        self.assertEqual(self.client.operations.count('approach_block'), 1)
        self.assertEqual(self.client.operations.count('mine_block'), 1)
        self.assertEqual(self.client.operations.count('interact'), 1)

    def test_vertical_direct_face_change_stops_before_placement_intent(self):
        pos = [761019, 63, 797829]
        self.client = FakeClient(Path(self.temp.name) / 'vertical-face-change', pos=pos)
        self.client.pickup_inside = True
        self.client.block_after_vertical_selection = True
        with self.assertRaisesRegex(PavingBlocked, 'Direct vertical support face'):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.assertNotIn('place_intent', [row['phase'] for row in self.journal()['receipts']])
        self.assertNotIn('interact', self.client.operations)

    def test_vertical_pose_drift_during_final_scan_stops_before_intent(self):
        pos = [761019, 63, 797829]
        self.client = FakeClient(Path(self.temp.name) / 'vertical-drift', pos=pos)
        self.client.pickup_inside = True
        self.client.direct_scan_drift = True
        with self.assertRaisesRegex(PavingBlocked, 'Direct vertical support face'):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.assertNotIn('place_intent', [row['phase'] for row in self.journal()['receipts']])
        self.assertNotIn('interact', self.client.operations)

    def test_vertical_column_obstruction_keeps_edge_cell_recovered(self):
        pos = [761021, 63, 797829]
        self.client = FakeClient(Path(self.temp.name) / 'edge-no-route', pos=pos)
        self.client.pickup_inside = True
        x, y, z = pos
        self.client.air_obstacles = {(x-1, y+1, z), (x+1, y+1, z),
                                     (x, y+1, z-1), (x, y+1, z+1),
                                     (x, y+3, z)}
        with self.assertRaisesRegex(PavingBlocked, 'No freshly scanned dry axis route'):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.assertEqual(self.client.navigation_params, [])
        self.assertNotIn('interact', self.client.operations)

    def test_y66_cap_uses_low_air_only_axis_route_without_remining(self):
        pos = [761013, 63, 797829]
        self.client = FakeClient(Path(self.temp.name) / 'low-ceiling', pos=pos)
        self.client.pickup_inside = True
        self.client.pickup_feet_y = 63.154938061599374
        self.client.animal_after_pickup = True
        with self.assertRaisesRegex(PavingBlocked, 'animal, player, or unowned drop'):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.client.entities = []
        self.client.animal_after_pickup = False
        self.client.low_settle_y = 64.14
        self.client.air_obstacles = {(pos[0], 66, pos[2])}
        self.assertEqual(self.run_one()[0]['result'], 'placed')
        targets = [row['target'] for row in self.client.navigation_params]
        self.assertTrue(targets)
        self.assertEqual(targets[0], [pos[0]+.5, 64.2, pos[2]+.5])
        self.assertTrue(all(target[1] == 64.2 for target in targets))
        self.assertAlmostEqual(self.client.player_feet[1], 64.14)
        self.assertTrue(all(row['air_only'] is True for row in self.client.navigation_params))
        self.assertEqual(self.client.operations.count('mine_block'), 1)
        self.assertEqual(self.client.operations.count('interact'), 1)

    def test_centered_y64_14_is_clear_but_lower_unsafe_pose_is_not(self):
        pos = (761013, 63, 797829)
        self.assertTrue(paving._player_body_clear(
            {'pos': [pos[0]+.5, 64.14, pos[2]+.5]}, pos))
        self.assertFalse(paving._player_body_clear(
            {'pos': [pos[0]+.5, 64.08, pos[2]+.5]}, pos))

    def test_y66_cap_and_unsafe_y65_neighbors_keep_recovered_hole(self):
        pos = [761013, 63, 797829]
        self.client = FakeClient(Path(self.temp.name) / 'low-ceiling-blocked', pos=pos)
        self.client.pickup_inside = True
        x, _, z = pos
        self.client.air_obstacles = {(x, 66, z), (x-1, 65, z), (x+1, 65, z),
                                     (x, 65, z-1), (x, 65, z+1)}
        with self.assertRaisesRegex(PavingBlocked, 'No freshly scanned dry axis route'):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'recovered')
        self.assertEqual(self.client.navigation_params, [])
        self.assertNotIn('place_intent', [row['phase'] for row in self.journal()['receipts']])
        self.assertNotIn('interact', self.client.operations)

    def test_nearby_animal_blocks_mutation(self):
        self.client.entities = [{'type': 'minecraft:salmon', 'uuid': 'pet-fish',
                                 'pos': [POS[0]+.5, 63.5, POS[2]+.5]}]
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.assertNotIn('mine_block', self.client.operations)

    def test_animal_arriving_after_mining_holds_the_cell_without_pickup_or_placement(self):
        self.client.animal_after_mine = True
        with self.assertRaises(PavingPending):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'mined')
        self.assertEqual(self.client.operations.count('mine_block'), 1)
        self.assertNotIn('collect_item', self.client.operations)
        self.assertNotIn('interact', self.client.operations)

    def test_pinned_original_and_replacement_stock_are_required(self):
        self.client.actual = 'Block{minecraft:stone}'
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.client.actual = OLD
        self.client.items['minecraft:stone_bricks'] = 0
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.assertNotIn('mine_block', self.client.operations)

    def test_support_fluid_body_and_protected_cells_fail_closed(self):
        self.client.fluid = True
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.client.fluid = False
        self.client.extra = {'pos': [POS[0], 64, POS[2]], 'state': 'Block{minecraft:torch}',
                             'solid': False, 'fluid': False, 'block_entity': False}
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.client.extra = None
        # This is still a pinned target; only the protection guard can reject it.
        self.assertIn(tuple(POS), SITE['pinned_conflicts'])
        self.client.site = {**self.client.site,
                            'protected_xz': ((POS[0], POS[0], POS[2], POS[2]),)}
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.assertNotIn('mine_block', self.client.operations)

    def test_callers_cannot_replace_pinned_site_or_protection(self):
        with self.assertRaises(TypeError):
            pave_batch(self.client, [POS], site=self.client.site, settle=lambda _: None)
        with self.assertRaises(TypeError):
            SITE['protected_xz'] = ()
        with self.assertRaises(TypeError):
            SITE['pinned_conflicts'][tuple(POS)] = (WANTED, OLD)

    def test_water_targets_and_oversized_or_duplicate_batches_are_rejected(self):
        self.client.expected = 'Block{minecraft:water}[level=0]'
        with self.assertRaises(PavingBlocked):
            self.run_one()
        self.assertNotIn('mine_block', self.client.operations)
        with self.assertRaises(PavingBlocked):
            pave_batch(self.client, [POS]*2)
        with self.assertRaises(PavingBlocked):
            pave_batch(self.client, [POS]*5)


if __name__ == '__main__':
    unittest.main()
