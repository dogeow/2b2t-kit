import copy, unittest
from unittest.mock import patch
from printer_rejected_interval import prove
from printer_partial_interval import HOST_HASHES, REASON

class RejectedIntervalTests(unittest.TestCase):
 def fixture(self):
  item='minecraft:dark_oak_planks';positions=[[1,64,2]]
  pending={'positions':positions,'item':item,'before':{item:35}}
  p={'fast_proposals':1,'complex_proposals':0,'server_confirmed':0,'travel_pending':1,'enabled':False,'owned':False,'waiting_for_server':False,'failure':'','last_proposal':{'target':'1, 64, 2','expected':'Block{'+item+'}','final_target':'Block{'+item+'}','hand':item,'interaction_seen':True,'interaction_matches_proposal':True,'server_update_seen':True,'sent_tick':1,'server_update_tick':8,'server_update_state':'Block{minecraft:air}'}}
  owner={'id':'l','kind':'materials','job_session':'j','world_session':'w'}
  r={'id':'r','phase':'waiting','detail':REASON,'outcome_pending':True,'server_confirmed':False,'bounded_targets':positions,'bounded_target_count':1,'world_session':'w','placement_key':'k','supervision_lease':owner,'time':100,'control_revision':1,'professional_printer':p}
  f={'phase':'done','world_session':'w','connected':True,'health':20,'manual_movement':False,'screen':'','professional_printer':p,'supervision_lease':owner,'projection_selection':{'key':'k'},'menu':{'cursor':{'count':0}},'control_revision':1,'scan_start_revision':1,'scan_end_revision':1,'scan_cells_read':1,'scan_total_cells':1,'blocks':[]}
  command={'action':'native','op':'scan','params':{'min':[1,64,2],'max':[1,64,2],'details':True}}
  return pending,r,[{'command':command,'result':dict(f,time=101)},{'command':command,'result':dict(f,time=102)}]
 def test_negative_result_has_no_positive_ack_or_credit(self):
  with patch('printer_rejected_interval.inventory_counts',return_value={'minecraft:dark_oak_planks':35}):
   p=prove(*self.fixture(),HOST_HASHES);self.assertEqual(0,p['placement_credit']);self.assertFalse(p['positive_ack_created']);self.assertFalse(p['original_request_replayed'])
 def test_absent_or_early_packet_and_multiple_sends_remain_unknown(self):
  for field,value in [('server_update_seen',False),('server_update_tick',1),('interaction_seen',False),('server_update_state','Block{minecraft:dark_oak_planks}'),('target','2, 64, 2')]:
   parts=copy.deepcopy(self.fixture());parts[1]['professional_printer']['last_proposal'][field]=value
   with patch('printer_rejected_interval.inventory_counts',return_value={'minecraft:dark_oak_planks':35}),self.assertRaises(RuntimeError):prove(*parts,HOST_HASHES)
  parts=self.fixture();parts[1]['professional_printer']['fast_proposals']=2
  with self.assertRaises(RuntimeError):prove(*parts,HOST_HASHES)
 def test_changed_world_scene_stock_owner_or_incomplete_scan_refuses_resolution(self):
  for change in [{'world_session':'other'},{'scan_start_revision':2},{'scan_cells_read':0},{'time':100},{'blocks':[{'pos':[1,64,2],'state':'Block{minecraft:dark_oak_planks}'}]},{'supervision_lease':{}}]:
   parts=copy.deepcopy(self.fixture());parts[2][1]['result'].update(change)
   with patch('printer_rejected_interval.inventory_counts',return_value={'minecraft:dark_oak_planks':35}),self.assertRaises(RuntimeError):prove(*parts,HOST_HASHES)
  with patch('printer_rejected_interval.inventory_counts',return_value={'minecraft:dark_oak_planks':34}),self.assertRaises(RuntimeError):prove(*self.fixture(),HOST_HASHES)

 def test_scan_intent_must_cover_pending_target(self):
  parts=copy.deepcopy(self.fixture());parts[2][1]['command']['params']['min']=[2,64,2]
  with patch('printer_rejected_interval.inventory_counts',return_value={'minecraft:dark_oak_planks':35}),self.assertRaises(RuntimeError):prove(*parts,HOST_HASHES)
