import unittest
from mega_spruce_growth import body_clear,candidates

class MegaSpruceGrowthTests(unittest.TestCase):
 def test_axis_stance_can_be_filled_with_low_crown_leaves(self):
  self.assertFalse(body_clear([100,64,100],[103.5,64,100.5]))
  self.assertFalse(body_clear([100,64,100],[104.5,64,101.5]))
 def test_all_corner_candidates_clear_both_trunks_and_widest_leaf_mask(self):
  for root in[[100,64,100],[-100,64,-100],[760963,64,797812]]:
   rows=candidates(root);self.assertEqual(len(rows),4)
   for row in rows:self.assertTrue(body_clear(root,row['pose']))
 def test_body_width_near_a_leaf_column_is_not_treated_as_a_point(self):
  self.assertTrue(body_clear([0,64,0],[-2.4,64,-2.4]))
  self.assertFalse(body_clear([0,64,0],[-1.9,64,-2.4]))
 def test_unknown_feature_envelope_or_invalid_position_fails_closed(self):
  with self.assertRaises(ValueError):body_clear([0,64,0],[4.4,64,4.4],radius=5)
  with self.assertRaises(ValueError):candidates([0.5,64,0])
  self.assertFalse(body_clear([0,64,0],[float('nan'),64,4.4]))

if __name__=='__main__':unittest.main()
