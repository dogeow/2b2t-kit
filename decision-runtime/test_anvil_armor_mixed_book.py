from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from anvil_enchant_preview import inspect_preview, validate_inputs, run
from test_anvil_enchant_preview import Client


def stack(item, enchantments=(), *, slot=0):
    field = 'stored_enchantments' if item == 'minecraft:enchanted_book' else 'enchantments'
    row = {'item': item, 'count': 1, 'max_stack': 1, 'slot': slot,
           field: [{'id': name, 'level': level} for name, level in enchantments]}
    if item != 'minecraft:enchanted_book':
        row.update(durability=363, max_durability=363)
    return row


class MixedArmorBookTests(unittest.TestCase):
    def setUp(self):
        self.helmet = stack('minecraft:diamond_helmet')
        self.book = stack('minecraft:enchanted_book', [
            ('minecraft:protection', 4), ('minecraft:piercing', 4), ('minecraft:riptide', 3)])
        self.expected = {'minecraft:protection': 4}
        self.ignored = ('minecraft:piercing', 'minecraft:riptide')

    def test_default_still_refuses_discarding_book_effects(self):
        with self.assertRaises(ValueError):
            validate_inputs(self.helmet, self.book, self.expected)

    def test_explicit_known_incompatible_effects_allow_armor_only(self):
        validate_inputs(self.helmet, self.book, self.expected, ignored_book_enchantments=self.ignored)
        with self.assertRaises(ValueError):
            validate_inputs(stack('minecraft:diamond_sword'), self.book, self.expected,
                            ignored_book_enchantments=self.ignored)

    def test_cannot_ignore_protection_or_effect_on_existing_armor(self):
        with self.assertRaises(ValueError):
            validate_inputs(self.helmet, self.book, {'minecraft:piercing': 4, 'minecraft:riptide': 3},
                            ignored_book_enchantments=('minecraft:protection',))
        cursed = stack('minecraft:diamond_helmet', [('minecraft:riptide', 1)])
        with self.assertRaises(ValueError):
            validate_inputs(cursed, self.book, self.expected, ignored_book_enchantments=self.ignored)

    def test_preview_must_match_exact_armor_output(self):
        output = stack('minecraft:diamond_helmet', [('minecraft:protection', 4)], slot=2)
        state = {'menu': {'type': 'AnvilMenu', 'cursor': {'count': 0},
                          'anvil_cost': 3, 'anvil_result_may_pickup': True,
                          'slots': [self.helmet, self.book, output] +
                                   [{'item': 'minecraft:air', 'count': 0, 'slot': i}
                                    for i in range(3, 39)]}}
        self.assertTrue(inspect_preview(state, self.helmet, self.book, self.expected)['preview_accepted'])
        output['enchantments'].append({'id': 'minecraft:piercing', 'level': 4})
        self.assertFalse(inspect_preview(state, self.helmet, self.book, self.expected)['preview_accepted'])

    def test_full_preview_returns_original_mixed_book_and_records_explicit_exclusions(self):
        helmet, book = self.helmet, self.book
        class ArmorClient(Client):
            def __init__(self, out):
                super().__init__(out, cost=3)
                self.inventory[0] = {**deepcopy(helmet), 'slot': 0}
                self.inventory[1] = {**deepcopy(book), 'slot': 1}
            def sync(self):
                super().sync()
                if self.menu and all(self.menu['slots'][i]['count'] for i in (0, 1)):
                    self.menu['slots'][2] = stack('minecraft:diamond_helmet',
                                                  [('minecraft:protection', 4)], slot=2)
        with tempfile.TemporaryDirectory() as d, patch('anvil_enchant_preview.time.sleep'):
            c = ArmorClient(d)
            result = run(c, [1, 2, 3], 0, 1, helmet, book, self.expected, Path(d) / 'preview',
                         ignored_book_enchantments=self.ignored)
            self.assertTrue(result['complete'])
            self.assertEqual(result['ignored_book_enchantments'], sorted(self.ignored))
            self.assertEqual(result['output_clicks'], 0)
            self.assertEqual(c.level, 30)
            self.assertFalse(any(op == 'slot_click' and p['slot'] == 2 for op, p in c.calls))


if __name__ == '__main__':
    unittest.main()
