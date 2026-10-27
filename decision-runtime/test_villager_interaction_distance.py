import unittest
from villager_trading import body_distance_from_eye
class InteractionDistanceTests(unittest.TestCase):
 def test_far_centre_can_have_an_ordinary_reachable_body_surface(self):
  actor={'pos':[0,64,0],'bounds':{'min':[-.3,64,-.3],'max':[.3,65.95,.3]}}
  self.assertAlmostEqual(2.91,body_distance_from_eye(actor,[0,65.62,3.2]))
  self.assertGreater(actor['pos'][2]+3.2,3)
 def test_status_only_or_invalid_geometry_cannot_be_treated_as_reach_evidence(self):
  for actor in [{},{'pos':[0,64,0]},{'bounds':{'min':[0,64,0],'max':[0,66,1]}},{'bounds':{'min':[0,64,0],'max':[1,float('nan'),1]}}]:
   with self.subTest(actor=actor),self.assertRaises(ValueError):body_distance_from_eye(actor,[0,65.62,2])
 def test_out_of_range_surface_is_still_out_of_range(self):
  actor={'bounds':{'min':[-.3,64,-.3],'max':[.3,65.95,.3]}}
  self.assertGreater(body_distance_from_eye(actor,[0,65.62,4]),3)
if __name__=='__main__':unittest.main()
