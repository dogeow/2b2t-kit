import copy,unittest
from owned_sign_ui import may_close

class OwnedSignUITests(unittest.TestCase):
 def fixture(self):
  scope={'world':'w','task':'t','key':'k','target':[1,2,3],'item':'minecraft:spruce_sign','expected':'Block{minecraft:spruce_wall_sign}[facing=east,waterlogged=false]','before_count':1,'start_revision':7}
  state={'connected':True,'world_session':'w','control_revision':8,'manual_movement':False,'screen':'SignEditScreen','health':20,'food':20,'guard_armed':True,'guard_pve_only':True,
   'supervision_lease':{'kind':'materials','job_session':'t','world_session':'w','revision':8},
   'menu':{'type':'InventoryMenu','id':0,'cursor':{'count':0},'slots':[{'count':0}for _ in range(5)]},'inventory':[],
   'projection_batch':{'active':True,'count':1,'placement_key':'k','task_session':'t'},
   'professional_printer':{'owned':True,'last_proposal':{'target':'1, 2, 3','final_target':scope['expected'],'hand':'minecraft:spruce_sign','interaction_seen':True}}}
  return state,scope
 def test_exact_new_owned_sign_with_no_input_since_before_print_is_closeable(self):
  s,g=self.fixture();self.assertTrue(may_close(s,g,40,5))
 def test_later_typing_is_preserved_even_after_it_becomes_idle(self):
  s,g=self.fixture();self.assertFalse(may_close(s,g,29,5));self.assertFalse(may_close(s,g,40,50));self.assertFalse(may_close(s,g,None,5));self.assertFalse(may_close(s,g,float('nan'),5))
 def test_other_screens_control_takeover_and_health_are_never_closed(self):
  for k,v in [('screen','ChatScreen'),('screen','InventoryScreen'),('manual_movement',True),('world_session','other'),('control_revision',9),('guard_busy',True),('health',18.9),('food',17),('safety_hold',{'active':True})]:
   s,g=self.fixture();s[k]=v;self.assertFalse(may_close(s,g,40,5),k)
 def test_wrong_proposal_batch_or_item_balance_cannot_authorize_closing_a_draft(self):
  for k,v in [('target','9, 9, 9'),('final_target','Block{minecraft:air}'),('hand','minecraft:oak_sign'),('interaction_seen',False)]:
   s,g=self.fixture();s['professional_printer']['last_proposal'][k]=v;self.assertFalse(may_close(s,g,40,5),k)
  s,g=self.fixture();s['projection_batch']['count']=2;self.assertFalse(may_close(s,g,40,5))
  s,g=self.fixture();s['inventory']=[{'slot':8,'item':'minecraft:spruce_sign','count':1}];self.assertFalse(may_close(s,g,40,5))
 def test_cursor_crafting_and_foreign_lease_are_preserved(self):
  s,g=self.fixture();s['menu']['cursor']['count']=1;self.assertFalse(may_close(s,g,40,5))
  s,g=self.fixture();s['menu']['slots'][2]['count']=1;self.assertFalse(may_close(s,g,40,5))
  s,g=self.fixture();s['supervision_lease']['job_session']='other';self.assertFalse(may_close(s,g,40,5))
if __name__=='__main__':unittest.main()
