import unittest
from copy import deepcopy
from air_stop_pause import allowed
class AirStopPauseTests(unittest.TestCase):
 def setUp(self):
  self.c={'action':'native','op':'navigate','params':{'air_only':True,'target':[2,63.1,3]}};self.r={'phase':'waiting','detail':'air-only path changed; no blocks were excavated','id':'r','world_session':'w','control_revision':4,'inventory':[]};self.s=dict(self.r,last_request='r',pos=[2,62.945,3],health=20,connected=True,manual_movement=False,screen='',movement_keys={},velocity=[0,0,0]);self.e={'phase':'waiting','detail':self.r['detail'],'request_id':'r','world_session':'w','revision_after':4,'op':'navigate','params':{'task_session':'t','target':[2,63.1,3]},'inventory_delta':{}}
 def check(self,action='pause',unknown=False):return allowed(action,self.c,self.r,self.s,self.e,'w','t',unknown)
 def test_exact_known_stop_can_end_lease_despite_passive_fractional_settling(self):self.assertTrue(self.check())
 def test_other_actions_and_unknown_receipts_remain_blocked(self):self.assertFalse(self.check('navigate'));self.assertFalse(self.check(unknown=True))
 def test_foreign_owner_health_or_actual_movement_cannot_pause_through_this_rule(self):
  for key,value in [('health',19),('manual_movement',True),('last_request','other'),('velocity',[0,-1,0]),('navigating',True)]:
   original=deepcopy(self.s);self.s[key]=value;self.assertFalse(self.check());self.s=original
  self.e['params']['task_session']='other';self.assertFalse(self.check())
if __name__=='__main__':unittest.main()
