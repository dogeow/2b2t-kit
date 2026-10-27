import copy,unittest
from full_transfer_reconciliation import unstarted_full_deposit
class UnstartedDepositTests(unittest.TestCase):
 def fixture(self):
  c=dict(action='transfer',item='minecraft:iron_ingot',target=32,deposit=True)
  err=dict(error='Destination has no space for minecraft:iron_ingot',type='RuntimeError',native_inflight=None,unconfirmed_native_request=None,last_request='last')
  prior=dict(action='transfer',item='minecraft:emerald',target=0,deposit=True)
  scope=dict(type='ChestMenu',id=1,world_session='w',task_session='t',lease_id='lease',control_revision=4)
  receipt=dict(actual_held=0,owned_menu=scope)
  inv=[dict(slot=0,item='minecraft:iron_ingot',count=64)]
  slots=[dict(item='minecraft:stone',count=64,max_stack=64)for i in range(54)]+[dict(item='minecraft:air',count=0)for i in range(36)]
  s=dict(world_session='w',health=20,manual_movement=False,phase='done',screen='ContainerScreen',pos=[1,2,3],control_revision=4,last_request='last',inventory=inv,menu=dict(type='ChestMenu',id=1,cursor=dict(count=0),slots=slots),supervision_lease=dict(id='lease',kind='materials',job_session='t',world_session='w'))
  event=dict(request_id='last',world_session='w',phase='done',op='slot_click',params=dict(task_session='t',expected_item='minecraft:emerald',kind='quick_move'),revision_after=4,position_after=[1,2,3])
  return c,err,prior,receipt,s,event
 def test_no_first_click_when_last_native_receipt_is_prior_other_item(self):
  result=unstarted_full_deposit(*self.fixture(),'w','t');self.assertEqual(result['confirmed_moved'],0);self.assertTrue(result['original_transfer_not_replayed'])
 def test_rejects_unknown_clicks_cursor_space_changed_scope_and_prior_receipt(self):
  for mode in ['unknown','clicked_iron','free_slot','partial_stack','cursor','world','revision','manual','prior_held','last_request','lease','position']:
   with self.subTest(mode=mode):
    c,e,p,r,s,v=self.fixture()
    if mode=='unknown':e['unconfirmed_native_request']={'id':'pending'}
    if mode=='clicked_iron':v['params']['expected_item']='minecraft:iron_ingot'
    if mode=='free_slot':s['menu']['slots'][0]['count']=0
    if mode=='partial_stack':s['menu']['slots'][0]=dict(item='minecraft:iron_ingot',count=63,max_stack=64)
    if mode=='cursor':s['menu']['cursor']['count']=1
    if mode=='world':s['world_session']='different'
    if mode=='revision':s['control_revision']=5
    if mode=='manual':s['manual_movement']=True
    if mode=='prior_held':r['actual_held']=1
    if mode=='last_request':v['request_id']='other'
    if mode=='lease':s['supervision_lease']['id']='other'
    if mode=='position':s['pos']=[2,2,3]
    self.assertIsNone(unstarted_full_deposit(c,e,p,r,s,v,'w','t'))
if __name__=='__main__':unittest.main()
