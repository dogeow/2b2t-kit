import copy,unittest
from food_approach_observation import observable
class FoodApproachStopTests(unittest.TestCase):
 def fixture(self):
  p={'target':[2,64,2],'arrival':.1,'restore_flight':False,'seconds':20};c={'action':'feed_village_founders','quotas':{'v':3}};err={'error':'time limit reached; inspect progress before resuming','native_inflight':None,'unconfirmed_native_request':None,'last_request':'walk'};b={'world_session':'w','required':{'v':3},'complete':False,'receipts':[],'delivered':{'v':0},'pending_food':None,'pending':{'op':'walk','params':p}};e={'op':'walk','phase':'waiting','detail':err['error'],'world_session':'w','params':{**p,'task_session':'t'},'request_id':'walk','inventory_delta':{},'health_before':20,'health_after':20,'position_after':[2,64,4],'revision_after':3};s={'last_request':'walk','health':20,'pos':[2,64,4],'control_revision':3,'inventory':[{'item':'minecraft:bread','count':15,'slot':0}],'screen':'','menu':{'type':'InventoryMenu','id':0,'cursor':{'count':0}},'manual_movement':False,'movement_keys':{}};return c,err,b,e,s
 def test_stopped_walk_with_no_food_input_can_be_observed(self):self.assertTrue(observable(*self.fixture(),'w','t',15))
 def test_queued_food_unknown_input_or_moving_inventory_cannot_be_released(self):
  for mode in ['food','receipt','quantity','unknown','keys','target','world']:
   c,err,b,e,s=copy.deepcopy(self.fixture())
   if mode=='food':b['pending_food']={'target':'v'}
   elif mode=='receipt':b['receipts']=[{'amount':1}]
   elif mode=='quantity':s['inventory'][0]['count']=14
   elif mode=='unknown':err['native_inflight']={'id':'q'}
   elif mode=='keys':s['movement_keys']['forward']=True
   elif mode=='target':e['params']['target']=[5,64,2]
   else:e['world_session']='other'
   with self.subTest(mode=mode):self.assertFalse(observable(c,err,b,e,s,'w','t',15))
if __name__=='__main__':unittest.main()
