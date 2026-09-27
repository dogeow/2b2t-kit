import unittest
from unittest.mock import patch
from material_shutdown import drain_pending

def state(phase='running',rev=2):
 return dict(connected=True,world_session='w',manual_movement=False,last_request='r',phase=phase,health=20,control_revision=rev,supervision_lease={'kind':'materials','job_session':'t','revision':rev})
class Client:
 world='w';task='t';last='r';rev=1
 def __init__(self,states):self.states=iter(states);self.current=None
 def raw(self):self.current=next(self.states,self.current);return self.current
 def request(self,*a,**kw):raise AssertionError('Never replace the pending native action')
class MaterialShutdownTest(unittest.TestCase):
 def test_already_settled_owned_action_updates_revision_before_cleanup(self):
  for phase in ('done','waiting','stopped','error'):
   with self.subTest(phase=phase):
    c=Client([state(phase,4)])
    with patch('material_shutdown.time.sleep') as sleep:result=drain_pending(c)
    self.assertTrue(result['safe_to_cleanup']);self.assertEqual(4,c.rev);sleep.assert_not_called()
 def test_terminal_state_requires_matching_owner_before_adopting_revision(self):
  for key,value in [('manual_movement',True),('connected',False),('world_session','other'),('last_request','other'),
                    ('supervision_lease',{'kind':'materials','job_session':'other','revision':4}),
                    ('supervision_lease',{'kind':'materials','job_session':'t','revision':3})]:
   with self.subTest(key=key,value=value):
    s=state('done',4);s[key]=value;c=Client([s]);result=drain_pending(c)
    self.assertFalse(result['safe_to_cleanup']);self.assertEqual('control_handoff',result['reason']);self.assertEqual(1,c.rev)
 def test_owned_terminal_revision_is_accepted_without_new_commands(self):
  c=Client([state(),state('waiting',4)])
  with patch('material_shutdown.time.sleep'):result=drain_pending(c)
  self.assertTrue(result['safe_to_cleanup']);self.assertEqual('owned_action_settled',result['reason']);self.assertEqual(4,c.rev)
 def test_manual_or_other_controller_receives_no_cleanup(self):
  for key,value in [('manual_movement',True),('world_session','other'),('last_request','other')]:
   s=state();s[key]=value;r=drain_pending(Client([s]));self.assertFalse(r['safe_to_cleanup']);self.assertEqual('control_handoff',r['reason'])
 def test_low_health_does_not_wait(self):
  s=state();s['health']=13;r=drain_pending(Client([s]));self.assertFalse(r['safe_to_cleanup']);self.assertEqual('low_health',r['reason'])
 def test_wait_is_bounded(self):
  with patch('material_shutdown.time.monotonic',side_effect=[0,2]):r=drain_pending(Client([state()]),seconds=1)
  self.assertEqual('pending_action_timeout',r['reason'])
 def test_normal_finish_does_not_wait(self):
  with patch('material_shutdown.time.sleep') as sleep:self.assertTrue(drain_pending(Client([state('done')]))['safe_to_cleanup']);sleep.assert_not_called()
if __name__=='__main__':unittest.main()
