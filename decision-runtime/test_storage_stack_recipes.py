import copy
import unittest
from unittest.mock import patch
from storage_stack_recipes import supported
from stack_recipe import plan_batch,settled_result,supported as batch_supported
from test_stack_recipe import fixture
from test_grouped_recipe import Client
from kit_runtime.inventory import InventorySession

CHEST={'recipe_id':'chest','output':'minecraft:chest','width':3,'produces':1,
       'ingredients':{'minecraft:spruce_planks':[1,2,3,4,6,7,8,9]}}
HOPPER={'recipe_id':'hopper','output':'minecraft:hopper','width':3,'produces':1,
        'ingredients':{'minecraft:iron_ingot':[1,3,4,6,8],'minecraft:chest':[5]}}

class StorageStackRecipeTest(unittest.TestCase):
    def test_only_exact_vanilla_recipes_are_admitted(self):
        for spec in (CHEST,HOPPER):
            self.assertTrue(supported(spec));self.assertTrue(batch_supported(spec))
            for change in ({'recipe_id':'custom'},{'width':2},{'width':True},
                           {'produces':True},{'produces':2},
                           {'ingredients':{**spec['ingredients'],'minecraft:water_bucket':[9]}}):
                self.assertFalse(supported({**spec,**change}))
            wrong=copy.deepcopy(spec);next(iter(wrong['ingredients'].values()))[0]=True
            self.assertFalse(supported(wrong))
        self.assertFalse(supported({**HOPPER,'ingredients':{'minecraft:iron_ingot':[1,3,4,6,9],'minecraft:chest':[5]}}))
        self.assertFalse(supported({**CHEST,'ingredients':{'minecraft:spruce_planks':[1,2,3,4,6,7,8,8]}}))
        self.assertFalse(supported({**CHEST,'ingredients':{'minecraft:stone':[1,2,3,4,6,7,8,9]}}))
        mixed={**CHEST,'ingredients':{'minecraft:spruce_planks':[1,2,3,4], 'minecraft:oak_planks':[6,7,8,9]}}
        self.assertTrue(supported(mixed))
    def test_eight_chests_share_one_confirmed_distribution(self):
        state=fixture([('spruce_planks',64)],empty=4)
        plan=plan_batch(state,CHEST,16)
        self.assertEqual((8,8,'exact_groups'),(plan['rounds'],plan['produced'],plan['distribution']))
        c=Client(state);session=InventorySession(c)
        with patch('kit_runtime.inventory.time.sleep'):
            for a in plan['actions']:
                session.distribute_exact(c.status(),c.status()['menu']['slots'][a['source']],a['cells'],a['count'])
        self.assertEqual(2,len(c.calls));self.assertEqual([8]*8,[c.status()['menu']['slots'][i]['count']for i in [1,2,3,4,6,7,8,9]])
        self.assertEqual(0,c.status()['menu']['cursor']['count'])
    def test_hopper_group_keeps_exact_iron_and_chest_balances(self):
        before=fixture([('iron_ingot',60),('chest',12)],empty=4)
        plan=plan_batch(before,HOPPER,12)
        self.assertEqual((12,12,2),(plan['rounds'],plan['produced'],len(plan['actions'])))
        after=fixture([('hopper',12)],empty=5)
        self.assertTrue(settled_result(before,after,HOPPER,plan))
        wrong=fixture([('hopper',12),('iron_ingot',1)],empty=4)
        self.assertFalse(settled_result(before,wrong,HOPPER,plan))
    def test_fragmented_iron_uses_only_available_material_and_per_cell_fallback(self):
        state=fixture([('iron_ingot',40),('iron_ingot',24),('chest',12)],empty=4)
        group=plan_batch(state,HOPPER,12)
        self.assertEqual(8,group['rounds'])
        fallback=plan_batch(state,HOPPER,12,grouped=False)
        self.assertIsNotNone(fallback)
        self.assertLessEqual(fallback['rounds']*5,64)
        self.assertFalse(any(a['item']=='minecraft:iron_ingot'and a['count']>a['source_count']for a in fallback['actions']))

if __name__=='__main__':unittest.main()
