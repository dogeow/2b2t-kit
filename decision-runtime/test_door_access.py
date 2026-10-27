import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from door_access import crossing_destination,WOOD_DOORS,crossing_hand,use_visible_door
class Tests(unittest.TestCase):
 def test_near_closed_door_opens_walks_and_restores_from_other_side_without_work_face(self):
  state={'pos':[.5,65.,1.5],'projection_selection':{'min':[-2,60,-2],'max':[2,70,2]},'inventory':[{'item':'minecraft:netherite_sword','count':1}]}
  opened=False;uses=[]
  base='Block{minecraft:oak_door}[facing=south,half=lower,hinge=left,open=false,powered=false]'
  def row(*args):return {'pos':[0,65,0],'state':base.replace('open=false','open=true')if opened else base,'fluid':False}
  def request(op,**kw):
   nonlocal opened
   if op=='interact':
    visible='south'if state['pos'][2]>.5 else'north'
    if kw['face']!=visible:return {'phase':'error','detail':'Target interaction face is occluded or out of reach'}
    opened=not opened;uses.append(visible);return {'phase':'done'}
   rows=[{'pos':[x,64,z],'state':'Block{minecraft:stone}','solid':True,'fluid':False}for x in range(-2,3)for z in range(-2,3)]
   rows+=[row(),{**row(),'pos':[0,66,0],'state':row()['state'].replace('half=lower','half=upper')}]
   return {'blocks':rows}
  def checked(op,**kw):
   if op=='walk':state['pos']=kw['target']
  with tempfile.TemporaryDirectory()as d:
   c=SimpleNamespace(status=lambda:state,checked=Mock(side_effect=checked),request=request,out=Path(d))
   with patch('door_access.read_block',side_effect=row),patch('door_access.approach_faces',side_effect=RuntimeError('work face unavailable'))as approach,patch('door_access.time.sleep'):
    from door_access import cross_door
    result=cross_door(c,[0,65,0])
   approach.assert_not_called();self.assertFalse(opened);self.assertEqual(['south','north'],uses)
   self.assertLess(result['destination'][2],0)

 def test_approach_hover_is_not_rounded_up_to_a_nonexistent_floor(self):
  state={'pos':[993.5,70.83,839.5],'projection_selection':{'min':[990,65,834],'max':[999,75,842]},'inventory':[{'item':'minecraft:netherite_sword','count':1}]}
  door={'pos':[995,70,839],'state':'Block{minecraft:birch_door}[facing=east,half=lower,hinge=right,open=true,powered=false]','fluid':False}
  rows=[{'pos':[x,69,z],'state':'Block{minecraft:oak_planks}','solid':True,'fluid':False}for x in range(990,1000)for z in range(834,843)]
  rows+=[door,{**door,'pos':[995,71,839],'state':door['state'].replace('half=lower','half=upper')}]
  def action(op,**kw):
   if op=='walk':state['pos']=kw['target']
  with tempfile.TemporaryDirectory()as d:
   c=SimpleNamespace(status=lambda:state,checked=Mock(side_effect=action),request=Mock(return_value={'blocks':rows}),out=Path(d))
   with patch('door_access.read_block',return_value=door),patch('door_access.approach_faces',return_value='west'):
    from door_access import cross_door
    result=cross_door(c,door['pos'])
   self.assertGreater(result['destination'][0],995.5)
   self.assertEqual(70.,result['destination'][1])

 def test_restore_after_crossing_uses_visible_current_side_without_movement(self):
  c=SimpleNamespace(request=Mock(side_effect=[{'phase':'error','detail':'Target interaction face is occluded or out of reach'},{'phase':'done'}]))
  with patch('door_access.read_block',return_value={'state':'door-open'}):
   use_visible_door(c,[0,65,0],'door-open','minecraft:netherite_sword','north')
  self.assertEqual(['north','south'],[r.kwargs['face']for r in c.request.call_args_list])
  self.assertTrue(all(r.args[0]=='interact'for r in c.request.call_args_list))
 def test_unknown_door_toggle_never_tries_another_face(self):
  c=SimpleNamespace(request=Mock(return_value={'phase':'waiting','detail':'outcome pending'}))
  with patch('door_access.read_block',return_value={'state':'door-open'}),self.assertRaisesRegex(RuntimeError,'pending'):
   use_visible_door(c,[0,65,0],'door-open','minecraft:netherite_sword','north')
  self.assertEqual(1,c.request.call_count)
 def test_changed_door_after_known_pre_use_rejection_prevents_duplicate_toggle(self):
  c=SimpleNamespace(request=Mock(return_value={'phase':'error','detail':'Target interaction face is occluded or out of reach'}))
  with patch('door_access.read_block',side_effect=[{'state':'open'},{'state':'closed'}]),self.assertRaisesRegex(RuntimeError,'changed'):
   use_visible_door(c,[0,65,0],'open','minecraft:netherite_sword','north')
  self.assertEqual(1,c.request.call_count)
 def test_open_door_uses_observed_ground_passage_without_an_unavailable_work_face(self):
  state={'pos':[.5,65.,1.5],'projection_selection':{'min':[0,60,0],'max':[2,70,2]},
         'inventory':[{'item':'minecraft:netherite_sword','count':1}]}
  row={'state':'Block{minecraft:oak_door}[facing=south,half=lower,hinge=left,open=true,powered=false]','fluid':False}
  rows=[{'pos':[x,64,z],'state':'Block{minecraft:stone}','solid':True,'fluid':False}for x in range(-2,3)for z in range(-2,3)]
  rows+=[{**row,'pos':[0,65,0]},{**row,'pos':[0,66,0],'state':row['state'].replace('half=lower','half=upper')}]
  def action(op,**kw):
   if op=='walk':state['pos']=kw['target']
  with tempfile.TemporaryDirectory() as d:
   c=SimpleNamespace(status=lambda:state,checked=Mock(side_effect=action),request=Mock(return_value={'blocks':rows}),out=Path(d))
   with patch('door_access.read_block',return_value=row),patch('door_access.approach_faces',side_effect=RuntimeError('No work face'))as approach:
    from door_access import cross_door
    result=cross_door(c,[0,65,0])
   approach.assert_not_called();self.assertLess(result['destination'][2],-.05)
   self.assertTrue(all(a.args[0]in ('select_item','walk')for a in c.checked.call_args_list))
 def test_uses_actual_carried_sword_and_never_assumes_a_diamond_sword(self):
  self.assertEqual('minecraft:netherite_sword',crossing_hand({'inventory':[{'item':'minecraft:netherite_sword','count':1}]}))
  with self.assertRaises(RuntimeError):crossing_hand({'inventory':[{'item':'minecraft:diamond_sword','count':0}]} )
 def test_crosses_to_opposite_side_for_both_door_axes(self):
  self.assertEqual(crossing_destination([10,65,38],{'facing':'west'},[15,65,35]),([9,65,38],0,-1))
  self.assertEqual(crossing_destination([10,65,38],{'facing':'east'},[8,65,35]),([11,65,38],0,1))
  self.assertEqual(crossing_destination([14,65,40],{'facing':'south'},[15,65,35]),([14,65,41],2,1))
 def test_power_required_doors_are_not_offered(self):
  self.assertNotIn('minecraft:iron_door',WOOD_DOORS)
  self.assertIn('minecraft:birch_door',WOOD_DOORS)
if __name__=='__main__':unittest.main()
