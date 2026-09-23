import unittest
import craft_recipe


class ScreenTest(unittest.TestCase):
    def test_inventory_menu_without_open_screen_is_not_a_safe_click_target(self):
        class Fake:
            def status(self):
                return {'screen': '', 'menu': {'type': 'InventoryMenu',
                        'cursor': {'item': 'minecraft:air'}, 'slots': []}, 'inventory': []}
        previous = craft_recipe.k
        try:
            craft_recipe.k = Fake()
            with self.assertRaisesRegex(RuntimeError, 'Open the inventory screen'):
                craft_recipe.mixed({'minecraft:iron_block': [1]}, 'minecraft:iron_ingot', 9, 9)
        finally:
            craft_recipe.k = previous


if __name__ == '__main__': unittest.main()
