import unittest
from village_corridor_route import flat_corridor_route
class CorridorRoutes(unittest.TestCase):
 def test_elbow_keeps_turn_instead_of_cutting_diagonally_through_wall(self):
  cells={(5,z)for z in range(2,7)}|{(x,2)for x in range(2,6)}
  self.assertEqual([[5.5,64.15,2.5],[2.5,64.15,2.5]],flat_corridor_route(cells,[5.53,64.18,6.48],[2.5,64.15,2.5]))
 def test_straight_route_is_compressed_without_native_noop(self):
  cells={(5,z)for z in range(2,7)}
  self.assertEqual([[5.5,64.15,6.5]],flat_corridor_route(cells,[5.5,64.15,2.5],[5.5,64.15,6.5]))
  self.assertEqual([],flat_corridor_route(cells,[5.5,64.15,2.5],[5.5,64.15,2.5]))
 def test_blocked_or_wrong_height_cannot_create_a_route(self):
  with self.assertRaises(ValueError):flat_corridor_route({(1,1),(3,1)},[1.5,64,1.5],[3.5,64,1.5])
  with self.assertRaises(ValueError):flat_corridor_route({(1,1)},[1.5,64,1.5],[1.5,65,1.5])
if __name__=='__main__':unittest.main()
