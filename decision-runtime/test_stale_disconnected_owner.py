import copy,unittest
from game_connection_cli import stale_owner_releasable
class StaleOwnerTests(unittest.TestCase):
 def test_parked_owner_requires_exact_native_receipt_and_settled_action(self):
  lease={'id':'lease','world_session':'old','job_session':'task','kind':'parking','revision':7}
  state={'connected':False,'screen':'DisconnectedScreen','world_session':'new','supervision_lease':copy.deepcopy(lease)}
  proof={'native_receipt':True,'action':'KEEP_PVE_GUARD','lease':'lease','job_session':'task',
         'parking_confirmation':{'world_session':'old','connected':True,'health':20,'guard_armed':True,'guard_pve_only':True,'supervision_lease':copy.deepcopy(lease)},
         'drain':{'safe_to_cleanup':True,'reason':'owned_action_settled','observed':{'world_session':'old'}}}
  self.assertTrue(stale_owner_releasable(state,'old','task',proof))
  for key in ('native_receipt','action','lease','job_session','parking_confirmation','drain'):
   broken=copy.deepcopy(proof);broken.pop(key)
   with self.subTest(key=key):self.assertFalse(stale_owner_releasable(state,'old','task',broken))
  other=copy.deepcopy(state);other['supervision_lease']['revision']=8
  self.assertFalse(stale_owner_releasable(other,'old','task',proof))
 def test_only_disconnected_exact_old_scope_without_safety_hold_is_eligible(self):
  state={'connected':False,'screen':'DisconnectedScreen','world_session':'new','supervision_lease':{'world_session':'old','job_session':'task','kind':'materials'}}
  self.assertTrue(stale_owner_releasable(state,'old','task'))
  for mode in ['live','same_world','other_task','other_world','health_hold','safety_hold','inventory']:
   s=copy.deepcopy(state)
   if mode=='live':s['connected']=True
   if mode=='same_world':s['world_session']='old'
   if mode=='other_task':s['supervision_lease']['job_session']='other'
   if mode=='other_world':s['supervision_lease']['world_session']='other'
   if mode=='health_hold':s['health_recovery_hold']=True
   if mode=='safety_hold':s['safety_hold']={'active':True}
   if mode=='inventory':s['screen']='ContainerScreen'
   with self.subTest(mode=mode):self.assertFalse(stale_owner_releasable(s,'old','task'))
