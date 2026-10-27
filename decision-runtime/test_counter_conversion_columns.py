import unittest
from north_counter_conversion import counter_columns
class ConversionColumnsTest(unittest.TestCase):
 def test_north_existing_live_configuration_preserved(self):
  self.assertEqual(counter_columns(797809,-1),(797808,797807,797806))
 def test_south_keeps_gate_between_front_and_rear_bed_cell(self):
  self.assertEqual(counter_columns(797813,1),(797814,797815,797816))
 def test_does_not_allow_lateral_or_noninteger_workpoint(self):
  for z,d in [(797813,0),(797813,2),(797813.5,1)]:
   with self.assertRaises(ValueError):counter_columns(z,d)
