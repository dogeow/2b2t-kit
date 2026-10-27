from copy import deepcopy
import unittest
from librarian_quote_observation import unwanted_quote_observation
class Tests(unittest.TestCase):
 def fixture(self):
  m={'protocol':1,'owned':True,'owner_task':'task','villager_uuid':'source','level':1,'trader_xp':0,'opening_request_id':'server-opening','observation_scope':'current_server_received_merchant_menu_not_trade_completion','offers':[{'uses':0,'result':{'item':'minecraft:enchanted_book','count':1,'stored_enchantments':[{'id':'minecraft:infinity','level':1}]}}]}
  s={'connected':True,'health':20,'manual_movement':False,'world_session':'world','supervision_lease':{'world_session':'world','job_session':'task'},'menu':{'type':'MerchantMenu','material_owned':True,'merchant':deepcopy(m),'cursor':{'count':0},'slots':[{'count':0}for _ in range(3)]}};return m,s
 def observe(self,m,s,targets=None):return unwanted_quote_observation(m,targets or {'minecraft:efficiency':5},s,expected_uuid='source',expected_world='world')
 def test_existing_unwanted_quote_is_an_observation_with_no_payment_or_lock_credit(self):
  m,s=self.fixture();r=self.observe(m,s);self.assertTrue(r['no_native_trade_action_sent']);self.assertFalse(r['locked']);self.assertFalse(r['goal_complete']);self.assertEqual('server-opening',r['quote']['opening_request_id']);r['quote']['offers'].clear();self.assertTrue(m['offers'])
 def test_any_wanted_maximum_preserves_normal_trade_path_even_if_out_of_stock(self):
  for stock in (False,True):
   m,s=self.fixture();m['offers'][0]['out_of_stock']=stock;s['menu']['merchant']=deepcopy(m);self.assertIsNone(self.observe(m,s,{'minecraft:infinity':1}))
 def test_changed_world_owner_or_actual_quote_cannot_shortcut_the_worker(self):
  for mode in ('world','owner','quote','uuid','scope'):
   m,s=self.fixture()
   if mode=='world':s['world_session']='foreign'
   elif mode=='owner':s['supervision_lease']['job_session']='foreign'
   elif mode=='quote':s['menu']['merchant']['offers']=[]
   elif mode=='uuid':m['villager_uuid']='other';s['menu']['merchant']=deepcopy(m)
   else:m['observation_scope']='prediction';s['menu']['merchant']=deepcopy(m)
   self.assertIsNone(self.observe(m,s))
 def test_payment_cursor_used_offer_or_paid_villager_never_gets_unwanted_shortcut(self):
  for mode in ('cursor','payment','used','paid','unowned','manual','health'):
   m,s=self.fixture()
   if mode=='cursor':s['menu']['cursor']['count']=1
   elif mode=='payment':s['menu']['slots'][0]['count']=1
   elif mode=='used':m['offers'][0]['uses']=1;s['menu']['merchant']=deepcopy(m)
   elif mode=='paid':m['trader_xp']=1;s['menu']['merchant']=deepcopy(m)
   elif mode=='unowned':s['menu']['material_owned']=False
   elif mode=='manual':s['manual_movement']=True
   else:s['health']=19
   self.assertIsNone(self.observe(m,s))
if __name__=='__main__':unittest.main()
