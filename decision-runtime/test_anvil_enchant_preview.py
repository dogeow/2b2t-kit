from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from anvil_enchant_preview import (run, stack_key, inspect_preview, validate_inputs,
                                    infer_left_penalty, infer_right_penalty, menu_slot)


def empty(slot=None):
    r = {'item': 'minecraft:air', 'count': 0, 'max_stack': 1}
    if slot is not None: r['slot'] = slot
    return r


def seed():
    return {'item': 'minecraft:wooden_shovel', 'count': 1, 'max_stack': 1,
            'durability': 59, 'max_durability': 59}


def book(name='minecraft:mending', level=1):
    return {'item': 'minecraft:enchanted_book', 'count': 1, 'max_stack': 1,
            'stored_enchantments': [{'id': name, 'level': level}]}


class Client:
    world = 'w'; task = 'task'
    def __init__(self, out, cost=2, level=30, fail_return=False):
        self.out = Path(out) / 'control'; self.out.mkdir()
        self.inventory = [empty(i) for i in range(36)]
        self.inventory[0] = {**seed(), 'slot': 0}
        self.inventory[1] = {**book(), 'slot': 1}
        self.inventory[2] = {'item': 'minecraft:netherite_sword', 'count': 1, 'max_stack': 1, 'slot': 2}
        self.menu = None; self.cost = cost; self.level = level; self.time = 0
        self.calls = []; self.fail_return = fail_return; self.owned_material_menu = None

    def sync(self):
        if self.menu:
            for i in range(36):
                self.inventory[i] = {**deepcopy(self.menu['slots'][menu_slot(i)]), 'slot': i}
            slots = self.menu['slots']
            if slots[0]['count'] and slots[1]['count']:
                result = {**seed(), 'enchantments': [{'id': 'minecraft:mending', 'level': 1}], 'slot': 2}
                slots[2] = result if self.cost < 40 else empty(2)
                self.menu['anvil_cost'] = self.cost
            else:
                slots[2] = empty(2); self.menu['anvil_cost'] = 0

    def status(self):
        self.sync(); self.time += 1
        menu = self.menu or {'id': 0, 'type': 'InventoryMenu', 'cursor': empty(), 'slots': []}
        return deepcopy({'time': self.time, 'world_session': self.world,
                         'screen': 'AnvilScreen' if self.menu else '',
                         'experience_level': self.level, 'inventory': self.inventory,
                         'hand': {'item': 'minecraft:netherite_sword'}, 'control_revision': 3,
                         'supervision_lease': {'id': 'lease'}, 'menu': menu})

    def checked(self, op, **params):
        self.calls.append((op, deepcopy(params)))
        if op == 'scan':
            return {'phase': 'done', 'blocks': [{'state': 'Block{minecraft:anvil}[facing=south]'}]}
        if op == 'interact':
            slots = [empty(i) for i in range(39)]
            for i in range(36): slots[menu_slot(i)] = {**deepcopy(self.inventory[i]), 'slot': menu_slot(i)}
            self.menu = {'id': 7, 'type': 'AnvilMenu', 'cursor': empty(), 'slots': slots,
                         'anvil_cost': 0, 'anvil_too_expensive': self.cost >= 40,
                         'anvil_result_may_pickup': self.level >= self.cost and self.cost < 40}
            self.owned_material_menu = 7
        elif op == 'slot_click':
            i = params['slot']; row = self.menu['slots'][i]
            if i == 2: raise AssertionError('Preview must never click output')
            if params['kind'] == 'quick_move':
                if self.fail_return: raise RuntimeError('original return click outcome unknown')
                destination = next(r for r in self.menu['slots'][3:] if not r['count'])
                self.menu['slots'][destination['slot']] = {**deepcopy(row), 'slot': destination['slot']}
                self.menu['slots'][i] = empty(i)
            else:
                cursor = self.menu['cursor']
                self.menu['slots'][i] = {**deepcopy(cursor), 'slot': i}
                self.menu['cursor'] = {k: deepcopy(v) for k, v in row.items() if k != 'slot'}
        elif op == 'close_menu':
            self.sync(); self.menu = None; self.owned_material_menu = None
        else:
            raise AssertionError(op)
        return {**self.status(), 'phase': 'done', 'id': 'request-' + str(len(self.calls))}


