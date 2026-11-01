import copy,os,unittest
from stack_recipe import supported,plan_batch,settled_result
from test_stack_recipe import fixture
SPEC={'recipe_id':'spruce_trapdoor','output':'minecraft:spruce_trapdoor','width':3,'produces':2,
      'ingredients':{'minecraft:spruce_planks':[1,2,3,4,5,6]}}
class SpruceTrapdoorBatchTest(unittest.TestCase):
 def test_rejects_wrong_material_shape_count_width_and_custom_recipe(self):
  self.assertTrue(supported(SPEC))
  for change in [{'produces':1},{'produces':True},{'width':2},{'width':True},{'recipe_id':'custom'},
                 {'ingredients':{'minecraft:oak_planks':[1,2,3,4,5,6]}},
                 {'ingredients':{'minecraft:spruce_planks':[1,2,3,4,5,5]}},
                 {'ingredients':{'minecraft:spruce_planks':[1,2,3,4,5,True]}},
                 {'ingredients':{'minecraft:spruce_planks':[1,2,3,4,5,6],'minecraft:iron_ingot':[7]}}]:
   self.assertFalse(supported({**SPEC,**change}),change)
 def test_full_six_stack_batch_makes128_with_exact384_plank_consumption(self):
  before=fixture([('spruce_planks',64)]*6)
  batch=plan_batch(before,SPEC,64)
  self.assertEqual((64,128),(batch['rounds'],batch['produced']))
  after=fixture([('spruce_trapdoor',64),('spruce_trapdoor',64)],empty=4)
  self.assertTrue(settled_result(before,after,SPEC,batch))
  wrong=fixture([('spruce_trapdoor',64),('spruce_trapdoor',63)],empty=4)
  self.assertFalse(settled_result(before,wrong,SPEC,batch))
 def test_final_odd_recipe_preserves_unused_planks_and_exact_output(self):
  before=fixture([('spruce_planks',8)],empty=4);batch=plan_batch(before,SPEC,1)
  self.assertEqual((1,2),(batch['rounds'],batch['produced']))
  after=fixture([('spruce_planks',2),('spruce_trapdoor',2)],empty=3)
  self.assertTrue(settled_result(before,after,SPEC,batch))
  wrong=fixture([('spruce_planks',1),('spruce_trapdoor',2)],empty=3)
  self.assertFalse(settled_result(before,wrong,SPEC,batch))
 @unittest.skipUnless(os.environ.get('MINECRAFT_TEST_CLIENT_JAR'),'Minecraft recipe jar not configured')
 def test_contract_matches_actual_installed_recipe_catalog(self):
  from recipe_catalog import RecipeCatalog
  spec=RecipeCatalog(os.environ['MINECRAFT_TEST_CLIENT_JAR']).choose('minecraft:spruce_trapdoor',{'minecraft:spruce_planks':384},3)
  self.assertEqual({k:spec[k]for k in SPEC},SPEC);self.assertTrue(supported(spec))
if __name__=='__main__':unittest.main()
