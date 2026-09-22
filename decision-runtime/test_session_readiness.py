import unittest
from session_readiness import lost_since
class Tests(unittest.TestCase):
 def state(self,items):return {'player_uuid':'player','inventory':[{'slot':n,'item':i,'count':v} for n,(i,v) in enumerate(items.items())]}
 def test_reordering_stacks_is_not_loss(self):
  a=self.state({'minecraft:diamond_sword':1,'minecraft:oak_log':64});b=self.state({'minecraft:oak_log':64,'minecraft:diamond_sword':1});self.assertFalse(lost_since(a,b))
 def test_empty_respawn_inventory_is_not_ready_to_resume_material_work(self):
  self.assertEqual(lost_since(self.state({'minecraft:diamond_sword':1,'minecraft:oak_log':64}),self.state({})),{'minecraft:diamond_sword':1,'minecraft:oak_log':64})
 def test_eating_during_shutdown_is_expected_but_gear_loss_is_not(self):
  self.assertFalse(lost_since(self.state({'minecraft:golden_carrot':10}),self.state({'minecraft:golden_carrot':9})))
 def test_crafting_inputs_and_cursor_are_expected_back_after_disconnect(self):
  before=self.state({'minecraft:oak_planks':2})
  before['menu']={'type':'CraftingMenu','cursor':{'item':'minecraft:oak_planks','count':6},'slots':[{'item':'minecraft:oak_planks','count':4},{'item':'minecraft:oak_log','count':64}]}
  self.assertFalse(lost_since(before,self.state({'minecraft:oak_planks':8,'minecraft:oak_log':64})))
  self.assertEqual(lost_since(before,self.state({'minecraft:oak_planks':8})),{'minecraft:oak_log':64})
 def test_chest_contents_are_not_mistaken_for_player_gear(self):
  before=self.state({'minecraft:diamond_sword':1});before['menu']={'type':'ChestMenu','slots':[{'item':'minecraft:diamond','count':64}]}
  self.assertFalse(lost_since(before,self.state({'minecraft:diamond_sword':1})))
if __name__=='__main__':unittest.main()
