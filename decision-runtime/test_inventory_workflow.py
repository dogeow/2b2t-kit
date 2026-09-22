import unittest
from unittest.mock import patch
from inventory_workflow import store_spares

class Tests(unittest.TestCase):
 def client(self):
  class C:
   pos=None;count=3;closed=0;transfers=0
   def status(self):return {'inventory':[{'slot':1,'item':'minecraft:diamond_pickaxe','count':1}]+[{'slot':9+i,'item':'minecraft:diamond_pickaxe','count':1} for i in range(self.count-1)]}
   def transfer(self,item,n,deposit):
    self.transfers+=1
    if self.pos==[1,2,3]:raise RuntimeError('Depot has no space for '+item)
    self.count=n;return n
   def checked(self,op):assert op=='close_menu';self.closed+=1
  return C()
 def test_full_first_depot_uses_next_and_keeps_active_tool(self):
  c=self.client()
  with patch('inventory_workflow.visit',side_effect=lambda c,p:setattr(c,'pos',p)):
   result=store_spares(c,[[1,2,3],[4,5,6]],{'minecraft:diamond_pickaxe':1})
  self.assertEqual(c.count,1);self.assertEqual(c.closed,2);self.assertEqual(result['minecraft:diamond_pickaxe'],[{'count':2,'pos':[4,5,6]}])
 def test_noncapacity_errors_stop_instead_of_clicking_another_depot(self):
  c=self.client()
  def fail(*a,**kw):raise RuntimeError('Control changed')
  c.transfer=fail
  with patch('inventory_workflow.visit') as visit:
   with self.assertRaises(RuntimeError):store_spares(c,[[1,2,3],[4,5,6]],{'minecraft:diamond_pickaxe':1})
  self.assertEqual(visit.call_count,1);self.assertEqual(c.closed,1)
 def test_tool_not_in_hotbar_is_not_deposited(self):
  c=self.client();c.status=lambda:{'inventory':[{'slot':9,'item':'minecraft:diamond_pickaxe','count':2}]}
  with patch('inventory_workflow.visit'):
   with self.assertRaises(RuntimeError):store_spares(c,[[1,2,3]],{'minecraft:diamond_pickaxe':1})
  self.assertEqual(c.transfers,0)
if __name__=='__main__':unittest.main()
