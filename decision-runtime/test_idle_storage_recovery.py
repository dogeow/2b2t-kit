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
 def test_same_item_and_count_with_changed_components_is_activity(self):
  a=self.fixture();a['menu']['slots'][0]['components']={'enchantments':{'minecraft:protection':4}}
  b=deepcopy(a);b['menu']['slots'][0]['components']['enchantments']['minecraft:protection']=3
  self.assertFalse(may_recover_ui(a,b,30,authorized=True))
 def test_no_safety_or_critical_health_exception(self):
  for key,value in [('safety_hold',{'active':True}),('health_recovery_hold',True),('health',18.9),('material_task',{'occupied':True})]:
   s=self.fixture();s[key]=value;self.assertFalse(may_recover_ui(s,s,30,authorized=True))
 def test_foreground_game_needs_real_hardware_idle(self):
  s=self.fixture();s['window_active']=True;self.assertFalse(may_recover_ui(s,s,30,authorized=True));self.assertFalse(may_recover_ui(s,s,30,authorized=True,hardware_idle=1));self.assertTrue(may_recover_ui(s,s,30,authorized=True,hardware_idle=30))

 def test_personal_crafting_grid_items_must_not_be_returned_or_dropped(self):
  s=self.fixture();s['screen']='InventoryScreen';s['menu']['type']='InventoryMenu';s['menu']['slots']=[{'slot':i,'item':'minecraft:air','count':0}for i in range(5)];s['menu']['slots'][1]={'slot':1,'item':'minecraft:diamond','count':1};self.assertFalse(may_recover_ui(s,s,30,authorized=True))

class IdleStorageCloseFlowTest(TestCase):
 def state(self):
  return IdleStorageRecoveryTest().fixture()
 def test_stable_storage_closes_once(self):
  from idle_storage_recovery import close_stable_storage
  s=self.state();t=[0];calls=[]
  class Client:
   def __init__(self,*args,**kw):calls.append(('init',kw))
   def checked(self,op):
    calls.append(('op',op));s['screen']='';return {'phase':'done'}
  self.assertTrue(close_stable_storage('/tmp','/tmp','example',observe=lambda:deepcopy(s),clock=lambda:t[0],sleep=lambda n:t.__setitem__(0,t[0]+n),hardware=lambda:None,client_type=Client))
  self.assertEqual(1,sum(op=='op' for op,_ in calls))
 def test_changed_slot_never_dispatches(self):
  from idle_storage_recovery import close_stable_storage
  s=self.state();t=[0];calls=[]
  def sleep(n):t[0]+=n;s['menu']['slots'][0]['count']-=1
  self.assertFalse(close_stable_storage('/tmp','/tmp','example',observe=lambda:deepcopy(s),clock=lambda:t[0],sleep=sleep,hardware=lambda:None,client_type=lambda *a,**k:calls.append('sent')))
  self.assertEqual([],calls)

class IdleStorageClientFenceTest(TestCase):
 def test_idle_close_client_refuses_other_actions_and_replay(self):
  from material_client import Client,Handoff
  c=Client.__new__(Client);c.idle_storage_proof={'before':{}}
  with self.assertRaises(Handoff):c.request('slot_click')
  c._idle_storage_attempted=True
  with self.assertRaises(Handoff):c.request('close_menu')
