from collections import Counter
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from material_manufacture import manufacture, inventory_plan
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


class InventoryCraftClient:
    """Simulate native menu-0 slot semantics, using the real InventorySession."""
    def __init__(self, root, stone=48):
        self.root=self.out=root;self.calls=[];self.screen='';self.after_click=None
        self.slots=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64} for i in range(46)]
        self.slots[9].update(item='minecraft:stone',count=stone)
        self.cursor={'item':'minecraft:air','count':0}

    def status(self):
        ready=all(self.slots[i]['item']=='minecraft:stone' and self.slots[i]['count'] for i in range(1,5))
        self.slots[0].update(item='minecraft:stone_bricks' if ready else 'minecraft:air',count=4 if ready else 0)
        return copy.deepcopy({'time':12345,'screen':self.screen,
            'inventory_isolation':{'supported':True,'active':True},
            'menu':{'id':0,'type':'InventoryMenu','cursor':self.cursor,'slots':self.slots},
            'inventory':[{**row,'slot':i} for i,row in enumerate(self.slots[9:45])]})

    def checked(self,op,**params):
        assert op=='slot_click', 'Inventory manufacturing may not move, open, or close player UI'
        self.calls.append((op,dict(params)));row=self.slots[params['slot']]
        assert params['menu_id']==0 and row['item']==params['expected_item'] and row['count']==params['expected_count']
        if params['kind']=='quick_move':
            item,amount=row['item'],row['count']
            target=next((r for r in self.slots[9:45] if r['item']==item and r['count']+amount<=64),None)
            if target is None:target=next((r for r in self.slots[9:45] if not r['count']),None)
            assert target is not None, 'No output space'
            target.update(item=item,count=target['count']+amount)
            if params['slot']==0:
                for i in range(1,5):
                    self.slots[i]['count']-=1
                    if not self.slots[i]['count']:self.slots[i]['item']='minecraft:air'
            row.update(item='minecraft:air',count=0)
        elif params.get('button',0)==1:
            if self.cursor['count']:
                assert not row['count'] or row['item']==self.cursor['item']
                row.update(item=self.cursor['item'],count=row['count']+1);self.cursor['count']-=1
                if not self.cursor['count']:self.cursor['item']='minecraft:air'
            else:
                amount=(row['count']+1)//2;self.cursor.update(item=row['item'],count=amount);row['count']-=amount
                if not row['count']:row['item']='minecraft:air'
        else:
            if self.cursor['count'] and self.cursor['item']==row['item']:
                row['count']+=self.cursor['count'];self.cursor.update(item='minecraft:air',count=0)
            else:
                row['item'],self.cursor['item']=self.cursor['item'],row['item']
                row['count'],self.cursor['count']=self.cursor['count'],row['count']
        if self.after_click:self.after_click(self)
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
                ('white_dye', 'minecraft:white_dye', 1, ['minecraft:bone_meal']),
                ('door', 'minecraft:oak_door', 3, ['minecraft:oak_planks'] * 6),
            ):
                z.writestr('data/minecraft/recipe/' + name + '.json', json.dumps({
                    'type': 'minecraft:crafting_shapeless', 'ingredients': ingredients,
                    'result': {'id': output, 'count': count}}))
            z.writestr('data/minecraft/recipe/stone_bricks.json',json.dumps({
                'type':'minecraft:crafting_shaped','pattern':['##','##'],'key':{'#':'minecraft:stone'},
                'result':{'id':'minecraft:stone_bricks','count':4}}))
        self.catalog = RecipeCatalog(jar)

    def test_inventory_plan_uses_native_two_by_two_cells_and_rejects_missing_or_three_by_three(self):
        plan=inventory_plan(self.catalog,{'minecraft:stone_bricks':48},{'minecraft:stone':48})
        step=next(row for row in plan['steps'] if row['kind']=='craft')
        self.assertEqual(2,step['width']);self.assertEqual({'minecraft:stone':[1,2,3,4]},step['grid'])
        self.assertIsNone(inventory_plan(self.catalog,{'minecraft:stone_bricks':48},{'minecraft:stone':47}))
        self.assertIsNone(inventory_plan(self.catalog,{'minecraft:oak_door':3},{'minecraft:oak_planks':6}))
        self.assertIsNone(inventory_plan(self.catalog,{'minecraft:stone_bricks':48},{'minecraft:stone':48},{'minecraft:stone':1}))

    def test_inventory_manufacture_consumes_48_stone_and_produces_48_bricks_without_workbench(self):
        c=InventoryCraftClient(self.root)
        with patch('kit_runtime.inventory.time.sleep'),patch('material_manufacture.time.sleep'):
            result=manufacture(c,self.catalog,{'minecraft:stone_bricks':48})
        self.assertTrue(result['complete']);self.assertEqual({},result['remaining_targets'])
        from material_plan import inventory_counts
        self.assertEqual(48,inventory_counts(c.status())['minecraft:stone_bricks'])
        self.assertEqual(0,inventory_counts(c.status())['minecraft:stone'])
        self.assertTrue(all(op=='slot_click' for op,_ in c.calls))
        self.assertTrue(all(not c.status()['menu']['slots'][i]['count'] for i in range(1,5)))
        self.assertEqual('',c.screen);self.assertEqual(0,c.cursor['count'])
        self.assertEqual(12,sum(params['slot']==0 and params['kind']=='quick_move' for _,params in c.calls))

    def test_inventory_manufacture_preserves_player_screen_cursor_and_preexisting_grid(self):
        for kind in ('screen','cursor','grid'):
            with self.subTest(kind=kind):
                c=InventoryCraftClient(self.root)
                if kind=='screen':c.screen='InventoryScreen'
                elif kind=='cursor':c.cursor.update(item='minecraft:diamond',count=1)
                else:c.slots[1].update(item='minecraft:diamond',count=1)
                before=c.status()
                with self.assertRaises(RuntimeError):manufacture(c,self.catalog,{'minecraft:stone_bricks':48})
                self.assertEqual([],c.calls);self.assertEqual(before,c.status())

    def test_inventory_manufacture_stops_if_player_opens_screen_between_owned_clicks(self):
        c=InventoryCraftClient(self.root);c.after_click=lambda client:setattr(client,'screen','InventoryScreen')
        with self.assertRaises(RuntimeError):manufacture(c,self.catalog,{'minecraft:stone_bricks':48})
        self.assertEqual(1,len(c.calls));self.assertEqual('InventoryScreen',c.screen)

    def test_inventory_manufacture_without_output_capacity_does_not_touch_grid(self):
        c=InventoryCraftClient(self.root)
        for row in c.slots[10:45]:row.update(item='minecraft:diamond_sword',count=1,max_stack=1)
        result=manufacture(c,self.catalog,{'minecraft:stone_bricks':48})
        self.assertFalse(result['complete']);self.assertEqual([],c.calls)
        self.assertEqual('waiting_for_inventory_space',result['steps'][0]['state'])

    def test_verified_material_recipe_uses_stack_executor_with_exact_balances(self):
        c=Client(self.root,{'minecraft:bone_meal':64})
        with patch('material_manufacture.stack_recipe.execute',side_effect=c.execute) as fast,patch('material_manufacture.craft_recipe.execute') as legacy:
            result=manufacture(c,self.catalog,{'minecraft:white_dye':64})
        self.assertTrue(result['complete']);self.assertEqual(64,c.stock['minecraft:white_dye'])
        self.assertEqual(0,c.stock['minecraft:bone_meal']);self.assertEqual(1,fast.call_count);legacy.assert_not_called()

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
