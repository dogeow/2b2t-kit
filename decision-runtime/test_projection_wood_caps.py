import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import projection_wood_caps as caps

TARGET=[2,64,2]
def block(pos,state='Block{minecraft:cherry_planks}',**extra):
 return {'pos':list(pos),'state':state,'solid':True,'fluid':False,'block_entity':False,**extra}
class Client:
 def __init__(self,root):
  self.out=Path(root);self.world='w';self.task='t';self.rev=1;self.clock=1000
  self.blocks={(2,64,3):'Block{minecraft:cherry_planks}'};self.items={caps.RAW:2,'minecraft:dirt':15};self.hand=None;self.calls=[];self.unknown=None
 def status(self):
  self.clock+=500
  return {'world_session':'w','server':'server','dimension':'minecraft:overworld','projection_selection':{'key':'k','min':[0,64,0],'max':[4,64,4]},'health':20,'food':20,'pos':[4.5,67,2.5],'manual_movement':False,'screen':'','guard_armed':True,'guard_pve_only':True,'time':self.clock,'entities':[],
   'inventory':[{'slot':0,'item':caps.RAW,'count':self.items[caps.RAW]},{'slot':1,'item':'minecraft:dirt','count':self.items['minecraft:dirt']},{'slot':2,'item':'minecraft:diamond_shovel','count':1,'durability':100}]}
 def request(self,op,**kw):
  self.calls.append((op,kw))
  if self.unknown==op:return {'phase':'waiting'}
  if op=='projection_audit':
   r={'pos':TARGET,'expected':caps.EXPECTED,'actual':self.blocks.get(tuple(TARGET),'Block{minecraft:air}'),'kind':'missing','neighbors_loaded':True,'fluid':False,'adjacent_fluid':False,'block_entity':False}
   return {'projection_audit':{'placement_key':'k','server':'server','dimension':'minecraft:overworld','observed_at':self.clock,'loaded_chunks_verified':True,'kinds':{},'matched':24,'total':25,'mismatches':[r]}}
  if op=='scan':
   lo,hi=kw['min'],kw['max'];rows=[block(pos,state)for pos,state in self.blocks.items()if all(a<=p<=b for p,a,b in zip(pos,lo,hi))]
   n=1
   for a,b in zip(lo,hi):n*=b-a+1
   return {'phase':'done','world_session':'w','blocks':rows,'scan_cells_read':n,'scan_total_cells':n,'scan_start_revision':1,'scan_end_revision':1}
  if op=='select_item':self.hand=kw['item']
  elif op=='interact':
   pos=kw['pos'];delta={'up':(0,1,0),'north':(0,0,-1),'south':(0,0,1),'east':(1,0,0),'west':(-1,0,0)}[kw['face']]
   assert self.blocks[tuple(pos)]==kw['expected_state'];assert self.hand=='minecraft:dirt'
   self.blocks[tuple(a+b for a,b in zip(pos,delta))]=caps.DIRT;self.items['minecraft:dirt']-=1
  elif op=='mine_block':
   assert self.blocks[tuple(kw['pos'])]==caps.DIRT
   del self.blocks[tuple(kw['pos'])];self.items['minecraft:dirt']+=1
  else:raise AssertionError(op)
  return {'phase':'done'}
 def checked(self,*a,**kw):return self.request(*a,**kw)
