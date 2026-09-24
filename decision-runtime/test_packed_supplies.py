import unittest
from packed_supplies import contents,choose_box
class PackedTest(unittest.TestCase):
 def test_selects_exact_enchanted_book_in_mixed_box(self):
  from packed_supplies import matching_source
  rows=[{'slot':0,'item':'minecraft:enchanted_book','count':1,
         'stored_enchantments':[{'id':'minecraft:efficiency','level':5}]},
        {'slot':1,'item':'minecraft:enchanted_book','count':1,
         'stored_enchantments':[{'id':'minecraft:silk_touch','level':1}]}]
  required={'minecraft:enchanted_book':{'minecraft:silk_touch':1}}
  self.assertEqual(matching_source(rows,'minecraft:enchanted_book',required)['slot'],1)
  self.assertIsNone(matching_source(rows,'minecraft:enchanted_book',
                    {'minecraft:enchanted_book':{'minecraft:respiration':3}}))
 def test_skips_nearly_broken_fishing_rods(self):
  from packed_supplies import matching_source
  rows=[{'slot':0,'item':'minecraft:fishing_rod','count':1,'durability':6},
        {'slot':1,'item':'minecraft:fishing_rod','count':1,'durability':47}]
  self.assertEqual(matching_source(rows,'minecraft:fishing_rod',
                    minimum_durability={'minecraft:fishing_rod':24})['slot'],1)
 def test_duplicate_stacks_are_summed_not_overwritten(self):
  self.assertEqual(contents([{'item':'minecraft:paper','count':64},{'item':'minecraft:paper','count':16}]),{'minecraft:paper':80})
 def test_only_observed_useful_box_is_selected_and_existing_stock_is_subtracted(self):
  rows=[{'slot':0,'item':'minecraft:shulker_box','count':1,'contains':[{'item':'minecraft:paper','count':64}]},{'slot':3,'item':'minecraft:shulker_box','count':1,'contains':[{'item':'minecraft:diamond','count':32}]}]
  choice=choose_box(rows,{'minecraft:paper':30,'minecraft:diamond':2},{'minecraft:paper':30})
  self.assertEqual(choice,(2,3,{'minecraft:diamond':2}))
 def test_empty_or_unobserved_box_is_not_guessed(self):
  self.assertIsNone(choose_box([{'slot':1,'item':'minecraft:shulker_box','count':1}],{'minecraft:diamond':2},{}))

class DropIdentityTest(unittest.TestCase):
 def drop(self,uid='new'):
  return {'uuid':uid,'type':'minecraft:item','pos':[1.5,64,2.5],'stack':{'item':'minecraft:shulker_box','count':1,'contains':[]}}
 def test_new_drop_with_hidden_contents_is_collected_before_content_check(self):
  from packed_supplies import owned_drop
  e=self.drop();self.assertEqual(owned_drop([e],'minecraft:shulker_box',[1,64,2],set()),e)
 def test_existing_or_ambiguous_boxes_are_not_claimed(self):
  from packed_supplies import owned_drop
  self.assertIsNone(owned_drop([self.drop('old')],'minecraft:shulker_box',[1,64,2],{'old'}))
  with self.assertRaises(RuntimeError):owned_drop([self.drop('one'),self.drop('two')],'minecraft:shulker_box',[1,64,2],set())
 def test_inventory_contents_must_match_after_pickup(self):
  from packed_supplies import carried_box
  s={'inventory':[{'item':'minecraft:shulker_box','count':1,'contains':[]}]}
  self.assertIsNone(carried_box(s,'minecraft:shulker_box',{'minecraft:book':2}))

class ReturnWorkflowTest(unittest.TestCase):
 def test_hidden_drop_contents_are_checked_after_pickup_and_box_returns_to_same_slot(self):
  import tempfile,json,copy
  from pathlib import Path
  from unittest.mock import patch
  from packed_supplies import recover_and_return
  remaining={'minecraft:book':2};box={'item':'minecraft:shulker_box','count':1,'contains':[{'item':'minecraft:book','count':2}]}
  with tempfile.TemporaryDirectory() as d:
   class Client:
    def __init__(self):
     self.out=Path(d);self.resource_cleanup={};self.moves=[]
     self.s={'screen':'','inventory':[],'entities':[{'uuid':'fresh-box','type':'minecraft:item','pos':[1.5,64,2.5],'stack':{'item':'minecraft:shulker_box','count':1,'contains':[]}}],'menu':{'id':0,'type':'InventoryMenu','cursor':{'item':'minecraft:air','count':0}}}
    def status(self):return copy.deepcopy(self.s)
    def checked(self,op,**kw):
     self.moves.append((op,kw));m=self.s['menu']
     if op=='close_menu':self.s['screen']='';return
     cell=m['slots'][kw['slot']];assert cell['item']==kw['expected_item'] and cell['count']==kw['expected_count']
     value={k:v for k,v in cell.items() if k!='slot'};cell.update(m['cursor']);m['cursor']=value
   c=Client();journal=c.out/'box.json';record={'slot':1,'item':'minecraft:shulker_box','initial_counts':{'minecraft:book':3},'remaining_counts':remaining,'temporary_position':[1,64,2],'stage':'broken','before_drop_uuids':[]}
   def pickup(client,drop,observation=None):
    self.assertEqual(drop['uuid'],'fresh-box');client.s['inventory']=[dict(box,slot=9)];client.s['entities']=[];return True
   def open_ender(client,*args):
    slots=[{'slot':i,'item':'minecraft:air','count':0} for i in range(63)];slots[27]=dict(box,slot=27)
    client.s['menu']={'id':10,'type':'ChestMenu','cursor':{'item':'minecraft:air','count':0},'slots':slots};client.s['screen']='ContainerScreen';return client.status()
   with patch('packed_supplies.collect_drop',side_effect=pickup),patch('packed_supplies.open_box',side_effect=open_ender):recover_and_return(c,record,[4,64,5],journal)
   self.assertEqual(record['stage'],'returned');self.assertEqual(record['drop_uuid'],'fresh-box')
   self.assertEqual(c.s['menu']['slots'][1]['contains'],box['contains']);self.assertEqual(c.s['menu']['cursor']['count'],0)
   self.assertEqual([kw['slot'] for op,kw in c.moves if op=='slot_click'],[27,1])

if __name__=='__main__':unittest.main()
