import unittest,copy
from trade_workspace_observation import observable,DETAIL
class WorkspaceObservationTests(unittest.TestCase):
 def fixture(self):
  c=dict(action='merchant_buy_one',index=0);err=dict(error=DETAIL,type='RuntimeError',native_inflight=None,unconfirmed_native_request=None,last_request='s');s=dict(last_request='s',world_session='w',connected=True,health=20,manual_movement=False,screen='MerchantScreen',pos=[0,64,0],control_revision=3,supervision_lease=dict(kind='materials',job_session='t',world_session='w'),menu=dict(type='MerchantMenu',id=4,cursor=dict(count=0),merchant=dict(owned=True,owner_task='t',villager_uuid='v',opening_request_id='o',offers=[{}])));e=dict(request_id='s',op='snapshot',phase='done',world_session='w',params=dict(task_session='t'),position_before=[0,64,0],position_after=[0,64,0],inventory_delta={},revision_before=3,revision_after=3);return c,err,s,e
 def test_only_unstarted_capacity_check_is_observed(self):self.assertTrue(observable(*self.fixture(),'w','t',journal_exists=False,unknown_exists=False))
 def test_exact_normal_opening_can_be_the_last_event_but_not_another_entity(self):
  c,err,s,e=self.fixture();s['menu']['merchant']['opening_request_id']='s';e.update(op='interact_entity',params=dict(task_session='t',expected_uuid='v',expected_hand='minecraft:netherite_sword'))
  self.assertTrue(observable(c,err,s,e,'w','t',journal_exists=False,unknown_exists=False))
  e['params']['expected_uuid']='other';self.assertFalse(observable(c,err,s,e,'w','t',journal_exists=False,unknown_exists=False))
 def test_purchase_journal_unknown_input_cursor_foreign_menu_or_effects_stay_fenced(self):
  for bad in ['journal','unknown','cursor','foreign','effect','selection','manual']:
   c,err,s,e=self.fixture()
   if bad=='cursor':s['menu']['cursor']['count']=1
   if bad=='foreign':s['menu']['merchant']['owner_task']='other'
   if bad=='effect':e['inventory_delta']={'minecraft:emerald':1}
   if bad=='selection':e['op']='merchant_select_trade'
   if bad=='manual':s['manual_movement']=True
   with self.subTest(bad=bad):self.assertFalse(observable(c,err,s,e,'w','t',journal_exists=bad=='journal',unknown_exists=bad=='unknown'))
if __name__=='__main__':unittest.main()
