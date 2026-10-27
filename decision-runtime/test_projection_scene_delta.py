from unittest import TestCase
from projection_scene_delta import classify,DIRT,GRASS
HOPPER='Block{minecraft:hopper}[enabled=false,facing=west]'
class SceneDeltaTest(TestCase):
 def test_construction_and_off_model_growth_are_both_reported(self):
  a,b=(1,65,1),(9,60,9);r=classify({b:DIRT},{b:GRASS,a:HOPPER},{a:HOPPER},{a:HOPPER})
  self.assertEqual({a},r['completed']);self.assertEqual({b},r['incidental_grass']);self.assertEqual(set(),r['unexpected'])
 def test_growth_of_a_required_model_block_is_not_ignored(self):
  p=(1,2,3);r=classify({p:DIRT},{p:GRASS},{p:DIRT},{})
  self.assertEqual({p},r['unexpected']);self.assertEqual(set(),r['incidental_grass'])
 def test_target_growth_is_not_accepted_as_placement_or_incidental(self):
  p=(1,2,3);r=classify({p:DIRT},{p:GRASS},{},{p:HOPPER})
  self.assertEqual({p},r['unexpected']);self.assertEqual(set(),r['completed'])
 def test_destroyed_changed_or_added_structures_are_unexpected(self):
  p=(1,2,3)
  for before,after in [({p:DIRT},{}),({}, {p:DIRT}),({p:HOPPER},{p:DIRT}),({p:GRASS},{p:DIRT})]:
   self.assertEqual({p},classify(before,after,{}, {})['unexpected'])
 def test_unplaced_targets_do_not_become_completion(self):
  p=(1,2,3);r=classify({}, {}, {p:HOPPER}, {p:HOPPER});self.assertEqual(set(),r['completed']);self.assertEqual(set(),r['unexpected'])
 def test_wrong_property_or_material_does_not_become_completion(self):
  p=(1,2,3)
  for state in ['Block{minecraft:hopper}[enabled=true,facing=west]','Block{minecraft:stone}']:
   r=classify({}, {p:state}, {p:HOPPER}, {p:HOPPER});self.assertEqual({p},r['unexpected']);self.assertEqual(set(),r['completed'])
