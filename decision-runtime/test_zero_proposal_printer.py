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
