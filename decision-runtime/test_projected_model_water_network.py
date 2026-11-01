import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import projected_model_water as w
import test_projected_model_water as fixtures

class Client:
 world='w';task='t';last='r'
 def __init__(self,unknown=False):self.calls=[];self.used=False;self.unknown=unknown
 def status(self):
  return {'projected_model_water_source_protocol':1,'health':20,'food':20,'air_supply':300,'guard_armed':True,'guard_pve_only':True,'supervision_lease':{'job_session':'t'},'projection_selection':{'key':'k'},'hand':{'item':'minecraft:water_bucket','count':1}}
 def checked(self,op,**kw):
  self.calls.append(op)
  if op=='select_item':return self.status()
  low,high=kw['min'],kw['max'];count=1
  for i in range(3):count*=high[i]-low[i]+1
  return {'world_session':'w','phase':'done','scan_cells_read':count,'scan_total_cells':count,'scan_coherent':True,'scan_predictions':{'complete':True,'pending_count':0},'time':len(self.calls),'blocks':[{'pos':[10,67,20],'state':'Block{minecraft:stone}','solid':True,'fluid':False,'block_entity':False}]}
 def request(self,op,**kw):
  self.calls.append(op);self.used=True
  r=fixtures.ModelWaterTests().valid();r['bucket_water']['unknown_outcome']=self.unknown;return r

def model():return {'placement_key':'k','expected':[{'pos':[10,68,20],'state':w.SOURCE},{'pos':[11,68,20],'state':w.SOURCE}]}
class NetworkTests(unittest.TestCase):
 def test_first_source_ack_does_not_require_or_claim_second_source_flow(self):
  c=Client()
  with tempfile.TemporaryDirectory() as t,patch.object(w,'observe_original_floors',return_value={'mismatches':[]}),patch.object(w,'inventory_counts',return_value={'minecraft:water_bucket':2}):
   b=w.place_network_source(c,[10,68,20],[10,67,20],'up','k',model(),Path(t)/'source')
   self.assertTrue(b['source_confirmed']);self.assertFalse(b['complete']);self.assertTrue(b['full_flow_still_requires_observation']);self.assertIsNone(b['pending'])
   self.assertEqual(['scan','select_item','bucket_place'],c.calls)
 def test_unknown_receipt_retained_and_never_automatically_retried(self):
  c=Client(unknown=True)
  with tempfile.TemporaryDirectory() as t,patch.object(w,'observe_original_floors',return_value={'mismatches':[]}),patch.object(w,'inventory_counts',return_value={'minecraft:water_bucket':2}):
   p=Path(t)/'source'
   with self.assertRaisesRegex(RuntimeError,'unresolved'):w.place_network_source(c,[10,68,20],[10,67,20],'up','k',model(),p)
   self.assertEqual('one_original_source_use',json.loads((p/'progress.json').read_text())['pending'])
   with self.assertRaises(FileExistsError):w.place_network_source(c,[10,68,20],[10,67,20],'up','k',model(),p)
   self.assertEqual(1,c.calls.count('bucket_place'))
 def test_single_source_still_requires_original_full_flow_method(self):
  c=Client();m=model();m['expected'].pop()
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(ValueError):w.place_network_source(c,[10,68,20],[10,67,20],'up','k',m,Path(t)/'source')
  self.assertEqual([],c.calls)
 def test_final_network_verification_requires_three_distinct_complete_frames(self):
  c=Client();original=c.checked
  def scan(op,**kw):
   a=original(op,**kw);a['blocks']=[{'pos':v['pos'],'state':v['state']} for v in model()['expected']];return a
  c.checked=scan
  with tempfile.TemporaryDirectory() as t,patch.object(w.time,'sleep'):
   b=w.verify_network(c,[10,68,20],'k',model(),Path(t)/'verify');self.assertTrue(b['complete']);self.assertEqual(3,len(set(b['flow_frames'])));self.assertTrue(b['no_inputs_sent'])
  self.assertEqual(['scan']*3,c.calls)
 def test_partial_network_never_passes_final_acceptance_or_places_more_water(self):
  c=Client();original=c.checked
  def scan(op,**kw):
   a=original(op,**kw);a['blocks']=[{'pos':[10,68,20],'state':w.SOURCE}];return a
  c.checked=scan
  with tempfile.TemporaryDirectory() as t,patch.object(w.time,'monotonic',side_effect=[0,19]):
   with self.assertRaisesRegex(RuntimeError,'not stable'):w.verify_network(c,[10,68,20],'k',model(),Path(t)/'verify')
   self.assertFalse(json.loads((Path(t)/'verify/progress.json').read_text())['complete'])
  self.assertEqual(['scan'],c.calls)
 def test_selected_network_change_prevents_completion(self):
  c=Client();m=model();m['placement_key']='other'
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(RuntimeError):w.verify_network(c,[10,68,20],'k',m,Path(t)/'verify')
  self.assertEqual([],c.calls)
if __name__=='__main__':unittest.main()
