import unittest
import craft_recipe


class ScreenTest(unittest.TestCase):
    def test_restricted_ingredient_never_falls_back_to_personal_bow(self):
        rows=[{'slot':10,'item':'minecraft:bow','count':1,'enchantments':[{'id':'minecraft:power','level':5}]},
              {'slot':11,'item':'minecraft:bow','count':1}]
        self.assertEqual([rows[1]],craft_recipe.ingredient_sources(rows,'minecraft:bow',11))
        self.assertEqual([],craft_recipe.ingredient_sources(rows,'minecraft:bow',12))
        inventory=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64} for i in range(36)]
        inventory[0].update(item='minecraft:bow',count=1,max_stack=1)
        slots=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64} for i in range(46)]
        slots[10].update(item='minecraft:bow',count=1,max_stack=1)
        class Fake:
            def status(self):
                return {'screen':'CraftingScreen','menu':{'type':'CraftingMenu','id':1,
                        'cursor':{'item':'minecraft:air','count':0},'slots':slots},'inventory':inventory}
        previous=craft_recipe.k
        try:
            craft_recipe.k=Fake()
            with self.assertRaisesRegex(RuntimeError,'Missing recipe ingredient'):
                craft_recipe.mixed({'minecraft:bow':[5]},'minecraft:dispenser',1,1,ingredient_slots={'minecraft:bow':11})
            self.assertEqual('minecraft:bow',slots[10]['item'])
        finally:craft_recipe.k=previous
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
