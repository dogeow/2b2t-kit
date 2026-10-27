import copy,json,tempfile,unittest
from pathlib import Path
from recovery_confirmation import request_for,connection_request_for
from safety_interlock import explicit_chat_acknowledgement,require_unlocked

class RecoveryTests(unittest.TestCase):
 def test_recovery_connection_keeps_incident_and_requires_idle_title(self):
  s={'explicit_recovery_connection_protocol':1,'connected':False,'screen':'TitleScreen','account_name':'p','safety_hold':{'active':True,'time':100},'world_session':'w','control_revision':2}
  args={'user_reference':'human','user_text':'你操作','hold_time':100,'confirmation_recorded_at':120,'now_ms':200}
  r=connection_request_for(s,'s','p',**args);self.assertTrue(r['recovery_only']);self.assertEqual(100,r['confirmed_hold_time'])
  for change in [{'connected':True},{'screen':'ChatScreen'},{'pending_scan':{}},{'account_name':'other'},{'manual_movement':True},{'explicit_recovery_connection_protocol':True},{'safety_hold':{'active':True,'time':101}}]:
   with self.subTest(change=change),self.assertRaises(RuntimeError):connection_request_for({**s,**change},'s','p',**args)
 def state(self):return {'explicit_recovery_confirmation_protocol':1,'connected':True,'health':20,'food':20,'screen':'PauseScreen','manual_movement':False,'safety_hold':{'active':True},'server':'s','dimension':'minecraft:overworld','pos':[1,100,2],'world_session':'w','control_revision':3,'menu':{'type':'InventoryMenu','cursor':{'count':0},'slots':[{'count':0}for _ in range(5)]}}
 def request(self,state=None,**changes):
  values={'user_reference':'direct-user-message','user_text':'已恢复，你操作','hold_time':100,'confirmation_recorded_at':120,'now_ms':200};values.update(changes);return request_for(self.state()if state is None else state,**values)
 def test_direct_confirmation_is_one_scoped_native_request_not_a_file_unlock(self):
  r=self.request();self.assertEqual('confirm_recovery',r['op']);self.assertEqual('human_chat',r['authorization_channel']);self.assertTrue(r['confirmed_by_user']);self.assertEqual(3,r['expected_revision']);self.assertEqual(100,r['confirmed_hold_time'])
  state=self.state();state['screen']='InventoryScreen';self.assertEqual('confirm_recovery',self.request(state)['op'])
  state['menu']['cursor']['count']=1
  with self.assertRaisesRegex(RuntimeError,'carried'):self.request(state)
  state['menu']['cursor']['count']=0;state['menu']['slots'][1]['count']=1
  with self.assertRaisesRegex(RuntimeError,'drafts'):self.request(state)
 def test_no_default_or_old_automatic_confirmation(self):
  for changes in [{'user_reference':''},{'user_text':''},{'hold_time':True},{'confirmation_recorded_at':99},{'confirmation_recorded_at':201}]:
   with self.subTest(changes=changes),self.assertRaises(ValueError):self.request(**changes)
 def test_offline_low_health_unknown_api_manual_and_foreign_ui_stay_blocked(self):
  for changes in [{'connected':False},{'health':10.7},{'health':float('nan')},{'health':float('inf')},{'screen':'ChatScreen'},{'manual_movement':True},{'supervision_lease':{'id':'other'}},{'pending_scan':{}},{'explicit_recovery_confirmation_protocol':True}]:
   with self.subTest(changes=changes),self.assertRaises(RuntimeError):self.request({**self.state(),**changes})
 def test_native_chat_acknowledgement_is_accepted_only_for_its_incident(self):
  native={**self.request(),'active':False,'cleared_by':'explicit_chat','cleared_at':200}
  self.assertTrue(explicit_chat_acknowledgement(native,100));self.assertFalse(explicit_chat_acknowledgement(native,101))
  for key,value in [('confirmed_by_user','true'),('authorization_channel','goal'),('confirmation_recorded_at',True),('confirmed_hold_time',99)]:
   self.assertFalse(explicit_chat_acknowledgement({**native,key:value},100))
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);(root/'safety-hold.json').write_text(json.dumps(native));(root/'material-health-hold.json').write_text('{"active":true,"time":100}');require_unlocked(root,{'safety_hold':{'active':False}})
   (root/'material-health-hold.json').write_text('{"active":true,"time":101}')
   with self.assertRaises(RuntimeError):require_unlocked(root)
