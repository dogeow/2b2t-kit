import json,copy,unittest
from pathlib import Path
from zero_proposal_printer import conserved
class Tests(unittest.TestCase):
 def fixture(self):
  f=json.loads((Path(__file__).parent/'test_fixtures/zero-proposal-printer.json').read_text());reply=f['reply'];state=copy.deepcopy(reply);state['last_request']=reply['id'];return [f['command'],reply,f['prior_intent'],f['prior'],f['event'],state,reply['world_session'],f['event']['params']['task_session']]
 def test_recorded_zero_input_interval_is_observable(self):self.assertTrue(conserved(*self.fixture()))
 def test_any_proposal_pending_confirmation_or_failure_is_fenced(self):
  for k,value in [('fast_proposals',1),('complex_proposals',1),('server_confirmed',1),('travel_pending',1),('last_proposal',{'target':'x'}),('waiting_for_server',True),('failure','unknown')]:
   for index in (1,5):
    a=self.fixture();a[index]['professional_printer'][k]=value;self.assertFalse(conserved(*a))
 def test_inventory_change_wrong_scope_and_health_change_rejected(self):
  for index in (1,3,5):
   a=self.fixture();a[index]['inventory'][0]['count']+=1;self.assertFalse(conserved(*a))
  a=self.fixture();a[5]['projection_batch']['placement_key']='other';self.assertFalse(conserved(*a))
  a=self.fixture();a[5]['health']=19;self.assertFalse(conserved(*a))
 def test_unrelated_event_cannot_unlock_old_interval(self):
  a=self.fixture();a[4]['request_id']='later';self.assertFalse(conserved(*a))
if __name__=='__main__':unittest.main()

class HistoricalTerminalTests(unittest.TestCase):
 def fixture(self):
  f=json.loads((Path(__file__).parent/'test_fixtures/zero-proposal-printer.json').read_text());r=f['reply'];e=f['event'];task=e['params']['task_session'];r['op']='professional_print';r['server_confirmed']=False;r['supervision_lease']={'kind':'materials','job_session':task,'world_session':r['world_session']};cmd={'id':r['id'],'op':'professional_print','world_session':r['world_session'],'task_session':task,'expected_revision':f['prior']['control_revision']};mask={'request_id':f['prior'].get('id','mask'),'op':'projection_batch_set','phase':'done','world_session':r['world_session'],'params':f['prior_intent']['params']};f['prior']['id']=mask['request_id'];return [cmd,r,mask,f['prior'],e]
 def test_historical_zero_proposals_is_not_a_claim_of_goal_success(self):
  from zero_proposal_printer import terminal_unqueued
  a=self.fixture();self.assertTrue(terminal_unqueued(*a));self.assertEqual(a[1]['phase'],'waiting');self.assertIs(a[1]['server_confirmed'],False)
 def test_any_queued_or_unconfirmed_proposal_stays_fenced(self):
  from zero_proposal_printer import terminal_unqueued
  for key,value in [('complex_proposals',1),('last_proposal',{'interaction_seen':True}),('waiting_for_server',True),('failure','unknown')]:
   a=self.fixture();a[1]['professional_printer'][key]=value;self.assertFalse(terminal_unqueued(*a))
 def test_identity_owner_mask_inventory_and_event_must_all_match(self):
  from zero_proposal_printer import terminal_unqueued
  a=self.fixture();a[0]['world_session']='later';self.assertFalse(terminal_unqueued(*a))
  a=self.fixture();a[2]['params']['positions']=[[1,2,3]];self.assertFalse(terminal_unqueued(*a))
  a=self.fixture();a[1]['inventory'][0]['count']+=1;self.assertFalse(terminal_unqueued(*a))
  a=self.fixture();a[4]['request_id']='other';self.assertFalse(terminal_unqueued(*a))
