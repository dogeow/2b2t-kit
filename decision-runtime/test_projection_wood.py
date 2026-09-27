import unittest
from pathlib import Path
import tempfile
from projection_wood import log_target,anchors,use_with_margin,finish_beams,post_work,POST_ITEM
from unittest.mock import patch

class PostClient:
 def __init__(self,out,targets=None):
  self.out=Path(out);self.world='world-1';self.server='example.test:25565'
  self.selection='yard';self.held=None;self.items={'minecraft:oak_log':2,'minecraft:diamond_axe':1}
  self.target_positions=targets or [[0,1,0],[0,2,0],[1,1,0]]
  self.blocks={(0,0,0):'Block{minecraft:grass_block}[snowy=false]',
               (1,0,0):'Block{minecraft:dirt}',
               (0,1,0):'Block{minecraft:short_grass}',
               (1,1,0):'Block{minecraft:oak_log}[axis=y]'}
  self.replaceable=True;self.apply_interaction=True;self.interactions=[];self.observed_at=1000
  self.audit_server=self.server
 def status(self):
  return {'server':self.server,'dimension':'minecraft:overworld','world_session':self.world,
          'projection_selection':{'key':self.selection,'min':[0,0,0],'max':[1,2,0]},
          'pos':[0.5,2,0.5],
          'inventory':[{'slot':i,'item':item,'count':count,
                        'durability':100 if item.endswith('_axe') else None}
                       for i,(item,count) in enumerate(self.items.items())]}
 def checked(self,op,**kwargs):
  assert op=='select_item';assert self.items.get(kwargs['item'],0)>0
  self.held=kwargs['item']
 def audit(self):
  self.observed_at+=1;rows=[]
  for pos in self.target_positions:
   actual=self.blocks.get(tuple(pos),'Block{minecraft:air}')
   expected='Block{'+POST_ITEM+'}[axis=y]'
   if actual==expected:continue
   rows.append({'pos':pos,'expected':expected,'actual':actual,
                'kind':'missing' if actual in ('Block{minecraft:air}','Block{minecraft:short_grass}') else 'occupied',
                'fluid':False,'adjacent_fluid':False,'block_entity':False,'neighbors_loaded':True})
  return {'placement_key':self.selection,'server':self.audit_server,
          'dimension':'minecraft:overworld','loaded_chunks_verified':True,
          'observed_at':self.observed_at,'matched':len(self.target_positions)-len(rows),
          'total':len(self.target_positions),'mismatches':rows,
          'replacement_items':{POST_ITEM:len(rows)} if rows else {},'kinds':{'missing':len(rows)}}
 def request(self,op,**kwargs):
  if op=='projection_audit':return {'projection_audit':self.audit()}
  if op=='scan':
   low,high=kwargs['min'],kwargs['max'];rows=[]
   for pos,state in self.blocks.items():
    if all(a<=n<=b for n,a,b in zip(pos,low,high)) and state!='Block{minecraft:air}':
     rows.append({'pos':list(pos),'state':state,'solid':state not in ('Block{minecraft:short_grass}','Block{minecraft:chest}'),
                  'replaceable':state=='Block{minecraft:short_grass}' and self.replaceable,
                  'fluid':False,'block_entity':state=='Block{minecraft:chest}'})
   return {'blocks':rows}
  if op=='interact':
   pos=tuple(kwargs['pos']);self.interactions.append((pos,self.held))
   assert self.blocks.get(pos,'Block{minecraft:air}')==kwargs['expected_state']
   assert self.held==kwargs['expected_hand']
   if self.apply_interaction:
    if self.held.endswith('_axe'):
     self.blocks[pos]='Block{minecraft:stripped_oak_log}[axis=y]'
    else:
     assert kwargs['face']=='up'
     target=(pos[0],pos[1]+1,pos[2]);self.blocks[target]='Block{minecraft:oak_log}[axis=y]'
     self.items[self.held]-=1
   return {'phase':'done'}
  raise AssertionError(op)

