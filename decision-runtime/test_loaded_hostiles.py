import unittest,tempfile,json
from pathlib import Path
from copy import deepcopy
from loaded_hostiles import valid,read,SCOPE
class LoadedHostilesTests(unittest.TestCase):
 def setUp(self):
  self.state={'connected':True,'time':2000,'world_session':'world','server':'s','dimension':'d','player_uuid':'p','runtime_version':'1.8.20','runtime_generation':3}
  self.row={'id':1,'uuid':'00000000-0000-0000-0000-000000000001','type':'minecraft:zombie','alive':True,'hostile':True,'is_baby':False,'has_custom_name':False,'visible':False,'on_fire':False,'in_water':False,'health':20,'pos':[1,2,3],'bounds':{'min':[.7,2,2.7],'max':[1.3,3.95,3.3]},'main_hand':'minecraft:air','off_hand':'minecraft:air','head_item':'minecraft:air'}
  self.frame=dict(self.state,protocol=1,scope=SCOPE,world_entered_at=1000,truncated=False,equipment_scope='current_client_entity_equipment_not_predicted_drops',hostiles=[self.row])
 def test_fresh_frame_and_positive_truncated_frame_can_be_read(self):
  self.assertTrue(valid(self.frame,self.state,2000));self.frame['truncated']=True;self.assertTrue(valid(self.frame,self.state,2000))
 def test_stale_future_and_replaced_runtime_are_rejected(self):
  self.assertFalse(valid(self.frame,self.state,3001));self.assertFalse(valid(self.frame,self.state,1999))
  for key,value in [('runtime_generation',4),('world_session','other'),('runtime_version','1.8.19'),('player_uuid','other')]:
   frame=deepcopy(self.frame);frame[key]=value;self.assertFalse(valid(frame,self.state,2000))
 def test_unknown_equipment_duplicate_identity_and_bad_bounds_are_rejected(self):
  self.frame['hostiles'].append(deepcopy(self.row));self.assertFalse(valid(self.frame,self.state,2000));self.frame['hostiles'].pop()
  del self.row['main_hand'];self.assertFalse(valid(self.frame,self.state,2000));self.row['main_hand']='minecraft:air';self.row['bounds']['max'][0]=.7;self.assertFalse(valid(self.frame,self.state,2000))
 def test_file_reader_rejects_wrong_scope_and_missing_file(self):
  with tempfile.TemporaryDirectory()as tmp:
   self.assertIsNone(read(tmp,self.state,2000));p=Path(tmp)/'loaded-hostile-survey.json';p.write_text(json.dumps(self.frame));self.assertIsNotNone(read(tmp,self.state,2000));self.frame['scope']='cached_world';p.write_text(json.dumps(self.frame));self.assertIsNone(read(tmp,self.state,2000))
if __name__=='__main__':unittest.main()
