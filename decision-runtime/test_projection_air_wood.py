import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from projection_air_wood import run_one,run_from_poses

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
 def test_exact_admission_rejection_is_deferred_after_proving_no_change(self):
  self.receipt={'phase':'error','detail':'Air seed requires the current healthy idle guarded material lease'}
  def reject(op,**kw):self.calls.append(op);return self.receipt
  self.client.request=reject
  from work_access import ApproachUnavailable
  with self.assertRaises(ApproachUnavailable):
   self.run_case(['Block{minecraft:air}']*3)
  self.assertEqual(self.calls.count('projection_air_seed'),1)
 def test_admission_rejection_with_unexplained_stock_change_is_not_recoverable(self):
  self.receipt={'phase':'error','detail':'Air seed requires the current healthy idle guarded material lease'}
  with self.assertRaisesRegex(RuntimeError,'actual state changed'):
   self.run_case(['Block{minecraft:air}']*3)
  self.assertEqual(self.calls.count('projection_air_seed'),1)
 def test_old_host_is_rejected_before_send(self):
  self.state['projection_air_seed_axis_protocol']=None
  with self.assertRaisesRegex(RuntimeError,'unavailable'):
   self.run_case([])
  self.assertEqual(self.calls,[])
 def test_native_presend_occlusion_is_known_not_sent_after_proving_no_change(self):
  self.receipt={'phase':'error','detail':'Air seed target is occluded'}
  def reject(op,**kw):self.calls.append(op);return self.receipt
  self.client.request=reject
  from work_access import ApproachUnavailable
  with self.assertRaises(ApproachUnavailable):self.run_case(['Block{minecraft:air}']*3)
  self.assertEqual(1,self.calls.count('projection_air_seed'))

 def test_pose_fallback_requires_explicit_no_send_witness_and_distinct_poses(self):
  from work_access import ApproachUnavailable
  moves=[]
  def place(c,row,out,checkpoint):
   out.mkdir()
   if len(moves)==1:
    (out/'progress.json').write_text(json.dumps({'world_session':'world','target':self.pos,'known_not_sent':True,'pending':None,'complete':False}))
    raise ApproachUnavailable('known occlusion')
   return {'complete':True}
  with tempfile.TemporaryDirectory()as d,patch('projection_air_wood.run_one',side_effect=place)as attempt:
   result=run_from_poses(self.client,self.row,[[.5,64.,2.5],[1.5,64.,2.5]],Path(d)/'attempts',lambda:self.state,lambda p,out:moves.append(p))
  self.assertTrue(result['complete']);self.assertEqual(2,attempt.call_count);self.assertEqual(2,len(moves))

 def test_unknown_or_pending_placement_never_selects_another_pose(self):
  from work_access import ApproachUnavailable
  for uncertain in(True,False):
   moves=[]
   def place(c,row,out,checkpoint):
    if uncertain:raise RuntimeError('unknown server outcome')
    out.mkdir();(out/'progress.json').write_text(json.dumps({'world_session':'world','target':self.pos,'known_not_sent':True,'pending':'one_native_air_seed','complete':False}))
    raise ApproachUnavailable('incomplete witness')
   with self.subTest(uncertain=uncertain),tempfile.TemporaryDirectory()as d,patch('projection_air_wood.run_one',side_effect=place):
    with self.assertRaises(RuntimeError):run_from_poses(self.client,self.row,[[.5,64.,2.5],[1.5,64.,2.5]],Path(d)/'attempts',lambda:self.state,lambda p,out:moves.append(p))
   self.assertEqual(1,len(moves))

if __name__=='__main__':unittest.main()
