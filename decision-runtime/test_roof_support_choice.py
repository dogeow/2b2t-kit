import unittest
from roof_support_choice import options
class RoofSupportTest(unittest.TestCase):
 def test_retained_west_wall_torch_is_not_on_the_selected_ray(self):
  rows={(0,67,0):{'state':'Block{minecraft:wall_torch}[facing=east]'},(-1,68,0):{'state':'Block{minecraft:dark_oak_planks}'},(1,68,0):{'state':'Block{minecraft:dark_oak_planks}'}}
  self.assertEqual([([1,68,0],'west')],options(rows,[0,68,0]));self.assertIn((0,67,0),rows)
 def test_foreign_blocks_and_missing_anchors_are_not_candidates(self):
  self.assertEqual([],options({(-1,68,0):{'state':'Block{minecraft:chest}'}},[0,68,0]))
 def test_original_priority_is_retained_when_clear(self):
  rows={(-1,68,0):{'state':'Block{minecraft:dark_oak_planks}'},(1,68,0):{'state':'Block{minecraft:dark_oak_planks}'}}
  self.assertEqual(([-1,68,0],'east'),options(rows,[0,68,0])[0])
