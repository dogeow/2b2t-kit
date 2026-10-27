import unittest
from resident_potion import request_for
class PotionRequestTest(unittest.TestCase):
 def fixture(self):
  s=dict(runtime_version='1.8.30',health=20,screen='',manual_movement=False,guard_armed=True,guard_pve_only=True,guard_busy=False,phase='done',connected=True,world_session='w',control_revision=2,time=1000,selected_slot=5,hand=dict(item='minecraft:splash_potion',count=1),player_uuid='p',pos=[1,64,2],supervision_lease=dict(kind='materials',world_session='w',id='l',job_session='t',revision=2),loaded_villagers={'villagers':[dict(uuid='v',is_baby=False,health=11.39,pos=[1,64,3])]})
  p=dict(menu_id=0,menu_type='InventoryMenu',complete=True,observed_at=1000,potions=[dict(slot=41,nonempty_child_index=-1,item='minecraft:splash_potion',count=1,potion_contents={'potion':'minecraft:healing'})]);return s,p
 def run_request(self,s,p):return request_for(s,p,'v','minecraft:healing',1000,'00000000-0000-4000-8000-000000000001')
 def test_exact_held_components_and_patient(self):s,p=self.fixture();self.assertEqual(11.39,self.run_request(s,p)['expected_health'])
 def test_wrong_slot_effect_and_custom_effects_refused(self):
  for value in [{'potion':'minecraft:poison'},{'potion':'minecraft:healing','custom_effects':[]}]:
   s,p=self.fixture();p['potions'][0]['potion_contents']=value
   with self.assertRaises(ValueError):self.run_request(s,p)
  s,p=self.fixture();s['selected_slot']=6
  with self.assertRaises(ValueError):self.run_request(s,p)
 def test_stale_or_foreign_frame_refused(self):
  s,p=self.fixture();p['observed_at']=-1
  with self.assertRaises(ValueError):self.run_request(s,p)
  s,p=self.fixture();s['manual_movement']=True
  with self.assertRaises(ValueError):self.run_request(s,p)
