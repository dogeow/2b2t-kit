import unittest,time,tempfile,json
from pathlib import Path
from unittest.mock import patch
from capture_receiver import request_for,arm
class Tests(unittest.TestCase):
 def test_unleashed_mode_is_explicit_new_runtime_only_and_rejects_foreign_leashes(self):
  s,b=self.fixture();b.update(leashed=False,leash_resolved=False,leash_holder={})
  with self.assertRaises(ValueError):request_for(s,b,1000,'r123',allow_unleashed=True)
  s['runtime_version']='1.8.24';r=request_for(s,b,1000,'r123',allow_unleashed=True);self.assertTrue(r['allow_unleashed'])
  with self.assertRaises(ValueError):request_for(s,b,1000,'r123')
  b.update(leashed=True,leash_resolved=True,leash_holder=dict(uuid='other'))
  with self.assertRaises(ValueError):request_for(s,b,1000,'r123',allow_unleashed=True)
 def fixture(self):
  s=dict(runtime_version='1.8.22',connected=True,health=20,food=20,manual_movement=False,screen='',time=1000,guard_armed=True,guard_pve_only=True,world_session='w',control_revision=7,player_uuid='00000000-0000-0000-0000-000000000001',pos=[1,10,1],supervision_lease=dict(id='lease',job_session='task',kind='materials',world_session='w'));b=dict(uuid='00000000-0000-0000-0000-000000000002',type='minecraft:oak_boat',alive=True,passengers=[],leashed=True,leash_resolved=True,leash_holder=dict(uuid=s['player_uuid']),pos=[1,5,1],has_custom_name=False);return s,b
 def test_exact_empty_receiver_is_registered_even_while_other_defense_is_busy(self):
  s,b=self.fixture();s['guard_busy']=True;r=request_for(s,b,1000,'r123');self.assertEqual(r['boat_uuid'],b['uuid']);self.assertEqual(r['expires_at']-r['issued_at'],600000)
 def test_takeover_health_owner_cargo_and_foreign_leash_refuse_before_writing(self):
  s,b=self.fixture()
  for change in [dict(health=19),dict(runtime_version='1.8.21'),dict(manual_movement=True),dict(screen='ChatScreen'),dict(time=-10),dict(supervision_lease={})]:
   with self.assertRaises(ValueError):request_for(dict(s,**change),b,1000,'r123')
  for change in [dict(passengers=[{'uuid':'other'}]),dict(leashed=False),dict(leash_resolved=False),dict(leash_holder=dict(uuid='other')),dict(type='minecraft:oak_chest_boat'),dict(pos=[1,0,1])]:
   with self.assertRaises(ValueError):request_for(s,dict(b,**change),1000,'r123')
 def test_original_pending_receiver_is_not_replaced(self):
  s,b=self.fixture();s['time']=int(time.time()*1000)
  with tempfile.TemporaryDirectory()as directory:
   class Q:
    root=Path(directory)
    def status(self):return s
   p=Path(directory)/'capture-receiver.json';prior=dict(world_session='w',lease_id='lease',id='prior',expires_at=s['time']+100000);p.write_text(json.dumps(prior));old=p.read_bytes()
   with patch('capture_receiver.read_frame',return_value=dict(vehicles=[b])),self.assertRaisesRegex(RuntimeError,'pending receiver'):
    arm(Q(),b['uuid'],Path(directory)/'out')
   self.assertEqual(old,p.read_bytes())
