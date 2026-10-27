import unittest
from door_access import open_door_center
class DoorOpeningGeometryTest(unittest.TestCase):
 def test_north_right_hinge_uses_actual_gap_centre_instead_of_tight_block_centre(self):
  q=open_door_center([0,71,0],{'facing':'north','hinge':'right'})
  self.assertEqual([.40625,71.5,.5],q)
  self.assertAlmostEqual(.10625,.8125-(q[0]+.3))
 def test_other_hinge_and_cardinal_axes_are_mirrored(self):
  self.assertEqual([.59375,71.5,.5],open_door_center([0,71,0],{'facing':'north','hinge':'left'}))
  self.assertEqual([.5,71.5,.40625],open_door_center([0,71,0],{'facing':'east','hinge':'right'}))
