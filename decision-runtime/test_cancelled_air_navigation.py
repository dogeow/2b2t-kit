import unittest
from cancelled_air_navigation import admit
class NavigationHandoffTests(unittest.TestCase):
 def fixture(self):
  u=dict(op='navigate',params=dict(target=[1,70,2],air_only=True),original_request_replayed=False,world_session='w',task_session='t',request_id='r');c=dict(action='native',op='navigate',params=u['params']);e=dict(op='scan',phase='done',world_session='w',params=dict(task_session='t'),inventory_delta={},revision_after=7);s=dict(last_request='r',world_session='w',control_revision=8,connected=True,health=20,manual_movement=False,screen='',phase='stopped',detail='手动移动接管');return u,c,e,s
 def test_new_route_admission_keeps_cancelled_navigation_unknown(self):
  u,c,e,s=self.fixture();self.assertTrue(admit(u,c,e,s));self.assertNotIn('complete',u)
 def test_world_input_live_or_unknown_owner_and_unconfirmed_stop_refuse(self):
  for which,change in [('u',{'op':'mine_block'}),('u',{'params':{'target':[1,70,2],'air_only':False}}),('s',{'detail':'navigation timed out'}),('s',{'supervision_lease':{'id':'active'}}),('s',{'manual_movement':True}),('s',{'health':19}),('s',{'control_revision':7}),('s',{'last_request':'other'}),('e',{'inventory_delta':{'minecraft:cobblestone':-1}})]:
   u,c,e,s=self.fixture();{'u':u,'s':s,'e':e}[which].update(change)
   with self.subTest(change=change):self.assertFalse(admit(u,c,e,s))
if __name__=='__main__':unittest.main()
