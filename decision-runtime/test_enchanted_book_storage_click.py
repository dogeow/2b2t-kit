import copy,unittest
from enchanted_book_storage_click import equipment_deposit_signature, equipment_signature, signature
class BookClickTests(unittest.TestCase):
 def test_exact_book_only(self):
  rows=[{'slot':i,'item':'minecraft:air','count':0} for i in range(63)];rows[6]={'slot':6,'item':'minecraft:enchanted_book','count':1,'stored_enchantments':[{'id':'minecraft:thorns','level':3},{'id':'minecraft:mending','level':1}]}
  state={'connected':True,'world_session':'w','health':20,'manual_movement':False,'control_revision':2,'screen':'ContainerScreen','supervision_lease':{'kind':'materials','job_session':'t','world_session':'w','revision':2},'menu':{'type':'ChestMenu','id':7,'cursor':{'item':'minecraft:air','count':0},'slots':rows}}
  params={'menu_id':7,'slot':6,'kind':'quick_move','expected_item':'minecraft:enchanted_book','expected_count':1,'expected_cursor':'minecraft:air','expected_cursor_count':0}; expected={'minecraft:thorns':3,'minecraft:mending':1}
  self.assertIsNotNone(signature(state,params,'w','t',expected))
  for change in ('wrong_book','extra','full','cursor','lease','held','slot','health'):
   s,p=copy.deepcopy((state,params))
   if change=='wrong_book':s['menu']['slots'][6]['stored_enchantments'][0]['level']=2
   if change=='extra':s['menu']['slots'][6]['stored_enchantments'].append({'id':'minecraft:fire_aspect','level':2})
   if change=='full':
    for row in s['menu']['slots'][-36:]:row.update(item='minecraft:stone',count=64)
   if change=='cursor':s['menu']['cursor']['count']=1
   if change=='lease':s['supervision_lease']['job_session']='other'
   if change=='held':s['manual_movement']=True
   if change=='slot':p['slot']=7
   if change=='health':s['health']=19
   with self.subTest(change=change):self.assertIsNone(signature(s,p,'w','t',expected))
  bow={'slot':6,'item':'minecraft:bow','count':1,'durability':384,'max_durability':384,
       'enchantments':[{'id':'minecraft:power','level':5}]}
  state['menu']['slots'][6]=copy.deepcopy(bow);params['expected_item']='minecraft:bow'
  self.assertIsNotNone(equipment_signature(state,params,'w','t',bow))
  for change in ({'durability':383},{'enchantments':[{'id':'minecraft:power','level':4}]}):
   changed=copy.deepcopy(state);changed['menu']['slots'][6].update(change)
   self.assertIsNone(equipment_signature(changed,params,'w','t',bow))
  self.assertIsNone(equipment_signature(state,{**params,'slot':42},'w','t',bow))
 def test_deposit_requires_exact_item_box_and_empty_slot(self):
  rows=[{'slot':i,'item':'minecraft:air','count':0} for i in range(63)]
  rows[0]={'slot':0,'item':'minecraft:diamond','count':3}
  bow={'slot':35,'item':'minecraft:bow','count':1,'durability':384,'max_durability':384,'enchantments':[{'id':'minecraft:power','level':5}]}
  rows[35]=copy.deepcopy(bow)
  state={'connected':True,'world_session':'w','health':20,'manual_movement':False,'control_revision':2,'screen':'ShulkerBoxScreen','supervision_lease':{'kind':'materials','job_session':'t','world_session':'w','revision':2},'menu':{'type':'ShulkerBoxMenu','id':7,'cursor':{'item':'minecraft:air','count':0},'slots':rows}}
  params={'menu_id':7,'slot':35,'kind':'quick_move','expected_item':'minecraft:bow','expected_count':1,'expected_cursor':'minecraft:air','expected_cursor_count':0}
  expected={'item':bow,'contents':[copy.deepcopy(rows[0])]}
  self.assertIsNotNone(equipment_deposit_signature(state,params,'w','t',expected))
  for change in ('item','contents','full','cursor','lease','movement','slot'):
   s,p=copy.deepcopy((state,params))
   if change=='item':s['menu']['slots'][35]['enchantments'][0]['level']=4
   if change=='contents':s['menu']['slots'][0]['count']=2
   if change=='full':
    for row in s['menu']['slots'][1:27]:row.update(item='minecraft:stone',count=64)
   if change=='cursor':s['menu']['cursor']['count']=1
   if change=='lease':s['supervision_lease']['job_session']='other'
   if change=='movement':s['manual_movement']=True
   if change=='slot':p['slot']=0
   with self.subTest(change=change):self.assertIsNone(equipment_deposit_signature(s,p,'w','t',expected))
if __name__=='__main__':unittest.main()
