from unittest import TestCase
from projection_scene_delta import classify_flowing_water

H='Block{minecraft:hopper}[enabled=true,facing=west]'
W='Block{minecraft:water}[level=8]'
S='Block{minecraft:water}[level=0]'

class WetSceneTests(TestCase):
 def check(self,before,after,**kw):
  return classify_flowing_water(before,after,{(0,0,0):H},{(0,0,0):H},kw.get('boxes',[{'min':[-2,-2,-2],'max':[2,2,2]}]))
 def test_exact_hopper_and_flow_changes_are_separate(self):
  r=self.check({(0,0,0):W,(1,0,0):W},{(0,0,0):H,(2,0,0):W})
  self.assertEqual({(0,0,0)},r['completed']);self.assertEqual({(1,0,0),(2,0,0)},r['water_updates']);self.assertFalse(r['unexpected'])
 def test_sources_are_never_waived_even_at_the_target(self):
  r=self.check({(0,0,0):W,(1,0,0):S},{(0,0,0):H})
  self.assertEqual({(1,0,0)},r['sources_lost']);self.assertIn((1,0,0),r['unexpected'])
  r=self.check({(0,0,0):S},{(0,0,0):H});self.assertFalse(r['completed']);self.assertIn((0,0,0),r['unexpected'])
 def test_changed_containers_and_waterlogged_blocks_remain_unexpected(self):
  for old,new in [('Block{minecraft:chest}[waterlogged=false]','Block{minecraft:chest}[waterlogged=true]'),('Block{minecraft:stone}',W),(W,'Block{minecraft:stone}')]:
   with self.subTest(old=old,new=new):self.assertIn((1,0,0),self.check({(1,0,0):old},{(1,0,0):new})['unexpected'])
 def test_outside_scope_changes_and_unfinished_targets_are_not_ignored(self):
  self.assertIn((9,0,0),self.check({(9,0,0):W},{})['unexpected'])
  r=self.check({(0,0,0):W},{(0,0,0):'Block{minecraft:water}[level=1]'});self.assertFalse(r['completed']);self.assertIn((0,0,0),r['unexpected'])
 def test_unbounded_invalid_and_target_excluding_scopes_fail(self):
  for boxes in [[],None,[{'min':[-100,-100,-100],'max':[100,100,100]}],[{'min':[1,1,1],'max':[2,2,2]}],[{'min':[False,0,0],'max':[1,1,1]}]]:
   with self.subTest(boxes=boxes),self.assertRaises(ValueError):self.check({}, {},boxes=boxes)
