import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from protected_zombie_transport import aboard,observed_aboard

class ProtectedZombieTransportTests(unittest.TestCase):
 def fixture(self):
  s=dict(connected=True,manual_movement=False,screen='',health=20,world_session='world',player_uuid='player',control_revision=9,
   supervision_lease=dict(kind='materials',id='lease',job_session='task',world_session='world'))
  r=dict(expected_type='minecraft:zombie',entity_uuid='z',world_session='world',player_uuid='player',lease_id='lease',task_session='task',control_revision=7,id='capture')
  a=dict(active=True,named=True,id='capture',entity_uuid='z')
  b=dict(leashed=True,leash_resolved=True,leash_holder=dict(uuid='player'),passengers=[dict(uuid='z',type='minecraft:zombie',alive=True,health=20,has_custom_name=True)])
  return b,s,r,a
 def test_unnamed_bait_requires_new_runtime_and_exact_current_protected_boat(self):
  b,s,r,a=self.fixture();b['uuid']='boat';b['passengers'][0]['has_custom_name']=False;r['boat_uuid']='boat';a.update(named=False,boat_bound=True,boat_uuid='boat',runtime_version='1.8.21')
  self.assertTrue(aboard(b,['z'],s,r,a))
  for changes in [{'boat_uuid':'other'},{'boat_bound':False},{'runtime_version':'1.8.20'}]:
   self.assertFalse(aboard(b,['z'],s,r,{**a,**changes}))
  self.assertFalse(aboard({**b,'uuid':'other'},['z'],s,r,a))
 def test_exact_named_bait_uses_same_live_lease_after_normal_native_inputs(self):
  b,s,r,a=self.fixture();self.assertTrue(aboard(b,['z'],s,r,a))
 def test_newer_protection_frame_uses_current_clock_and_still_rejects_stale_or_future_ack(self):
  b,s,r,a=self.fixture();s['time']=999800
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);(root/'capture-target.json').write_text(json.dumps(r))
   for stamp,expected in [(999950,True),(999000,False),(1000001,False)]:
    (root/'capture-target-state.json').write_text(json.dumps(dict(a,protocol=1,runtime_version='1.8.20',time=stamp)))
    with self.subTest(stamp=stamp),patch('protected_zombie_transport.time.time',return_value=1000):
     self.assertEqual(observed_aboard(root,b,['z'],s),expected)
 def test_drowned_must_match_the_exact_armed_type(self):
  b,s,r,a=self.fixture();r['expected_type']='minecraft:drowned';self.assertFalse(aboard(b,['z'],s,r,a))
  b['passengers'][0]['type']='minecraft:drowned';self.assertTrue(aboard(b,['z'],s,r,a))
  b['passengers'][0]['type']='minecraft:villager';self.assertFalse(aboard(b,['z'],s,r,a))
 def test_other_cargo_injury_foreign_leash_or_missing_name_refuses(self):
  for patch in ({'uuid':'other'},{'type':'minecraft:villager'},{'health':19},{'alive':False},{'has_custom_name':False}):
   b,s,r,a=self.fixture();b['passengers'][0].update(patch);self.assertFalse(aboard(b,['z'],s,r,a))
  b,s,r,a=self.fixture();b['passengers'].append(copy.deepcopy(b['passengers'][0]));self.assertFalse(aboard(b,['z'],s,r,a))
  b,s,r,a=self.fixture();b['leash_holder']['uuid']='other';self.assertFalse(aboard(b,['z'],s,r,a))
 def test_stopped_manual_or_changed_owner_never_authorizes_transport(self):
  for patch in ({'manual_movement':True},{'connected':False},{'health':19},{'screen':'InventoryScreen'},{'control_revision':6},{'world_session':'other'},{'supervision_lease':{}}):
   b,s,r,a=self.fixture();s.update(patch);self.assertFalse(aboard(b,['z'],s,r,a))
  for patch in ({'active':False},{'named':False},{'id':'old'},{'entity_uuid':'other'}):
   b,s,r,a=self.fixture();a.update(patch);self.assertFalse(aboard(b,['z'],s,r,a))

if __name__=='__main__':unittest.main()
