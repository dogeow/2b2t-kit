import unittest
from villager_nudge_geometry import route,intersects,inside,push_points
class NudgeGeometryTests(unittest.TestCase):
 def test_ground_approach_avoids_boat_and_supply_chest(self):
  obstacles=[[3,2,5,4],[0.5,5,2,6.5]];bounds=[0,0,7,8];p=route([4,6],[5.8,1],obstacles,bounds)
  self.assertEqual(p[0],[4,6]);self.assertEqual(p[-1],[5.8,1]);self.assertGreater(len(p),2)
  self.assertTrue(all(not intersects(a,b,r)for a,b in zip(p,p[1:])for r in obstacles))
 def test_invalid_or_blocked_endpoints_never_generate_a_route(self):
  for target in [[4,3],[9,3]]:
   with self.assertRaises(ValueError):route([1,1],target,[[3,2,5,4]],[0,0,7,8])
 def test_push_goal_stays_outside_the_boat_body(self):
  rects=[[3,2,5,4],[.5,5,2,6.5]];bounds=[0,0,7,8];points=push_points([5.4,1.6],[4,3],rects,bounds);self.assertIsNotNone(points);behind,goal=points
  self.assertTrue(inside(behind,bounds));self.assertFalse(any(inside(goal,r)for r in rects))
if __name__=='__main__':unittest.main()
