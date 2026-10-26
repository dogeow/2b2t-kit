import copy
import unittest
from unittest.mock import patch
from cobblestone_stack_recipes import supported
from stack_recipe import plan_batch, settled_result, supported as batch_supported
from test_stack_recipe import fixture
from test_grouped_recipe import Client
from kit_runtime.inventory import InventorySession

SLAB = {'recipe_id':'cobblestone_slab','output':'minecraft:cobblestone_slab','width':3,'produces':6,
        'ingredients':{'minecraft:cobblestone':[1,2,3]}}
STAIR = {'recipe_id':'cobblestone_stairs','output':'minecraft:cobblestone_stairs','width':3,'produces':4,
         'ingredients':{'minecraft:cobblestone':[1,4,5,7,8,9]}}

class CobblestoneRecipeTest(unittest.TestCase):
    def test_rejects_wrong_yield_shape_material_and_recipe(self):
        for spec in [SLAB, STAIR]:
            self.assertTrue(supported(spec));self.assertTrue(batch_supported(spec))
            for change in [{'produces':True},{'produces':1},{'recipe_id':'custom'}, {'width':True},
                           {'ingredients':{'minecraft:stone':next(iter(spec['ingredients'].values()))}},
                           {'ingredients':{'minecraft:cobblestone':[1,2,3,4]}}]:
                self.assertFalse(supported({**spec,**change}))
            wrong=copy.deepcopy(spec);wrong['ingredients']['minecraft:cobblestone'][0]=True
            self.assertFalse(supported(wrong))
    def test_slab_group_distributes_once_and_keeps_partial_source_remainder(self):
        before=fixture([('cobblestone',64)],empty=4)
        batch=plan_batch(before,SLAB,10)
        self.assertEqual((10,60,'exact_groups'),(batch['rounds'],batch['produced'],batch['distribution']))
        client=Client(before);session=InventorySession(client)
        with patch('kit_runtime.inventory.time.sleep'):
            for action in batch['actions']:
                session.distribute_exact(client.status(),client.status()['menu']['slots'][action['source']],action['cells'],action['count'])
        self.assertEqual([10,10,10],[client.status()['menu']['slots'][i]['count'] for i in [1,2,3]])
        self.assertEqual(34,client.status()['menu']['slots'][10]['count'])
        self.assertEqual(1,sum(op=='distribute' for op,_ in client.calls))
    def test_yield_is_verified_against_actual_consumption(self):
        for spec,used,made in [(SLAB,30,60),(STAIR,30,20)]:
            before=fixture([('cobblestone',64)],empty=4);batch=plan_batch(before,spec,10)
            after=fixture([('cobblestone',64-used),(spec['output'].removeprefix('minecraft:'),made)],empty=3)
            self.assertTrue(settled_result(before,after,spec,batch))
            wrong=fixture([('cobblestone',65-used),(spec['output'].removeprefix('minecraft:'),made)],empty=3)
            self.assertFalse(settled_result(before,wrong,spec,batch))
