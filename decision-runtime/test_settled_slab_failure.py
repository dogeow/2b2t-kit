from copy import deepcopy
import unittest
from settled_slab_failure import prove,HOST_HASHES,DOUBLE,FAILURE
HALF='Block{minecraft:cobblestone_slab}[type=bottom,waterlogged=false]'
def fixture():
 mask=[[0,0,0],[1,0,0],[2,0,0]];owner={'kind':'materials','id':'lease','job_session':'task','world_session':'world','revision':1}
 before=dict(id='before',phase='done',world_session='world',kit_version='2026.10.26.2',connected=True,health=20,manual_movement=False,screen='',time=1,control_revision=1,scan_start_revision=1,scan_end_revision=1,scan_cells_read=4,scan_total_cells=4,projection_selection={'key':'model'},supervision_lease=owner,menu={'cursor':{'count':0}},blocks=[{'pos':[3,0,0],'state':'Block{minecraft:stone}'}],inventory=[{'slot':0,'item':'minecraft:cobblestone_slab','count':5},{'slot':1,'item':'minecraft:cooked_beef','count':10}])
 after=deepcopy(before);after.update(id='after1',time=2,control_revision=2,scan_start_revision=2,scan_end_revision=2);after['supervision_lease']['revision']=2;after['blocks'] += [{'pos':[0,0,0],'state':DOUBLE},{'pos':[1,0,0],'state':HALF}];after['inventory'][0]['count']=2
 after['professional_printer']=dict(owned=False,enabled=False,waiting_for_server=False,travel_pending=0,failure=FAILURE,fast_proposals=0,complex_proposals=1,server_confirmed=1,last_proposal=dict(target='1, 0, 0',interaction_seen=True,server_update_seen=True,interaction_matches_proposal=True,expected=HALF,server_update_state=HALF,ack_actual=HALF,ack_final=False,final_target=DOUBLE))
 after['build_job']=dict(active=False,loading=False,outcome='printer_error',queue_settled=True,placement_key='model',new_blocks=1,session='job');other=deepcopy(after);other.update(id='after2',time=3)
 model={'loaded_server_chunks_verified':True,'placement_key':'model','expected':[{'pos':p,'state':DOUBLE}for p in mask]};intent=dict(op='scan',details=True,id='before',world_session='world',task_session='task',expected_revision=1,min=[0,0,0],max=[3,0,0])
 return [mask,before,[after,other],model,intent,deepcopy(HOST_HASHES)]
class SettledSlabFailureTest(unittest.TestCase):
 def bad(self,mutate):
  a=fixture();mutate(a)
  with self.assertRaises(RuntimeError):prove(*a)
 def test_settled_prefix_is_not_mask_completion(self):
  r=prove(*fixture());self.assertFalse(r['original_mask_complete']);self.assertFalse(r['outstanding_native_input']);self.assertEqual(r['slab_debit'],3);self.assertEqual(r['partial_targets'],[[1,0,0]]);self.assertEqual(r['never_attempted_air_targets'],[[2,0,0]])
 def test_unacked_input(self):self.bad(lambda a:a[2][0]['professional_printer'].update(server_confirmed=0))
 def test_unsettled_queue(self):self.bad(lambda a:a[2][0]['build_job'].update(queue_settled=False))
 def test_pending_travel(self):self.bad(lambda a:a[2][0]['professional_printer'].update(travel_pending=1))
 def test_world_change(self):self.bad(lambda a:a[2][0].update(world_session='other'))
 def test_owner_change(self):self.bad(lambda a:a[2][0]['supervision_lease'].update(job_session='other'))
 def test_wrong_request(self):self.bad(lambda a:a[4].update(id='other'))
 def test_equal_volume_elsewhere(self):self.bad(lambda a:a[4].update(min=[4,0,0],max=[7,0,0]))
 def test_changed_anchor(self):self.bad(lambda a:a[2][0]['blocks'][0].update(state=DOUBLE))
 def test_other_inventory_debit(self):self.bad(lambda a:a[2][0]['inventory'][1].update(count=9))
 def test_wrong_individual_ack(self):self.bad(lambda a:a[2][0]['professional_printer']['last_proposal'].update(ack_actual=DOUBLE))
 def test_second_frame_differs(self):self.bad(lambda a:a[2][1]['build_job'].update(session='other'))
 def test_other_host(self):self.bad(lambda a:a[5].update(jar='other'))
 def test_wrong_or_duplicate_mask(self):
  self.bad(lambda a:a[0].append([0,0,0]));self.bad(lambda a:a[3]['expected'][0].update(state=HALF))
if __name__=='__main__':unittest.main()
