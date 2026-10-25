import copy,unittest
from owned_furnace_origin import certificate
class OwnedFurnaceOriginTest(unittest.TestCase):
 def fixture(self):
  p={'pos':[1,64,2],'face':'up','expected_state':'Block{minecraft:furnace}[facing=north,lit=false]','expected_hand':'minecraft:cooked_beef'};c={'action':'native','op':'interact','params':p};r={'phase':'done','id':'r','world_session':'w','control_revision':5,'health':20,'pos':[1.5,66.1,2.5],'inventory':[],'menu':{'type':'InventoryMenu','id':0,'cursor':{'count':0}}};e={'op':'interact','phase':'done','request_id':'r','world_session':'w','params':dict(p,task_session='t'),'revision_before':5,'revision_after':5,'health_before':20,'health_after':20,'position_before':r['pos'],'position_after':r['pos'],'inventory_delta':{}};s={'last_request':'r','world_session':'w','control_revision':5,'health':20,'pos':r['pos'],'inventory':[],'menu':{'type':'FurnaceMenu','id':7,'cursor':{'count':0}},'supervision_lease':{'id':'l','kind':'materials','world_session':'w','job_session':'t','revision':5},'connected':True,'screen':'FurnaceScreen','manual_movement':False,'interface_paused':False,'inventory_interface_paused':False,'guard_armed':True,'guard_pve_only':True,'guard_busy':False,'movement_keys':{}};return c,r,e,s
 def cert(self,*args):return certificate(*args,world='w',task='t',lease_id='l',pos=[1,64,2])
 def test_original_late_menu_is_certified_for_observation_and_close_only(self):
  result=self.cert(*self.fixture());self.assertEqual('original_furnace_observation_and_close_only',result['purpose']);self.assertEqual('r',result['source_request'])
 def test_foreign_unsafe_or_mutated_context_is_not_adopted(self):
  for mode in ['manual','cursor','request','pos','world','lease','revision','health','input','active','keys','reply','old_menu','delta']:
   c,r,e,s=copy.deepcopy(self.fixture())
   if mode=='manual':s['manual_movement']=True
   elif mode=='cursor':s['menu']['cursor']['count']=1
   elif mode=='request':s['last_request']='other'
   elif mode=='pos':c['params']['pos']=[3,64,2]
   elif mode=='world':s['world_session']='other'
   elif mode=='lease':s['supervision_lease']['id']='other'
   elif mode=='revision':e['revision_after']=6
   elif mode=='health':s['health']=19
   elif mode=='input':s['inventory']=[{'slot':1,'item':'minecraft:glass','count':1}]
   elif mode=='active':s['navigating']=True
   elif mode=='keys':s['movement_keys']['forward']=True
   elif mode=='reply':r['phase']='waiting'
   elif mode=='old_menu':r['menu']={'type':'FurnaceMenu','id':99,'cursor':{'count':0}}
   else:e['inventory_delta']={'minecraft:glass':1}
   with self.subTest(mode=mode):self.assertIsNone(self.cert(c,r,e,s))
if __name__=='__main__':unittest.main()
