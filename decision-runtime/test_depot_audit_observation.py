import unittest
from copy import deepcopy
from depot_audit_observation import observable

class DepotAuditObservationTest(unittest.TestCase):
 def setUp(self):
  self.command={'action':'audit_depots','positions':[[1,2,3],[4,5,6]],'items':['minecraft:paper']}
  self.error={'error':'Storage position has no current scoped Kit record','type':'JobBlocked','native_inflight':None,'unconfirmed_native_request':None,'last_request':'read1'}
  self.partial={'complete':False,'world_session':'world','visited':[{'pos':[1,2,3],'counts':{'minecraft:paper':4},'at_ms':15}],'counts':{'minecraft:paper':4}}
  self.prior={'world_session':'world','phase':'done','time':10,'inventory':[]}
  self.state={'world_session':'world','phase':'done','time':20,'inventory':[],'last_request':'read1','control_revision':2,'pos':[9,8,7],'health':20,'screen':'','movement_keys':{'forward':False}}
  self.event={'world_session':'world','phase':'done','request_id':'read1','op':'navigate','params':{'task_session':'task'},'revision_after':2,'position_after':[9,8,7],'inventory_delta':{},'health_before':20,'health_after':20}
 def check(self):return observable(self.command,self.error,self.partial,self.prior,self.state,self.event,'world','task')
 def test_exact_read_only_partial_audit_can_be_observed(self):self.assertTrue(self.check())
 def test_unconfirmed_input_or_inventory_change_is_rejected(self):
  self.error['unconfirmed_native_request']='unknown';self.assertFalse(self.check());self.error['unconfirmed_native_request']=None
  self.event['inventory_delta']={'minecraft:paper':-1};self.assertFalse(self.check())
 def test_partial_counts_and_visited_prefix_must_be_exact(self):
  self.partial['counts']['minecraft:paper']=8;self.assertFalse(self.check());self.partial['counts']['minecraft:paper']=4
  self.partial['visited'][0]['pos']=[4,5,6];self.assertFalse(self.check())
 def test_no_closed_menu_or_owner_or_current_terminal_no_observation(self):
  for key,value in [('screen','ChestScreen'),('last_request','another'),('control_revision',3),('movement_keys',{'forward':True})]:
   old=deepcopy(self.state);self.state[key]=value;self.assertFalse(self.check());self.state=old
  self.event['params']['task_session']='another';self.assertFalse(self.check())
 def test_completed_audit_and_exchange_cannot_use_this_observer(self):
  self.partial['complete']=True;self.assertFalse(self.check());self.partial['complete']=False
  self.command['action']='exchange';self.assertFalse(self.check())
 def test_incomplete_or_future_evidence_is_rejected(self):
  self.partial['visited'][0]['at_ms']=21;self.assertFalse(self.check());self.partial['visited'][0]['at_ms']=15
  del self.error['native_inflight'];self.assertFalse(self.check())
if __name__=='__main__':unittest.main()
