from unittest import TestCase
from projection_scene_delta import classify_neighbor_state_completion

W0='Block{minecraft:redstone_wire}[east=none,power=0]'
W1='Block{minecraft:redstone_wire}[east=side,power=0]'
H='Block{minecraft:hopper}[enabled=true,facing=west]'

class NeighborStateTests(TestCase):
 def test_neighbor_connection_is_not_an_additional_placed_item(self):
  target,neighbor=(0,0,0),(1,0,0)
  r=classify_neighbor_state_completion({neighbor:W0},{target:W1,neighbor:W1},{target:W1,neighbor:W1},{target:W1})
  self.assertEqual({target},r['completed']);self.assertEqual({neighbor},r['neighbor_state_matches']);self.assertFalse(r['unexpected'])
 def test_only_actual_full_goal_matches_are_accepted(self):
  p=(0,0,0);r=classify_neighbor_state_completion({p:W0},{p:W1},{p:'Block{minecraft:redstone_wire}[east=side,power=15]'},{})
  self.assertEqual({p},r['unexpected']);self.assertFalse(r['neighbor_state_matches'])
 def test_persistent_direction_delay_mode_and_waterlogging_remain_protected(self):
  p=(0,0,0)
  for before,after in [('Block{minecraft:hopper}[enabled=true,facing=east]',H),('Block{minecraft:repeater}[delay=1,powered=false]','Block{minecraft:repeater}[delay=4,powered=false]'),('Block{minecraft:comparator}[mode=compare,powered=false]','Block{minecraft:comparator}[mode=subtract,powered=false]'),('Block{minecraft:glass_pane}[east=false,waterlogged=true]','Block{minecraft:glass_pane}[east=true,waterlogged=false]')]:
   with self.subTest(before=before):self.assertEqual({p},classify_neighbor_state_completion({p:before},{p:after},{p:after},{})['unexpected'])
 def test_added_replaced_and_unplanned_cells_are_not_waived(self):
  p=(0,0,0)
  for before,after,expected in [({}, {p:W1},{p:W1}),({p:H},{p:W1},{p:W1}),({p:W0},{p:W1},{})]:
   self.assertEqual({p},classify_neighbor_state_completion(before,after,expected,{})['unexpected'])
 def test_changed_target_cannot_hide_as_neighbor_update(self):
  p=(0,0,0);r=classify_neighbor_state_completion({p:W0},{p:W1},{p:W1},{p:H});self.assertEqual({p},r['unexpected']);self.assertFalse(r['completed'])
 def test_source_water_loss_is_never_a_neighbor_completion(self):
  p=(0,0,0);old='Block{minecraft:water}[level=0]';new='Block{minecraft:water}[level=8]'
  self.assertEqual({p},classify_neighbor_state_completion({p:old},{p:new},{p:new},{})['unexpected'])
 def test_incomplete_property_baseline_does_not_prove_a_derived_change(self):
  p=(0,0,0);self.assertEqual({p},classify_neighbor_state_completion({p:'Block{minecraft:redstone_wire}[power=0]'},{p:W1},{p:W1},{})['unexpected'])
