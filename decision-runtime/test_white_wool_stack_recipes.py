import copy,os,unittest
from stack_recipe import supported,plan_batch,settled_result
from test_stack_recipe import fixture
STRING={'recipe_id':'white_wool_from_string','output':'minecraft:white_wool','width':3,'produces':1,'ingredients':{'minecraft:string':[1,2,4,5]}}
DYE={'recipe_id':'dye_white_wool','output':'minecraft:white_wool','width':3,'produces':1,'ingredients':{'minecraft:white_dye':[1],'minecraft:light_gray_wool':[2]}}
class WhiteWoolStackRecipeTest(unittest.TestCase):
 def test_only_exact_vanilla_string_and_recolor_recipes(self):
  for spec in [STRING,DYE]:
   self.assertTrue(supported(spec))
   for change in [{'recipe_id':'custom'},{'width':True},{'produces':True},{'produces':2},{'ingredients':{'minecraft:stone':[1,2,4,5]}},{'ingredients':{'minecraft:string':[1,2,4,True]}}]:self.assertFalse(supported({**spec,**change}))
  self.assertFalse(supported({**DYE,'ingredients':{'minecraft:white_dye':[1],'minecraft:white_wool':[2]}}))
  self.assertFalse(supported({**DYE,'ingredients':{'minecraft:black_dye':[1],'minecraft:gray_wool':[2]}}))
 def test_one_stack_string_is_evenly_distributed_in_two_calls(self):
  from unittest.mock import patch
  from test_grouped_recipe import Client
  from kit_runtime.inventory import InventorySession
  before=fixture([('string',64)],empty=4);plan=plan_batch(before,STRING,16);self.assertEqual(('exact_groups',16,16),(plan['distribution'],plan['rounds'],plan['produced']));client=Client(before)
  with patch('kit_runtime.inventory.time.sleep'):
   for a in plan['actions']:InventorySession(client).distribute_exact(client.status(),client.status()['menu']['slots'][a['source']],a['cells'],a['count'])
  self.assertEqual([16]*4,[client.status()['menu']['slots'][i]['count']for i in [1,2,4,5]]);self.assertEqual(2,len(client.calls));self.assertEqual(0,client.status()['menu']['cursor']['count'])
 def test_string_conversion_requires_exact64_to16_balance(self):
  before=fixture([('string',64)],empty=3);plan=plan_batch(before,STRING,16);after=fixture([('white_wool',16)],empty=3);self.assertTrue(settled_result(before,after,STRING,plan));wrong=fixture([('white_wool',15)],empty=3);self.assertFalse(settled_result(before,wrong,STRING,plan))
 def test_recolor_consumes_one_dye_per_existing_wool(self):
  before=fixture([('white_dye',12),('light_gray_wool',11)],empty=3);plan=plan_batch(before,DYE,11);after=fixture([('white_dye',1),('white_wool',11)],empty=3);self.assertTrue(settled_result(before,after,DYE,plan));wrong=fixture([('white_dye',2),('white_wool',11)],empty=3);self.assertFalse(settled_result(before,wrong,DYE,plan))
 @unittest.skipUnless(os.environ.get('MINECRAFT_TEST_CLIENT_JAR'),'Minecraft recipe jar not configured')
 def test_contracts_match_current26_2_recipe_catalog(self):
  from recipe_catalog import RecipeCatalog
  cat=RecipeCatalog(os.environ['MINECRAFT_TEST_CLIENT_JAR'])
  for expected,stock in [(STRING,{'minecraft:string':64}),(DYE,{'minecraft:white_dye':12,'minecraft:light_gray_wool':11})]:
   actual=cat.choose('minecraft:white_wool',stock,3);self.assertEqual({k:actual[k]for k in expected},expected);self.assertTrue(supported(actual))
if __name__=='__main__':unittest.main()
