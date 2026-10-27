import unittest
from stack_recipe import supported,plan_batch

class FurnishingStackTest(unittest.TestCase):
 def test_nine_glow_frames_use_exact_inputs_and_preserve_tenth_normal_frame(self):
  spec={'recipe_id':'glow_item_frame','output':'minecraft:glow_item_frame','produces':1,'width':3,'ingredients':{'minecraft:item_frame':[1],'minecraft:glow_ink_sac':[2]}}
  self.assertTrue(supported(spec));self.assertTrue(supported({**spec,'width':2}))
  for change in ({'produces':2},{'ingredients':{'minecraft:item_frame':[True],'minecraft:glow_ink_sac':[2]}},{'ingredients':{'minecraft:item_frame':[1],'minecraft:ink_sac':[2]}},{'recipe_id':'other'}):self.assertFalse(supported({**spec,**change}))
  slots=[{'slot':i,'item':'minecraft:air','count':0}for i in range(46)]
  slots[10].update(item='minecraft:item_frame',count=10);slots[11].update(item='minecraft:glow_ink_sac',count=9)
  batch=plan_batch({'menu':{'type':'CraftingMenu','cursor':{'count':0},'slots':slots}},spec,9)
  self.assertEqual((batch['rounds'],batch['produced']),(9,9))
  self.assertEqual([(a['item'],a['count'])for a in batch['actions']],[('minecraft:item_frame',9),('minecraft:glow_ink_sac',9)])
 def test_only_exact_original_wool_recolor_and_carpet_recipes_are_accepted(self):
  dye={'recipe_id':'dye_light_gray_wool','output':'minecraft:light_gray_wool','produces':1,'width':3,'ingredients':{'minecraft:light_gray_dye':[1],'minecraft:white_wool':[2]}}
  carpet={'recipe_id':'light_gray_carpet','output':'minecraft:light_gray_carpet','produces':3,'width':3,'ingredients':{'minecraft:light_gray_wool':[1,2]}}
  self.assertTrue(supported(dye));self.assertTrue(supported(carpet))
  for change in ({'produces':2},{'ingredients':{'minecraft:light_gray_dye':[1],'minecraft:gray_wool':[2]}},{'recipe_id':'other'},{'ingredients':{'minecraft:light_gray_dye':[True],'minecraft:white_wool':[2]}}):
   self.assertFalse(supported({**dye,**change}))
  self.assertFalse(supported({**carpet,'produces':6}))
 def test_banner_requires_exact_six_wool_and_one_stick_layout(self):
  banner={'recipe_id':'white_banner','output':'minecraft:white_banner','produces':1,'width':3,'ingredients':{'minecraft:white_wool':[1,2,3,4,5,6],'minecraft:stick':[8]}}
  self.assertTrue(supported(banner));self.assertFalse(supported({**banner,'width':2}))
  self.assertFalse(supported({**banner,'ingredients':{'minecraft:white_wool':[1],'minecraft:stick':[8]}}))
 def test_ten_wool_dye_operations_share_one_verified_stack_plan(self):
  slots=[{'slot':i,'item':'minecraft:air','count':0}for i in range(46)]
  slots[10].update(item='minecraft:white_wool',count=22);slots[11].update(item='minecraft:light_gray_dye',count=13)
  state={'menu':{'type':'CraftingMenu','cursor':{'count':0},'slots':slots}}
  spec={'recipe_id':'dye_light_gray_wool','output':'minecraft:light_gray_wool','produces':1,'width':3,'ingredients':{'minecraft:light_gray_dye':[1],'minecraft:white_wool':[2]}}
  plan=plan_batch(state,spec,10)
  self.assertEqual((10,10,2),(plan['rounds'],plan['produced'],len(plan['actions'])))

if __name__=='__main__':unittest.main()
