import unittest
from capture_standoff import validate,retreat
from capture_target import NAME

class CaptureStandoffTests(unittest.TestCase):
 def fixture(self):
  state=dict(connected=True,health=20,manual_movement=False,screen='',guard_armed=True,guard_pve_only=True,guard_busy=False,
             world_session='w',player_uuid='p',control_revision=8,pos=[.04,65.15,.0],
             supervision_lease=dict(kind='materials',id='l',job_session='t',world_session='w'))
  request=dict(world_session='w',player_uuid='p',control_revision=7,lease_id='l',task_session='t',entity_uuid='z',expected_type='minecraft:zombie',id='a')
  ack=dict(active=True,named=True,id='a',entity_uuid='z')
  mob=dict(uuid='z',type='minecraft:zombie',health=20,has_custom_name=True,name=NAME,pos=[0,62.4875,0],bounds=dict(min=[-.3,62.4875,-.3],max=[.3,64.4375,.3]))
  return state,request,ack,mob
 def test_observation_directly_above_boat_is_not_a_safe_melee_standoff(self):
  s,r,a,m=self.fixture()
  # Recorded vertical separation looked large at the feet, but the bodies were only .7125 apart.
  with self.assertRaises(ValueError):validate(s,r,a,m,[0,65.15,0])
  with self.assertRaises(ValueError):validate(s,r,a,m,[3,65.15,0])
  validate(s,r,a,m,[4,65.15,0])
 def test_named_identity_protection_health_and_manual_control_remain_required(self):
  for which,change in [('s',{'manual_movement':True}),('s',{'health':19}),('s',{'supervision_lease':{}}),('s',{'world_session':'other'}),('a',{'active':False}),('a',{'entity_uuid':'other'}),('m',{'health':19}),('m',{'name':'other'})]:
   s,r,a,m=self.fixture();{'s':s,'a':a,'m':m}[which].update(change)
   with self.subTest(which=which,change=change),self.assertRaises(ValueError):validate(s,r,a,m,[4,65.15,0])
 def test_unbounded_or_nonfinite_retreat_does_not_authorize_movement(self):
  s,r,a,m=self.fixture()
  for p in [[100,65.15,0],[float('nan'),65.15,0],[4,65.15],None]:
   with self.subTest(p=p),self.assertRaises(ValueError):validate(s,r,a,m,p)
 def test_existing_retreat_intent_is_never_replayed(self):
  class Builder:
   book={'named_bait_retreat':{'pending':True}}
   def check(self):raise AssertionError('No second movement or observation needed to repeat refusal')
  with self.assertRaises(RuntimeError):retreat(Builder(),{},[4,65,0])

if __name__=='__main__':unittest.main()
