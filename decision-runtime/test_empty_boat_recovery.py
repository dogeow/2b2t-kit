import copy,unittest
from empty_boat_recovery import request_for
class Tests(unittest.TestCase):
 def fixture(self):
  s=dict(runtime_version='1.8.25',connected=True,health=20,food=20,manual_movement=False,screen='',guard_busy=False,guard_armed=True,guard_pve_only=True,time=1000,world_session='w',control_revision=7,player_uuid='00000000-0000-0000-0000-000000000001',pos=[1,90,3],hand=dict(item='minecraft:diamond_axe'),inventory=[dict(slot=0,item='minecraft:air',count=0)],supervision_lease=dict(id='l',job_session='t',kind='materials',world_session='w'))
  b=dict(uuid='00000000-0000-0000-0000-000000000002',id=3,type='minecraft:oak_boat',alive=True,has_custom_name=False,passengers=[],leashed=False,on_ground=True,in_water=False,visible=True,pos=[1,90,1]);return s,b
 def test_fresh_exact_empty_boat_request_is_not_recovery_credit(self):
  s,b=self.fixture();r=request_for(s,b,1000,'one');self.assertEqual(r['boat_uuid'],b['uuid']);self.assertEqual(r['expires_at'],6000);self.assertNotIn('recovery_credit',r)
 def test_cargo_manual_takeover_and_full_inventory_refuse_before_request(self):
  s,b=self.fixture()
  for edit in [dict(health=19),dict(manual_movement=True),dict(guard_busy=True),dict(screen='ChatScreen'),dict(inventory=[]),dict(hand=dict(item='minecraft:netherite_sword'))]:
   with self.assertRaises(ValueError):request_for(dict(s,**edit),b,1000,'one')
  for edit in [dict(passengers=[dict(uuid='villager')]),dict(has_custom_name=True),dict(visible=False),dict(in_water=True),dict(leashed=True,leash_resolved=True,leash_holder=dict(uuid='foreign'))]:
   with self.assertRaises(ValueError):request_for(s,dict(b,**edit),1000,'one')
