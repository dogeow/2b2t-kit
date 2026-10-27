import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from local_printing import support_faces,finish_fixtures
class FixtureTest(unittest.TestCase):
 def test_wall_banner_uses_the_carried_banner_and_correct_wall_face(self):
  rows=[{'pos':[1,3,5],'state':'Block{minecraft:stone}','fluid':False},
        {'pos':[3,3,5],'state':'Block{minecraft:stone}','fluid':False}]
  self.assertEqual(['east'],[f for f,_ in support_faces([2,3,5],'Block{minecraft:light_gray_wall_banner}[facing=east]',rows)])
  with tempfile.TemporaryDirectory()as d,patch('local_printing.approach_faces',return_value='east'):
   c=FakeFixtureClient(Path(d));c.item='minecraft:light_gray_banner';c.row['expected']='Block{minecraft:light_gray_wall_banner}[facing=east]'
   result=finish_fixtures(c,[c.target]);self.assertEqual('matched',result[0]['result'])
   self.assertEqual(['minecraft:netherite_sword','minecraft:light_gray_banner'],c.selected)
   self.assertEqual(0,c.count)
 def test_current_pose_print_retains_scope_and_stock_proof_without_work_face_navigation(self):
  with tempfile.TemporaryDirectory()as d,patch('local_printing.approach_faces',side_effect=RuntimeError('No work face'))as nav:
   c=FakeFixtureClient(Path(d));result=finish_fixtures(c,[c.target],approach=False)
   nav.assert_not_called();self.assertEqual('matched',result[0]['result']);self.assertEqual(0,c.count)
   self.assertEqual(['minecraft:lantern'],c.selected);self.assertEqual([[c.target]],c.masks)
 def test_carpet_cannot_substitute_a_side_or_ceiling_for_its_missing_floor(self):
  rows=[{'pos':[2,4,5],'state':'Block{minecraft:stone}','fluid':False},{'pos':[2,3,4],'state':'Block{minecraft:light_gray_carpet}','fluid':False}]
  self.assertEqual([],support_faces([2,3,5],'Block{minecraft:light_gray_carpet}',rows))
 def test_hanging_lantern_only_approaches_underside_of_real_roof(self):
  rows=[{'pos':[2,4,5],'state':'Block{minecraft:stone}','fluid':False},{'pos':[2,2,5],'state':'Block{minecraft:stone}','fluid':False}]
  candidates=support_faces([2,3,5],'Block{minecraft:lantern}[hanging=true,waterlogged=false]',rows)
  self.assertEqual([(f,r['pos']) for f,r in candidates],[('down',[2,4,5])])
 def test_air_or_fluid_cannot_supply_a_placement_anchor(self):
  rows=[{'pos':[2,4,5],'state':'Block{minecraft:water}[level=0]','fluid':True}]
  self.assertEqual(support_faces([2,3,5],'Block{minecraft:lantern}[hanging=true,waterlogged=false]',rows),[])

 def test_hook_and_trapdoor_use_the_required_horizontal_attachment_face(self):
  rows=[{'pos':[x,y,z],'state':'Block{minecraft:stone}','fluid':False}
        for x,y,z in ((1,2,3),(3,2,3),(2,1,3),(2,3,3))]
  self.assertEqual(['east'],[f for f,_ in support_faces([2,2,3],'Block{minecraft:tripwire_hook}[attached=false,facing=east,powered=false]',rows)])
  self.assertEqual(['west'],[f for f,_ in support_faces([2,2,3],'Block{minecraft:birch_trapdoor}[facing=west,half=bottom,open=true,powered=false,waterlogged=false]',rows)])

 def test_scoped_fixture_print_uses_carried_netherite_sword_then_exact_material(self):
  with tempfile.TemporaryDirectory()as d,patch('local_printing.approach_faces',return_value='down'):
   c=FakeFixtureClient(Path(d));result=finish_fixtures(c,[c.target])
   self.assertEqual('matched',result[0]['result']);self.assertEqual(0,c.count)
   self.assertEqual([[c.target]],c.masks);self.assertEqual(1,c.clears)
   self.assertEqual(['minecraft:netherite_sword','minecraft:lantern'],c.selected)
   self.assertEqual(1,c.prints)

 def test_zero_proposal_interval_clears_only_after_proving_unchanged_cell_and_stock(self):
  with tempfile.TemporaryDirectory()as d,patch('local_printing.approach_faces',return_value='down'):
   c=FakeFixtureClient(Path(d),'zero');result=finish_fixtures(c,[c.target])
   self.assertEqual('unresolved',result[0]['result']);self.assertEqual(1,c.count)
   self.assertEqual(1,c.clears);self.assertEqual(1,c.prints)

 def test_unknown_or_forged_done_never_clears_mask_or_replays_print(self):
  for mode in('unknown','forged'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as d,patch('local_printing.approach_faces',return_value='down'):
    c=FakeFixtureClient(Path(d),mode)
    with self.assertRaisesRegex(RuntimeError,'unconfirmed'):finish_fixtures(c,[c.target])
    self.assertEqual(0,c.clears);self.assertEqual(1,c.prints)


class FakeFixtureClient:
 def __init__(self,out,mode='done'):
  self.out=out;self.mode=mode;self.world='w';self.rev=7;self.last=None
  self.target=[2,3,5];self.count=1;self.matched=False;self.prints=0;self.clears=0;self.masks=[];self.selected=[];self.hand='minecraft:stick';self.serial=0;self.item='minecraft:lantern'
  self.row={'pos':self.target,'expected':'Block{minecraft:lantern}[hanging=true,waterlogged=false]','actual':'Block{minecraft:air}','kind':'missing','fluid':False,'block_entity':False}
  self.yaw=0;self.pitch=0;self.time=0
 def status(self):
  self.time+=100
  return {'world_session':self.world,'pos':[.5,2.,5.5],'yaw':self.yaw,'pitch':self.pitch,'time':self.time,'projection_selection':{'key':'p'},'hand':{'item':self.hand,'count':1},'inventory':[{'item':'minecraft:netherite_sword','count':1,'slot':0},{'item':self.item,'count':self.count,'slot':1}]}
 def checked(self,op,**kwargs):
  if op=='look':self.yaw=kwargs['yaw'];self.pitch=kwargs['pitch']
  if op=='select_item':self.hand=kwargs['item'];self.selected.append(self.hand)
  if op=='projection_batch_set':self.masks.append(kwargs['positions'])
  if op=='projection_batch_clear':self.clears+=1
  return {'phase':'done'}
 def request(self,op,**kwargs):
  self.serial+=1;self.last='r%d'%self.serial
  if op=='projection_audit':return {'projection_audit':{'placement_key':'p','matched':int(self.matched),'mismatches':[]if self.matched else[self.row]}}
  if op=='scan':return {'blocks':[{'pos':[1,3,5]if self.item=='minecraft:light_gray_banner'else[2,4,5],'state':'Block{minecraft:stone}','fluid':False}]}
  if op!='professional_print':raise AssertionError(op)
  self.prints+=1;self.rev+=1
  r={'id':self.last,'world_session':self.world,'control_revision':self.rev,'op':op,'phase':'waiting',
     'detail':'printer interval ended without complete current bounded-mask server confirmation',
     'professional_printer':{'last_proposal':{},'failure':'','server_confirmed':0,'fast_proposals':0,'complex_proposals':0,'travel_pending':0,'owned':False,'enabled':False,'waiting_for_server':False}}
  if self.mode=='unknown':r['professional_printer']['waiting_for_server']=True
  if self.mode=='forged':r['phase']='done'
  if self.mode=='done':
   self.matched=True;self.count=0;r.update(phase='done',server_confirmed=True,outcome_pending=False,confirmation_scope='current_bounded_mask_distinct_exact_final_server_updates',full_projection_confirmed=False,bounded_targets=[self.target],bounded_target_count=1,placement_key='p')
  return r
if __name__=='__main__':unittest.main()
