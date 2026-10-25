"""Partial first chest rows must not force every later full stack to be split."""
import tempfile,unittest
from unittest.mock import patch
from test_material_depots import StorageClient
from material_depots import exchange

class BulkFetchTest(unittest.TestCase):
 def run_fetch(self,target,delayed=False):
  with tempfile.TemporaryDirectory()as tmp:
   c=StorageClient(tmp);c.put(0,'minecraft:cobblestone',23)
   for slot in range(1,13):c.put(slot,'minecraft:cobblestone',64)
   c.delay=delayed
   with patch('material_depots._open_depot',side_effect=lambda *args,**kw:c.status()),patch('kit_runtime.inventory.time.sleep'):
    result=exchange(c,[[1,64,2]],withdraw={'minecraft:cobblestone':target})
   held=sum(v['count']for v in c.menu['slots'][27:]if v['item']=='minecraft:cobblestone');left=sum(v['count']for v in c.menu['slots'][:27]if v['item']=='minecraft:cobblestone')
   self.assertTrue(result['complete']);self.assertEqual(held,target);self.assertEqual(left+held,791);self.assertEqual(c.menu['cursor']['count'],0)
   return c
 def test_twelve_full_stacks_use_twelve_whole_stack_moves(self):
  c=self.run_fetch(768);self.assertEqual(len(c.calls),12);self.assertTrue(all(v['kind']=='quick_move'for v in c.calls));self.assertEqual(c.menu['slots'][0]['count'],23)
 def test_final_partial_target_remains_exact(self):self.run_fetch(750)
 def test_delayed_acknowledgement_does_not_repeat_a_whole_stack_move(self):
  c=self.run_fetch(768,delayed=True);self.assertEqual(len(c.calls),12)
if __name__=='__main__':unittest.main()
