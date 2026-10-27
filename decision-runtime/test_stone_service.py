import unittest
from stone_service import recover
class Stub:
 def __init__(self,free=True,ack=True,full_after_select=False,kind='minecraft:cobblestone'):self.kind=kind;self.book={};self.calls=[];self.free=free;self.ack=ack;self.after=full_after_select;self.count=0
 def save(self):pass
 def scan(self,*a):self.calls.append('scan');return {},{(1,64,2):{'state':'Block{'+self.kind+'}','solid':True,'fluid':False,'block_entity':False}}
 def check(self):return {'inventory':[{'slot':i,'item':self.kind if i==0 and self.count else'minecraft:dirt','count':self.count if i==0 and self.count else(0 if i==35 and self.free else 64),'max_stack':64}for i in range(36)]}
 def n(self,op,**params):
  self.calls.append(op)
  if op=='select_item'and self.after:self.free=False
  if op=='mine_block':self.count=1;return {'id':'native','server_confirmed':self.ack,'native_sequence':7,'server_ack_sequence':7}
class Tests(unittest.TestCase):
 def test_protected_target_sends_nothing(self):
  b=Stub()
  with self.assertRaises(ValueError):recover(b,[1,64,2],'up',[[1,64,2]])
  self.assertEqual([],b.calls)
 def test_full_inventory_refuses_before_select_or_mine(self):
  b=Stub(free=False)
  with self.assertRaises(RuntimeError):recover(b,[1,64,2],'up')
  self.assertEqual(['scan'],b.calls)
 def test_capacity_rechecked_after_tool_selection(self):
  b=Stub(full_after_select=True)
  with self.assertRaises(RuntimeError):recover(b,[1,64,2],'up')
  self.assertNotIn('mine_block',b.calls)
 def test_no_ack_retains_pending_without_collection(self):
  b=Stub(ack=False)
  with self.assertRaises(RuntimeError):recover(b,[1,64,2],'up')
  self.assertTrue(b.book['stone_service'][0]['pending']);self.assertEqual(['scan','select_item','mine_block'],b.calls)
 def test_actual_pickup_and_ack_required_before_completion(self):
  b=Stub();r=recover(b,[1,64,2],'up',roof=True);self.assertFalse(r['pending']);self.assertEqual(1,r['after']);self.assertEqual([[1,64,2]],b.book['open_roofs'])
 def test_pending_original_not_replayed(self):
  b=Stub();b.book['stone_service']=[{'pending':True}]
  with self.assertRaises(RuntimeError):recover(b,[1,64,2],'up')
  self.assertEqual([],b.calls)
if __name__=='__main__':unittest.main()

class DeepslateTests(unittest.TestCase):
 def test_explicit_plain_cobbled_deepslate_uses_pickaxe_and_exact_drop(self):
  b=Stub(kind='minecraft:cobbled_deepslate');r=recover(b,[1,64,2],'south',item='minecraft:cobbled_deepslate');self.assertFalse(r['pending']);self.assertEqual('minecraft:cobbled_deepslate',r['item']);self.assertEqual(1,r['after'])
 def test_container_cannot_be_admitted_as_service_stone(self):
  b=Stub()
  with self.assertRaises(ValueError):recover(b,[1,64,2],'up',item='minecraft:chest')
  self.assertEqual([],b.calls)
