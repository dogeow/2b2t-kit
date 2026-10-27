import copy,unittest
from recovered_air_injury import observable,DETAIL

class RecoveryTest(unittest.TestCase):
 def fixture(self):
  command={'action':'native','op':'navigate','params':{'target':[1,74,2],'air_only':True}}
  inv=[{'slot':0,'item':'minecraft:cobblestone_slab','count':384}]
  reply={'id':'r','world_session':'w','control_revision':8,'phase':'waiting','detail':DETAIL,'health':19.6,'pos':[1,82,2],'inventory':inv}
  event={'op':'navigate','request_id':'r','world_session':'w','revision_after':8,'phase':'waiting','detail':DETAIL,'health_before':20,'health_after':19.6,'position_after':[1,82,2],'inventory_delta':{},'params':{'target':[1,74,2],'task_session':'t'}}
  state={**copy.deepcopy(reply),'last_request':'r','health':20,'time':40000,'recent_hurt_at':1000,'supervision_lease':{'kind':'materials','job_session':'t','world_session':'w','revision':8},'connected':True,'flight':True,'guard_armed':True,'guard_pve_only':True,'guard_busy':False,'manual_movement':False,'screen':'','under_water':False,'movement_keys':{'forward':False},'safety_hold':{'active':False}}
  return command,reply,event,state
 def test_only_fully_recovered_known_stop_is_observable(self):
  self.assertTrue(observable(*self.fixture(),'w','t'))
  for change in [{'health':19.9},{'recent_hurt_at':39999},{'guard_busy':True},{'guard_armed':False},{'guard_pve_only':False},{'connected':False},{'world_session':'other'},{'screen':'ChatScreen'},{'manual_movement':True},{'pos':[2,82,2]},{'movement_keys':{'forward':True}},{'safety_hold':{'active':True}},{'safety_hold':{}},{'inventory':[]}]:
   c,r,e,s=self.fixture();s.update(change)
   with self.subTest(change=change):self.assertFalse(observable(c,r,e,s,'w','t'))
 def test_unknown_wrong_request_inventory_change_or_large_injury_never_admitted(self):
  for target,change in [('reply',{'phase':'running'}),('reply',{'id':'other'}),('event',{'revision_after':9}),('event',{'inventory_delta':{'minecraft:cobblestone_slab':-1}}),('event',{'health_after':18}),('event',{'params':{'target':[2,74,2],'task_session':'t'}})]:
   c,r,e,s=self.fixture();(r if target=='reply' else e).update(change)
   self.assertFalse(observable(c,r,e,s,'w','t'))