class CapsTest(unittest.TestCase):
 def test_anchor_approach_pose_cannot_overlap_future_cap_cube(self):
  self.assertTrue(caps.body_overlaps_cell([761083.5,65.839,797759.5],[761083,65,797759]))
  self.assertFalse(caps.body_overlaps_cell([761083.5,66.25,797759.5],[761083,65,797759]))
  self.assertFalse(caps.body_overlaps_cell([761084.5,65.839,797759.5],[761083,65,797759]))
 def test_pose_above_cube_is_moved_sideways_before_restore_flight_can_sink_it(self):
  class PoseClient(Client):
   def __init__(self,root):super().__init__(root);self.pos=[2.5,66.02,3.5]
   def status(self):s=super().status();s['pos']=self.pos[:];return s
   def request(self,op,**kw):
    if op=='navigate':self.calls.append((op,kw));self.pos=kw['target'][:];return {'phase':'done'}
    if op=='interact':
     p=kw['pos'];d={'up':(0,1,0),'north':(0,0,-1),'south':(0,0,1),'east':(1,0,0),'west':(-1,0,0)}[kw['face']]
     self_target=[a+b for a,b in zip(p,d)]
     if caps.body_overlaps_cell(self.pos,self_target):raise AssertionError('player overlaps future cap')
    return super().request(op,**kw)
  with tempfile.TemporaryDirectory()as root:
   c=PoseClient(root)
   def finish(client,**kw):
    c.blocks[tuple(TARGET)]=caps.EXPECTED;c.items[caps.RAW]-=1
    return {'completed':[{'pos':TARGET}],'deferred':[]}
   with patch.object(caps,'approach_faces',return_value='up'),patch.object(caps,'wait_known_idle',side_effect=lambda c:c.status()),patch.object(caps,'swept_entities',return_value=[]),patch.object(caps,'_travel',side_effect=lambda client,point,checkpoint,trace:client.request('navigate',target=point)),patch.object(caps,'finish_beams',side_effect=finish):
    self.assertTrue(caps.run_one(c,TARGET,Path(root)/'run',c.status)['complete'])
   ops=[op for op,_ in c.calls];self.assertLess(ops.index('navigate'),ops.index('interact'))
   destination=next(kw['target']for op,kw in c.calls if op=='navigate')
   self.assertNotEqual(2.5,destination[0])
 def test_two_caps_and_longer_air_bridge_never_modify_the_anchor(self):
  rows=[block((2,64,3))];plan=caps.plan_caps(TARGET,rows,{(2,64,3)},[0,64,0],[4,64,4])
  self.assertEqual([[2,65,3],[2,65,2]],plan['caps'])
  rows=[block((2,64,4))];plan=caps.plan_caps(TARGET,rows,{(2,64,4)},[0,64,0],[4,64,4])
  self.assertEqual(3,len(plan['caps']))
 def test_confirmed_same_task_prefix_is_not_placed_twice_and_all_dirt_returns(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client(root);c.blocks[(2,65,3)]=caps.DIRT;c.items['minecraft:dirt']=14
   receipt=Path(root)/'prior.json'
   receipt.write_text(json.dumps({'pending':None,'world_session':'w','task_session':'t','placement_key':'k','target':TARGET,'complete':False,
    'plan':{'target':TARGET,'base':[2,64,3],'base_state':'Block{minecraft:cherry_planks}','caps':[[2,65,3],[2,65,2]]},'owned_caps':[[2,65,3]],'wood_before':2,'dirt_before':15}))
   def finish(client,**kw):
    c.blocks[tuple(TARGET)]=caps.EXPECTED;c.items[caps.RAW]-=1
    return {'completed':[{'pos':TARGET}],'deferred':[]}
   with patch.object(caps,'approach_faces',return_value='up'),patch.object(caps,'wait_known_idle',side_effect=lambda c:c.status()),patch.object(caps,'finish_beams',side_effect=finish):
    result=caps.run_one(c,TARGET,Path(root)/'resume',c.status,resume_confirmed=receipt)
   self.assertTrue(result['complete']);self.assertEqual(1,sum(op=='interact'for op,_ in c.calls));self.assertEqual(15,c.items['minecraft:dirt'])
 def test_cap_existing_block_container_fluid_or_unmatched_base_is_preserved(self):
  for rows,matched in [([block((2,64,3)),block((2,65,2))],{(2,64,3)}),([block((2,64,3),block_entity=True)],{(2,64,3)}),([block((2,64,3),fluid=True)],{(2,64,3)}),([block((2,64,3))],set())]:
   self.assertIsNone(caps.plan_caps(TARGET,rows,matched,[0,64,0],[4,64,4],2))
 def test_normal_place_strip_and_cleanup_conserve_dirt_and_one_wood(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client(root)
   def finish(client,**kw):
    self.assertEqual(caps.DIRT,c.blocks[(2,65,2)]);self.assertEqual('y',kw['target_axis'])
    c.blocks[tuple(TARGET)]=caps.EXPECTED;c.items[caps.RAW]-=1
    return {'completed':[{'pos':TARGET}],'deferred':[]}
   with patch.object(caps,'approach_faces',return_value='up'),patch.object(caps,'wait_known_idle',side_effect=lambda c:c.status()),patch.object(caps,'finish_beams',side_effect=finish):
    result=caps.run_one(c,TARGET,Path(root)/'run',c.status)
   self.assertTrue(result['complete']);self.assertEqual(15,c.items['minecraft:dirt']);self.assertEqual(1,c.items[caps.RAW])
   self.assertEqual({(2,64,3):'Block{minecraft:cherry_planks}',tuple(TARGET):caps.EXPECTED},c.blocks)
   self.assertEqual({},c.resource_cleanup)
 def test_unknown_cap_placement_does_not_mine_or_repeat(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client(root);c.unknown='interact'
   with patch.object(caps,'approach_faces',return_value='up'),patch.object(caps,'wait_known_idle',side_effect=lambda c:c.status()):
    with self.assertRaisesRegex(RuntimeError,'uncertain'):caps.run_one(c,TARGET,Path(root)/'run',c.status)
   self.assertEqual(1,sum(op=='interact'for op,_ in c.calls));self.assertFalse(any(op=='mine_block'for op,_ in c.calls))
   self.assertEqual('place_cap',json.loads((Path(root)/'run/progress.json').read_text())['pending']['op'])
   with self.assertRaisesRegex(RuntimeError,'Unknown'):next(iter(c.resource_cleanup.values()))()
 def test_unknown_wood_placement_keeps_caps_and_original_intent(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client(root)
   with patch.object(caps,'approach_faces',return_value='up'),patch.object(caps,'wait_known_idle',side_effect=lambda c:c.status()),patch.object(caps,'finish_beams',side_effect=RuntimeError('unknown wood')):
    with self.assertRaisesRegex(RuntimeError,'unknown wood'):caps.run_one(c,TARGET,Path(root)/'run',c.status)
   self.assertFalse(any(op=='mine_block'for op,_ in c.calls));self.assertEqual(13,c.items['minecraft:dirt'])
   with self.assertRaisesRegex(RuntimeError,'Unknown'):next(iter(c.resource_cleanup.values()))()
 def test_replaced_owned_cap_is_not_mined_after_known_wood_completion(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client(root)
   def finish(client,**kw):
    c.blocks[tuple(TARGET)]=caps.EXPECTED;c.items[caps.RAW]-=1
    c.blocks[(2,65,2)]='Block{minecraft:chest}'
    return {'completed':[{'pos':TARGET}],'deferred':[]}
   with patch.object(caps,'approach_faces',return_value='up'),patch.object(caps,'wait_known_idle',side_effect=lambda c:c.status()),patch.object(caps,'finish_beams',side_effect=finish):
    with self.assertRaisesRegex(RuntimeError,'Owned cap changed'):caps.run_one(c,TARGET,Path(root)/'run',c.status)
   self.assertFalse(any(op=='mine_block'for op,_ in c.calls));self.assertEqual('Block{minecraft:chest}',c.blocks[(2,65,2)])
 def test_unknown_cap_mining_is_not_repeated_or_counted_as_recovered(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client(root)
   def finish(client,**kw):
    c.blocks[tuple(TARGET)]=caps.EXPECTED;c.items[caps.RAW]-=1;c.unknown='mine_block'
    return {'completed':[{'pos':TARGET}],'deferred':[]}
   with patch.object(caps,'approach_faces',return_value='up'),patch.object(caps,'wait_known_idle',side_effect=lambda c:c.status()),patch.object(caps,'finish_beams',side_effect=finish):
    with self.assertRaisesRegex(RuntimeError,'mining not confirmed'):caps.run_one(c,TARGET,Path(root)/'run',c.status)
   self.assertEqual(1,sum(op=='mine_block'for op,_ in c.calls));self.assertEqual(13,c.items['minecraft:dirt'])
   with self.assertRaisesRegex(RuntimeError,'Unknown'):next(iter(c.resource_cleanup.values()))()
 def test_all_dirt_collected_during_level_route_skips_surface_descent(self):
  class RaceClient(Client):
   def __init__(self,root):super().__init__(root);self.drops=[]
   def status(self):s=super().status();s['entities']=self.drops[:];return s
   def request(self,op,**kw):
    r=super().request(op,**kw)
    if op=='mine_block':
     self.items['minecraft:dirt']-=1
     self.drops=[{'type':'minecraft:item','uuid':'merged-owned-dirt','stack':{'item':'minecraft:dirt','count':15-self.items['minecraft:dirt'],'max_stack':64},'pos':[2.5,65,2.5]}]
    return r
  with tempfile.TemporaryDirectory()as root:
   c=RaceClient(root)
   def finish(client,**kw):
    c.blocks[tuple(TARGET)]=caps.EXPECTED;c.items[caps.RAW]-=1
    return {'completed':[{'pos':TARGET}],'deferred':[]}
   def pickup_route(client,point,checkpoint,trace,**kw):
    self.assertTrue(kw.get('keep_cruise'));client.items['minecraft:dirt']=15;client.drops=[]
   with patch.object(caps,'approach_faces',return_value='up'),patch.object(caps,'wait_known_idle',side_effect=lambda c:c.status()),patch.object(caps,'finish_beams',side_effect=finish),patch.object(caps,'_travel',side_effect=pickup_route)as route:
    self.assertTrue(caps.run_one(c,TARGET,Path(root)/'run',c.status)['complete']);self.assertEqual(1,route.call_count)
   self.assertEqual(15,c.items['minecraft:dirt']);self.assertFalse(any(op in ('collect_item','navigate')for op,_ in c.calls))
 def test_explicit_consumable_dirt_records_actual_spent_soil_and_still_removes_every_cap(self):
  class SpentDirtClient(Client):
   def request(self,op,**kw):
    r=super().request(op,**kw)
    if op=='mine_block':self.items['minecraft:dirt']-=1
    return r
  with tempfile.TemporaryDirectory()as root:
   c=SpentDirtClient(root)
   def finish(client,**kw):
    c.blocks[tuple(TARGET)]=caps.EXPECTED;c.items[caps.RAW]-=1
    return {'completed':[{'pos':TARGET}],'deferred':[]}
   with patch.object(caps,'approach_faces',return_value='up'),patch.object(caps,'wait_known_idle',side_effect=lambda c:c.status()),patch.object(caps,'finish_beams',side_effect=finish):
    result=caps.run_one(c,TARGET,Path(root)/'run',c.status,consumable_dirt=True)
   self.assertTrue(result['complete']);self.assertTrue(result['all_caps_removed'])
   self.assertFalse(result['dirt_restored']);self.assertEqual(2,result['unrecovered_dirt_at_finish'])
   self.assertEqual(13,result['dirt_after']);self.assertEqual(1,c.items[caps.RAW]);self.assertEqual(2,len(c.blocks))
 def test_late_dirt_from_prior_work_is_recorded_as_extra_not_current_recovery(self):
  class ExtraClient(Client):
   def request(self,op,**kw):
    r=super().request(op,**kw)
    if op=='mine_block':self.items['minecraft:dirt']+=1
    return r
  with tempfile.TemporaryDirectory()as root:
   c=ExtraClient(root)
   def finish(client,**kw):
    c.blocks[tuple(TARGET)]=caps.EXPECTED;c.items[caps.RAW]-=1
    return {'completed':[{'pos':TARGET}],'deferred':[]}
   with patch.object(caps,'approach_faces',return_value='up'),patch.object(caps,'wait_known_idle',side_effect=lambda c:c.status()),patch.object(caps,'finish_beams',side_effect=finish):
    result=caps.run_one(c,TARGET,Path(root)/'run',c.status,consumable_dirt=True)
   self.assertTrue(result['all_caps_removed']);self.assertFalse(result['dirt_restored'])
   self.assertEqual(17,result['dirt_after']);self.assertEqual(2,result['additional_dirt_received']);self.assertEqual(0,result['unrecovered_dirt_at_finish'])
if __name__=='__main__':unittest.main()
