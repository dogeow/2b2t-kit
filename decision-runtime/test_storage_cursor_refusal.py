import unittest,copy
from storage_cursor_refusal import return_plan
class StorageCursorRefusalTests(unittest.TestCase):
 def fixture(self):
  slots=[dict(slot=i,item='minecraft:air',count=0)for i in range(63)]
  slots[0].update(item='minecraft:sugar_cane',count=64)
  state=dict(world_session='w',health=20,manual_movement=False,control_revision=3,pos=[1,2,3],last_request='refused',menu=dict(id=25,type='ChestMenu',slots=slots,cursor=dict(item='minecraft:sugar_cane',count=64,max_stack=64)))
  base=dict(world_session='w',op='slot_click',revision_after=3,position_after=[1,2,3],inventory_delta={})
  a=dict(base,phase='done',request_id='pickup',params=dict(task_session='t',menu_id=25,slot=0,kind='pickup',button=0,expected_item='minecraft:sugar_cane',expected_count=64,expected_cursor='minecraft:air',expected_cursor_count=0))
  b=dict(base,phase='error',request_id='refused',detail='Slot item changed',params=dict(task_session='t',menu_id=25,slot=0,kind='pickup',button=1,expected_item='minecraft:air',expected_count=0,expected_cursor='minecraft:sugar_cane',expected_cursor_count=64))
  command=dict(action='transfer',item='minecraft:sugar_cane',target=63)
  error=dict(error='Slot item changed',type='RuntimeError',native_inflight=None,unconfirmed_native_request=None,last_request='refused')
  return command,error,state,[a,b]
 def test_refilled_source_returns_whole_cursor_to_empty_player_slot(self):
  c,e,s,v=self.fixture();p=return_plan(c,e,s,v,'w','t');self.assertEqual(27,p['slot']);self.assertEqual(64,p['expected_cursor_count']);self.assertNotEqual(p['slot'],v[-1]['params']['slot'])
 def test_unknown_pickup_or_changed_context_never_authorizes_input(self):
  for key in ['world','cursor','menu','revision','unknown','unconfirmed','pickup','last','item','target_slot','inventory','missing_marker']:
   c,e,s,v=self.fixture()
   if key=='world':s['world_session']='other'
   if key=='cursor':s['menu']['cursor']['count']=63
   if key=='menu':s['menu']['id']=26
   if key=='revision':s['control_revision']=4
   if key=='unknown':e['native_inflight']='pending'
   if key=='unconfirmed':e['unconfirmed_native_request']='pending'
   if key=='pickup':v[0]['phase']='waiting'
   if key=='last':s['last_request']='other'
   if key=='item':c['item']='minecraft:diamond'
   if key=='target_slot':v[-1]['params']['slot']=2
   if key=='inventory':v[0]['inventory_delta']={'minecraft:sugar_cane':64}
   if key=='missing_marker':e.pop('native_inflight')
   with self.subTest(key=key):self.assertIsNone(return_plan(c,e,s,v,'w','t'))
 def test_full_player_inventory_does_not_close_or_drop_cursor(self):
  c,e,s,v=self.fixture()
  for r in s['menu']['slots'][27:]:r.update(item='minecraft:stone',count=64)
  self.assertIsNone(return_plan(c,e,s,v,'w','t'))

 def test_positive_full_pickup_with_refilled_source_can_store_cursor_without_replaying_pickup(self):
  c,e,s,v=self.fixture();v=v[:1];v[0]['time']=10;s['time']=16000;s['last_request']='pickup';e.update(last_request='pickup',error='Inventory acknowledgement missing at storage_pickup; no action replay')
  self.assertEqual(27,return_plan(c,e,s,v,'w','t')['slot'])
  for changed in ['empty_source','cursor','too_soon','unknown']:
   ss=copy.deepcopy(s);ee=copy.deepcopy(e)
   if changed=='empty_source':ss['menu']['slots'][0]['count']=0
   if changed=='cursor':ss['menu']['cursor']['count']=63
   if changed=='too_soon':ss['time']=10001
   if changed=='unknown':ee['unconfirmed_native_request']='pending'
   with self.subTest(changed=changed):self.assertIsNone(return_plan(c,ee,ss,v,'w','t'))
