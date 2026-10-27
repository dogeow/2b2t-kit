import copy,unittest
from sleeping_merchant_observation import observable,DETAIL
class SleepingMerchantObservationTests(unittest.TestCase):
 def test_bridged_wait_is_read_only_and_requires_exact_original_opening_and_adult(self):
  from sleeping_merchant_observation import observable_bridged
  c,err,o,e,s,f=self.fixture();c={'action':'native','op':'interact_entity','params':{k:v for k,v in e['params'].items()if k!='task_session'}}
  s['world_session']='w';f['villagers'][0]['entity_id']=4;r={'id':'n','phase':'waiting','detail':DETAIL,'world_session':'w'}
  self.assertTrue(observable_bridged(c,o,e,r,s,f,'w','t'));f['villagers'][0]['sleeping']=False
  self.assertTrue(observable_bridged(c,o,e,r,s,f,'w','t'))
  f['villagers'][0]['sleeping']=None;self.assertFalse(observable_bridged(c,o,e,r,s,f,'w','t'))
  f['villagers'][0]['sleeping']=True;s['screen']='MerchantScreen';self.assertFalse(observable_bridged(c,o,e,r,s,f,'w','t'))
 def fixture(self):
  c={'action':'merchant_open','actor':{'uuid':'v','id':4}};err={'error':DETAIL,'native_inflight':None,'unconfirmed_native_request':None,'last_request':'n'};o={'uuid':'v','world_session':'w','pending':True,'request_id':'n'};s={'last_request':'n','hand':{'item':'minecraft:netherite_sword'},'pos':[0,65,0],'control_revision':8,'health':20,'screen':'','menu':{'type':'InventoryMenu','id':0,'cursor':{'count':0}},'manual_movement':False,'movement_keys':{}};e={'request_id':'n','op':'interact_entity','phase':'waiting','detail':DETAIL,'world_session':'w','params':{'task_session':'t','expected_uuid':'v','entity_id':4,'expected_hand':'minecraft:netherite_sword'},'inventory_delta':{},'position_before':s['pos'],'position_after':s['pos'],'revision_before':8,'revision_after':8,'health_before':20,'health_after':20};f={'villagers':[{'uuid':'v','sleeping':True,'client_health':20,'is_baby':False,'passenger':False}]};return c,err,o,e,s,f
 def test_sleeping_known_idle_terminal_only_qualifies_for_observation(self):self.assertTrue(observable(*self.fixture(),'w','t'))
 def test_trader_may_naturally_wake_before_read_only_observation(self):
  c,err,o,e,s,f=self.fixture();f['villagers'][0]['sleeping']=False;self.assertTrue(observable(c,err,o,e,s,f,'w','t'))
 def test_unknown_inventory_changed_or_late_open_menu_is_never_released(self):
  for mode in ['unknown','inventory','menu','invalid_flag','uuid','revision','keys','hand','world']:
   with self.subTest(mode=mode):
    c,err,o,e,s,f=copy.deepcopy(self.fixture())
    if mode=='unknown':err['native_inflight']={'id':'n'}
    if mode=='inventory':e['inventory_delta']={'minecraft:emerald':-1}
    if mode=='menu':s['screen']='MerchantScreen'
    if mode=='invalid_flag':f['villagers'][0]['sleeping']=None
    if mode=='uuid':e['params']['expected_uuid']='other'
    if mode=='revision':s['control_revision']=9
    if mode=='keys':s['movement_keys']['forward']=True
    if mode=='hand':s['hand']['item']='minecraft:name_tag'
    if mode=='world':o['world_session']='other'
    self.assertFalse(observable(c,err,o,e,s,f,'w','t'))
if __name__=='__main__':unittest.main()
