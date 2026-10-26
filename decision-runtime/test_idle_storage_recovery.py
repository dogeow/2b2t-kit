from copy import deepcopy
from unittest import TestCase
from idle_storage_recovery import may_recover_ui
class IdleStorageRecoveryTest(TestCase):
 def fixture(self):return {'world_session':'world','control_revision':4,'connected':True,'manual_movement':False,'window_active':False,'health':19.687,'food':17,'pos':[1.,69.,2.],'recent_hurt_at':1,'screen':'ShulkerBoxScreen','menu':{'id':18,'type':'ShulkerBoxMenu','cursor':{'item':'minecraft:air','count':0},'slots':[{'slot':0,'item':'minecraft:stone','count':64}]}}
 def test_stable_inactive_storage_can_close_only_for_authorized_recovery(self):
  s=self.fixture();self.assertTrue(may_recover_ui(s,s,30,authorized=True));self.assertFalse(may_recover_ui(s,s,30));self.assertFalse(may_recover_ui(s,s,29,authorized=True))
 def test_cursor_item_or_transient_editor_is_never_discarded(self):
  for screen in ['ChatScreen','CraftingScreen','AnvilScreen','MerchantScreen']:
   s=self.fixture();s['screen']=screen;self.assertFalse(may_recover_ui(s,s,30,authorized=True))
  s=self.fixture();s['menu']['cursor']['count']=1;self.assertFalse(may_recover_ui(s,s,30,authorized=True))
 def test_new_damage_world_control_or_slot_change_blocks_recovery_admission(self):
  for key,value in [('health',19.2),('world_session','other'),('control_revision',5),('recent_hurt_at',2),('pos',[2.,69.,2.]),('manual_movement',True),('supervision_lease',{'id':'other'}),('under_water',True),('guard_busy',True)]:
   a=self.fixture();b=deepcopy(a);b[key]=value;self.assertFalse(may_recover_ui(a,b,30,authorized=True),key)
  a=self.fixture();b=deepcopy(a);b['menu']['slots'][0]['count']=63;self.assertFalse(may_recover_ui(a,b,30,authorized=True))
 def test_no_safety_or_critical_health_exception(self):
  for key,value in [('safety_hold',{'active':True}),('health_recovery_hold',True),('health',18.9),('material_task',{'occupied':True})]:
   s=self.fixture();s[key]=value;self.assertFalse(may_recover_ui(s,s,30,authorized=True))
 def test_foreground_game_needs_real_hardware_idle(self):
  s=self.fixture();s['window_active']=True;self.assertFalse(may_recover_ui(s,s,30,authorized=True));self.assertFalse(may_recover_ui(s,s,30,authorized=True,hardware_idle=1));self.assertTrue(may_recover_ui(s,s,30,authorized=True,hardware_idle=30))

 def test_personal_crafting_grid_items_must_not_be_returned_or_dropped(self):
  s=self.fixture();s['screen']='InventoryScreen';s['menu']['type']='InventoryMenu';s['menu']['slots']=[{'slot':i,'item':'minecraft:air','count':0}for i in range(5)];s['menu']['slots'][1]={'slot':1,'item':'minecraft:diamond','count':1};self.assertFalse(may_recover_ui(s,s,30,authorized=True))
