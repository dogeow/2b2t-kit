import copy,unittest
from disconnected_roof_handoff import admit,STATE

class Tests(unittest.TestCase):
 def fixture(self):
  inv=[{'slot':0,'item':'minecraft:dark_oak_planks','count':1}]
  u={'op':'mine_block','request_id':'lost','world_session':'old','params':{'pos':[761026,68,797814],'expected_state':STATE,'seconds':12}}
  error={'error':'World disconnected','type':'Handoff','native_inflight':{'request_id':'lost'},'unconfirmed_native_request':u}
  state={'time':3,'world_session':'new','connected':True,'health':20,'screen':'','manual_movement':False,'inventory':inv,'server':'simpcraft.com','dimension':'minecraft:overworld','player_uuid':'player','loaded_villagers':{'villagers':[{'uuid':str(i),'health':20}for i in range(45)]}}
  baseline=copy.deepcopy(state);baseline['world_session']='old'
  frame={'world_session':'new','scan_cells_read':1,'scan_total_cells':1,'scan_predictions':{'complete':True,'pending_count':0,'pending_positions':[]},'blocks':[{'pos':u['params']['pos'],'state':STATE}]}
  obs={'complete':True,'unknown':u,'old_request_replayed':False,'old_mining_completion_claimed':False,'baseline_before_unknown':baseline,'snapshot':copy.deepcopy(state),'expected_known_uuids':[str(i)for i in range(50)],'frames':[copy.deepcopy(frame),copy.deepcopy(frame)],'states':[dict(copy.deepcopy(state),time=1),dict(copy.deepcopy(state),time=2)]}
  start={'action':'native','op':'snapshot','params':{}}
  return copy.deepcopy((u,error,obs,state,start))
 def test_only_new_world_snapshot_admitted_without_resolving_old_input(self):
  result=admit(*self.fixture());self.assertEqual(0,result['mining_credit']);self.assertFalse(result['old_mining_completion_claimed']);self.assertFalse(result['old_request_replayed']);self.assertTrue(result['full_population_recheck_required']);self.assertEqual([761026,68,797814],result['protected_target'])
 def test_replay_scope_expansion_inventory_loss_and_unsafe_control_refused(self):
  for kind in ('world','startup','target','op','health','manual','owner','inventory','server','population','stranger','error','claim','scan'):
   u,e,o,s,c=self.fixture()
   if kind=='world':s['world_session']='old'
   if kind=='startup':c['op']='mine_block'
   if kind=='target':u['params']['pos']=[1,68,1]
   if kind=='op':u['op']='slot_click'
   if kind=='health':s['health']=19
   if kind=='manual':s['manual_movement']=True
   if kind=='owner':s['supervision_lease']={'id':'other'}
   if kind=='inventory':s['inventory'][0]['count']=2
   if kind=='server':s['server']='other'
   if kind=='population':s['loaded_villagers']['villagers']=s['loaded_villagers']['villagers'][:44]
   if kind=='stranger':s['loaded_villagers']['villagers'][0]['uuid']='unknown'
   if kind=='error':e['error']='Safety exit'
   if kind=='scan':s['pending_scan']={'id':'reading'}
   if kind=='claim':o['old_mining_completion_claimed']=True
   with self.subTest(kind=kind),self.assertRaises(ValueError):admit(u,e,o,s,c)
 def test_roof_predictions_and_duplicate_observations_keep_admission_closed(self):
  for kind in ('air','pending','frame_world','time','count'):
   u,e,o,s,c=self.fixture()
   if kind=='air':o['frames'][0]['blocks']=[]
   if kind=='pending':o['frames'][0]['scan_predictions']['pending_count']=1
   if kind=='frame_world':o['frames'][0]['world_session']='old'
   if kind=='time':o['states'][1]['time']=1
   if kind=='count':o['frames'][0]['scan_cells_read']=0
   with self.subTest(kind=kind),self.assertRaises(ValueError):admit(u,e,o,s,c)

 def heartbeat_fixture(self):
  u,e,o,s,c=self.fixture();u.update(lease_id='lease',task_session='task')
  e['error']='Control revision changed outside the owned request'
  s['supervision_safety']={'lease':'lease','job_session':'task','cause':'heartbeat_lost','action':'LOGOUT','confirmed':True,'confirmed_at':2,'confirmation':'network_disconnect_event'}
  o['original_native_reply']={'id':'lost','world_session':'old','phase':'stopped','server_confirmed':False,'native_sequence':236,'server_ack_sequence':-1}
  o['expected_known_uuids']=[str(i)for i in range(52)]
  return u,e,o,s,c

 def test_confirmed_heartbeat_logout_retains_unacknowledged_mining(self):
  result=admit(*self.heartbeat_fixture())
  self.assertEqual(0,result['mining_credit']);self.assertFalse(result['old_request_replayed'])

 def test_revision_change_alone_or_unrelated_logout_never_admits(self):
  for kind in ('missing_reply','lease','task','cause','confirmation','future','reply_id','reply_world','ack','confirmed','not_started','too_many_residents'):
   u,e,o,s,c=self.heartbeat_fixture()
   if kind=='missing_reply':o.pop('original_native_reply')
   if kind=='lease':s['supervision_safety']['lease']='other'
   if kind=='task':s['supervision_safety']['job_session']='other'
   if kind=='cause':s['supervision_safety']['cause']='manual'
   if kind=='confirmation':s['supervision_safety']['confirmed']=False
   if kind=='future':s['supervision_safety']['confirmed_at']=4
   if kind=='reply_id':o['original_native_reply']['id']='other'
   if kind=='reply_world':o['original_native_reply']['world_session']='other'
   if kind=='ack':o['original_native_reply']['server_ack_sequence']=236
   if kind=='confirmed':o['original_native_reply']['server_confirmed']=True
   if kind=='not_started':o['original_native_reply']['native_sequence']=-1
   if kind=='too_many_residents':o['expected_known_uuids']=[str(i)for i in range(65)]
   with self.subTest(kind=kind),self.assertRaises(ValueError):admit(u,e,o,s,c)

if __name__=='__main__':unittest.main()
