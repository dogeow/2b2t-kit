import unittest
from storage_profile_refusal import observable
class RefusalTests(unittest.TestCase):
 def fixture(self):
  return ({'action':'exchange','profile':'new-profile'}, {'type':'RuntimeError','error':'Original registered storage profile changed during its live route','native_inflight':None,'unconfirmed_native_request':None,'last_request':'old'}, {'request_id':'old','phase':'done','world_session':'world','params':{'task_session':'task'},'revision_after':8}, {'last_request':'old','connected':True,'world_session':'world','health':20,'manual_movement':False,'screen':'','guard_busy':False,'control_revision':8,'supervision_lease':{'kind':'materials','world_session':'world','job_session':'task','revision':8}})
 def test_exact_pre_adapter_refusal(self):self.assertTrue(observable(*self.fixture(),'world','task'))
 def test_different_failure_is_not_settlement(self):
  a,b,c,d=self.fixture();b['error']='Inventory click outcome unknown';self.assertFalse(observable(a,b,c,d,'world','task'))
 def test_unknown_or_new_native_input_remains_pending(self):
  for key,val in [('native_inflight',{'id':'new'}),('unconfirmed_native_request',{'id':'new'}),('last_request','new')]:
   a,b,c,d=self.fixture();b[key]=val;self.assertFalse(observable(a,b,c,d,'world','task'))
 def test_manual_or_owner_change_cannot_resume(self):
  for key,val in [('manual_movement',True),('health',19),('world_session','other'),('control_revision',9),('screen','ContainerScreen')]:
   a,b,c,d=self.fixture();d[key]=val;self.assertFalse(observable(a,b,c,d,'world','task'))
 def test_single_missing_record_before_any_native_input_only(self):
  a,b,c,d=self.fixture();b.update(type='JobBlocked',error='Storage position has no current scoped Kit record');a['positions']=[[1,2,3]];self.assertTrue(observable(a,b,c,d,'world','task'))
  a['positions'].append([4,5,6]);self.assertFalse(observable(a,b,c,d,'world','task'))

if __name__=='__main__':unittest.main()
