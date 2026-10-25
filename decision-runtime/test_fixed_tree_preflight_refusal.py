import unittest
from copy import deepcopy
from fixed_tree_preflight_refusal import observable,DETAIL
class RefusalTest(unittest.TestCase):
 def fixture(self):
  p={'tree_root':[1,64,2],'tree_min':[0,64,0],'tree_max':[5,90,5],'item':'minecraft:spruce_log','tree_limit':1};c={'action':'native','op':'chop','params':p};r={'id':'r','phase':'stopped','detail':'脚本参数无效','world_session':'w','control_revision':12};e={'request_id':'r','op':'chop','phase':'stopped','detail':'脚本参数无效','world_session':'w','revision_before':10,'revision_after':12,'position_before':[1.5,64,2.5],'position_after':[1.5,64,2.5],'inventory_delta':{},'params':{**p,'task_session':'t'}};s={'phase':'error','detail':DETAIL,'world_session':'w','last_request':'r','control_revision':12,'pos':[1.5,64,2.5],'health':20,'connected':True,'manual_movement':False,'supervision_lease':{'kind':'materials','job_session':'t','world_session':'w','revision':12}};return c,r,e,s
 def test_exact_native_stop_is_only_observable(self):self.assertTrue(observable(*self.fixture(),'w','t'))
 def test_movement_stock_revisions_or_active_work_are_never_settled(self):
  for mode in ['move','stock','rev','busy','health','reason','world','scope']:
   with self.subTest(mode=mode):
    c,r,e,s=deepcopy(self.fixture())
    if mode=='move':e['position_after']=[2,64,2.5]
    if mode=='stock':e['inventory_delta']={'minecraft:spruce_log':1}
    if mode=='rev':e['revision_after']=13
    if mode=='busy':s['chopping']=True
    if mode=='health':s['health']=19
    if mode=='reason':s['detail']='another failure'
    if mode=='world':s['world_session']='other'
    if mode=='scope':e['params']['tree_root']=[2,64,2]
    self.assertFalse(observable(c,r,e,s,'w','t'))
if __name__=='__main__':unittest.main()
