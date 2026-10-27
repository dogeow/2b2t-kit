import unittest
from unittest.mock import patch
from types import SimpleNamespace
from village_occupied_bed import wake_claim,wake_assigned

class OccupiedBedTest(unittest.TestCase):
 def fixture(self):
  s=dict(world_session='w',time=1000,scan_cells_read=20,scan_total_cells=20,scan_entities=[dict(uuid='own',id=7,type='minecraft:villager',alive=True,health=20,is_baby=False,pos=[5.5,64.5625,10.5])],blocks=[dict(pos=[5,64,z],state='Block{minecraft:white_bed}[facing=north,occupied=true,part='+part+']')for z,part in [(10,'head'),(11,'foot')]])
  f=dict(world_session='w',time=1050,villagers=[dict(uuid='own',entity_id=7,is_baby=False,sleeping=True,passenger=False,no_ai_client_flag=False,sleeping_pos=[5.,64.,10.])]);slot=dict(occupant_uuid='own',bed_head=[5,64,10],bed_foot=[5,64,11]);return s,f,slot
 def test_actual_occupied_bed_authorizes_without_a_clock_assumption(self):
  s,f,slot=self.fixture();s['day_time']=6000;self.assertEqual(wake_claim(s,f,slot,'minecraft:overworld')['foot'],slot['bed_foot'])
 def test_wrong_dimension_or_assigned_bed_is_rejected(self):
  for mode in ['nether','other_bed','wrong_world','unoccupied','other_sleeper']:
   s,f,slot=self.fixture();dimension='minecraft:overworld'
   if mode=='nether':dimension='minecraft:the_nether'
   elif mode=='other_bed':slot['bed_head']=[7,64,10]
   elif mode=='wrong_world':f['world_session']='other'
   elif mode=='unoccupied':s['blocks'][0]['state']=s['blocks'][0]['state'].replace('occupied=true','occupied=false')
   else:f['villagers'].append(dict(uuid='other',sleeping=True,sleeping_pos=[5,64,10]))
   with self.subTest(mode=mode),self.assertRaises(ValueError):wake_claim(s,f,slot,dimension)
 def test_visible_head_uses_same_bound_resident_and_does_not_use_the_foot(self):
  scene,flags,slot=self.fixture();state={'dimension':'minecraft:overworld','time':1100};calls=[]
  awake={**flags,'villagers':[{**flags['villagers'][0],'sleeping':False}]}
  builder=SimpleNamespace(root=None,book={},check=lambda:state,scan=lambda *_:(scene,{}),save=lambda:None)
  builder.n=lambda op,**kw:(calls.append((op,kw)) or {'id':'ordinary-bed-use'})
  with patch('village_occupied_bed.read',side_effect=[flags,flags,awake]):
   self.assertTrue(wake_assigned(builder,slot,bed_part='head'))
  uses=[v for op,v in calls if op=='interact'];self.assertEqual(1,len(uses))
  self.assertEqual(slot['bed_head'],uses[0]['pos']);self.assertIn('part=head',uses[0]['expected_state'])
  self.assertFalse(builder.book['occupied_bed_wakes'][0]['pending'])
 def test_invalid_bed_part_sends_no_input(self):
  with self.assertRaises(ValueError):wake_assigned(None,{},bed_part='other')
 def test_visible_side_of_own_occupied_foot_keeps_the_same_binding(self):
  scene,flags,slot=self.fixture();state={'dimension':'minecraft:overworld','time':1100};calls=[]
  awake={**flags,'villagers':[{**flags['villagers'][0],'sleeping':False}]}
  builder=SimpleNamespace(root=None,book={},check=lambda:state,scan=lambda *_:(scene,{}),save=lambda:None)
  builder.n=lambda op,**kw:(calls.append((op,kw)) or {'id':'side-bed-use'})
  with patch('village_occupied_bed.read',side_effect=[flags,flags,awake]):
   self.assertTrue(wake_assigned(builder,slot,bed_part='foot',bed_face='south'))
  uses=[v for op,v in calls if op=='interact'];self.assertEqual(1,len(uses))
  self.assertEqual(slot['bed_foot'],uses[0]['pos']);self.assertEqual('south',uses[0]['face'])
  self.assertIn('part=foot',uses[0]['expected_state'])
 def test_invalid_face_sends_no_input(self):
  for face in ('diagonal','down',None):
   with self.subTest(face=face),self.assertRaises(ValueError):wake_assigned(None,{},bed_face=face)
if __name__=='__main__':unittest.main()
