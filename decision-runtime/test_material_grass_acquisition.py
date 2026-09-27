"""Offline grass-block acquisition contracts; no game client or worker is started."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_client import Handoff
from material_jobs.acquisition import acquire
from material_jobs.discovery import choose_region
from material_jobs.equipment import prepare
from test_material_dirt_acquisition import FakeClient as DirtClient, profile, soil_patch


GRASS = 'minecraft:grass_block'


def grass_patch():
    return [dict(row, state='Block{minecraft:grass_block}[snowy=false]')
            if row['pos'][1] == 64 else row for row in soil_patch()]


def grass_profile(region=None):
    return profile(region or {'item': GRASS, 'min': [0, 64, 0], 'max': [6, 64, 6]})


class GrassClient(DirtClient):
    def __init__(self, *, silk=True, durability=600, slot=0, before=0):
        super().__init__(grass_patch(), before)
        shovel = {'slot': slot, 'item': 'minecraft:diamond_shovel', 'count': 1,
                  'durability': durability, 'max_stack': 1,
                  'enchantments': [{'id': 'minecraft:silk_touch', 'level': 1}] if silk else []}
        self.state['inventory'][0] = {'slot': 0, 'item': 'minecraft:air', 'count': 0,
                                      'max_stack': 64}
        self.state['inventory'][slot] = shovel
        self.state['inventory'][1] = {'slot': 1, 'item': GRASS, 'count': before, 'max_stack': 64}
        self.state['grass_block_tool_protocol'] = 1
        self.selected_override = None

    def request(self, op, **params):
        if op == 'select_item':
            self.actions.append((op, copy.deepcopy(params)))
            source = self.state['inventory'][params['slot']]
            assert (source['item'], source['count']) == (params['item'], 1)
            selected = params['slot'] if params['slot'] < 9 else 5
            if selected != params['slot']:
                self.state['inventory'][params['slot']], self.state['inventory'][5] = (
                    dict(self.state['inventory'][5], slot=params['slot']),
                    dict(source, slot=5))
            self.state['selected_slot'] = selected
            self.state['hand'] = copy.deepcopy(self.state['inventory'][selected])
            if self.selected_override is not None:
                self.selected_override(self.state)
            return {'phase': 'done'}
        return super().request(op, **params)


class GrassAcquisitionTest(unittest.TestCase):
    def setUp(self):
        settled = patch('material_jobs.navigation.settled_state',
                        side_effect=lambda c, *args, **kwargs: c.status())
        settled.start(); self.addCleanup(settled.stop)

    def test_exact_silk_shovel_slot_and_grass_inventory_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            c = GrassClient(slot=20, before=2)
            result = acquire(c, GRASS, 3, grass_profile(), directory, lambda: None)
            self.assertEqual(('done', 2, 3, 1),
                             (result['phase'], result['before'], result['after'], result['gained']))
            selection = next(params for op, params in c.actions if op == 'select_item')
            mine = next(params for op, params in c.actions if op == 'mine_block')
            self.assertEqual(20, selection['slot'])
            self.assertEqual('Block{minecraft:grass_block}[snowy=false]', mine['expected_state'])
            self.assertEqual((True, 5, 'minecraft:diamond_shovel'),
                             (mine['required_silk_shovel'], mine['expected_tool_slot'], mine['expected_tool_item']))
            self.assertTrue(all(params['air_only'] for op, params in c.actions if op == 'navigate'))
            ledger = json.loads((Path(directory) / 'acquisition-grass_block.json').read_text())
            receipt = next(v for k, v in ledger['visited'].items()
                           if k.startswith('grass_block-block-'))
            self.assertEqual(('collected', 2, 3, 1),
                             (receipt['state'], receipt['before'], receipt['after'], receipt['gained']))

    def test_four_grass_cells_each_have_silk_guard_and_inventory_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            c = GrassClient(slot=20, before=2)
            result = acquire(c, GRASS, 6, grass_profile(), directory, lambda: None)
            self.assertEqual(('done', 2, 6, 4, 4),
                             (result['phase'], result['before'], result['after'],
                              result['gained'], result['collected_cells']))
            mines = [p for op, p in c.actions if op == 'mine_block']
            selections = [p for op, p in c.actions if op == 'select_item']
            self.assertEqual(4, len(mines))
            self.assertEqual(4, len(selections))
            self.assertTrue(all(p['required_silk_shovel'] and p['expected_tool_slot'] == 5
                                and p['expected_tool_item'] == 'minecraft:diamond_shovel'
                                for p in mines))
            self.assertTrue(all(p['item'] == 'minecraft:diamond_shovel' for p in selections))
            ledger = json.loads((Path(directory) / 'acquisition-grass_block.json').read_text())
            receipts = [v for k, v in ledger['visited'].items()
                        if k.startswith('grass_block-block-')]
            self.assertEqual(4, len(receipts))
            self.assertEqual([2, 3, 4, 5], sorted(v['before'] for v in receipts))
            self.assertTrue(all(v['state'] == 'collected' and v['gained'] == 1
                                for v in receipts))

    def test_second_grass_cell_rechecks_selection_safety_and_tool(self):
        changes = (
            lambda s: s.update(projection_selection={
                'key': 'new-build', 'min': [0, 50, 0], 'max': [6, 95, 6]}),
            lambda s: s.update(flight=False),
            lambda s: s['inventory'][0].update(durability=32),
        )

        for change in changes:
            class ChangedAfterFirst(GrassClient):
                def request(self, op, **params):
                    reply = super().request(op, **params)
                    if op == 'mine_block':
                        change(self.state)
                    return reply

            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                c = ChangedAfterFirst()
                result = acquire(c, GRASS, 4, grass_profile(), directory, lambda: None)
                self.assertEqual('blocked', result['phase'])
                self.assertEqual(1, sum(op == 'mine_block' for op, _ in c.actions))
                ledger = json.loads((Path(directory) / 'acquisition-grass_block.json').read_text())
                receipts = [v for k, v in ledger['visited'].items()
                            if k.startswith('grass_block-block-')]
                self.assertEqual(1, len(receipts))
                self.assertEqual('collected', receipts[0]['state'])

    def test_plain_stored_only_worn_or_wrong_shovel_never_mines(self):
        for silk, durability, replacement in (
                (False, 600, None),
                (True, 32, None),
                (True, 600, {'item': 'minecraft:iron_shovel'}),
                (True, 600, {'enchantments': [], 'stored_enchantments': [
                    {'id': 'minecraft:silk_touch', 'level': 1}]})):
            with self.subTest(silk=silk, durability=durability, replacement=replacement), \
                    tempfile.TemporaryDirectory() as directory:
                c = GrassClient(silk=silk, durability=durability)
                if replacement:
                    c.state['inventory'][0].update(replacement)
                result = acquire(c, GRASS, 1, grass_profile(), directory, lambda: None)
                self.assertEqual('blocked', result['phase'])
                self.assertFalse(any(op == 'mine_block' for op, _ in c.actions))

    def test_changed_hand_or_selected_slot_stops_before_native_mining(self):
        for change in (lambda s: s.update(selected_slot=2),
                       lambda s: s['hand'].update(enchantments=[]),
                       lambda s: s['hand'].update(durability=32),
                       lambda s: s['hand'].update(durability=500)):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                c = GrassClient()
                c.selected_override = change
                result = acquire(c, GRASS, 1, grass_profile(), directory, lambda: None)
                self.assertEqual('blocked', result['phase'])
                self.assertFalse(any(op == 'mine_block' for op, _ in c.actions))

    def test_projection_change_during_travel_stops_before_tool_selection(self):
        class ChangedProjection(GrassClient):
            def request(self, op, **params):
                reply = super().request(op, **params)
                if op == 'navigate':
                    self.state['projection_selection'] = {
                        'key': 'new-build', 'min': [0, 50, 0], 'max': [6, 95, 6]}
                return reply

        with tempfile.TemporaryDirectory() as directory:
            c = ChangedProjection()
            result = acquire(c, GRASS, 1, grass_profile(), directory, lambda: None)
            self.assertEqual('blocked', result['phase'])
            self.assertFalse(any(op in ('select_item', 'mine_block') for op, _ in c.actions))

    def test_changed_or_malformed_projection_after_tool_selection_never_mines(self):
        for selection in ({'key': 'new-build', 'min': [0, 50, 0], 'max': [6, 95, 6]},
                          {'key': 'incomplete-build', 'min': [0, 50, 0]}):
            with self.subTest(selection=selection), tempfile.TemporaryDirectory() as directory:
                c = GrassClient()
                c.selected_override = lambda state: state.update(
                    projection_selection=copy.deepcopy(selection))
                result = acquire(c, GRASS, 1, grass_profile(), directory, lambda: None)
                self.assertEqual('blocked', result['phase'])
                self.assertTrue(any(op == 'select_item' for op, _ in c.actions))
                self.assertFalse(any(op == 'mine_block' for op, _ in c.actions))

    def test_buffer_change_during_tool_selection_is_rescanned(self):
        class ChangedBuffer(GrassClient):
            def request(self, op, **params):
                reply = super().request(op, **params)
                if op == 'select_item':
                    for row in self.rows:
                        if row['pos'] == [5, 64, 3]:
                            row.update(state='Block{minecraft:chest}', block_entity=True)
                return reply

        with tempfile.TemporaryDirectory() as directory:
            c = ChangedBuffer()
            result = acquire(c, GRASS, 1, grass_profile(), directory, lambda: None)
            self.assertEqual('waiting', result['phase'])
            self.assertFalse(any(op == 'mine_block' for op, _ in c.actions))
            ledger = json.loads((Path(directory) / 'acquisition-grass_block.json').read_text())
            entry = next(v for k, v in ledger['visited'].items()
                         if k.startswith('grass_block-block-'))
            self.assertEqual('source_or_buffer_changed_after_tool_selection', entry['reason'])

    def test_discovery_distinguishes_grass_from_dirt(self):
        rows = grass_patch()
        found = choose_region(rows, GRASS, 0, 0, [3.5, 70, 3.5])
        self.assertEqual((GRASS, 'natural_survey', 64),
                         (found['item'], found['source'], found['surface_y']))
        self.assertIsNone(choose_region(rows, 'minecraft:dirt', 0, 0, [3.5, 70, 3.5]))

    def test_older_native_host_cannot_start_grass_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            c = GrassClient(); c.state.pop('grass_block_tool_protocol')
            result = acquire(c, GRASS, 1, grass_profile(), directory, lambda: None)
            self.assertEqual('blocked', result['phase'])
            self.assertEqual([], c.actions)

    def test_site_buffer_flight_and_manual_handoff_prevent_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            c = GrassClient()
            self.assertEqual('blocked', acquire(c, GRASS, 1,
                             {**grass_profile(), 'depots': [[8, 64, 8]]}, directory,
                             lambda: None)['phase'])
            self.assertEqual([], c.actions)
        with tempfile.TemporaryDirectory() as directory:
            c = GrassClient(); c.state['flight'] = False
            self.assertEqual('blocked', acquire(c, GRASS, 1, grass_profile(), directory,
                             lambda: None)['phase'])
            self.assertFalse(any(op == 'mine_block' for op, _ in c.actions))
        with tempfile.TemporaryDirectory() as directory:
            c = GrassClient(); c.mine_reply = Handoff('manual control')
            with self.assertRaises(Handoff):
                acquire(c, GRASS, 1, grass_profile(), directory, lambda: None)
            before = len(c.actions)
            result = acquire(c, GRASS, 1, grass_profile(), directory, lambda: None)
            self.assertEqual('blocked', result['phase'])
            self.assertEqual(before, len(c.actions))

    def test_native_success_without_removed_block_remains_inflight(self):
        with tempfile.TemporaryDirectory() as directory:
            c = GrassClient(); c.mine_reply = {'phase': 'done'}
            self.assertEqual('block_unconfirmed', acquire(c, GRASS, 1, grass_profile(),
                             directory, lambda: None)['code'])
            before = len(c.actions)
            self.assertEqual('blocked', acquire(c, GRASS, 1, grass_profile(),
                             directory, lambda: None)['phase'])
            self.assertEqual(before, len(c.actions))

    def test_equipment_requires_silk_touch_shovel(self):
        with tempfile.TemporaryDirectory() as directory:
            c = GrassClient(silk=False)
            self.assertEqual('blocked', prepare(c, GRASS, 1, grass_profile(),
                             Path(directory), lambda: None)['phase'])
            c.state['inventory'][0]['enchantments'] = [
                {'id': 'minecraft:silk_touch', 'level': 1}]
            self.assertEqual('done', prepare(c, GRASS, 1, grass_profile(),
                             Path(directory), lambda: None)['phase'])


if __name__ == '__main__':
    unittest.main()
