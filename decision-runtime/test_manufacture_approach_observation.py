import copy,json,tempfile,unittest
from pathlib import Path
from manufacture_approach_observation import observable,observe,DETAIL

class ManufactureApproachObservationTest(unittest.TestCase):
 def fixture(self):
  command={'action':'manufacture','targets':{'minecraft:bucket':1}};error={'error':DETAIL,'native_inflight':None,'unconfirmed_native_request':None,'last_request':'r'};event={'op':'approach_block','phase':'waiting','detail':DETAIL,'world_session':'w','params':{'task_session':'t','pos':[1,64,2],'face':'up','expected_state':'Block{minecraft:crafting_table}'},'request_id':'r','position_before':[8,66,9],'position_after':[2.5,65,2.5],'inventory_delta':{},'revision_before':5,'revision_after':5,'health_before':20,'health_after':20};state={'world_session':'w','connected':True,'supervision_lease':{'world_session':'w','job_session':'t','kind':'materials','revision':5},'last_request':'r','pos':event['position_after'],'control_revision':5,'health':20,'screen':'','menu':{'type':'InventoryMenu','id':0,'cursor':{'count':0},'slots':[{'count':0}for _ in range(5)]},'manual_movement':False,'movement_keys':{'forward':False},'guard_armed':True,'guard_pve_only':True,'guard_busy':False};return command,error,event,state
 def test_known_navigation_without_interaction_or_inventory_change_can_be_observed(self):self.assertTrue(observable(*self.fixture(),'w','t',[1,64,2]))
 def test_uncertain_receipts_or_active_control_never_admit_observation(self):
  for mode in ['interact','unknown','delta','moved_after','keys','menu','grid','health','world','lease','guard','source','cost','revision']:
   c,e,v,s=copy.deepcopy(self.fixture())
   if mode=='interact':v['op']='interact'
   elif mode=='unknown':e['unconfirmed_native_request']={'id':'x'}
   elif mode=='delta':v['inventory_delta']={'minecraft:iron_ingot':-3}
   elif mode=='moved_after':s['pos']=[9,65,9]
   elif mode=='keys':s['movement_keys']['forward']=True
   elif mode=='menu':s['screen']='CraftingScreen'
   elif mode=='grid':s['menu']['slots'][1]['count']=1
   elif mode=='health':s['health']=19
   elif mode=='world':v['world_session']='other'
   elif mode=='lease':s['supervision_lease']['job_session']='other'
   elif mode=='guard':s['guard_busy']=True
   elif mode=='source':v['params']['pos']=[2,64,2]
   elif mode=='cost':c['targets']['minecraft:bucket']=True
   else:v['revision_after']=6
   with self.subTest(mode=mode):self.assertFalse(observable(c,e,v,s,'w','t',[1,64,2]))
 def test_adapter_only_sends_snapshot_and_restores_fence_on_failure(self):
  with tempfile.TemporaryDirectory()as t:
   root=Path(t);c,e,v,s=self.fixture();profile=root/'profile.json';profile.write_text(json.dumps({'workbench':[1,64,2]}));c.update(id='cmd',profile=str(profile));(root/'command.json').write_text(json.dumps(c));(root/'cmd').mkdir();(root/'cmd/error.json').write_text(json.dumps(e));(root/'control').mkdir();(root/'control/events.jsonl').write_text(json.dumps(v)+'\n')
   class Q:
    out=root;world='w';lease={'job_session':'t'};calls=[]
    def status(self):return s
    def native(self,op):self.calls.append(op);raise RuntimeError('read failed')
   q=Q()
   with self.assertRaisesRegex(RuntimeError,'read failed'):observe(q)
   self.assertEqual(['snapshot'],q.calls);self.assertIsNone(q._workbench_route_read)
if __name__=='__main__':unittest.main()
