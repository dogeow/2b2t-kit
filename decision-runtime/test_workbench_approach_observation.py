import copy,unittest
from workbench_approach_observation import observable,DETAIL
class WorkbenchApproachObservationTests(unittest.TestCase):
 def fixture(self):
  c={'action':'open_workbench','pos':[1,65,2]};err={'error':DETAIL,'native_inflight':None,'unconfirmed_native_request':None,'last_request':'r'};e={'op':'approach_block','phase':'waiting','detail':DETAIL,'world_session':'w','params':{'task_session':'t','pos':[1,65,2],'face':'up','expected_state':'Block{minecraft:crafting_table}'},'request_id':'r','position_before':[1,111,2],'position_after':[1,111,2],'inventory_delta':{},'revision_before':5,'revision_after':5,'health_before':20,'health_after':20};s={'last_request':'r','pos':[1,111,2],'control_revision':5,'health':20,'screen':'','menu':{'type':'InventoryMenu','id':0,'cursor':{'count':0}},'manual_movement':False,'movement_keys':{}};return c,err,e,s
 def test_exact_pre_use_route_refusal_allows_only_observation(self):self.assertTrue(observable(*self.fixture(),'w','t'))
 def test_any_interaction_movement_or_unknown_receipt_stays_retained(self):
  for mode in ['op','move','delta','unknown','menu','keys','block']:
   c,err,e,s=copy.deepcopy(self.fixture())
   if mode=='op':e['op']='interact'
   elif mode=='move':e['position_after']=[2,111,2]
   elif mode=='delta':e['inventory_delta']={'minecraft:iron_ingot':-2}
   elif mode=='unknown':err['native_inflight']={'id':'x'}
   elif mode=='menu':s['screen']='CraftingScreen'
   elif mode=='keys':s['movement_keys']['forward']=True
   else:e['params']['expected_state']='Block{minecraft:chest}'
   with self.subTest(mode=mode):self.assertFalse(observable(c,err,e,s,'w','t'))
if __name__=='__main__':unittest.main()
