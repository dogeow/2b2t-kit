"""Offline surface-dirt worker regressions; no live Kit client is constructed."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_client import Handoff
from material_jobs.acquisition import acquire
from material_jobs.dirt_harvest import candidate, validate_region
from material_jobs.discovery import choose_region


def block(pos, name, *, fluid=False, block_entity=False):
    return {'pos': list(pos), 'state': 'Block{minecraft:' + name + '}',
            'solid': not fluid, 'passable': False, 'fluid': fluid,
            'block_entity': block_entity}


def soil_patch():
    return ([block((x, 63, z), 'stone') for x in range(7) for z in range(7)]
            + [block((x, 64, z), 'dirt') for x in range(7) for z in range(7)])


def profile(region=None):
    return {'protected_regions': [{'min': [-100, 50, -100], 'max': [-80, 95, -80]}],
            'depots': [[-94, 64, -94]], 'search_origin': [-90, 80, -90],
            'resource_regions': [region or {'item': 'minecraft:dirt',
                                             'min': [0, 64, 0], 'max': [6, 64, 6]}]}


class FakeClient:
    world = 'offline-world'

    def __init__(self, rows=None, before=0):
        self.rows = copy.deepcopy(rows if rows is not None else soil_patch())
        self.actions = []
        self.last = None
        self.mine_reply = None
        self.state = {'world_session': self.world, 'pos': [3.5, 70.1, 3.5],
                      'health': 20, 'food': 20, 'guard_armed': True,
                      'guard_pve_only': True, 'flight': True,
                      'air_only_navigation_protocol': 2,
                      'time': 1, 'inventory': [
                          {'slot': i, 'item': 'minecraft:air', 'count': 0, 'max_stack': 64}
                          for i in range(36)]}
        self.state['inventory'][0] = {'slot': 0, 'item': 'minecraft:diamond_shovel',
                                      'count': 1, 'durability': 600, 'max_stack': 1}
        self.state['inventory'][1] = {'slot': 1, 'item': 'minecraft:dirt',
                                      'count': before, 'max_stack': 64}

    def status(self):
        return copy.deepcopy(self.state)

    def checked(self, op, **params):
        reply = self.request(op, **params)
        if reply.get('phase') != 'done':
            raise RuntimeError(reply.get('detail', 'failed'))
        return reply

    def request(self, op, **params):
        self.actions.append((op, copy.deepcopy(params)))
        self.last = 'offline-' + str(len(self.actions))
        if op == 'scan':
            return {'blocks': [copy.deepcopy(row) for row in self.rows
                               if all(params['min'][i] <= row['pos'][i] <= params['max'][i]
                                      for i in range(3))]}
        if op == 'navigate':
            self.state['pos'] = list(params['target'])
            return {'phase': 'done'}
        if op == 'select_item':
            self.state['hand'] = {'item': params['item']}
            return {'phase': 'done'}
        if op == 'mine_block':
            if isinstance(self.mine_reply, Exception):
                raise self.mine_reply
            if self.mine_reply is not None:
                return self.mine_reply
            target = next(row for row in self.rows if row['pos'] == params['pos'])
            assert target['state'] == params['expected_state']
            self.rows.remove(target)
            self.state['inventory'][1]['count'] += 1
            self.state['time'] += 1
            return {'phase': 'done'}
        raise AssertionError(op)


class DirtAcquisitionTest(unittest.TestCase):
    def setUp(self):
        settled = patch('material_jobs.navigation.settled_state',
                        side_effect=lambda c, *args, **kwargs: c.status())
        settled.start(); self.addCleanup(settled.stop)

    def test_one_dirt_block_has_exact_mining_and_inventory_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            c = FakeClient(before=2)
            result = acquire(c, 'minecraft:dirt', 3, profile(), directory, lambda: None)
            self.assertEqual(('done', 3, 1),
                             (result['phase'], result['after'], result['gained']))
            mines = [params for op, params in c.actions if op == 'mine_block']
            self.assertEqual(1, len(mines))
            self.assertEqual('Block{minecraft:dirt}', mines[0]['expected_state'])
            self.assertEqual('up', mines[0]['face'])
            self.assertTrue(all(params['air_only'] for op, params in c.actions if op == 'navigate'))
            ledger = json.loads((Path(directory) / 'acquisition-dirt.json').read_text())
            receipt = next(v for k, v in ledger['visited'].items() if k.startswith('dirt-block-'))
            self.assertEqual(('collected', 2, 3, 1),
                             (receipt['state'], receipt['before'], receipt['after'], receipt['gained']))
            self.assertEqual(mines[0]['pos'], receipt['pos'])

    def test_454_dirt_target_uses_absolute_inventory_count(self):
        with tempfile.TemporaryDirectory() as directory:
            c = FakeClient(before=9)
            result = acquire(c, 'minecraft:dirt', 454, profile(), directory, lambda: None)
            self.assertEqual(('waiting', 9, 10, 1),
                             (result['phase'], result['before'], result['after'], result['gained']))
            self.assertEqual(1, sum(op == 'mine_block' for op, _ in c.actions))

    def test_next_call_never_digs_below_the_previous_column(self):
        with tempfile.TemporaryDirectory() as directory:
            c = FakeClient()
            first = acquire(c, 'minecraft:dirt', 2, profile(), directory, lambda: None)
            second = acquire(c, 'minecraft:dirt', 2, profile(), directory, lambda: None)
            mines = [params['pos'] for op, params in c.actions if op == 'mine_block']
            self.assertEqual(('waiting', 'done'), (first['phase'], second['phase']))
            self.assertEqual(2, len(mines))
            self.assertNotEqual(mines[0][::2], mines[1][::2])
            self.assertEqual([64, 64], [p[1] for p in mines])

    def test_grass_only_patch_is_not_excavated_for_dirt(self):
        rows = [dict(row, state='Block{minecraft:grass_block}') if row['pos'][1] == 64
                else row for row in soil_patch()]
        self.assertIsNone(choose_region(rows, 'minecraft:dirt', 0, 0, [3.5, 70, 3.5]))
        with tempfile.TemporaryDirectory() as directory:
            c = FakeClient(rows)
            result = acquire(c, 'minecraft:dirt', 1, profile(), directory, lambda: None)
            self.assertEqual('no_safe_candidate', result['code'])
            self.assertFalse(any(op in ('navigate', 'mine_block') for op, _ in c.actions))

    def test_protected_site_or_depot_blocks_before_any_native_action(self):
        with tempfile.TemporaryDirectory() as directory:
            for changed in ({'protected_regions': []},
                            {'protected_regions': [{'min': [0, 50, 0], 'max': [6, 95, 6]}]},
                            {'depots': [[8, 64, 8]]}):
                with self.subTest(changed=changed):
                    c = FakeClient(); p = {**profile(), **changed}
                    result = acquire(c, 'minecraft:dirt', 1, p, directory, lambda: None)
                    self.assertEqual('blocked', result['phase'])
                    self.assertEqual([], c.actions)

    def test_silk_touch_shovel_still_collects_exact_dirt(self):
        with tempfile.TemporaryDirectory() as directory:
            c = FakeClient()
            c.state['inventory'][0]['enchantments'] = [
                {'id': 'minecraft:silk_touch', 'level': 1}]
            result = acquire(c, 'minecraft:dirt', 1, profile(), directory, lambda: None)
            self.assertEqual(('done', 1), (result['phase'], result['gained']))
            self.assertEqual(1, sum(op == 'mine_block' for op, _ in c.actions))

    def test_unconfirmed_flight_cannot_start_a_break(self):
        with tempfile.TemporaryDirectory() as directory:
            c = FakeClient()
            c.state['flight'] = False
            result = acquire(c, 'minecraft:dirt', 1, profile(), directory, lambda: None)
            self.assertEqual('blocked', result['phase'])
            self.assertFalse(any(op == 'mine_block' for op, _ in c.actions))

    def test_water_lava_containers_burial_and_missing_support_reject_candidate(self):
        pos = [3, 64, 3]
        for replacement in (block((5, 64, 3), 'water', fluid=True),
                            block((5, 64, 3), 'lava', fluid=True),
                            block((5, 64, 3), 'chest', block_entity=True),
                            block((3, 65, 3), 'dirt'),
                            block((3, 63, 3), 'air')):
            with self.subTest(replacement=replacement):
                rows = [row for row in soil_patch() if row['pos'] != replacement['pos']]
                if replacement['state'] != 'Block{minecraft:air}':
                    rows.append(replacement)
                self.assertFalse(candidate(rows, pos))

    def test_unsafe_local_buffer_never_reaches_native_mining(self):
        region = {'item': 'minecraft:dirt', 'min': [3, 64, 3], 'max': [3, 64, 3]}
        for hazard in (block((5, 64, 3), 'water', fluid=True),
                       block((5, 64, 3), 'lava', fluid=True),
                       block((5, 64, 3), 'chest', block_entity=True)):
            with self.subTest(hazard=hazard), tempfile.TemporaryDirectory() as directory:
                rows = [row for row in soil_patch() if row['pos'] != hazard['pos']] + [hazard]
                c = FakeClient(rows)
                result = acquire(c, 'minecraft:dirt', 1, profile(region), directory, lambda: None)
                self.assertEqual('no_safe_candidate', result['code'])
                self.assertFalse(any(op in ('navigate', 'mine_block') for op, _ in c.actions))

    def test_region_scan_checks_bottom_layer_of_safety_buffer(self):
        region = {'item': 'minecraft:dirt', 'min': [3, 64, 3], 'max': [3, 64, 3]}
        with tempfile.TemporaryDirectory() as directory:
            c = FakeClient(soil_patch() + [block((3, 61, 3), 'chest', block_entity=True)])
            result = acquire(c, 'minecraft:dirt', 1, profile(region), directory,
                             lambda: None)
            self.assertEqual('no_safe_candidate', result['code'])
            self.assertFalse(any(op in ('navigate', 'mine_block') for op, _ in c.actions))

    def test_fresh_local_scan_checks_bottom_layer_after_region_scan(self):
        region = {'item': 'minecraft:dirt', 'min': [3, 64, 3], 'max': [3, 64, 3]}

        class ChangedClient(FakeClient):
            def request(self, op, **params):
                reply = super().request(op, **params)
                if op == 'scan' and sum(name == 'scan' for name, _ in self.actions) == 1:
                    self.rows.append(block((3, 61, 3), 'chest', block_entity=True))
                return reply

        with tempfile.TemporaryDirectory() as directory:
            c = ChangedClient()
            result = acquire(c, 'minecraft:dirt', 1, profile(region), directory,
                             lambda: None)
            self.assertEqual('waiting', result['phase'])
            self.assertFalse(any(op in ('navigate', 'mine_block') for op, _ in c.actions))

    def test_benign_native_rejection_is_skipped_without_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            c = FakeClient(); c.mine_reply = {'phase': 'error', 'detail': 'Mining target out of reach'}
            first = acquire(c, 'minecraft:dirt', 1, profile(), directory, lambda: None)
            self.assertEqual('waiting', first['phase'])
            ledger = json.loads((Path(directory) / 'acquisition-dirt.json').read_text())
            self.assertEqual('skipped', next(v for k, v in ledger['visited'].items()
                                             if k.startswith('dirt-block-'))['state'])
            acquire(c, 'minecraft:dirt', 1, profile(), directory, lambda: None)
            mines = [params['pos'] for op, params in c.actions if op == 'mine_block']
            self.assertEqual(2, len(mines))
            self.assertNotEqual(mines[0], mines[1])

    def test_handoff_keeps_inflight_block_and_prevents_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            c = FakeClient(); c.mine_reply = Handoff('manual control')
            with self.assertRaises(Handoff):
                acquire(c, 'minecraft:dirt', 1, profile(), directory, lambda: None)
            before = len(c.actions)
            result = acquire(c, 'minecraft:dirt', 1, profile(), directory, lambda: None)
            self.assertEqual('blocked', result['phase'])
            self.assertEqual(before, len(c.actions))
            ledger = json.loads((Path(directory) / 'acquisition-dirt.json').read_text())
            self.assertEqual('inflight', next(v for k, v in ledger['visited'].items()
                                              if k.startswith('dirt-block-'))['state'])

    def test_native_done_without_block_change_remains_inflight(self):
        with tempfile.TemporaryDirectory() as directory:
            c = FakeClient(); c.mine_reply = {'phase': 'done'}
            first = acquire(c, 'minecraft:dirt', 1, profile(), directory, lambda: None)
            self.assertEqual('block_unconfirmed', first['code'])
            before = len(c.actions)
            second = acquire(c, 'minecraft:dirt', 1, profile(), directory, lambda: None)
            self.assertEqual('blocked', second['phase'])
            self.assertEqual(before, len(c.actions))

    def test_discovery_offers_only_bounded_natural_topsoil(self):
        found = choose_region(soil_patch(), 'minecraft:dirt', 0, 0, [3.5, 70, 3.5])
        self.assertIsNotNone(found)
        self.assertEqual(('minecraft:dirt', 'natural_survey'),
                         (found['item'], found['source']))
        self.assertEqual(([0, 0], [15, 15]),
                         ([found['min'][0], found['min'][2]],
                          [found['max'][0], found['max'][2]]))
        self.assertLessEqual(found['max'][1] - found['min'][1], 15)
        unsafe = soil_patch() + [block((5, 64, 3), 'lava', fluid=True)]
        self.assertFalse(candidate(unsafe, [3, 64, 3]))

    def test_region_cannot_be_extended_to_deep_excavation(self):
        p = profile()
        for region in ({'min': [0, 40, 0], 'max': [6, 64, 6]},
                       {'min': [0, 64, 0], 'max': [32, 64, 6]}):
            with self.assertRaises(ValueError):
                validate_region(region, p, {})


if __name__ == '__main__':
    unittest.main()
