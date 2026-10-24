import unittest
from cane_stack_fetch import planned_take
class CaneStackFetchTests(unittest.TestCase):
 def test_live_full_collector_uses_whole_stacks_without_crossing_request_or_capacity(self):
  rows=[dict(item='minecraft:sugar_cane',count=64)for _ in range(27)]
  self.assertEqual(128,planned_take(500,1728,189,rows))
  self.assertEqual(64,planned_take(100,1728,189,rows))
 def test_small_request_or_partial_leading_source_keeps_exact_craft_batch(self):
  self.assertEqual(60,planned_take(60,64,64,[dict(item='minecraft:sugar_cane',count=64)]))
  self.assertEqual(126,planned_take(128,128,128,[dict(item='minecraft:sugar_cane',count=10),dict(item='minecraft:sugar_cane',count=64)]))
 def test_invalid_counts_never_authorize_withdrawal(self):
  for values in [(True,64,64),(-1,64,64),(64,64,1.5)]:
   with self.assertRaises(ValueError):planned_take(*values,[])
  self.assertEqual(0,planned_take(0,100,100,[]))
