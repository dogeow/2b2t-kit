import unittest
from unittest.mock import patch

import craft_recipe


class CraftCursorSettleTest(unittest.TestCase):
    def test_concrete_mix_is_limited_to_one_verified_recipe_per_transaction(self):
        self.assertEqual(1, craft_recipe.bounded_rounds('minecraft:white_concrete_powder', 7))
        self.assertEqual(1, craft_recipe.bounded_rounds('minecraft:bone_meal', 7))
        self.assertEqual(1, craft_recipe.bounded_rounds('minecraft:white_dye', 7))
        self.assertEqual(1, craft_recipe.bounded_rounds('minecraft:polished_andesite', 7))
        self.assertEqual(1, craft_recipe.bounded_rounds('minecraft:chest', 7))
        self.assertEqual(1, craft_recipe.bounded_rounds('minecraft:hopper', 7))
        self.assertEqual(1, craft_recipe.bounded_rounds('minecraft:spruce_planks', 7))
        self.assertTrue(craft_recipe.safe_single_round('minecraft:chest'))
        self.assertTrue(craft_recipe.safe_single_round('minecraft:hopper'))
        self.assertEqual(7, craft_recipe.bounded_rounds('minecraft:iron_ingot', 7))

    def test_delayed_server_cursor_update_is_observed_without_another_click(self):
        old = craft_recipe.k
        stale = {'menu': {'id': 3, 'cursor': {'item': 'minecraft:gravel', 'count': 50}}}
        clear = {'menu': {'id': 3, 'cursor': {'item': 'minecraft:air', 'count': 0}}}
        try:
            class Client:
                calls = 0
                def status(self):
                    self.calls += 1
                    return clear
            craft_recipe.k = Client()
            with patch.object(craft_recipe.time, 'sleep'):
                self.assertIs(craft_recipe.wait_clear_cursor(stale, 3), clear)
            self.assertEqual(1, craft_recipe.k.calls)
        finally:
            craft_recipe.k = old

    def test_remaining_ingredient_is_confirmed_before_return_click(self):
        old = craft_recipe.k
        stale = {'menu': {'id': 3, 'cursor': {'item': 'minecraft:air', 'count': 0}}}
        ready = {'menu': {'id': 3, 'cursor': {'item': 'minecraft:gravel', 'count': 50}}}
        try:
            class Client:
                def status(self): return ready
            craft_recipe.k = Client()
            with patch.object(craft_recipe.time, 'sleep'):
                self.assertIs(craft_recipe.wait_cursor_count(stale, 3, 'minecraft:gravel', 50), ready)
        finally:
            craft_recipe.k = old

    def test_grid_requires_two_observations_before_next_ingredient(self):
        old = craft_recipe.k
        good = {'menu': {'id': 3, 'cursor': {'item': 'minecraft:air', 'count': 0},
                         'slots': [{}, {'item': 'minecraft:white_dye', 'count': 1}]}}
        try:
            class Client:
                calls = 0
                def status(self):
                    self.calls += 1
                    return good
            craft_recipe.k = Client()
            with patch.object(craft_recipe.time, 'sleep'):
                self.assertIs(craft_recipe.wait_grid_placed(good, 3, 'minecraft:white_dye', [1], 1), good)
            self.assertEqual(1, craft_recipe.k.calls)
        finally:
            craft_recipe.k = old


if __name__ == '__main__':
    unittest.main()
