import copy,unittest
from capture_target import request_for

class CaptureTargetTests(unittest.TestCase):
 def test_explicit_long_preparation_is_new_runtime_only_bounded_and_default_is_unchanged(self):
  s=self.state();uid=s['entities'][0]['uuid'];s['runtime_version']='1.8.25'
  with self.assertRaises(ValueError):request_for(s,uid,1100,'capture-test',window_ms=60000)
  s['runtime_version']='1.8.26';r=request_for(s,uid,1100,'capture-test',window_ms=60000)
  self.assertEqual(r['expires_at']-r['issued_at'],60000)
  self.assertEqual(request_for(s,uid,1100,'capture-test')['expires_at']-1100,15000)
  for value in [True,14999,60001]:
   with self.assertRaises(ValueError):request_for(s,uid,1100,'capture-test',window_ms=value)
 def state(self):
  return dict(connected=True,screen='',manual_movement=False,health=20,guard_armed=True,
   guard_pve_only=True,guard_busy=False,world_session='world',runtime_version='1.8.14',
   control_revision=4,player_uuid='player',time=1000,pos=[0,65,0],
   supervision_lease=dict(kind='materials',id='lease',job_session='task',world_session='world'),
   inventory=[dict(slot=0,item='minecraft:name_tag',count=1)],
   entities=[dict(uuid='00000000-0000-0000-0000-000000000001',type='minecraft:zombie',
    health=20,is_baby=False,has_custom_name=False,pos=[20,65,0])])
 def test_explicit_boat_binding_keeps_original_arming_window_and_old_runtime_refuses(self):
  s=self.state();uid=s['entities'][0]['uuid'];boat='00000000-0000-0000-0000-000000000002'
  with self.assertRaises(ValueError):request_for(s,uid,1100,'capture-test',boat_uuid=boat)
  s['runtime_version']='1.8.21';s['inventory']=[];r=request_for(s,uid,1100,'capture-test',boat_uuid=boat)
  self.assertEqual(r['boat_uuid'],boat);self.assertEqual(r['expires_at']-r['issued_at'],15000)
 def test_only_explicit_current_zombie_is_armed_without_capture_credit(self):
  s=self.state();r=request_for(s,s['entities'][0]['uuid'],1100,'capture-test')
  self.assertEqual('lease',r['lease_id']);self.assertEqual(15000,r['expires_at']-r['issued_at'])
  self.assertEqual('minecraft:zombie',r['expected_type'])
 def test_drowned_requires_updated_runtime_and_retains_its_actual_type(self):
  s=self.state();s['entities'][0]['type']='minecraft:drowned'
  with self.assertRaises(ValueError):request_for(s,s['entities'][0]['uuid'],1100,'capture-test')
  s['runtime_version']='1.8.19';r=request_for(s,s['entities'][0]['uuid'],1100,'capture-test');self.assertEqual('minecraft:drowned',r['expected_type'])
 def test_current_passive_server_entity_frame_works_without_block_scan(self):
  from loaded_hostiles import SCOPE
  s=self.state();s.update(runtime_version='1.8.20',runtime_generation=3,server='s',dimension='d');mob=s['entities'].pop();mob.update(id=1,alive=True,hostile=True,visible=False,on_fire=False,in_water=False,bounds={'min':[19.7,65,-.3],'max':[20.3,66.95,.3]},main_hand='minecraft:air',off_hand='minecraft:air',head_item='minecraft:air')
  frame={k:s[k]for k in ['connected','time','world_session','server','dimension','player_uuid','runtime_version','runtime_generation']};frame.update(protocol=1,scope=SCOPE,world_entered_at=500,truncated=False,equipment_scope='current_client_entity_equipment_not_predicted_drops',hostiles=[mob]);self.assertEqual(mob['uuid'],request_for(s,mob['uuid'],1100,'capture-test',frame)['entity_uuid'])
  frame['runtime_generation']=2
  with self.assertRaises(ValueError):request_for(s,mob['uuid'],1100,'capture-test',frame)
 def test_new_runtime_needs_known_safe_drowned_equipment(self):
  s=self.state();s['runtime_version']='1.8.20';mob=s['entities'][0];mob['type']='minecraft:drowned'
  for hand in [None,'minecraft:trident']:
   if hand:mob['main_hand']=hand
   with self.assertRaises(ValueError):request_for(s,mob['uuid'],1100,'capture-test')
  mob['main_hand']='minecraft:air';self.assertEqual('minecraft:drowned',request_for(s,mob['uuid'],1100,'capture-test')['expected_type'])
 def test_control_health_interface_and_world_changes_refuse(self):
  for change in ({'manual_movement':True},{'health':19},{'screen':'InventoryScreen'},
                 {'guard_busy':True},{'world_session':'other'},{'time':0},{'runtime_version':'1.8.12'}):
   s=self.state();s.update(change)
   with self.subTest(change=change),self.assertRaises(ValueError):request_for(s,s['entities'][0]['uuid'],1100,'capture-test')
 def test_villagers_babies_named_mobs_and_injured_targets_are_not_capture_candidates(self):
  for change in ({'type':'minecraft:villager'},{'is_baby':True},{'has_custom_name':True},{'health':19}):
   s=self.state();s['entities'][0].update(change)
   with self.subTest(change=change),self.assertRaises(ValueError):request_for(s,s['entities'][0]['uuid'],1100,'capture-test')
 def test_high_hover_uses_only_the_exact_fresh_completed_native_scan(self):
  s=self.state();mob=s['entities'].pop();s['last_request']='scan'
  scan=dict(id='scan',phase='done',world_session='world',time=1000,
            scan_total_cells=10,scan_cells_read=10,scan_entities=[mob])
  self.assertEqual(mob['uuid'],request_for(s,mob['uuid'],1100,'capture-test',scan)['entity_uuid'])
  for change in ({'id':'other'},{'world_session':'old'},{'time':0},{'scan_cells_read':9},{'unloaded_chunks':1}):
   with self.subTest(change=change),self.assertRaises(ValueError):request_for(s,mob['uuid'],1100,'capture-test',{**scan,**change})

if __name__=='__main__':unittest.main()
