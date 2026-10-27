from unittest import TestCase
from copy import deepcopy
from bow_repair import validate_preview

def bow(durability,**ench):
 return {'item':'minecraft:bow','count':1,'max_durability':384,'durability':durability,'enchantments':[{'id':k,'level':v}for k,v in ench.items()]}

class BowRepairPreviewTests(TestCase):
 def setUp(self):
  self.left=bow(9,infinity=1,punch=1);self.right=bow(384)
  self.state={'experience_level':36,'menu':{'type':'AnvilMenu','cursor':{'count':0},'anvil_cost':3,'anvil_result_may_pickup':True,'anvil_too_expensive':False,'slots':[deepcopy(self.left),deepcopy(self.right),bow(384,infinity=1,punch=1)]}}
 def test_actual_full_durability_preview_preserves_infinity_and_punch(self):
  out,cost=validate_preview(self.state,self.left,self.right,minimum_durability=384)
  self.assertEqual(out['durability'],384);self.assertEqual(cost,3)
 def test_lost_enchantment_or_partial_repair_cannot_be_taken(self):
  for result in [bow(384,infinity=1),bow(125,infinity=1,punch=1)]:
   self.state['menu']['slots'][2]=result
   with self.assertRaises(ValueError):validate_preview(self.state,self.left,self.right,minimum_durability=384)
 def test_level_cost_or_unconfirmed_server_result_cannot_be_taken(self):
  for key,value in [('anvil_cost',40),('anvil_cost',9),('anvil_result_may_pickup',False)]:
   s=deepcopy(self.state);s['menu'][key]=value
   with self.assertRaises(ValueError):validate_preview(s,self.left,self.right,minimum_durability=384)
 def test_different_carried_bow_or_cursor_prevents_output_click(self):
  for modify in [lambda s:s['menu']['slots'][1].update(durability=70),lambda s:s['menu']['cursor'].update(count=1)]:
   s=deepcopy(self.state);modify(s)
   with self.assertRaises(ValueError):validate_preview(s,self.left,self.right,minimum_durability=384)
 def test_unbreaking_upgrade_can_preserve_full_durability(self):
  left=bow(384,infinity=1,punch=1);right=bow(70,unbreaking=1);s=deepcopy(self.state)
  s['menu']['slots']=[left,right,bow(384,infinity=1,punch=1,unbreaking=1)]
  self.assertEqual(validate_preview(s,left,right,minimum_durability=384)[0]['durability'],384)
 def test_spare_warehouse_bow_cannot_introduce_vanishing_curse(self):
  right=bow(36,vanishing_curse=1,power=4);s=deepcopy(self.state)
  s['menu']['slots']=[self.left,right,bow(384,infinity=1,punch=1,vanishing_curse=1,power=4)]
  with self.assertRaisesRegex(ValueError,'curse'):
   validate_preview(s,self.left,right,minimum_durability=384)
