import unittest
from door_access import crossing_destination,WOOD_DOORS
class Tests(unittest.TestCase):
 def test_crosses_to_opposite_side_for_both_door_axes(self):
  self.assertEqual(crossing_destination([10,65,38],{'facing':'west'},[15,65,35]),([9,65,38],0,-1))
  self.assertEqual(crossing_destination([10,65,38],{'facing':'east'},[8,65,35]),([11,65,38],0,1))
  self.assertEqual(crossing_destination([14,65,40],{'facing':'south'},[15,65,35]),([14,65,41],2,1))
 def test_power_required_doors_are_not_offered(self):
  self.assertNotIn('minecraft:iron_door',WOOD_DOORS)
  self.assertIn('minecraft:birch_door',WOOD_DOORS)
if __name__=='__main__':unittest.main()
