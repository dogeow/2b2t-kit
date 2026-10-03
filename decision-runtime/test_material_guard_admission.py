"""Only a proven native admission rejection may be retried after stable defense."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from material_client import Client,MaterialClient,Handoff
BUSY='Construction guard is defending or eating; wait before changing items or starting work'
class GuardAdmissionTest(unittest.TestCase):
 def client(self,d,states):
  c=MaterialClient.__new__(MaterialClient);c.task='task';c.world='world';c.rev=1;c.last='original'
  c.root=c.out=Path(d);current=[None];stream=iter(states);seen=[]
  def status(**kwargs):
   current[0]=next(stream,current[0]);seen.append(current[0].copy());return current[0].copy()
  c.status=status;c.seen=seen
  return c
 def frame(self,n,**changes):
  return {'health':20,'time':n,'pos':[1.,130.,2.],'guard_busy':False,'entities':[],**changes}
 def test_waits_for_busy_live_hostile_and_three_distinct_stable_frames_before_one_retry(self):
  with tempfile.TemporaryDirectory() as d:
   states=[self.frame(i,guard_busy=True) for i in range(8)]
   states += [self.frame(i,entities=[{'hostile':True,'health':20}]) for i in range(8,15)]
   states += [self.frame(15),self.frame(15),self.frame(16,pos=[1.5,130.,2.]),
              self.frame(17,pos=[1.5,130.,2.]),self.frame(18,pos=[1.5,130.,2.])]
   c=self.client(d,states);calls=[]
   def native(*args,**kw):
    calls.append(kw)
    if len(calls)==1:return {'id':'reject','phase':'error','detail':BUSY}
    self.assertEqual(18,c.seen[-1]['time'])
    return {'phase':'done'}
   with patch.object(Client,'request',side_effect=native),patch('material_client.time.sleep'),patch('material_client.time.monotonic',side_effect=range(100)):
    r=c.request('navigate',target=[10,130,20])
   self.assertEqual('done',r['phase']);self.assertEqual(2,len(calls))
   self.assertNotIn('guard_admission_deadline',c.__dict__)
 def test_budget_returns_waiting_and_original_resume_details_without_second_dispatch(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.client(d,[self.frame(1,guard_busy=True)])
   with patch.object(Client,'request',return_value={'id':'reject-1','phase':'error','detail':BUSY}) as native,patch('material_client.time.sleep'),patch('material_client.time.monotonic',side_effect=[0,5,31]):
    r=c.request('navigate',target=[10,130,20])
   self.assertEqual('waiting',r['phase']);self.assertEqual(1,native.call_count)
   proof=r['guard_admission_wait'];self.assertFalse(proof['action_dispatched'])
   self.assertEqual('reject-1',proof['rejected_request_id'])
   self.assertEqual([10,130,20],proof['requested_params']['target'])
 def test_dead_hostiles_do_not_block_but_duplicate_frames_do_not_prove_stability(self):
  with tempfile.TemporaryDirectory() as d:
   dead=[{'hostile':True,'alive':False,'health':20},{'hostile':True,'health':0}]
   c=self.client(d,[self.frame(1,entities=dead),self.frame(1,entities=dead),self.frame(2,entities=dead),self.frame(3,entities=dead)])
   with patch.object(Client,'request',side_effect=[{'phase':'error','detail':BUSY},{'phase':'done'}]) as native,patch('material_client.time.sleep'),patch('material_client.time.monotonic',side_effect=range(100)):
    self.assertEqual('done',c.request('slot_click')['phase'])
   self.assertEqual(4,len(c.seen));self.assertEqual(2,native.call_count)
 def test_manual_world_revision_handoff_is_not_retried(self):
  for reason in ('manual movement','world changed','foreign revision'):
   with self.subTest(reason=reason),tempfile.TemporaryDirectory() as d:
    c=self.client(d,[]);c.status=lambda **kw:(_ for _ in ()).throw(Handoff(reason))
    with patch.object(Client,'request',return_value={'phase':'error','detail':BUSY}) as native:
     with self.assertRaises(Handoff):c.request('navigate',target=[1,130,2])
    self.assertEqual(1,native.call_count)
 def test_low_health_outranks_retry(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.client(d,[self.frame(1,health=13)])
   with patch.object(Client,'request',return_value={'phase':'error','detail':BUSY}) as native:
    with self.assertRaisesRegex(RuntimeError,'Health reserve changed'):c.request('navigate',target=[1,130,2])
   self.assertEqual(1,native.call_count)
 def test_unrelated_errors_and_unknown_dispatch_exceptions_are_not_replayed(self):
  for response in ({'phase':'error','detail':'Inventory transfer not confirmed'},RuntimeError('timeout after publish')):
   with self.subTest(response=response),tempfile.TemporaryDirectory() as d:
    c=self.client(d,[])
    with patch.object(Client,'request',side_effect=response if isinstance(response,Exception) else None,return_value=response) as native:
     if isinstance(response,Exception):
      with self.assertRaises(RuntimeError):c.request('slot_click')
     else:self.assertEqual(response,c.request('slot_click'))
    self.assertEqual(1,native.call_count)
 def test_explicit_safe_logout_never_enters_defense_wait(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.client(d,[]);c._record_health_stop=lambda *args,**kw:None
   with patch.object(Client,'request',return_value={'phase':'error','detail':BUSY}) as native,patch.object(c,'_wait_guard_admission') as wait:
    self.assertEqual('error',c.request('safe_logout')['phase'])
   self.assertEqual(1,native.call_count);wait.assert_not_called()
 def test_guard_race_before_second_dispatch_is_bounded_and_does_not_publish_a_request(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.client(d,[]);native_calls=[0]
   def native(*args,**kw):
    native_calls[0]+=1
    if native_calls[0]==1:return {'phase':'error','detail':BUSY}
    raise RuntimeError('Defense remains busy')
   with patch.object(Client,'request',side_effect=native),patch.object(c,'_wait_guard_admission',return_value=True),patch('material_client.time.monotonic',side_effect=[0,31]):
    self.assertEqual('waiting',c.request('navigate')['phase'])
   self.assertEqual(2,native_calls[0]);self.assertEqual('original',c.last)
 def test_underlying_native_preflight_uses_the_shared_admission_deadline(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.client(d,[self.frame(1,guard_busy=True)]);c.guard_admission_deadline=2
   with patch('material_client.time.sleep'),patch('material_client.time.monotonic',side_effect=[0,1,3]):
    with self.assertRaisesRegex(RuntimeError,'Defense remains busy'):
     Client.request(c,'navigate',target=[5,130,5])
   self.assertFalse((c.root/'request.json').exists())
 def test_matching_error_text_after_request_publication_is_not_absorbed(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.client(d,[]);calls=[0]
   def native(*args,**kw):
    calls[0]+=1
    if calls[0]==1:return {'phase':'error','detail':BUSY}
    c.last='published-new-request'
    raise RuntimeError('Defense remains busy')
   with patch.object(Client,'request',side_effect=native),patch.object(c,'_wait_guard_admission',return_value=True),patch('material_client.time.monotonic',side_effect=[0,31]):
    with self.assertRaisesRegex(RuntimeError,'Defense remains busy'):c.request('navigate')
   self.assertEqual('published-new-request',c.last)
if __name__=='__main__':unittest.main()
