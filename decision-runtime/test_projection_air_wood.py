import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from projection_air_wood import run_one

class AirWoodTests(unittest.TestCase):
 def setUp(self):
  self.pos=[1,64,2];self.row={'pos':self.pos,'kind':'missing','actual':'Block{minecraft:air}','expected':'Block{minecraft:stripped_cherry_wood}[axis=y]','fluid':False,'adjacent_fluid':False,'block_entity':False}
  self.state={'projection_air_seed_axis_protocol':1,'projection_selection':{'key':'projection'},'inventory':[{'item':'minecraft:cherry_wood','count':3,'slot':0}]};self.calls=[]
  self.receipt={'phase':'done','projection_air_seed':{'server_confirmed':True,'target':self.pos,'use_count':1,'expected_state':'Block{minecraft:cherry_wood}[axis=y]','projected_state':self.row['expected'],'requires_stripping':True,'projection_matches':False,'inventory_before':3,'inventory_after':2}}
  def request(op,**kw):
   self.calls.append(op)
   if op=='projection_air_seed':self.state['inventory'][0]['count']=2;return self.receipt
   return {}
  self.client=SimpleNamespace(world='world',task='task',status=lambda:self.state,checked=lambda *a,**kw:None,request=request)
 def run_case(self,cells):
  with tempfile.TemporaryDirectory()as d,patch('projection_air_wood.cell_at',side_effect=[{'state':s}for s in cells]),patch('projection_air_wood.finish_beams',return_value={'completed':[{'pos':self.pos}]}),patch('projection_air_wood.wait_known_idle'),patch('projection_air_wood.time.sleep'):
   return run_one(self.client,self.row,Path(d)/'case',lambda:self.state)
 def test_exact_server_confirmed_raw_is_stripped_then_final_state_proved(self):
  result=self.run_case(['Block{minecraft:air}']*2+['Block{minecraft:cherry_wood}[axis=y]']+[self.row['expected']]*2)
  self.assertTrue(result['complete']);self.assertEqual(result['temporary_supports_placed'],0);self.assertEqual(self.calls.count('projection_air_seed'),1)
 def test_waiting_raw_never_replayed_or_promoted(self):
  self.receipt['phase']='waiting'
  with self.assertRaisesRegex(RuntimeError,'unconfirmed'):
   self.run_case(['Block{minecraft:air}']*2)
  self.assertEqual(self.calls.count('projection_air_seed'),1)
 def test_wrong_axis_receipt_never_counts_as_raw_success(self):
  self.receipt['projection_air_seed']['expected_state']='Block{minecraft:cherry_wood}[axis=x]'
  with self.assertRaisesRegex(RuntimeError,'unconfirmed'):
   self.run_case(['Block{minecraft:air}']*2)
  self.assertEqual(self.calls.count('projection_air_seed'),1)
 def test_changed_target_prevents_any_send(self):
  with self.assertRaisesRegex(RuntimeError,'changed before'):
   self.run_case(['Block{minecraft:stone}'])
  self.assertNotIn('projection_air_seed',self.calls)
 def test_old_host_is_rejected_before_send(self):
  self.state['projection_air_seed_axis_protocol']=None
  with self.assertRaisesRegex(RuntimeError,'unavailable'):
   self.run_case([])
  self.assertEqual(self.calls,[])

if __name__=='__main__':unittest.main()