class WoodTest(unittest.TestCase):
 def row(self,actual='Block{minecraft:air}'):
  return {'pos':[2,3,4],'expected':'Block{minecraft:stripped_spruce_log}[axis=x]','actual':actual,'kind':'missing','fluid':False,'adjacent_fluid':False,'block_entity':False}
 def test_same_axis_raw_logs_can_be_stripped_but_wrong_axis_is_preserved(self):
  self.assertTrue(log_target(self.row('Block{minecraft:spruce_log}[axis=x]'))['strip'])
  self.assertIsNone(log_target(self.row('Block{minecraft:spruce_log}[axis=z]')))
 def test_only_axis_correct_non_container_support_is_used(self):
  rows=[{'pos':[1,3,4],'state':'Block{minecraft:stone}','solid':True,'fluid':False,'block_entity':False},{'pos':[2,2,4],'state':'Block{minecraft:stone}','solid':True,'fluid':False,'block_entity':False}]
  self.assertEqual([x[0] for x in anchors([2,3,4],'x',rows)],['east'])
  rows[0]['block_entity']=True;self.assertEqual(anchors([2,3,4],'x',rows),[])
 def test_fluid_or_existing_player_block_is_not_modified(self):
  r=self.row();r['adjacent_fluid']=True;self.assertIsNone(log_target(r));self.assertIsNone(log_target(self.row('Block{minecraft:oak_log}[axis=x]')))
 def test_only_known_pre_use_failure_gets_one_closer_attempt(self):
  class Client:
   calls=0
   def request(self,*a,**kw):
    self.calls+=1
    return {'phase':'error','detail':'Target interaction face is occluded or out of reach'} if self.calls==1 else {'phase':'done'}
  c=Client();checks=[]
  with patch('projection_wood.approach_faces',return_value='east') as approach:
   use_with_margin(c,[1,2,3],'Block{minecraft:stone}','minecraft:spruce_log',['east'],lambda:checks.append(True))
   self.assertEqual([v.kwargs['stand_distance'] for v in approach.call_args_list],[2.4,1.8])
  self.assertEqual(c.calls,2);self.assertEqual(len(checks),2)
 def test_uncertain_mutation_is_never_replayed(self):
  class Client:
   calls=0
   def request(self,*a,**kw):self.calls+=1;return {'phase':'waiting','detail':'server acknowledgement timed out'}
  c=Client()
  with patch('projection_wood.approach_faces',return_value='east'):
   with self.assertRaises(RuntimeError):use_with_margin(c,[1,2,3],'Block{minecraft:stone}','minecraft:spruce_log',['east'])
  self.assertEqual(c.calls,1)

 def test_three_oak_post_cells_use_dry_grass_ground_and_exact_receipts(self):
  with tempfile.TemporaryDirectory() as folder:
   c=PostClient(folder)
   with patch('projection_wood.approach_faces',side_effect=lambda _c,_p,_s,faces,**_k:faces[0]):
    result=finish_beams(c,limit=3,expected_key='yard',expected_world='world-1',
                        expected_server='example.test',target_item=POST_ITEM,target_axis='y')
   self.assertEqual(3,len(result['completed']))
   self.assertEqual(3,c.audit()['matched'])
   self.assertEqual(0,c.items['minecraft:oak_log'])
   for receipt in result['completed']:
    self.assertEqual(receipt['expected'],receipt['post_scan_state'])
    self.assertEqual('yard',receipt['placement_key'])
    self.assertGreater(receipt['strip_audit_at'],1000)
   self.assertEqual(3,len((Path(folder)/'finished-beams.jsonl').read_text().splitlines()))

 def test_short_grass_requires_fresh_replaceable_scan_and_occupied_blocks_stay(self):
  with tempfile.TemporaryDirectory() as folder:
   c=PostClient(folder,targets=[[0,1,0]]);c.replaceable=False
   with patch('projection_wood.approach_faces',return_value='up'):
    self.assertFalse(finish_beams(c,expected_key='yard',target_item=POST_ITEM,target_axis='y')['completed'])
   self.assertFalse(c.interactions)
   c.blocks[(0,1,0)]='Block{minecraft:chest}';c.replaceable=True
   self.assertEqual(0,post_work(c.audit(),c.status())['eligible'])
   with patch('projection_wood.approach_faces',return_value='up'):
    self.assertFalse(finish_beams(c,expected_key='yard',target_item=POST_ITEM,target_axis='y')['completed'])
   self.assertFalse(c.interactions)

 def test_scope_and_unconfirmed_placement_stop_before_replay(self):
  with tempfile.TemporaryDirectory() as folder:
   c=PostClient(folder,targets=[[0,1,0]])
   with self.assertRaisesRegex(RuntimeError,'Selected projection'):
    finish_beams(c,expected_key='house',target_item=POST_ITEM,target_axis='y')
   c.audit_server='other.test'
   with self.assertRaisesRegex(RuntimeError,'another site'):
    finish_beams(c,expected_key='yard',target_item=POST_ITEM,target_axis='y')
   c.audit_server=c.server;c.apply_interaction=False
   with patch('projection_wood.approach_faces',return_value='up'):
    with self.assertRaisesRegex(RuntimeError,'not confirmed'):
     finish_beams(c,expected_key='yard',target_item=POST_ITEM,target_axis='y')
   self.assertEqual(1,len(c.interactions))

 def test_netherite_axe_is_accepted_and_missing_axe_blocks_before_placement(self):
  with tempfile.TemporaryDirectory() as folder:
   c=PostClient(folder,targets=[[1,1,0]])
   c.items.pop('minecraft:diamond_axe');c.items['minecraft:netherite_axe']=1
   with patch('projection_wood.approach_faces',return_value='up'):
    receipts=finish_beams(c,expected_key='yard',target_item=POST_ITEM,target_axis='y')['completed']
   self.assertEqual('minecraft:netherite_axe',receipts[0]['axe'])
   c=PostClient(folder,targets=[[0,1,0]]);c.items.pop('minecraft:diamond_axe')
   with self.assertRaisesRegex(RuntimeError,'No confirmed durable'):
    finish_beams(c,expected_key='yard',target_item=POST_ITEM,target_axis='y')
   self.assertFalse(c.interactions)
if __name__=='__main__':unittest.main()
