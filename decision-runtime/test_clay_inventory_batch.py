import unittest
from stack_recipe import supported
from material_manufacture import _inventory_batch

class ClayInventoryBatchTest(unittest.TestCase):
    def test_full_inventory_clay_balls_merge_into_existing_clay_output(self):
        slots=[{'slot':i,'item':'minecraft:diamond_sword','count':1,'max_stack':1}for i in range(45)]
        slots[9].update(item='minecraft:clay_ball',count=40,max_stack=64)
        slots[10].update(item='minecraft:clay',count=5,max_stack=64)
        state={'menu':{'slots':slots},'inventory':[{**r,'slot':i}for i,r in enumerate(slots[9:45])]}
        spec={'recipe_id':'clay','output':'minecraft:clay','produces':1,'width':2,'ingredients':{'minecraft:clay_ball':[1,2,3,4]}}
        self.assertTrue(supported(spec));batch=_inventory_batch(state,spec,15)
        self.assertEqual((10,10),(batch['rounds'],batch['produced']))
        self.assertEqual([10]*4,[a['count']for a in batch['actions']])
    def test_unknown_recipe_remainders_wrong_count_or_duplicate_cells_not_enabled(self):
        good={'recipe_id':'clay','output':'minecraft:clay','produces':1,'width':2,'ingredients':{'minecraft:clay_ball':[1,2,3,4]}}
        for change in({'recipe_id':'custom_clay'},{'produces':True},{'produces':4},{'width':1},
                {'ingredients':{'minecraft:clay_ball':[1,2,3,3]}},{'ingredients':{'minecraft:water_bucket':[1,2,3,4]}}):
            self.assertFalse(supported({**good,**change}))
if __name__=='__main__':unittest.main()
