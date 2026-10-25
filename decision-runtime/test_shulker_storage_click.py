import copy,unittest
from shulker_storage_click import permitted
class ShulkerClickTests(unittest.TestCase):
 def fixture(self):
  air={'item':'minecraft:air','count':0};rows=[dict(air)for _ in range(63)];rows[19]={'item':'minecraft:shulker_box','count':1}
  s=dict(connected=True,health=20,world_session='w',manual_movement=False,interface_paused=False,
         inventory_interface_paused=False,control_revision=5,screen='ContainerScreen',
         menu=dict(id=4,type='ChestMenu',cursor=dict(air),slots=rows),inventory=[dict(slot=i,**air)for i in range(36)],
         supervision_lease=dict(kind='materials',job_session='t',world_session='w',revision=5))
  p=dict(menu_id=4,slot=19,expected_item='minecraft:shulker_box',expected_count=1,
         expected_cursor='minecraft:air',expected_cursor_count=0,kind='quick_move',button=0);return s,p
 def test_one_box_can_quick_move_into_reserved_player_space(self):
  s,p=self.fixture();self.assertTrue(permitted(s,p,'w','t'))
 def test_inventory_box_can_be_picked_up_without_swapping_any_storage_slot(self):
  s,p=self.fixture();s['menu']['slots'][32]=dict(s['menu']['slots'][19]);p.update(slot=32,kind='pickup')
  self.assertTrue(permitted(s,p,'w','t'));p['kind']='quick_move';self.assertFalse(permitted(s,p,'w','t'))
 def test_invalid_protocol_types_are_not_numeric_aliases(self):
  for key in ['menu_id','slot','expected_count','expected_cursor_count','button']:
   s,p=self.fixture();p[key]=True;self.assertFalse(permitted(s,p,'w','t'))
  s,p=self.fixture();self.assertFalse(permitted(s,p,'','t'));self.assertFalse(permitted(s,p,'w',''))
 def test_return_requires_empty_destination_and_exact_box_cursor(self):
  s,p=self.fixture();s['menu']['slots'][19]={'item':'minecraft:air','count':0};s['menu']['cursor']={'item':'minecraft:shulker_box','count':1};p.update(kind='pickup',expected_item='minecraft:air',expected_count=0,expected_cursor='minecraft:shulker_box',expected_cursor_count=1)
  self.assertTrue(permitted(s,p,'w','t'));s['menu']['slots'][19]={'item':'minecraft:diamond','count':1};self.assertFalse(permitted(s,p,'w','t'))
 def test_mismatches_drop_targets_nonboxes_and_foreign_scope_are_rejected(self):
  for mode in ['menu','slot','item','count','cursor','button','world','task','health','manual','pause','space','extra','drop']:
   with self.subTest(mode=mode):
    s,p=self.fixture()
    if mode=='menu':p['menu_id']=9
    if mode=='slot':p['slot']=-999
    if mode=='item':s['menu']['slots'][19]['item']='minecraft:enchanted_book';p['expected_item']='minecraft:enchanted_book'
    if mode=='count':s['menu']['slots'][19]['count']=2;p['expected_count']=2
    if mode=='cursor':s['menu']['cursor']={'item':'minecraft:diamond','count':1}
    if mode=='button':p['button']=1
    if mode=='world':s['world_session']='other'
    if mode=='task':s['supervision_lease']['job_session']='other'
    if mode=='health':s['health']=19
    if mode=='manual':s['manual_movement']=True
    if mode=='pause':s['interface_paused']=True
    if mode=='space':s['inventory']=[{'slot':i,'item':'minecraft:stone','count':64}for i in range(36)]
    if mode=='extra':p['drop_all']=True
    if mode=='drop':p['kind']='throw'
    self.assertFalse(permitted(s,p,'w','t'))
if __name__=='__main__':unittest.main()
