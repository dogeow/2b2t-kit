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
  return {'world_session':'w','server':'server','dimension':'minecraft:overworld','projection_selection':{'key':'k','min':[0,64,0],'max':[4,64,4]},'health':20,'food':20,'manual_movement':False,'screen':'','guard_armed':True,'guard_pve_only':True,'time':self.clock,'entities':[],
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
 def test_two_caps_and_longer_air_bridge_never_modify_the_anchor(self):
  rows=[block((2,64,3))];plan=caps.plan_caps(TARGET,rows,{(2,64,3)},[0,64,0],[4,64,4])
  self.assertEqual([[2,65,3],[2,65,2]],plan['caps'])
  rows=[block((2,64,4))];plan=caps.plan_caps(TARGET,rows,{(2,64,4)},[0,64,0],[4,64,4])
  self.assertEqual(3,len(plan['caps']))
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
 def test_drop_collected_before_pickup_admission_is_observed_without_replay(self):
  class RaceClient(Client):
   def __init__(self,root):super().__init__(root);self.drop=None;self.drop_id=0
   def status(self):
    s=super().status()
    if self.drop:s['entities']=[self.drop]
    return s
   def request(self,op,**kw):
    if op=='collect_item':
     self.calls.append((op,kw));self.items['minecraft:dirt']+=1;self.drop=None
     return {'phase':'error','detail':'Drop is no longer loaded; observe again'}
    r=super().request(op,**kw)
    if op=='mine_block':
     self.items['minecraft:dirt']-=1;self.drop_id+=1
     self.drop={'type':'minecraft:item','uuid':'drop-'+str(self.drop_id),'stack':{'item':'minecraft:dirt','count':1},'pos':[v+.5 for v in kw['pos']]}
    return r
  with tempfile.TemporaryDirectory()as root:
   c=RaceClient(root)
   def finish(client,**kw):
    c.blocks[tuple(TARGET)]=caps.EXPECTED;c.items[caps.RAW]-=1
    return {'completed':[{'pos':TARGET}],'deferred':[]}
   with patch.object(caps,'approach_faces',return_value='up'),patch.object(caps,'wait_known_idle',side_effect=lambda c:c.status()),patch.object(caps,'finish_beams',side_effect=finish):
    self.assertTrue(caps.run_one(c,TARGET,Path(root)/'run',c.status)['complete'])
   self.assertEqual(15,c.items['minecraft:dirt']);self.assertEqual(2,sum(op=='collect_item'for op,_ in c.calls))
if __name__=='__main__':unittest.main()
