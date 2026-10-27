import copy,unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from projection_footer_pit import validate,BRICK,STONE,AIR,restore_plain_brick_after_zero,restore_original_ladder_after_zero

class FooterPitValidationTest(unittest.TestCase):
 def test_unknown_original_ladder_use_is_never_repeated(self):
  p=[1,61,1];wanted='Block{minecraft:ladder}[facing=east,waterlogged=false]';zero={'known_not_sent':True,'target':p,'remaining':{'expected':wanted,'actual':AIR}}
  c=SimpleNamespace(status=lambda:{'inventory':[{'slot':0,'item':'minecraft:ladder','count':1,'max_stack':64}]},checked=Mock(),request=Mock(return_value={'phase':'waiting'}))
  def cell(_c,pos):return {'state':AIR}if pos==p else{'state':STONE,'solid':True,'fluid':False,'block_entity':False}
  with tempfile.TemporaryDirectory()as d,patch('projection_footer_pit.cell_at',side_effect=cell),self.assertRaisesRegex(RuntimeError,'unconfirmed'):
   restore_original_ladder_after_zero(c,p,zero,Path(d)/'ladder',lambda:None)
  self.assertEqual(1,c.request.call_count)

 def test_ordinary_restore_needs_genuine_known_zero_classification(self):
  with tempfile.TemporaryDirectory()as d,self.assertRaisesRegex(RuntimeError,'zero-proposal'):
   restore_plain_brick_after_zero(None,[1,60,1],{'known_not_sent':False},Path(d)/'proof',lambda:None)
 def test_unknown_ordinary_restore_never_tries_a_second_support(self):
  p=[1,60,1];zero={'known_not_sent':True,'target':p,'remaining':{'expected':BRICK,'actual':AIR}}
  c=SimpleNamespace(status=lambda:{'inventory':[{'slot':0,'item':'minecraft:stone_bricks','count':1,'max_stack':64}]},checked=Mock(),request=Mock(return_value={'phase':'waiting','id':'unknown'}))
  def cell(_c,pos):return {'state':AIR}if pos==p else{'state':STONE,'solid':True,'fluid':False,'block_entity':False}
  with tempfile.TemporaryDirectory()as d,patch('projection_footer_pit.cell_at',side_effect=cell),self.assertRaisesRegex(RuntimeError,'unknown'):
   restore_plain_brick_after_zero(c,p,zero,Path(d)/'restore',lambda:None)
  self.assertEqual(1,c.request.call_count)

 def setUp(self):
  self.plan={'pit':[1,60,1],'goals':[[1,60,2]]}
  self.model={'loaded_chunks_verified':True,'bounds':{'min':[0,60,0]},'expected':[{'pos':[1,60,1],'state':BRICK},{'pos':[1,60,2],'state':BRICK}]}
  self.rows=[{'pos':p,'state':s,'solid':True,'fluid':False,'block_entity':False}for p,s in (([1,60,1],BRICK),([1,60,2],STONE),([1,59,1],STONE),([1,58,1],STONE))]
 def test_dry_original_floor_and_adjacent_footer_have_a_bounded_access_plan(self):
  expected,cells=validate(self.model,self.rows,self.plan);self.assertEqual(BRICK,expected[(1,60,2)])
 def test_adjacent_water_or_container_prevents_any_excavation(self):
  for extra in ({'pos':[2,60,2],'fluid':True},{'pos':[1,60,1],'state':BRICK,'fluid':False,'block_entity':True}):
   with self.subTest(extra=extra),self.assertRaises(RuntimeError):validate(self.model,self.rows+[extra],self.plan)
 def test_no_pit_under_original_furniture_or_through_an_ore_vein(self):
  for extra in ({'pos':[1,61,1],'state':'Block{minecraft:bookshelf}'},{'pos':[1,59,1],'state':'Block{minecraft:iron_ore}','solid':True,'fluid':False,'block_entity':False}):
   with self.subTest(extra=extra),self.assertRaises(RuntimeError):validate(self.model,self.rows+[extra],self.plan)
 def test_user_changed_floor_and_out_of_reach_target_are_rejected(self):
  with self.assertRaises(RuntimeError):validate(self.model,self.rows+[{'pos':[1,60,1],'state':'Block{minecraft:oak_planks}','fluid':False,'block_entity':False}],self.plan)
  with self.assertRaises(RuntimeError):validate(self.model,self.rows,{**self.plan,'goals':[[4,60,4]]})
 def test_original_ladder_can_be_temporarily_removed_but_not_an_unmodelled_block(self):
  model=copy.deepcopy(self.model);ladder='Block{minecraft:ladder}[facing=east,waterlogged=false]'
  model['expected'].append({'pos':[1,61,1],'state':ladder});rows=self.rows+[{'pos':[1,61,1],'state':ladder,'fluid':False,'block_entity':False}]
  validate(model,rows,{**self.plan,'temporary':[[1,61,1]]})
  with self.assertRaises(RuntimeError):validate(self.model,rows,{**self.plan,'temporary':[[1,61,1]]})

if __name__=='__main__':unittest.main()
