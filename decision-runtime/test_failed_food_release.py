import copy,unittest
from failed_food_release import allowed
class Tests(unittest.TestCase):
 def fixture(self):
  command={'action':'feed_village_founders'};error={'type':'RuntimeError','error':'Original bread drop lacks its exact server collector receipt; do not repeat','native_inflight':None,'unconfirmed_native_request':None,'last_request':'r'};book={'complete':False,'pending':None,'world_session':'w','pending_food':{'native_request':'r','target':'v'}};event={'request_id':'r','op':'villager_bread_drop','phase':'done','world_session':'w','params':{'task_session':'t','expected_uuid':'v'},'health_before':20,'health_after':20,'position_after':[1,64,2],'revision_after':7};state={'last_request':'r','phase':'done','world_session':'w','supervision_lease':{'job_session':'t','world_session':'w','kind':'materials'},'health':20,'pos':[1,64,2],'control_revision':7,'connected':True,'manual_movement':False,'screen':'','menu':{'cursor':{'count':0}},'movement_keys':{'forward':False}};return ['pause',command,error,book,event,state,'w','t']
 def test_only_release_and_original_book_preserved(self):
  a=self.fixture();original=copy.deepcopy(a);self.assertTrue(allowed(*a));self.assertEqual(a,original)
  for action in ['native','feed_village_founders','exchange']:
   a=self.fixture();a[0]=action;self.assertFalse(allowed(*a))
 def test_unknown_or_active_native_cannot_release(self):
  for key in ['native_inflight','unconfirmed_native_request']:
   a=self.fixture();a[2][key]='r';self.assertFalse(allowed(*a))
  a=self.fixture();a[3]['pending']={'op':'navigate'};self.assertFalse(allowed(*a))
 def test_current_owner_and_exact_native_identity_required(self):
  for mode in ['request','world','task','target','position','revision']:
   a=self.fixture()
   if mode=='request':a[4]['request_id']='other'
   elif mode=='world':a[4]['world_session']='other'
   elif mode=='task':a[4]['params']['task_session']='other'
   elif mode=='target':a[4]['params']['expected_uuid']='other'
   elif mode=='position':a[5]['pos']=[2,64,2]
   else:a[5]['control_revision']=8
   with self.subTest(mode=mode):self.assertFalse(allowed(*a))
 def test_health_manual_control_and_busy_remain_protected(self):
  for key,value in [('health',19),('manual_movement',True),('navigating',True),('pending_scan',{'id':'r'}),('native_material_busy',True),('screen','ChatScreen')]:
   a=self.fixture();a[5][key]=value;self.assertFalse(allowed(*a))
 def test_nonterminal_or_missing_event_refused(self):
  a=self.fixture();a[4]['phase']='waiting';self.assertFalse(allowed(*a));a=self.fixture();a[4]=None;self.assertFalse(allowed(*a))
