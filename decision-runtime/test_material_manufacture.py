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
    RECIPE_OUTPUTS = {
        'minecraft:stone': ('minecraft:stone_bricks', 4),
        'minecraft:cobbled_deepslate': ('minecraft:polished_deepslate', 4),
        'minecraft:polished_deepslate': ('minecraft:deepslate_bricks', 4),
        'minecraft:deepslate_bricks': ('minecraft:deepslate_tiles', 4),
    }

    def __init__(self, root, stone=48, stock=None):
        self.root=self.out=root;self.calls=[];self.screen='';self.after_click=None;self.clock=12345
        self.slots=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64} for i in range(46)]
        for slot,(item,count) in enumerate((stock or {'minecraft:stone':stone}).items(),start=9):
            self.slots[slot].update(item=item,count=count)
        self.cursor={'item':'minecraft:air','count':0}
        self.pending=[]

    def status(self):
        if self.pending:
            return copy.deepcopy(self.pending.pop(0))
        self.clock+=1
        grid={self.slots[i]['item'] for i in range(1,5) if self.slots[i]['count']}
        recipe=self.RECIPE_OUTPUTS.get(next(iter(grid))) if len(grid)==1 and all(self.slots[i]['count'] for i in range(1,5)) else None
        self.slots[0].update(item=recipe[0] if recipe else 'minecraft:air',count=recipe[1] if recipe else 0)
        return copy.deepcopy({'time':self.clock,'screen':self.screen,
            'inventory_cursor_precondition_protocol':1,
            'inventory_isolation':{'supported':True,'active':True},
            'menu':{'id':0,'type':'InventoryMenu','cursor':self.cursor,'slots':self.slots},
            'inventory':[{**row,'slot':i} for i,row in enumerate(self.slots[9:45])]})

    def checked(self,op,**params):
        assert op=='slot_click', 'Inventory manufacturing may not move, open, or close player UI'
        self.calls.append((op,dict(params)));row=self.slots[params['slot']]
        assert params['menu_id']==0 and row['item']==params['expected_item'] and row['count']==params['expected_count']
        assert params['expected_cursor']==(self.cursor['item'] if self.cursor['count'] else 'minecraft:air')
        assert params['expected_cursor_count']==self.cursor['count']
        if params['kind']=='quick_move':
            if params['slot']==0:
                crafts=min(self.slots[i]['count'] for i in range(1,5))
                item,amount=row['item'],row['count']*crafts
                for i in range(1,5):
                    self.slots[i]['count']-=crafts
                    if not self.slots[i]['count']:self.slots[i]['item']='minecraft:air'
            else:
                item,amount=row['item'],row['count']
            left=amount
            for target in [r for r in self.slots[9:45] if r['item']==item and r['count']<64]:
                moved=min(left,64-target['count']);target['count']+=moved;left-=moved
                if not left:break
            for target in [r for r in self.slots[9:45] if not r['count']]:
                moved=min(left,64);target.update(item=item,count=moved);left-=moved
                if not left:break
            assert not left, 'No output space'
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
            for name,source,output in (
                ('polished_deepslate','minecraft:cobbled_deepslate','minecraft:polished_deepslate'),
                ('deepslate_bricks','minecraft:polished_deepslate','minecraft:deepslate_bricks'),
                ('deepslate_tiles','minecraft:deepslate_bricks','minecraft:deepslate_tiles'),
            ):
                z.writestr('data/minecraft/recipe/'+name+'.json',json.dumps({
                    'type':'minecraft:crafting_shaped','pattern':['##','##'],'key':{'#':source},
                    'result':{'id':output,'count':4}}))
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

    def test_allowlisted_two_by_two_chain_uses_one_output_click_per_44_item_stage(self):
        c=InventoryCraftClient(self.root,stock={'minecraft:cobbled_deepslate':44})
        with patch('kit_runtime.inventory.time.sleep'):
            result=manufacture(c,self.catalog,{'minecraft:deepslate_tiles':44})
        from material_plan import inventory_counts
        stock=inventory_counts(c.status())
        self.assertTrue(result['complete'])
        self.assertEqual(44,stock['minecraft:deepslate_tiles'])
        self.assertEqual(0,stock['minecraft:cobbled_deepslate'])
        self.assertEqual(0,stock['minecraft:polished_deepslate'])
        self.assertEqual(0,stock['minecraft:deepslate_bricks'])
        output_clicks=[params for _,params in c.calls
                       if params['slot']==0 and params['kind']=='quick_move']
        self.assertEqual(3,len(output_clicks))
        self.assertLess(len(c.calls),90)
        self.assertEqual(0,c.cursor['count'])
        self.assertTrue(all(not c.slots[i]['count'] for i in range(1,5)))

    def test_allowlisted_batch_preserves_five_input_leftovers(self):
        c=InventoryCraftClient(self.root,stock={'minecraft:cobbled_deepslate':49})
        with patch('kit_runtime.inventory.time.sleep'):
            result=manufacture(c,self.catalog,{'minecraft:polished_deepslate':44})
        from material_plan import inventory_counts
        stock=inventory_counts(c.status())
        self.assertTrue(result['complete'])
        self.assertEqual((5,44),(stock['minecraft:cobbled_deepslate'],
                                 stock['minecraft:polished_deepslate']))
        self.assertEqual(1,sum(params['slot']==0 and params['kind']=='quick_move'
                               for _,params in c.calls))
        self.assertEqual(0,c.cursor['count'])
        self.assertTrue(all(not c.slots[i]['count'] for i in range(1,5)))

    def test_full_inventory_executes_the_exact_small_sources_that_prove_output_room(self):
        c=InventoryCraftClient(self.root,stock={'minecraft:cobbled_deepslate':64})
        for slot in range(10,14):
            c.slots[slot].update(item='minecraft:cobbled_deepslate',count=11)
        for slot in range(14,45):
            c.slots[slot].update(item='minecraft:diamond_sword',count=1,max_stack=1)
        with patch('kit_runtime.inventory.time.sleep'):
            result=manufacture(c,self.catalog,{'minecraft:polished_deepslate':44})
        from material_plan import inventory_counts
        stock=inventory_counts(c.status())
        self.assertTrue(result['complete'])
        self.assertEqual((64,44),(stock['minecraft:cobbled_deepslate'],
                                  stock['minecraft:polished_deepslate']))
        source_pickups=[params['slot'] for _,params in c.calls
                        if params['kind']=='pickup' and params['slot']>=9
                        and params['expected_cursor_count']==0]
        self.assertEqual([10,11,12,13],source_pickups)
        self.assertEqual(1,sum(params['slot']==0 and params['kind']=='quick_move'
                               for _,params in c.calls))
        self.assertEqual(0,c.cursor['count'])
        self.assertTrue(all(not c.slots[i]['count'] for i in range(1,5)))

    def test_batch_output_waits_through_optimistic_rollback_without_replay(self):
        class OutputRollback(InventoryCraftClient):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs);self.rolled_back=False
            def checked(self,op,**params):
                before=super().status()
                result=super().checked(op,**params)
                if params['slot']==0 and params['kind']=='quick_move' and not self.rolled_back:
                    self.rolled_back=True
                    final=copy.deepcopy(result)
                    rollback=copy.deepcopy(before)
                    rollback['time']=final['time']+1
                    authoritative=copy.deepcopy(final);authoritative['time']=final['time']+2
                    confirmed=copy.deepcopy(final);confirmed['time']=final['time']+3
                    self.pending=[rollback,authoritative,confirmed]
                return result
        c=OutputRollback(self.root,stock={'minecraft:cobbled_deepslate':44})
        with patch('kit_runtime.inventory.time.sleep'):
            result=manufacture(c,self.catalog,{'minecraft:polished_deepslate':44})
        self.assertTrue(result['complete']);self.assertTrue(c.rolled_back)
        self.assertEqual(1,sum(params['slot']==0 and params['kind']=='quick_move'
                               for _,params in c.calls))
        self.assertEqual(0,c.cursor['count'])
        self.assertTrue(all(not c.slots[i]['count'] for i in range(1,5)))

    def test_batch_output_timeout_never_replays_ambiguous_shift_click(self):
        class OutputNeverAcknowledged(InventoryCraftClient):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs);self.block_output=False;self.block_ticks=0
            def checked(self,op,**params):
                before=super().status()
                result=super().checked(op,**params)
                if params['slot']==0 and params['kind']=='quick_move':
                    # The native reply was optimistic, then the server rolled
                    # the whole click back. Keep returning the authoritative
                    # filled grid; the executor must time out without replay.
                    self.slots=copy.deepcopy(before['menu']['slots'])
                    self.cursor=copy.deepcopy(before['menu']['cursor'])
                    self.block_output=True
                return result
        c=OutputNeverAcknowledged(self.root,stock={'minecraft:cobbled_deepslate':44})
        def monotonic():
            if not c.block_output:
                return 0
            c.block_ticks+=1
            return 7 if c.block_ticks>=3 else 0
        with patch('kit_runtime.inventory.time.sleep'),patch(
                'kit_runtime.inventory.time.monotonic',side_effect=monotonic):
            with self.assertRaisesRegex(RuntimeError,'inventory_output; no action replay'):
                manufacture(c,self.catalog,{'minecraft:polished_deepslate':44})
        self.assertEqual(1,sum(params['slot']==0 and params['kind']=='quick_move'
                               for _,params in c.calls))
        self.assertIsNotNone(c.owned_inventory_crafting)
        self.assertEqual([11,11,11,11],[c.slots[i]['count'] for i in range(1,5)])

    def test_live_like_47_to_49_pickup_preserves_extra_stock_and_completes_target(self):
        c=InventoryCraftClient(self.root,stone=47);injected=False
        def collect_two(client):
            nonlocal injected
            if not injected and client.cursor['item']=='minecraft:stone' and client.cursor['count']==47:
                client.cursor['count']+=2;injected=True
        c.after_click=collect_two
        with patch('kit_runtime.inventory.time.sleep'),patch('material_manufacture.time.sleep'):
            result=manufacture(c,self.catalog,{'minecraft:stone_bricks':44})
        from material_plan import inventory_counts
        stock=inventory_counts(c.status())
        self.assertTrue(result['complete']);self.assertTrue(injected)
        self.assertEqual((5,44),(stock['minecraft:stone'],stock['minecraft:stone_bricks']))
        self.assertEqual(0,c.cursor['count']);self.assertTrue(all(not c.slots[i]['count'] for i in range(1,5)))
        first=c.calls[0][1]
        self.assertEqual((9,47,'minecraft:air',0),
                         (first['slot'],first['expected_count'],first['expected_cursor'],
                          first['expected_cursor_count']))
        self.assertEqual(1,c.calls[1][1]['slot'])
        self.assertIsNone(c.owned_inventory_crafting)

    def test_inventory_craft_failure_persists_owned_cursor_evidence(self):
        c=InventoryCraftClient(self.root,stone=47)
        def corrupt_cursor(client):
            if len(client.calls)==1:client.cursor.update(item='minecraft:diamond',count=47)
        c.after_click=corrupt_cursor
        with patch('kit_runtime.inventory.time.monotonic',side_effect=[0,7]):
            with self.assertRaisesRegex(RuntimeError,'no action replay'):
                manufacture(c,self.catalog,{'minecraft:stone_bricks':44})
        records=list(self.root.glob('inventory-craft-failure-*.json'))
        self.assertEqual(1,len(records));record=json.loads(records[0].read_text())
        self.assertEqual('ingredient_pickup',record['detail'].split(' at ')[-1].split(';')[0])
        self.assertEqual({'item':'minecraft:diamond','count':47},
                         {k:record['observed']['cursor'][k] for k in ('item','count')})
        self.assertEqual(0,record['observed']['grid'][1]['count'])
        self.assertEqual(0,record['owned_inventory_crafting']['menu_id'])

    def test_inventory_manufacture_preserves_player_screen_cursor_and_preexisting_grid(self):
        for kind in ('screen','cursor','grid'):
            with self.subTest(kind=kind):
                c=InventoryCraftClient(self.root)
                if kind=='screen':c.screen='InventoryScreen'
                elif kind=='cursor':c.cursor.update(item='minecraft:diamond',count=1)
                else:c.slots[1].update(item='minecraft:diamond',count=1)
                before=c.status()
                with self.assertRaises(RuntimeError):manufacture(c,self.catalog,{'minecraft:stone_bricks':48})
                after=c.status();before.pop('time');after.pop('time')
                self.assertEqual([],c.calls);self.assertEqual(before,after)

    def test_inventory_manufacture_rejects_old_host_before_any_click(self):
        c=InventoryCraftClient(self.root)
        original=c.status
        c.status=lambda:{k:v for k,v in original().items()
                         if k!='inventory_cursor_precondition_protocol'}
        with self.assertRaisesRegex(RuntimeError,'isolated inventory menu'):
            manufacture(c,self.catalog,{'minecraft:stone_bricks':48})
        self.assertEqual([],c.calls)

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
