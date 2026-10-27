import copy,unittest
from uncredited_food_observation import settled,DETAIL
class UncreditedFoodObservationTests(unittest.TestCase):
 def fixture(self):
  c={'action':'feed_village_founders','quotas':{'v':3}};err={'error':DETAIL,'native_inflight':None,'unconfirmed_native_request':None,'last_request':'retreat'};item={'uuid':'drop','type':'minecraft:item','stack':{'item':'minecraft:bread','count':1}};b={'world_session':'w','complete':False,'pending':None,'required':{'v':3},'delivered':{'v':0},'receipts':[],'pending_food':{'target':'v','native_request':'drop_request','before_bread':19,'seen_drop':{'world_session':'w','runtime_generation':1,'entity':item}}};e={'request_id':'drop_request','op':'villager_bread_drop','phase':'done','world_session':'w','params':{'task_session':'t','expected_uuid':'v'},'health_before':20,'health_after':20,'inventory_delta':{'minecraft:bread':-1},'revision_before':2,'revision_after':3,'position_after':[0,64,0]};walk={**e,'request_id':'retreat','op':'navigate','inventory_delta':{},'revision_before':3,'revision_after':4,'position_after':[3,64,0]};s={'runtime_generation':1,'inventory':[{'item':'minecraft:bread','count':18,'slot':0}],'entities':[],'last_request':'retreat','control_revision':4,'pos':[3,64,0],'health':20,'screen':'','menu':{'type':'InventoryMenu','id':0,'cursor':{'count':0}},'manual_movement':False,'movement_keys':{}};return c,err,b,[e,walk],s
 def test_known_debit_can_be_observed_without_assigning_collector_credit(self):self.assertTrue(settled(*self.fixture(),'w','t'))
 def test_exact_live_food_only_allows_explicit_recovery_observation(self):
  c,err,b,events,s=self.fixture();b['pending_food']['seen_drop']['entity']['id']=11;s['entities']=[copy.deepcopy(b['pending_food']['seen_drop']['entity'])]
  self.assertFalse(settled(c,err,b,events,s,'w','t'))
  self.assertTrue(settled(c,err,b,events,s,'w','t',recoverable=True))
  for key,value in [('id',12),('type','minecraft:cow')]:
   changed=copy.deepcopy(s);changed['entities'][0][key]=value
   self.assertFalse(settled(c,err,b,events,changed,'w','t',recoverable=True))
 def test_unknown_input_item_still_recoverable_or_any_later_quantity_change_is_retained(self):
  for mode in ['unknown','still_ground','quantity','later_drop','world','revision','cursor','credit']:
   c,err,b,events,s=copy.deepcopy(self.fixture())
   if mode=='unknown':err['native_inflight']={'id':'pending'}
   elif mode=='still_ground':s['entities']=[b['pending_food']['seen_drop']['entity']]
   elif mode=='quantity':s['inventory'][0]['count']=17
   elif mode=='later_drop':events[1]['op']='villager_bread_drop'
   elif mode=='world':events[0]['world_session']='other'
   elif mode=='revision':s['control_revision']=5
   elif mode=='cursor':s['menu']['cursor']['count']=1
   else:b['delivered']['v']=1
   with self.subTest(mode=mode):self.assertFalse(settled(c,err,b,events,s,'w','t'))
if __name__=='__main__':unittest.main()
