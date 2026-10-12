import copy
import unittest
from stack_recipe import supported,plan_batch,settled_result
from material_manufacture import _inventory_batch
from test_stack_recipe import fixture

class StoneBulkRecipesTest(unittest.TestCase):
    def test_exact_vanilla_stone_shapes_outputs_and_integer_cells(self):
        for output,raw,count,shapes in (
            ('stone_bricks','stone',4,{2:[1,2,3,4],3:[1,2,4,5]}),
            ('stone_brick_slab','stone_bricks',6,{3:[1,2,3]}),
            ('chiseled_stone_bricks','stone_brick_slab',1,{2:[1,3],3:[1,4]})):
            for width,cells in shapes.items():
                s={'output':'minecraft:'+output,'produces':count,'width':width,'ingredients':{'minecraft:'+raw:cells}}
                self.assertTrue(supported(s))
                for bad in ({'produces':True},{'produces':count+1},{'width':True},
                            {'ingredients':{'minecraft:dirt':cells}},
                            {'ingredients':{'minecraft:'+raw:[True]+cells[1:]}},
                            {'ingredients':{'minecraft:'+raw:cells+cells[:1]}}):
                    self.assertFalse(supported({**s,**bad}))
    def test_two_full_slab_stacks_make_64_chiseled_blocks_in_one_inventory_batch(self):
        s=fixture([('stone_brick_slab',64),('stone_brick_slab',64)],empty=5)
        # InventoryMenu uses 0..4 crafting, 5..8 armour, 9..44 carried slots.
        slots=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(46)]
        for i,row in enumerate(s['menu']['slots'][10:]):slots[i+9]={**row,'slot':i+9}
        state={'menu':{'id':0,'type':'InventoryMenu','cursor':{'item':'minecraft:air','count':0},'slots':slots},
               'inventory':[{**row,'slot':i}for i,row in enumerate(slots[9:45])]}
        spec={'output':'minecraft:chiseled_stone_bricks','produces':1,'width':2,'ingredients':{'minecraft:stone_brick_slab':[1,3]}}
        batch=_inventory_batch(state,spec,64)
        self.assertEqual((64,64,2),(batch['rounds'],batch['produced'],len(batch['actions'])))
        self.assertEqual([64,64],[a['count']for a in batch['actions']])
    def test_workbench_slab_batch_and_chiseled_consumption_are_exact(self):
        slab={'output':'minecraft:stone_brick_slab','produces':6,'width':3,'ingredients':{'minecraft:stone_bricks':[1,2,3]}}
        before=fixture([('stone_bricks',64)]*3,empty=4);batch=plan_batch(before,slab,32)
        self.assertEqual(192,batch['produced'])
        chiseled={'output':'minecraft:chiseled_stone_bricks','produces':1,'width':3,'ingredients':{'minecraft:stone_brick_slab':[1,4]}}
        before=fixture([('stone_brick_slab',64)]*2,empty=4);batch=plan_batch(before,chiseled,64)
        after=fixture([('chiseled_stone_bricks',64)],empty=5)
        self.assertTrue(settled_result(before,after,chiseled,batch))
        after['inventory'][1].update(item='minecraft:stone_brick_slab',count=1)
        self.assertFalse(settled_result(before,after,chiseled,batch))

if __name__=='__main__':unittest.main()
