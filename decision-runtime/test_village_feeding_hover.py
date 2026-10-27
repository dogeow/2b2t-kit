import unittest,tempfile,json,math
from pathlib import Path
from unittest.mock import patch
from village_feeding import close_hover_food_pose,feed

class HoverFoodTests(unittest.TestCase):
 def test_farmland_target_gets_a_collision_clear_pose_above_all_floor_work(self):
  target={'uuid':'p','pos':[3.5,63.9375,3.5]};state={'pos':[3.5,64,4.5]};cells={(3,63,3):{'state':'Block{minecraft:farmland}[moisture=7]','solid':False,'fluid':False},(3,64,3):{'state':'Block{minecraft:potatoes}[age=7]','passable':True,'fluid':False,'block_entity':False}}
  p=close_hover_food_pose([0,64,0],[8,67,8],cells,target,[target],state);self.assertIsNotNone(p);self.assertEqual(65.1,p[1]);self.assertLessEqual(math.dist(p,target['pos']),1.5);self.assertGreaterEqual(math.hypot(p[0]-3.5,p[2]-3.5),.65)
 def test_low_tunnel_roof_and_wet_upper_plane_never_yield_a_pose(self):
  target={'uuid':'p','pos':[3.5,64,3.5]};state={'pos':[3.5,64,4.5]}
  for row in ({'passable':False,'fluid':False,'block_entity':False},{'passable':True,'fluid':True,'block_entity':False}):
   cells={(x,66,z):row for x in range(9)for z in range(9)}
   self.assertIsNone(close_hover_food_pose([0,64,0],[8,67,8],cells,target,[target],state))
 def test_good_existing_hover_is_kept_instead_of_oscillating_between_poses(self):
  target={'uuid':'p','pos':[3.5,64,3.5]};state={'pos':[3.5,65.125,4.25]};p=close_hover_food_pose([0,64,0],[8,67,8],{},target,[target],state);self.assertEqual([3.5,65.1,4.25],p)
 def run_case(self,receipt):
  class Clock:
   now=0
   def monotonic(self):return self.now
   def sleep(self,n):self.now+=n
  clock=Clock();rows=[]
  for x in range(9):
   for y in range(63,68):
    for z in range(9):
     if x in(0,8)or z in(0,8)or y in(63,67):
      farm=y==63 and x in(2,3,4)and z in(2,3,4)
      rows.append({'pos':[x,y,z],'state':'Block{minecraft:farmland}[moisture=7]'if farm else'Block{minecraft:dark_oak_planks}','solid':not farm,'fluid':False,'block_entity':False})
  class Owner:
   world='w'
   def __init__(self):self.position=[3.5,64,4.5];self.flight=False;self.bread=2;self.started=None;self.calls=[]
   def status(self):
    person={'id':12,'uuid':'p','pos':[3.5,63.9375,3.5],'health':20,'is_baby':False,'visible':True}
    drop={'id':77,'uuid':'one-drop','type':'minecraft:item','pos':[3.5,64.5,3.5],'stack':{'item':'minecraft:bread','count':1}}
    return {'time':1000+int(clock.now*1000),'world_session':'w','runtime_generation':0,'player_uuid':'player','pos':list(self.position),'velocity':[0,0,0],'on_ground':not self.flight,'flight':self.flight,'navigating':False,'manual_movement':False,'health':20,'hand':{'item':'minecraft:bread','count':self.bread},'entities':[drop]if self.started is not None and clock.now-self.started<.5 else[],'inventory':[{'slot':0,'item':'minecraft:bread','count':self.bread}],'loaded_villagers':{'villagers':[person]}}
   def native(self,op,**params):
    self.calls.append((op,params))
    if op=='scan':return {'scan_cells_read':405,'scan_total_cells':405,'blocks':rows,'time':1000}
    if op=='navigate':self.position=params['target'];self.flight=True
    if op=='walk':raise AssertionError('Crop-side hover feeding must never land or walk the field')
    if op=='villager_bread_drop':
     assert self.flight and abs(self.position[1]-65.1)<.01
     self.started=clock.now;self.bread-=1
    return {'id':'r'+str(len(self.calls)),'phase':'done'}
  owner=Owner()
  def frame(root,state):
   events=[]
   if receipt and owner.started is not None and clock.now-owner.started>=.5:events=[{'kind':'pickup_entities_unresolved','source_entity_id':77,'collector_entity_id':12,'received_at':1000+int(owner.started*1000)+500,'amount':1,'collector':{'entity_id':12,'uuid':'p','type':'minecraft:villager','pos':[3.5,63.9375,3.5]}}]
   return {'world_session':'w','runtime_generation':0,'world_entered_at':0,'time':state['time'],'events':events,'villagers':[{'uuid':'p','sleeping':False}]}
  with tempfile.TemporaryDirectory()as tmp,patch('village_feeding.time.monotonic',clock.monotonic),patch('village_feeding.time.sleep',clock.sleep),patch('village_feeding.read',side_effect=frame):
   path=Path(tmp)/'food.json'
   if receipt:result=feed(owner,Path(tmp),{'p':1},path,[0,64,0],[8,67,8],hover_approach=True);self.assertTrue(result['complete']);self.assertEqual({'p':1},result['delivered'])
   else:
    with self.assertRaisesRegex(RuntimeError,'exact server collector receipt'):feed(owner,Path(tmp),{'p':1},path,[0,64,0],[8,67,8],hover_approach=True)
    self.assertIsNotNone(json.loads(path.read_text())['pending_food'])
  self.assertEqual(1,sum(op=='villager_bread_drop'for op,_ in owner.calls));self.assertEqual(1,owner.bread)
  drops=next(i for i,(op,_)in enumerate(owner.calls)if op=='villager_bread_drop');self.assertTrue(all(p['target'][1]==65.1 for op,p in owner.calls[drops+1:]if op=='navigate'))
  if receipt:self.assertFalse(any(op=='navigate'for op,_ in owner.calls[drops+1:]),'A received bread packet must not trigger an unnecessary retreat')
 def test_hover_opt_in_feeds_farmland_villager_and_retreats_at_same_height(self):self.run_case(True)
 def test_missing_receipt_retains_one_drop_without_retry_under_hover_mode(self):self.run_case(False)

 def test_bed_target_does_not_use_the_upper_hover_throw_pose(self):
  cells={(3,64,3):{'state':'Block{minecraft:white_bed}[facing=north,occupied=false,part=head]'},(3,64,4):{'state':'Block{minecraft:white_bed}[facing=north,occupied=false,part=foot]'}}
  self.assertIsNone(close_hover_food_pose([0,64,0],[8,67,8],cells,{'uuid':'p','pos':[3.5,64.5625,3.5]},[],{'pos':[3.5,65.1,4.5]}))
 def test_hover_opt_in_falls_back_to_same_bed_height_before_Q(self):
  class DroppedOnce(Exception):pass
  class Owner:
   world='w'
   def __init__(self):self.pos=[3.5,65.1,4.5];self.flight=True;self.time=1000;self.drops=0
   def status(self):
    self.time+=100
    return {'time':self.time,'world_session':'w','runtime_generation':0,'player_uuid':'player','health':20,'pos':self.pos,'velocity':[0,0,0],'on_ground':not self.flight,'flight':self.flight,'navigating':False,'manual_movement':False,'hand':{'item':'minecraft:bread','count':2},'entities':[],'inventory':[{'slot':0,'item':'minecraft:bread','count':2}],'loaded_villagers':{'villagers':[{'uuid':'p','id':12,'pos':[3.5,64.5625,3.5],'health':20,'is_baby':False,'visible':True}]}}
   def native(self,op,**params):
    if op=='scan':return {'blocks':[{'pos':[3,64,3],'state':'Block{minecraft:white_bed}[facing=north,occupied=false,part=head]'},{'pos':[3,64,4],'state':'Block{minecraft:white_bed}[facing=north,occupied=false,part=foot]'}]}
    if op=='walk':self.pos=params['target'];self.flight=False
    if op=='villager_bread_drop':
     assert self.pos[1]==64.5625,'Bed Q must not dispatch from upper hover'
     self.drops+=1;raise DroppedOnce()
    return {'phase':'done','id':'r'}
  for mode in (False,True):
   with self.subTest(hover_approach=mode):
    owner=Owner()
    with tempfile.TemporaryDirectory()as tmp,patch('village_feeding.feeding_containment',return_value={'verified':True}),patch('village_feeding.read',return_value={'villagers':[{'uuid':'p','sleeping':False}]}),patch('village_feeding.time.sleep'):
     with self.assertRaises(DroppedOnce):feed(owner,Path(tmp),{'p':1},Path(tmp)/'food.json',[0,64,0],[8,67,8],hover_approach=mode)
    self.assertEqual(1,owner.drops)

 def test_occupied_bed_partner_cannot_fall_through_to_an_upper_Q(self):
  class Owner:
   world='w'
   drops=0
   def status(self):return {'time':1000,'world_session':'w','runtime_generation':0,'player_uuid':'player','health':20,'pos':[3.5,65.1,4.5],'velocity':[0,0,0],'on_ground':False,'flight':True,'navigating':False,'manual_movement':False,'hand':{'item':'minecraft:bread','count':2},'entities':[],'inventory':[{'slot':0,'item':'minecraft:bread','count':2}],'loaded_villagers':{'villagers':[{'uuid':'p','id':12,'pos':[3.5,64.5625,3.5],'health':20,'is_baby':False,'visible':True},{'uuid':'blocker','id':13,'pos':[3.5,64.5625,4.5],'health':20,'is_baby':False,'visible':True}]}}
   def native(self,op,**params):
    if op=='scan':return {'blocks':[{'pos':[3,64,3],'state':'Block{minecraft:white_bed}[facing=north,occupied=false,part=head]'},{'pos':[3,64,4],'state':'Block{minecraft:white_bed}[facing=north,occupied=false,part=foot]'}]}
    if op=='villager_bread_drop':self.drops+=1
    return {'phase':'done','id':'r'}
  owner=Owner()
  with tempfile.TemporaryDirectory()as tmp,patch('village_feeding.feeding_containment',return_value={'verified':True}),patch('village_feeding.read',return_value={'villagers':[{'uuid':'p','sleeping':False},{'uuid':'blocker','sleeping':False}]}):
   with self.assertRaisesRegex(RuntimeError,'surface is occupied'):feed(owner,Path(tmp),{'p':1,'blocker':1},Path(tmp)/'food.json',[0,64,0],[8,67,8])
  self.assertEqual(0,owner.drops)
