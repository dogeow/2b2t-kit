import copy,unittest
from villager_station_identity import claimant,stable_claimant,StationNotReady
class StationIdentityTests(unittest.TestCase):
 def frame(self,time=1000):
  return {'world_session':'w','connected':True,'health':20,'manual_movement':False,'screen':'','guard_busy':False,'time':time,'supervision_lease':{'id':'l','kind':'materials','world_session':'w','job_session':'j','revision':1},'loaded_villagers':{'villagers':[{'uuid':'a','health':20,'is_baby':False,'pos':[.5,64,.5],'villager':{'profession':'minecraft:librarian'}},{'uuid':'b','health':20,'is_baby':False,'pos':[2.5,64,.5],'villager':{'profession':'minecraft:none'}}]}}
 def test_stable_live_identity_is_selected_without_mutating_frame(self):
  frames=[self.frame(),self.frame(1250)];before=copy.deepcopy(frames);r=stable_claimant(frames,{'a','b'},[0,64,0],'w');self.assertEqual('a',r['uuid']);r['pos'][0]=99;self.assertEqual(before,frames)
 def test_former_claimant_is_not_reused_after_profession_transfer(self):
  s=self.frame();s['loaded_villagers']['villagers'][0]['villager']['profession']='minecraft:none';s['loaded_villagers']['villagers'][1]['villager']['profession']='minecraft:librarian';s['loaded_villagers']['villagers'][1]['pos']=[1.5,64,.5];self.assertEqual('b',claimant(s,{'a','b'},[0,64,0],'w')['uuid'])
 def test_ambiguous_missing_or_nonadult_pair_is_never_selected(self):
  for change in ('two','none','missing','baby','hurt'):
   s=self.frame();v=s['loaded_villagers']['villagers']
   if change=='two':v[1]['villager']['profession']='minecraft:librarian'
   if change=='none':v[0]['villager']['profession']='minecraft:none'
   if change=='missing':v.pop()
   if change=='baby':v[1]['is_baby']=True
   if change=='hurt':v[1]['health']=19
   with self.assertRaises(StationNotReady):claimant(s,{'a','b'},[0,64,0],'w')
 def test_distance_margin_stops_quote_before_native_1p9_limit(self):
  s=self.frame();s['loaded_villagers']['villagers'][0]['pos']=[2,64,.5]
  with self.assertRaises(StationNotReady):claimant(s,{'a','b'},[0,64,0],'w')
 def test_changed_owner_stale_frame_and_movement_cannot_look_stable(self):
  for mode in ('lease','time','movement','identity'):
   a=self.frame();b=self.frame(1250)
   if mode=='lease':b['supervision_lease']['id']='other'
   if mode=='time':b['time']=1000
   if mode=='movement':b['loaded_villagers']['villagers'][0]['pos'][0]+=.2
   if mode=='identity':b['loaded_villagers']['villagers'].reverse();b['loaded_villagers']['villagers'][0].update(uuid='a')
   with self.assertRaises(StationNotReady):stable_claimant([a,b],{'a','b'},[0,64,0],'w')
 def test_foreign_world_manual_takeover_or_ui_prevents_selection(self):
  for change in ({'world_session':'other'},{'manual_movement':True},{'screen':'InventoryScreen'},{'connected':False}):
   s=self.frame();s.update(change)
   with self.assertRaises(StationNotReady):claimant(s,{'a','b'},[0,64,0],'w')

 def test_explicit_prepared_pose_margin_remains_below_native_ceiling(self):
  a=self.frame();b=self.frame(1250)
  for s in (a,b):s['loaded_villagers']['villagers'][0]['pos']=[2,64,.5]
  self.assertEqual('a',stable_claimant([a,b],{'a','b'},[0,64,0],'w',margin=1.65)['uuid'])
  with self.assertRaises(StationNotReady):claimant(a,{'a','b'},[0,64,0],'w',margin=1.9)

class AwakeStationIdentityTests(unittest.TestCase):
 frame=StationIdentityTests.frame
 def test_sleeping_pair_is_never_repositioned_or_selected(self):
  from unittest.mock import patch
  from villager_station_identity import awake_claimant
  frame={'villagers':[{'uuid':'a','sleeping':True},{'uuid':'b','sleeping':False}]}
  with patch('villager_events.read',return_value=frame),self.assertRaisesRegex(StationNotReady,'sleeping'):
   awake_claimant('.',self.frame(),{'a','b'},[0,64,0],'w')
 def test_missing_stale_or_incomplete_sleep_frame_refuses_selection(self):
  from unittest.mock import patch
  from villager_station_identity import awake_claimant
  for frame in (None,{'villagers':[{'uuid':'a','sleeping':False}]}):
   with patch('villager_events.read',return_value=frame),self.assertRaises(StationNotReady):
    awake_claimant('.',self.frame(),{'a','b'},[0,64,0],'w')
 def test_current_awake_flags_allow_the_same_guarded_identity_selector(self):
  from unittest.mock import patch
  from villager_station_identity import awake_claimant
  frame={'villagers':[{'uuid':'a','sleeping':False},{'uuid':'b','sleeping':False}]}
  with patch('villager_events.read',return_value=frame):
   self.assertEqual('a',awake_claimant('.',self.frame(),{'a','b'},[0,64,0],'w')['uuid'])
