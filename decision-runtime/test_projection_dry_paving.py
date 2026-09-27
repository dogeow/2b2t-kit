import copy
import hashlib
import json
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

    def _inventory(self):
        return [{'slot': 0, 'item': 'minecraft:stone_bricks', 'count': self.items['minecraft:stone_bricks'], 'max_stack': 64},
                {'slot': 1, 'item': 'minecraft:diamond_shovel', 'count': 1, 'durability': 100},
                {'slot': 2, 'item': 'minecraft:dirt', 'count': self.items['minecraft:dirt'], 'max_stack': 64},
                {'slot': 3, 'item': 'minecraft:air', 'count': 0, 'max_stack': 1}]

    def status(self):
        snapshot = copy.deepcopy({'time': 10000, 'connected': True, 'world_session': self.world,
                              'dry_paving_protocol': self.host_protocol,
                              'server': 'simpcraft.com:25565', 'dimension': 'minecraft:overworld',
                              'screen': '', 'manual_movement': False, 'health': 20, 'food': 20,
                              'guard_armed': True, 'guard_pve_only': True, 'guard_busy': False,
                              'flight': True, 'under_water': False, 'air_return_active': False,
                              'safety_hold': {'active': False},
                              'supervision_lease': {'kind': 'materials', 'job_session': self.task},
                              'projection_selection': {'key': self.key, **self.site['bounds']},
                              'pos': [self.pos[0]+.5, 64.3, self.pos[2]+.5],
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
                'dimension': 'minecraft:overworld', 'loaded_chunks_verified': True,
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
            return {'phase': 'done', 'world_session': self.world,
                    'blocks': self._scan(params['min'], params['max'])}
        if op == 'select_item':
            self.hand = params['item']
            return {'phase': 'done'}
        if op == 'approach_block':
            if self.block_after_mine and self.actual == 'Block{minecraft:air}':
                return {'phase': 'waiting', 'detail': 'No visible collision-free depot approach'}
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
        files = list(Path(self.temp.name).glob('dry-paving-v1/*/*.json'))
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
