import unittest
from village_roof_access import traverse_opening,column_aligned

class Builder:
 def __init__(self,stuck=False):self.pos=[10.23,64,20.5];self.calls=[];self.stuck=stuck
 def check(self):return {'pos':self.pos.copy()}
 def nav(self,target):
  self.calls.append(target)
  if not self.stuck:self.pos=target.copy()
  return {'phase':'done'}

class RoofAccessTests(unittest.TestCase):
 def test_horizontal_alignment_precedes_vertical_ascent(self):
  b=Builder();traverse_opening(b,[10,67,20],68.2)
  self.assertEqual([[10.5,64,20.5],[10.5,68.2,20.5]],b.calls)
 def test_failed_alignment_never_sends_vertical_input(self):
  b=Builder(stuck=True)
  with self.assertRaises(RuntimeError):traverse_opening(b,[10,67,20],68.2)
  self.assertEqual([[10.5,64,20.5]],b.calls)
 def test_invalid_target_never_moves(self):
  for roof,height in [([10.,67,20],68.2),([10,67,20],float('nan'))]:
   b=Builder()
   with self.assertRaises(ValueError):traverse_opening(b,roof,height)
   self.assertFalse(b.calls)
 def test_column_margin_rejects_edge_and_invalid_positions(self):
  self.assertTrue(column_aligned([10.5,64,20.5],[10,67,20]))
  for p in [[10.23,64,20.5],[10.5,64,20.8],[float('nan'),64,20.5]]:self.assertFalse(column_aligned(p,[10,67,20]))

if __name__=='__main__':unittest.main()
