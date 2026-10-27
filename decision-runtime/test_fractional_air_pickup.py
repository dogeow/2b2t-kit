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
 def test_falling_honeycomb_uses_current_air_geometry_without_another_collect(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client(root);c.drop['pos'][1]=61.;c.drop['stack'].update(item='minecraft:honeycomb',count=3)
   c.last_terminal_evidence['params'].update(expected_item='minecraft:honeycomb',expected_count=3)
   original=c.status;c.status=lambda:{**original(),'inventory':[{'slot':0,'item':'minecraft:honeycomb','count':c.count}]}
   with patch('material_jobs.dry_hover_harvest.pickup',return_value=True)as route,patch('material_jobs.local_air_path.move')as short:
    self.assertTrue(collect_nearby_air(c,c.drop,13));route.assert_called_once();short.assert_not_called()
    self.assertEqual('minecraft:honeycomb',route.call_args.kwargs['item']);self.assertEqual(3,route.call_args.kwargs['expected_count'])
 def test_four_clay_balls_can_use_a_proved_adjoining_body_route_after_fractional_rejection(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client(root);c.native_inflight=None;c.drop['stack'].update(item='minecraft:clay_ball',count=4)
   c.last_terminal_evidence['params'].update(expected_item='minecraft:clay_ball',expected_count=4)
   original=c.status;c.status=lambda:{**original(),'inventory':[{'slot':0,'item':'minecraft:clay_ball','count':c.count}]}
   def failed(*a,**k):
    c.last='scan';c.last_terminal_evidence={'op':'scan','phase':'done','request_id':'scan','world_session':'w'}
    raise RuntimeError('局部空气通道发生变化，未继续移动')
   def pickup(client,current,before,*a,**kw):
    self.assertEqual('d',current['uuid']);self.assertEqual(4,kw['expected_count']);client.count=before+4;client.present=False;return True
   with patch('material_jobs.local_air_path.move',side_effect=failed),patch('material_jobs.dry_hover_harvest.pickup',side_effect=pickup)as fallback:
    self.assertTrue(collect_nearby_air(c,c.drop,13));fallback.assert_called_once()
 def test_complete_scan_rejection_can_use_adjoining_air_without_collect_replay(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client(root);c.native_inflight=None
   def failed(*a,**k):
    c.last='scan';c.last_terminal_evidence={'op':'scan','phase':'done','request_id':'scan','world_session':'w'}
    raise RuntimeError('局部空气通道发生变化，未继续移动')
   def pickup(client,current,before,*a,**k):
    self.assertEqual('d',current['uuid']);self.assertEqual(13,before);self.assertEqual('minecraft:dirt',k['item']);return True
   with patch('material_jobs.local_air_path.move',side_effect=failed),patch('material_jobs.dry_hover_harvest.pickup',side_effect=pickup)as fallback:
    self.assertTrue(collect_nearby_air(c,c.drop,13));self.assertEqual(1,fallback.call_count)
 def test_unknown_correction_never_uses_a_second_air_route(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client(root)
   def failed(*a,**k):c.unconfirmed_native_request={'id':'unknown-move'};raise RuntimeError('局部空气通道发生变化，未继续移动')
   with patch('material_jobs.local_air_path.move',side_effect=failed),patch('material_jobs.dry_hover_harvest.pickup')as fallback:
    with self.assertRaises(RuntimeError):collect_nearby_air(c,c.drop,13)
    fallback.assert_not_called()
 def test_one_new_fractional_route_after_known_wait_does_not_repeat_collect(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client(root)
   def travel(client,target,out,**kw):
    self.assertEqual([2.375,65.3,3.5],target);self.assertEqual(.2,kw['foot_offset']);client.count=14;client.present=False
   with patch('material_jobs.local_air_path.move',side_effect=travel)as route:
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
    with patch('material_jobs.local_air_path.move')as route:
     self.assertFalse(collect_nearby_air(c,drop,13));route.assert_not_called()
 def test_four_ball_stack_uses_the_same_exact_terminal_proof_and_one_correction(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client(root);c.drop['stack'].update(item='minecraft:clay_ball',count=4)
   c.last_terminal_evidence['params'].update(expected_item='minecraft:clay_ball',expected_count=4)
   original=c.status
   c.status=lambda:{**original(),'inventory':[{'slot':0,'item':'minecraft:clay_ball','count':c.count}]}
   def travel(client,target,out,**kw):client.count=17;client.present=False
   with patch('material_jobs.local_air_path.move',side_effect=travel)as route:
    self.assertTrue(collect_nearby_air(c,c.drop,13));self.assertEqual(1,route.call_count)
if __name__=='__main__':unittest.main()
