import copy,unittest
from workstation_reclaim import replacement_ready
class Tests(unittest.TestCase):
 def fixture(self):
  actors=[{'uuid':u,'health':20,'is_baby':False,'pos':p,'villager':{'profession':'minecraft:none'}}for u,p in [('in',[.5,64,9.5]),('out',[.5,64,18.5])]];flags=[{'uuid':u,'client_health':20,'is_baby':False,'passenger':False,'sleeping':False}for u in ['in','out']];return [{'time':200,'world_session':'w','health':20,'connected':True,'manual_movement':False,'loaded_villagers':{'villagers':actors}},{'time':190,'world_session':'w','villagers':flags},{'time':180,'world_session':'w','uuid':'out','native_sequence':7,'server_ack_sequence':7},'in','out',[0,64,10]]
 def test_both_unemployed_far_outside_and_near_awake_inside(self):self.assertTrue(replacement_ready(*self.fixture()))
 def test_retained_old_profession_prevents_immediate_replacement(self):
  a=self.fixture();a[0]['loaded_villagers']['villagers'][1]['villager']['profession']='minecraft:librarian';self.assertFalse(replacement_ready(*a))
 def test_outside_must_actually_move_away(self):
  a=self.fixture();a[0]['loaded_villagers']['villagers'][1]['pos']=[.5,64,12];self.assertFalse(replacement_ready(*a))
 def test_sleeping_or_distant_intended_resident_not_admitted(self):
  for far in [True,False]:
   a=self.fixture()
   if far:a[0]['loaded_villagers']['villagers'][0]['pos']=[.5,64,7]
   else:a[1]['villagers'][0]['sleeping']=True
   self.assertFalse(replacement_ready(*a))
 def test_wrong_world_uuid_or_missing_native_ack_refused(self):
  for key,value in [('world_session','other'),('uuid','someone'),('native_sequence',0),('native_sequence',True),('server_ack_sequence',6),('time',201)]:
   a=self.fixture();a[2][key]=value;self.assertFalse(replacement_ready(*a))
 def test_manual_takeover_health_or_stale_frame_refused(self):
  for part,key,value in [(0,'manual_movement',True),(0,'health',19),(0,'connected',False),(1,'time',-1000),(1,'world_session','other')]:
   a=self.fixture();a[part][key]=value;self.assertFalse(replacement_ready(*a))
 def test_unloaded_outside_is_not_assumed_far_away(self):
  a=self.fixture();a[0]['loaded_villagers']['villagers'].pop();self.assertFalse(replacement_ready(*a))
if __name__=='__main__':unittest.main()