class PreviewTests(unittest.TestCase):
    def test_duplicate_status_frames_do_not_erase_a_valid_observation(self):
        from anvil_enchant_preview import _wait
        frames=iter([{'time':1,'valid':True},{'time':1,'valid':True},{'time':2,'valid':True}])
        class Observer:
            def status(self):return next(frames)
        with patch('anvil_enchant_preview.time.sleep'):
            result,times=_wait(Observer(),lambda s:s['valid'])
        self.assertEqual(times,[1,2])

    def test_stored_enchantment_identity_is_not_just_same_book_item_id(self):
        self.assertNotEqual(stack_key(book()), stack_key(book('minecraft:unbreaking', 3)))
        self.assertEqual(stack_key({**book(), 'slot': 5}), stack_key({**book(), 'slot': 12}))

    def test_does_not_accept_curse_or_discarded_input_enchantment(self):
        for right, expected in [(book('minecraft:binding_curse'), {'minecraft:binding_curse': 1}),
                                (book(), {'minecraft:unbreaking': 3})]:
            with self.assertRaises(ValueError): validate_inputs(seed(), right, expected)

    def test_full_preview_returns_both_inputs_without_output_click_or_xp(self):
        with tempfile.TemporaryDirectory() as d, patch('anvil_enchant_preview.time.sleep'):
            client = Client(d)
            result = run(client, [1, 2, 3], 0, 1, seed(), book(), {'minecraft:mending': 1}, Path(d) / 'preview')
            self.assertTrue(result['complete']); self.assertTrue(result['inputs_returned'])
            self.assertTrue(result['preview_accepted']); self.assertEqual(2, result['cost_levels'])
            self.assertEqual(30, client.level); self.assertIsNone(client.menu)
            self.assertEqual(0, result['output_clicks'])
            self.assertEqual({'right': 9, 'left': 10}, result['returned_slots'])
            self.assertEqual(stack_key(book()), stack_key(client.inventory[9]))
            self.assertEqual(stack_key(seed()), stack_key(client.inventory[10]))
            self.assertTrue(all(p['slot'] != 2 for op, p in client.calls if op == 'slot_click'))
            self.assertEqual(0, infer_right_penalty(result, right_enchantment_value=2, left_penalty=0))

    def test_unaffordable_preview_is_readable_but_never_spends_levels(self):
        with tempfile.TemporaryDirectory() as d, patch('anvil_enchant_preview.time.sleep'):
            client = Client(d, cost=9, level=1)
            result = run(client, [1, 2, 3], 0, 1, seed(), book(), {'minecraft:mending': 1}, Path(d) / 'preview')
            self.assertTrue(result['preview_accepted']); self.assertFalse(result['affordable_now'])
            self.assertEqual(1, client.level)
            self.assertEqual(7, infer_left_penalty(result, right_enchantment_value=2, right_penalty=0))

    def test_too_expensive_preview_restores_inputs_and_is_not_cost_inference(self):
        with tempfile.TemporaryDirectory() as d, patch('anvil_enchant_preview.time.sleep'):
            client = Client(d, cost=40)
            result = run(client, [1, 2, 3], 0, 1, seed(), book(), {'minecraft:mending': 1}, Path(d) / 'preview')
            self.assertTrue(result['complete']); self.assertTrue(result['too_expensive'])
            self.assertFalse(result['preview_accepted']); self.assertIsNone(client.menu)
            with self.assertRaises(ValueError): infer_left_penalty(result, right_enchantment_value=2, right_penalty=0)

    def test_unknown_input_return_is_not_repeated_or_automatically_closed(self):
        with tempfile.TemporaryDirectory() as d, patch('anvil_enchant_preview.time.sleep'):
            client = Client(d, fail_return=True); out = Path(d) / 'preview'
            with self.assertRaisesRegex(RuntimeError, 'outcome unknown'):
                run(client, [1, 2, 3], 0, 1, seed(), book(), {'minecraft:mending': 1}, out)
            returns = [p for op, p in client.calls if op == 'slot_click' and p['kind'] == 'quick_move']
            self.assertEqual(1, len(returns)); self.assertIsNotNone(client.menu)
            self.assertFalse(any(op == 'close_menu' for op, p in client.calls))
            receipt = json.loads((out / 'preview.json').read_text())
            self.assertFalse(receipt['complete']); self.assertEqual('return_input', receipt['pending']['stage'])

    def test_changed_declared_book_stops_before_open_or_click(self):
        with tempfile.TemporaryDirectory() as d:
            client = Client(d)
            with self.assertRaises(ValueError):
                run(client, [1, 2, 3], 0, 1, seed(), book('minecraft:unbreaking', 3),
                    {'minecraft:unbreaking': 3}, Path(d) / 'preview')
            self.assertEqual([], client.calls)


if __name__ == '__main__': unittest.main()
