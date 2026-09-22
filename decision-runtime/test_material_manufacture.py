from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from material_manufacture import manufacture
from recipe_catalog import RecipeCatalog


class Client:
    def __init__(self, root, stock):
        self.root = self.out = root
        self.stock = Counter(stock)
        self.crafted = []

    def status(self):
        return {'time': 12345, 'menu': {'type': 'CraftingMenu'},
                'inventory': [{'slot': i, 'item': item, 'count': count}
                              for i, (item, count) in enumerate(self.stock.items())]}

    def execute(self, client, spec, target):
        rounds = (target - self.stock[spec['output']]) // spec['produces']
        for item, slots in spec['ingredients'].items():
            count = rounds * len(slots)
            if self.stock[item] < count:
                raise AssertionError('Tried to craft with nonexistent ingredients')
            self.stock[item] -= count
        self.stock[spec['output']] += rounds * spec['produces']
        self.crafted.append(spec['output'])
        return self.status()


class ManufactureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        jar = self.root / 'recipes.jar'
        with zipfile.ZipFile(jar, 'w') as z:
            for name, output, count, ingredients in (
                ('planks', 'minecraft:oak_planks', 4, ['minecraft:oak_log']),
                ('door', 'minecraft:oak_door', 3, ['minecraft:oak_planks'] * 6),
            ):
                z.writestr('data/minecraft/recipe/' + name + '.json', json.dumps({
                    'type': 'minecraft:crafting_shapeless', 'ingredients': ingredients,
                    'result': {'id': output, 'count': count}}))
        self.catalog = RecipeCatalog(jar)

    def test_dependencies_execute_and_finished_planks_survive(self):
        c = Client(self.root, {'minecraft:oak_log': 3})
        with patch('material_manufacture.craft_recipe.execute', side_effect=c.execute):
            result = manufacture(c, self.catalog, {'minecraft:oak_door': 2, 'minecraft:oak_planks': 4})
        self.assertTrue(result['complete'])
        self.assertEqual(c.crafted, ['minecraft:oak_planks', 'minecraft:oak_door', 'minecraft:oak_planks'])
        self.assertGreaterEqual(c.stock['minecraft:oak_planks'], 4)

    def test_missing_supply_is_never_virtual_execution_stock(self):
        c = Client(self.root, {'minecraft:oak_log': 1})
        with patch('material_manufacture.craft_recipe.execute', side_effect=c.execute):
            result = manufacture(c, self.catalog, {'minecraft:oak_door': 2})
        self.assertFalse(result['complete'])
        self.assertEqual(c.crafted, [])
        self.assertEqual(c.stock['minecraft:oak_log'], 1)

    def test_personal_reserve_cannot_be_consumed(self):
        c = Client(self.root, {'minecraft:oak_log': 3})
        with patch('material_manufacture.craft_recipe.execute', side_effect=c.execute):
            result = manufacture(c, self.catalog, {'minecraft:oak_door': 2}, {'minecraft:oak_log': 2})
        self.assertFalse(result['complete'])
        self.assertEqual(c.stock['minecraft:oak_log'], 3)

    def test_safety_lock_blocks_before_first_inventory_mutation(self):
        c = Client(self.root, {'minecraft:oak_log': 3})
        (self.root / 'safety-hold.json').write_text('{"active":true}')
        with patch('material_manufacture.craft_recipe.execute') as execute:
            with self.assertRaises(RuntimeError):
                manufacture(c, self.catalog, {'minecraft:oak_door': 2})
            execute.assert_not_called()

    def test_partial_batch_uses_real_stock_and_keeps_the_full_remaining_goal(self):
        c=Client(self.root,{'minecraft:oak_log':2})
        with patch('material_manufacture.craft_recipe.execute',side_effect=c.execute):
            result=manufacture(c,self.catalog,{'minecraft:oak_door':9},allow_partial=True)
        self.assertEqual(c.stock['minecraft:oak_door'],3)
        self.assertEqual(result['remaining_targets'],{'minecraft:oak_door':6})
        self.assertFalse(result['complete'])
        self.assertTrue(any(s['state']=='crafted_partial' for s in result['steps']))

    def test_partial_mode_still_protects_personal_reserves(self):
        c=Client(self.root,{'minecraft:oak_log':2})
        with patch('material_manufacture.craft_recipe.execute',side_effect=c.execute):
            result=manufacture(c,self.catalog,{'minecraft:oak_door':9},{'minecraft:oak_log':1},allow_partial=True)
        self.assertEqual(c.stock['minecraft:oak_log'],1)
        self.assertFalse(result['complete']);self.assertEqual(c.stock['minecraft:oak_door'],0)

    def test_lock_appearing_mid_batch_prevents_next_recipe(self):
        c = Client(self.root, {'minecraft:oak_log': 3})
        def craft_then_lock(*args):
            state = c.execute(*args)
            (self.root / 'safety-hold.json').write_text('{"active":true}')
            return state
        with patch('material_manufacture.craft_recipe.execute', side_effect=craft_then_lock):
            with self.assertRaises(RuntimeError):
                manufacture(c, self.catalog, {'minecraft:oak_door': 2})
        self.assertEqual(c.crafted, ['minecraft:oak_planks'])


if __name__ == '__main__':
    unittest.main()
