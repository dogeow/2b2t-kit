import copy,unittest
from boat_face_refusal import observable,DETAIL
class Tests(unittest.TestCase):
 def fixture(self):
  c={'action':'boat_place','support':[1,2,3],'item':'minecraft:oak_boat'};err={'error':DETAIL,'native_inflight':None,'unconfirmed_native_request':None,'last_request':'r'};b={'complete':False,'pending':'place','world_session':'w','support':c['support'],'item':c['item'],'request_id':'r','before':{'minecraft:oak_boat':1}};e={'world_session':'w','params':{'pos':c['support'],'expected_hand':c['item'],'task_session':'t','face':'up'},'request_id':'r','op':'interact','phase':'error','detail':DETAIL,'position_before':[4,3,3],'position_after':[4,3,3],'inventory_delta':{},'revision_before':2,'revision_after':2};s={'world_session':'w','last_request':'r','control_revision':2,'connected':True,'health':20,'manual_movement':False};return c,err,b,e,s,'w','t',b['before'].copy()
 def test_known_ray_refusal_allows_read_after_guard_rise(self):
  f=self.fixture();f[4]['pos']=[4,30,3];self.assertTrue(observable(*f))
 def test_sent_changed_or_unknown_outcomes_stay_fenced(self):
  for index,key,value in [(1,'native_inflight','r'),(1,'unconfirmed_native_request','r'),(3,'phase','done'),(3,'inventory_delta',{'minecraft:oak_boat':-1}),(4,'manual_movement',True),(4,'control_revision',3),(4,'health',19),(2,'complete',True),(7,'minecraft:oak_boat',0)]:
   f=self.fixture();f[index][key]=value;self.assertFalse(observable(*f),(index,key))
