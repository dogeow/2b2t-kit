import copy,unittest
from unittest.mock import patch
from manual_idle_resume import may_close,hardware_idle_seconds
class ManualIdleResumeTests(unittest.TestCase):
 def fixture(self):
  s=dict(connected=True,health=20,world_session='w',manual_movement=False,interface_paused=True,control_revision=4,screen='InventoryScreen',menu=dict(type='InventoryMenu',id=0,cursor=dict(count=0),slots=[dict(count=0)for i in range(46)]),supervision_lease=dict(kind='materials',world_session='w',job_session='t',revision=4))
  return s,dict(authorized=True,idle_seconds=30)
 def test_requires_explicit_authority_and_real_thirty_second_idle(self):
  s,p=self.fixture();self.assertTrue(may_close(s,p,30,'w','t'))
  for idle in [None,-1,0,29.99,float('nan'),float('inf')]:self.assertFalse(may_close(s,p,idle,'w','t'))
  self.assertFalse(may_close(s,{},60,'w','t'));p['authorized']=False;self.assertFalse(may_close(s,p,60,'w','t'))
 def test_cursor_grid_drafts_safety_manual_and_world_changes_remain_protected(self):
  for mode in ['cursor','ingredient','chat','unsafe','dead','manual','world','owner','revision','not_paused','held_key','lease_kind','missing_grid']:
   with self.subTest(mode=mode):
    s,p=self.fixture()
    if mode=='cursor':s['menu']['cursor']['count']=1
    if mode=='ingredient':s['menu']['slots'][1]['count']=1
    if mode=='chat':s['screen']='ChatScreen'
    if mode=='unsafe':s['safety_hold']={'active':True}
    if mode=='dead':s['health']=0
    if mode=='manual':s['manual_movement']=True
    if mode=='world':s['world_session']='different'
    if mode=='owner':s['supervision_lease']['job_session']='other'
    if mode=='revision':s['control_revision']=5
    if mode=='not_paused':s['interface_paused']=False
    if mode=='held_key':s['movement_keys']={'forward':True}
    if mode=='lease_kind':s['supervision_lease']['kind']='parking'
    if mode=='missing_grid':s['menu']['slots']=[]
    self.assertFalse(may_close(s,p,60,'w','t'))
 def test_retained_operation_can_resume_after_its_interface_pause(self):
  s,p=self.fixture();s['native_material_busy']=True;self.assertTrue(may_close(s,p,60,'w','t'))
 def test_storage_contents_are_preserved_while_paid_merchant_input_is_not_closed(self):
  s,p=self.fixture();s['screen']='ContainerScreen';s['menu']['type']='ChestMenu';s['menu']['slots'][0]['count']=64;self.assertTrue(may_close(s,p,60,'w','t'))
  s['screen']='MerchantScreen';s['menu']['type']='MerchantMenu';self.assertFalse(may_close(s,p,60,'w','t'))
 def test_hardware_idle_uses_shortest_reported_device_and_fails_closed(self):
  with patch('manual_idle_resume.sys.platform','darwin'),patch('manual_idle_resume.subprocess.run') as run:
   run.return_value.stdout='"HIDIdleTime" = 31000000000\n"HIDIdleTime" = 1000000000';self.assertEqual(hardware_idle_seconds(),1)
   run.return_value.stdout='missing';self.assertIsNone(hardware_idle_seconds())
if __name__=='__main__':unittest.main()
