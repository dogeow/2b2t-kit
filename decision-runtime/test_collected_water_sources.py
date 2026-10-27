from unittest import TestCase
from projection_scene_delta import classify_collected_water_sources
S='Block{minecraft:water}[level=0]';F='Block{minecraft:water}[level=8]'
class CollectedSourceTests(TestCase):
 def run_case(self,before,after,expected=None,targets=None,boxes=None):
  return classify_collected_water_sources(before,after,expected or{},targets if targets is not None else{(0,0,0)},boxes if boxes is not None else[{'min':[-2,-2,-2],'max':[2,2,2]}])
 def test_only_declared_source_and_bounded_descendant_water_can_clear(self):
  r=self.run_case({(0,0,0):S,(1,0,0):F},{});self.assertEqual({(0,0,0)},r['cleared_sources']);self.assertEqual({(1,0,0)},r['water_updates']);self.assertFalse(r['unexpected'])
 def test_preserved_or_regenerated_source_is_not_called_removed(self):
  r=self.run_case({(0,0,0):S},{(0,0,0):S});self.assertFalse(r['cleared_sources']);self.assertEqual({(0,0,0)},r['uncleared_sources'])
 def test_another_source_is_protected_even_inside_the_scope(self):
  r=self.run_case({(0,0,0):S,(1,0,0):S},{});self.assertEqual({(1,0,0)},r['other_sources_lost']);self.assertIn((1,0,0),r['unexpected'])
 def test_container_or_outside_water_changes_are_not_excused(self):
  for p,old,new in [((1,0,0),'Block{minecraft:chest}',None),((9,0,0),F,None),((1,0,0),F,'Block{minecraft:cobblestone}')]:
   before={(0,0,0):S,p:old};after={}if new is None else{p:new};self.assertIn(p,self.run_case(before,after)['unexpected'])
 def test_planned_sources_and_invalid_baselines_or_unbounded_targets_fail(self):
  for args in [({'expected':{(0,0,0):S}}),({'targets':set()}),({'boxes':[]}),({'boxes':[{'min':[1,1,1],'max':[2,2,2]}]})]:
   with self.subTest(args=args),self.assertRaises(ValueError):self.run_case({(0,0,0):S},{},**args)
  with self.assertRaises(ValueError):self.run_case({(0,0,0):F},{})
 def test_replaced_source_with_a_solid_is_not_silently_accepted(self):
  r=self.run_case({(0,0,0):S},{(0,0,0):'Block{minecraft:stone}'});self.assertIn((0,0,0),r['unexpected']);self.assertFalse(r['cleared_sources'])
