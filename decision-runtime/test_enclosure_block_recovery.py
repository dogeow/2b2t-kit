"""A mined slab remains recoverable beneath an intact ceiling block."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'work/village-trading-20261017'))
from enclosure_native_builder import Builder
class RecoveryUnderCeilingTests(unittest.TestCase):
 def builder(self,target_remains=False):
  class Fake(Builder):
   def __init__(self):self.book={'recovered':[]};self.out=Path('/unused');self.held=0;self.calls=[]
   def check(self):return dict(inventory=[dict(slot=0,item='minecraft:dark_oak_slab',count=self.held)],pos=[.5,64,.5],entities=[])
   def save(self):pass
   def n(self,op,**params):self.calls.append(op);return dict(id='mine',server_confirmed=True,server_ack_sequence=1,native_sequence=1)
   def scan(self,lo,hi):return {},{(0,66,0):{'state':'stone'},**({(0,65,0):{'state':'slab'}}if target_remains else{})}
  return Fake()
 def test_ceiling_survives_while_original_mined_slab_is_collected_once(self):
  b=self.builder()
  def collect(builder,*args):builder.held=1
  with patch('block_recovery.pickup',side_effect=collect)as collector,patch('block_recovery.return_to_origin'):
   b.recover([0,65,0],'slab','minecraft:dark_oak_slab')
  self.assertEqual(b.calls,['select_item','mine_block']);collector.assert_called_once();self.assertEqual(len(b.book['recovered']),1)
 def test_target_still_present_blocks_collection_and_completion(self):
  b=self.builder(True)
  with patch('block_recovery.pickup')as collector,self.assertRaises(AssertionError):b.recover([0,65,0],'slab','minecraft:dark_oak_slab')
  collector.assert_not_called();self.assertEqual(b.book['recovered'],[])
if __name__=='__main__':unittest.main()
