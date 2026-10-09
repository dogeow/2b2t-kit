import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from drop_collection import collect_nearby_air
class Client:
 def __init__(self,out):
  self.out=Path(out);self.world='w';self.task='t';self.last='r';self.unconfirmed_native_request=None;self.count=13;self.present=True
  self.drop={'uuid':'d','type':'minecraft:item','pos':[2.875,65,3.5],'stack':{'item':'minecraft:dirt','count':1,'max_stack':64}}
  self.last_terminal_evidence={'op':'collect_item','phase':'waiting','detail':'Drop pickup not confirmed at the reached position','request_id':'r','world_session':'w','task_session':'t','revision_after':5,'params':{'expected_uuid':'d','expected_item':'minecraft:dirt','expected_count':1}}
 def status(self):return {'world_session':'w','control_revision':5,'health':20,'food':20,'flight':True,'guard_busy':False,'guard_armed':True,'guard_pve_only':True,'manual_movement':False,'screen':'','recent_hurt_at':1,'pos':[1.5,64.879,4.5],'entities':[copy.deepcopy(self.drop)]if self.present else [],'inventory':[{'slot':0,'item':'minecraft:dirt','count':self.count}]}
class AirPickupTest(unittest.TestCase):
 def test_one_new_fractional_route_after_known_wait_does_not_repeat_collect(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client(root)
   def travel(client,target,checkpoint,trace):
    self.assertEqual([2.375,65.3,3.5],target);checkpoint();client.count=14;client.present=False
   with patch('material_jobs.acquisition._travel',side_effect=travel)as route:
    self.assertTrue(collect_nearby_air(c,c.drop,13));self.assertEqual(1,route.call_count)
   self.assertTrue((Path(root)/'fractional-air-pickup-confirmed.jsonl').exists())
 def test_unknown_foreign_changed_drop_or_busy_state_do_not_start_route(self):
  for kind in ('unknown','foreign','revision','changed','busy'):
   with tempfile.TemporaryDirectory()as root:
    c=Client(root);drop=copy.deepcopy(c.drop)
    if kind=='unknown':c.unconfirmed_native_request={'id':'r'}
    if kind=='foreign':c.last='other'
    if kind=='revision':c.last_terminal_evidence['revision_after']=4
    if kind=='changed':c.drop['stack']['count']=2
    if kind=='busy':
     old=c.status;c.status=lambda:{**old(),'guard_busy':True}
    with patch('material_jobs.acquisition._travel')as route:
     self.assertFalse(collect_nearby_air(c,drop,13));route.assert_not_called()
if __name__=='__main__':unittest.main()
