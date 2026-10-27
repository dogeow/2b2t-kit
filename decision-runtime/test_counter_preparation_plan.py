import unittest
from counter_preparation_plan import oak_planks_needed,roof_light_plan
class CounterPreparationPlanTests(unittest.TestCase):
 def test_existing_parts_are_reused_and_only_missing_gate_inputs_are_requested(self):
  self.assertEqual(oak_planks_needed({'minecraft:oak_fence_gate':1,'minecraft:oak_trapdoor':2},1),0)
  self.assertEqual(oak_planks_needed({'minecraft:oak_trapdoor':1,'minecraft:stick':1},1),4)
 def test_clear_roof_needs_no_light_changes(self):
  self.assertEqual(roof_light_plan({(1,68,2):{'state':'Block{minecraft:dark_oak_planks}'}},[1,68,2]),{'kind':'clear'})
 def test_torch_is_moved_only_to_a_clear_existing_roof_and_other_decor_is_preserved(self):
  rows={(1,68,2):{'state':'Block{minecraft:dark_oak_planks}'},(1,69,2):{'state':'Block{minecraft:torch}'},(0,68,2):{'state':'Block{minecraft:dark_oak_planks}'}}
  self.assertEqual(roof_light_plan(rows,[1,68,2])['temporary'],[0,69,2]);rows[(0,69,2)]={'state':'Block{minecraft:lantern}'};self.assertEqual(roof_light_plan(rows,[1,68,2]),{'kind':'defer'})
  rows[(1,69,2)]={'state':'Block{minecraft:lantern}'};self.assertEqual(roof_light_plan(rows,[1,68,2]),{'kind':'defer'})

class StoneRoofLightTests(unittest.TestCase):
 def fixture(self):
  stone={'state':'Block{minecraft:cobblestone}','solid':True,'fluid':False,'block_entity':False};return {(1,67,2):dict(stone),(0,67,2):dict(stone),(1,68,2):{'state':'Block{minecraft:torch}'}}
 def test_cobblestone_uses_same_preserved_temporary_light_plan(self):
  rows=self.fixture();self.assertEqual({'kind':'temporary_torch','original':[1,68,2],'temporary':[0,68,2]},roof_light_plan(rows,[1,67,2]))
 def test_unknown_wet_or_occupied_support_is_deferred(self):
  for key,value in [('fluid',True),('solid',False),('block_entity',True)]:
   rows=self.fixture();rows[0,67,2][key]=value;self.assertEqual({'kind':'defer'},roof_light_plan(rows,[1,67,2]))
  rows=self.fixture();rows[0,68,2]={'state':'Block{minecraft:lantern}'};self.assertEqual({'kind':'defer'},roof_light_plan(rows,[1,67,2]))
