import unittest
import test_sleeping_merchant_observation as fixtures
from sleeping_merchant_observation import observable_reach,REACH_HOST_SHA256,OCCLUSION_HOST_SHA256,observable
class MerchantReachObservationTests(unittest.TestCase):
 def fixture(self):
  c,err,o,e,s,f=fixtures.SleepingMerchantObservationTests().fixture();err['error']='Entity out of reach';e['detail']='Entity out of reach';e['phase']='error';return c,err,o,e,s,f
 def test_pinned_zero_movement_range_guard_only_allows_observation(self):
  self.assertTrue(observable_reach(*self.fixture(),'w','t',REACH_HOST_SHA256));self.assertFalse(observable(*self.fixture(),'w','t'))
 def test_audited_20_4_host_keeps_unknown_receipts_and_effects_fenced(self):
  sha='7d29812c22ed57cd52ab0e1e310e029693eca2915a652cdb8b09b1b3acbc8607'
  self.assertTrue(observable_reach(*self.fixture(),'w','t',sha))
  c,err,o,e,s,f=self.fixture();e['inventory_delta']={'minecraft:emerald':1}
  self.assertFalse(observable_reach(c,err,o,e,s,f,'w','t',sha))
 def test_other_host_any_input_effect_or_late_menu_remains_retained(self):
  for mode in ['host','unknown','inventory','position','revision','menu','wrong_detail','wrong_phase','keys']:
   c,err,o,e,s,f=self.fixture();sha=REACH_HOST_SHA256
   if mode=='host':sha='other'
   elif mode=='unknown':err['unconfirmed_native_request']={'id':'n'}
   elif mode=='inventory':e['inventory_delta']={'minecraft:bread':6}
   elif mode=='position':s['pos']=[1,65,0]
   elif mode=='revision':e['revision_after']=9
   elif mode=='menu':s['screen']='MerchantScreen'
   elif mode=='wrong_detail':e['detail']='Entity is occluded'
   elif mode=='wrong_phase':e['phase']='waiting'
   else:s['movement_keys']['forward']=True
   with self.subTest(mode=mode):self.assertFalse(observable_reach(c,err,o,e,s,f,'w','t',sha))
 def test_current_host_occlusion_is_observation_only_after_all_zero_effect_checks(self):
  for mode in ['settled','older_host','unknown','inventory','position','revision','menu','mismatch']:
   c,err,o,e,s,f=self.fixture();err['error']=e['detail']='Entity is occluded';sha=OCCLUSION_HOST_SHA256
   if mode=='older_host':sha=REACH_HOST_SHA256
   elif mode=='unknown':err['native_inflight']={'id':'n'}
   elif mode=='inventory':e['inventory_delta']={'minecraft:emerald':-1}
   elif mode=='position':e['position_after']=[1,65,0]
   elif mode=='revision':s['control_revision']=9
   elif mode=='menu':s['screen']='MerchantScreen'
   elif mode=='mismatch':e['detail']='Entity out of reach'
   with self.subTest(mode=mode):self.assertEqual(mode=='settled',observable_reach(c,err,o,e,s,f,'w','t',sha))
if __name__=='__main__':unittest.main()
