import unittest
from village_public_roof import choose
class PublicRoofTest(unittest.TestCase):
 def fixture(self):return {(x,64,797811):dict(solid=True,fluid=False)for x in range(17,20)}|{(x,68,797811):dict(state='Block{minecraft:dark_oak_planks}')for x in range(17,20)}
 def call(self,r,blocked=()):return choose(r,18,65,blocked,low_x=17,high_x=19)
 def test_nearest_clear_central_column(self):self.assertEqual([18,68,797811],self.call(self.fixture()))
 def test_collision_lantern_or_roof_decoration_is_preserved(self):
  r=self.fixture();r[(18,67,797811)]={'passable':False,'fluid':False,'state':'Block{minecraft:lantern}'};self.assertNotEqual([18,68,797811],self.call(r));r=self.fixture();r[(18,69,797811)]={'passable':True};self.assertNotEqual([18,68,797811],self.call(r))
 def test_quarantined_column_is_never_chosen(self):self.assertNotEqual([18,68,797811],self.call(self.fixture(),[(18,68,797811)]))
 def test_passable_wall_torch_is_preserved_but_not_used_as_a_mining_ray_column(self):
  r=self.fixture();r[(18,66,797811)]={'passable':True,'fluid':False,'state':'Block{minecraft:wall_torch}[facing=south]'}
  self.assertNotEqual([18,68,797811],self.call(r))
 def test_west_hall_uses_its_actual_lower_floor(self):
  r={(998,63,797811):{'solid':True,'fluid':False},(998,67,797811):{'state':'Block{minecraft:dark_oak_planks}'}}
  self.assertEqual([998,67,797811],choose(r,998,64,low_x=997,high_x=1000))
