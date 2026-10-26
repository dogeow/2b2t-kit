import copy,unittest
from stopped_slab_interval import prove,HOST_HASHES,SLAB
class StoppedSlabTest(unittest.TestCase):
 def fixture(self):
  mask=[[0,72,0],[1,72,0]];inv=lambda n:[{'slot':0,'item':'minecraft:cobblestone_slab','count':n}]
  printer={'server_confirmed':1,'fast_proposals':0,'complex_proposals':1,'enabled':False,'owned':False,'waiting_for_server':False,'travel_pending':0,'failure':'','last_proposal':{**{k:True for k in ['interaction_seen','interaction_matches_proposal','server_update_seen','ack_final']},**{k:SLAB for k in ['expected','final_target','server_update_state','ack_actual']},'sent_tick':1,'server_update_tick':2}}
  r={'world_session':'w','id':'r','phase':'stopped','detail':'托管收尾，等待脱离战斗','server_confirmed':False,'outcome_pending':True,'bounded_targets':mask,'bounded_target_count':2,'time':10,'professional_printer':printer};u={'world_session':'w','request_id':'r','task_session':'t','lease_id':'l','op':'professional_print'}
  frame={'world_session':'w','health':20,'connected':True,'screen':'','manual_movement':False,'scan_cells_read':2,'scan_total_cells':2,'scan_start_revision':8,'scan_end_revision':8,'control_revision':8,'professional_printer':printer,'inventory':inv(9),'supervision_lease':{'world_session':'w','job_session':'t','id':'l','revision':8},'blocks':[{'pos':[0,72,0],'state':SLAB,'fluid':False,'block_entity':False}]}
  before={'id':'b','world_session':'w','phase':'done','scan_cells_read':2,'scan_total_cells':2,'scan_start_revision':7,'scan_end_revision':7,'blocks':[]};stock={'world_session':'w','phase':'done','control_revision':7,'inventory':inv(10)}
  return {'original_reply':r,'original_request':u,'frames':[{**copy.deepcopy(frame),'time':11},{**copy.deepcopy(frame),'time':12}]},before,stock
 def run_proof(self,parts):return prove(*parts,world='w',hashes=HOST_HASHES,before_intent={'op':'scan','id':'b','world_session':'w','task_session':'t','min':[0,72,0],'max':[1,72,0],'details':True,'expected_revision':7})
 def test_known_stopped_partial_does_not_become_a_complete_mask(self):
  r=self.run_proof(self.fixture());self.assertFalse(r['original_mask_complete']);self.assertFalse(r['old_request_replayed']);self.assertEqual([[1,72,0]],r['never_attempted_positions'])
 def test_never_rebinds_an_old_world(self):
  p=self.fixture();p[0]['original_reply']['world_session']='old'
  with self.assertRaises(ValueError):self.run_proof(p)
 def test_unacked_pending_failed_or_missing_input_is_not_released(self):
  for key,value in [('complex_proposals',2),('waiting_for_server',True),('travel_pending',1),('failure','unconfirmed')]:
   p=self.fixture();p[0]['original_reply']['professional_printer'][key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):self.run_proof(p)
 def test_wrong_or_changing_cells_and_material_debit_are_not_released(self):
  for bad in ['cell','stock','time','lease','before','final_ack']:
   p=self.fixture();f=p[0]['frames'][1]
   if bad=='cell':f['blocks'][0]['pos']=[1,72,0]
   if bad=='stock':f['inventory'][0]['count']=8
   if bad=='time':f['time']=11
   if bad=='lease':f['supervision_lease']['job_session']='foreign'
   if bad=='before':p[1]['blocks']=[{'pos':[0,72,0],'state':SLAB}]
   if bad=='final_ack':p[0]['original_reply']['professional_printer']['last_proposal']['ack_final']=False
   with self.subTest(bad=bad),self.assertRaises(ValueError):self.run_proof(p)

 def test_an_equal_volume_scan_from_elsewhere_is_not_a_mask_proof(self):
  parts=self.fixture()
  intent={'op':'scan','id':'b','world_session':'w','task_session':'t','min':[4,72,0],'max':[5,72,0],'details':True,'expected_revision':7}
  with self.assertRaises(ValueError):prove(*parts,world='w',hashes=HOST_HASHES,before_intent=intent)
