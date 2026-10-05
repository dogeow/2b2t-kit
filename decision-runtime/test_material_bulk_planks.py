"""Ordinary wood batching through the real catalog and isolated menu-0 executor."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

import craft_recipe
from material_manufacture import _inventory_batch, manufacture
from recipe_catalog import RecipeCatalog
import stack_recipe
from test_material_manufacture import InventoryCraftClient


PAIRS={'minecraft:oak_log':'minecraft:oak_planks','minecraft:spruce_log':'minecraft:spruce_planks'}


class WoodClient(InventoryCraftClient):
    def status(self):
        self.clock+=1
        raw=self.slots[1]
        valid=raw['count'] and raw['item'] in PAIRS and not any(row['count'] for row in self.slots[2:5])
        self.slots[0].update(item=PAIRS[raw['item']] if valid else 'minecraft:air',count=4 if valid else 0)
        return deepcopy({'time':self.clock,'screen':self.screen,
            'inventory_cursor_precondition_protocol':1,'inventory_isolation':{'supported':True,'active':True},
            'menu':{'id':0,'type':'InventoryMenu','cursor':self.cursor,'slots':self.slots},
            'inventory':[{**row,'slot':i}for i,row in enumerate(self.slots[9:45])]})

    def checked(self,op,**params):
        if params.get('slot')!=0 or params.get('kind')!='quick_move':return super().checked(op,**params)
        self.calls.append((op,dict(params)));output=self.slots[0];raw=self.slots[1]
        assert op=='slot_click' and params['menu_id']==0 and not self.cursor['count']
        assert output['item']==params['expected_item'] and output['count']==params['expected_count']==4
        assert PAIRS.get(raw['item'])==output['item'] and raw['count']>0
        left=4*raw['count'];item=output['item']
        raw.update(item='minecraft:air',count=0)
        for row in self.slots[9:45]:
            if row['item']==item and row['count']<64:
                put=min(left,64-row['count']);row['count']+=put;left-=put
        for row in self.slots[9:45]:
            if not row['count']:
                put=min(left,64);row.update(item=item,count=put);left-=put
                if not left:break
        assert left==0,'Native output cannot drop or overwrite existing items'
        return self.status()


class BulkPlankTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.jar=self.root/'recipes.jar'
        with zipfile.ZipFile(self.jar,'w')as jar:
            for raw,output in PAIRS.items():
                jar.writestr('data/minecraft/recipe/'+output.split(':')[1]+'.json',json.dumps({
                    'type':'minecraft:crafting_shapeless','ingredients':[raw],
                    'result':{'id':output,'count':4}}))
        self.catalog=RecipeCatalog(self.jar)

    def spec(self,raw):return self.catalog.choose(PAIRS[raw],{raw:64},2)

    def test_exact53_oak_and16_spruce_are_single_menu0_shift_batches(self):
        for raw,n,before in [('minecraft:oak_log',53,8),('minecraft:spruce_log',16,0)]:
            stock={raw:n,**({PAIRS[raw]:before}if before else{})}
            client=WoodClient(self.root,stock=stock)
            batch=_inventory_batch(client.status(),self.spec(raw),before+4*n)
            self.assertEqual((n,4*n),(batch['rounds'],batch['produced']))
            with patch('kit_runtime.inventory.time.sleep'),patch('material_manufacture.time.sleep'):
                made=manufacture(client,self.catalog,{PAIRS[raw]:before+4*n})
            self.assertTrue(made['complete'])
            results=[p for op,p in client.calls if p['slot']==0 and p['kind']=='quick_move']
            self.assertEqual(1,len(results));self.assertTrue(all(p['menu_id']==0 for op,p in client.calls))
            self.assertFalse(any(row['count']for row in client.slots[1:5]));self.assertFalse(client.cursor['count'])

    @unittest.skipUnless(Path('/Applications/.minecraft/versions/26.1.2/26.1.2.jar').is_file(),'Installed native recipe JAR is unavailable')
    def test_installed_catalog_proves_exact_actual_oak53_and_spruce16(self):
        catalog=RecipeCatalog('/Applications/.minecraft/versions/26.1.2/26.1.2.jar')
        for raw,n,before in [('minecraft:oak_log',53,8),('minecraft:spruce_log',16,0)]:
            spec=catalog.choose(PAIRS[raw],{raw:n},2)
            self.assertEqual({raw:[1]},spec['ingredients']);self.assertEqual(4,spec['produces'])
            client=WoodClient(self.root,stock={raw:n,**({PAIRS[raw]:before}if before else{})})
            batch=_inventory_batch(client.status(),spec,before+4*n)
            self.assertEqual((n,4*n),(batch['rounds'],batch['produced']))

    def test_two_species_use_one_controller_and_preserve_other_items(self):
        client=WoodClient(self.root,stock={'minecraft:oak_log':53,'minecraft:oak_planks':8,
                                        'minecraft:spruce_log':16,'minecraft:diamond_sword':1})
        client.slots[12].update(max_stack=1,durability=899)
        original=deepcopy(client.slots[12])
        with patch('kit_runtime.inventory.time.sleep'),patch('material_manufacture.time.sleep'):
            for item,target in [('minecraft:oak_planks',220),('minecraft:spruce_planks',64)]:
                self.assertTrue(manufacture(client,self.catalog,{item:target})['complete'])
        self.assertEqual(original,client.slots[12])
        totals={item:sum(r['count']for r in client.slots[9:45]if r['item']==item)for item in PAIRS.values()}
        self.assertEqual({'minecraft:oak_planks':220,'minecraft:spruce_planks':64},totals)
        self.assertEqual(2,sum(p['slot']==0 and p['kind']=='quick_move'for op,p in client.calls))

    def test_no_output_capacity_refuses_before_touching_any_grid_slot(self):
        client=WoodClient(self.root,stock={'minecraft:oak_log':53})
        for row in client.slots[10:45]:row.update(item='minecraft:diamond_sword',count=1,max_stack=1)
        with self.assertRaises(craft_recipe.InventoryCapacity):_inventory_batch(client.status(),self.spec('minecraft:oak_log'),212)
        made=manufacture(client,self.catalog,{'minecraft:oak_planks':212})
        self.assertFalse(made['complete']);self.assertEqual([],client.calls)

    def test_partial_input_stack_and_original_keep_never_require_return_to_storage(self):
        client=WoodClient(self.root,stock={'minecraft:oak_log':56,'minecraft:oak_planks':8})
        with patch('kit_runtime.inventory.time.sleep'),patch('material_manufacture.time.sleep'):
            made=manufacture(client,self.catalog,{'minecraft:oak_planks':220},keep={'minecraft:oak_log':3})
        self.assertTrue(made['complete']);self.assertEqual(3,sum(r['count']for r in client.slots[9:45]if r['item']=='minecraft:oak_log'))

    def test_allowlist_does_not_enable_other_wood_variants_or_tools(self):
        for item in PAIRS.values():self.assertTrue(stack_recipe.supported({'output':item}))
        for item in ('minecraft:birch_planks','minecraft:stripped_oak_log','minecraft:oak_door','minecraft:bucket'):
            self.assertFalse(stack_recipe.supported({'output':item}))


if __name__=='__main__':unittest.main()
