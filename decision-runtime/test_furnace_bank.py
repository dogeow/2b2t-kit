import unittest
from furnace_bank import choose_pads
class FurnaceBankTest(unittest.TestCase):
 def test_follows_uneven_surface_without_removing_plants(self):
  from furnace_bank import choose_surface_pads
  rows=[{'pos':[x,y,0],'state':'Block{minecraft:grass_block}','solid':True} for x,y in [(0,63),(3,64),(6,65),(9,64)]]
  rows.append({'pos':[6,66,0],'state':'Block{minecraft:short_grass}'})
  self.assertEqual([[0,64,0],[3,65,0],[9,65,0]],choose_surface_pads(rows,[(x,0) for x in (0,3,6,9)],3))
 def test_preserves_occupied_and_wet_land(self):
  floors=[{'pos':[x,63,0],'state':'Block{minecraft:grass_block}[snowy=false]','solid':True,'fluid':False} for x in [0,3,6,9]]
  rows=floors+[{'pos':[0,64,0],'state':'Block{minecraft:cornflower}'},{'pos':[4,63,0],'fluid':True}]
  self.assertEqual([[6,64,0],[9,64,0]],choose_pads(rows,[(0,0),(3,0),(6,0),(9,0)],64,2))
  with self.assertRaises(RuntimeError):choose_pads(rows,[(0,0),(3,0)],64,2)
class FurnaceResumeTest(unittest.TestCase):
 def setUp(self):
  import tempfile
  from pathlib import Path
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.path=Path(self.temp.name)/'bank.json'
  self.positions=[[0,64,0],[3,64,0],[6,64,0]]
  self.floors=[{'pos':[x,63,0],'state':'Block{minecraft:grass_block}[snowy=false]','solid':True,'fluid':False} for x in (0,3,6)]
  class Client:
   world='w'
   def __init__(inner):inner.blocks={tuple(r['pos']):dict(r) for r in self.floors};inner.stock=3;inner.actions=[]
   def status(inner):return {'inventory':[{'slot':0,'item':'minecraft:furnace','count':inner.stock}], 'pos':[9.5,64,9.5],'time':123}
   def checked(inner,op,**args):inner.actions.append((op,args));return inner.status()
   def request(inner,op,**args):
    self.assertEqual('scan',op)
    return {'blocks':[r for p,r in inner.blocks.items() if all(a<=n<=b for a,n,b in zip(args['min'],p,args['max']))]}
  self.client=Client()
 def place(self,c,floor,state,hand,faces,before_use):
  before_use();pos=[floor[0],floor[1]+1,floor[2]]
  c.blocks[tuple(pos)]={'pos':pos,'state':'Block{minecraft:furnace}[facing=north,lit=false]','solid':True,'block_entity':True}
  c.stock-=1;c.actions.append(('place',pos))
 def test_interrupted_approach_resumes_only_unplaced_furnaces(self):
  import json
  from unittest.mock import patch
  from furnace_bank import build
  def fail_second(c,floor,*args):
   if floor[0]==3:raise RuntimeError('Navigation interrupted before interaction')
   self.place(c,floor,*args)
  with patch('furnace_bank.use_with_margin',side_effect=fail_second):
   with self.assertRaisesRegex(RuntimeError,'Navigation interrupted'):build(self.client,self.positions,self.path)
  self.assertEqual(1,len(json.loads(self.path.read_text())['placed']))
  with patch('furnace_bank.use_with_margin',side_effect=self.place):
   result=build(self.client,self.positions,self.path,resume=True)
   again=build(self.client,self.positions,self.path,resume=True)
  self.assertTrue(result['complete']);self.assertTrue(again['complete'])
  self.assertEqual(3,len([a for a in self.client.actions if a[0]=='place']))
  self.assertEqual(0,self.client.stock)
 def test_uncertain_placement_is_not_replayed_even_if_block_exists(self):
  import json
  from unittest.mock import patch
  from furnace_bank import build
  def uncertain(c,*args):
   self.place(c,*args);raise RuntimeError('Reply lost after server placement')
  with patch('furnace_bank.use_with_margin',side_effect=uncertain):
   with self.assertRaisesRegex(RuntimeError,'Reply lost'):build(self.client,self.positions,self.path)
  self.assertEqual(self.positions[0],json.loads(self.path.read_text())['pending']['pos'])
  before=list(self.client.actions)
  with self.assertRaisesRegex(RuntimeError,'do not replay'):build(self.client,self.positions,self.path,resume=True)
  self.assertEqual(before,self.client.actions)
 def test_area_change_rejected_before_any_more_placements(self):
  import json
  from furnace_bank import build
  self.path.write_text(json.dumps({'world_session':'w','positions':self.positions,'placed':[], 'complete':False}))
  self.client.blocks[(4,63,0)]={'pos':[4,63,0],'state':'Block{minecraft:water}','fluid':True}
  with self.assertRaisesRegex(RuntimeError,'dry clear'):build(self.client,self.positions,self.path,resume=True)
  self.assertEqual([],self.client.actions)
 def test_changed_world_or_plan_and_removed_furnace_stop_without_actions(self):
  import json
  from furnace_bank import build
  for change,expected in (({'world_session':'new'},'world transition'),({'positions':[[4,64,0]]},'plan differs'), ({},'furnace changed')):
   with self.subTest(change=change):
    self.path.write_text(json.dumps({'world_session':'w','positions':self.positions,'placed':[{'pos':self.positions[0],'state':'Block{minecraft:furnace}'}], 'complete':False,**change}))
    with self.assertRaisesRegex(RuntimeError,expected):build(self.client,self.positions,self.path,resume=True)
    self.assertEqual([],self.client.actions)
 def test_bad_positions_do_not_consume_materials(self):
  from furnace_bank import build
  for positions in ([],[[0,64,0],[0,64,0]],[[0,64.0,0]],[[0,True,0]],[[0,64,0],[1,64,0]]):
   with self.assertRaises(ValueError):build(self.client,positions,self.path)
  self.assertEqual([],self.client.actions)
 def test_duplicate_candidate_columns_cannot_count_one_pad_twice(self):
  with self.assertRaises(RuntimeError):choose_pads(self.floors,[(0,0),(0,0)],64,2)
 def test_adjacent_candidates_are_spaced_before_any_placement(self):
  floors=[{'pos':[x,63,0],'state':'Block{minecraft:dirt}','solid':True,'fluid':False} for x in range(4)]
  self.assertEqual([[0,64,0],[2,64,0]],choose_pads(floors,[(x,0) for x in range(4)],64,2))
 def test_definite_pre_use_failure_does_not_leave_an_uncertain_placement(self):
  import json
  from unittest.mock import patch
  from furnace_bank import build
  from work_access import ApproachUnavailable
  original=self.client.request
  def request(op,**args):
   if op=='interact':
    self.client.actions.append(('pre_use_error',args))
    return {'phase':'error','detail':'Target interaction face is occluded or out of reach'}
   return original(op,**args)
  self.client.request=request
  with patch('projection_wood.approach_faces',return_value='up'):
   with self.assertRaises(ApproachUnavailable):build(self.client,self.positions,self.path)
  self.assertIsNone(json.loads(self.path.read_text())['pending'])
  self.assertEqual(3,self.client.stock)
  with patch('furnace_bank.use_with_margin',side_effect=self.place):
   self.assertTrue(build(self.client,self.positions,self.path,resume=True)['complete'])

if __name__=='__main__':unittest.main()
