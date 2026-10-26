import unittest
from roof_slab_window_plan import choices,SLAB

def row(state=SLAB):return {'state':state,'fluid':False,'block_entity':False}
class RoofPlanTest(unittest.TestCase):
 def fixture(self):
  expected={(x,72,z):SLAB for x in range(-1,4)for z in range(4)}
  observed={(-1,72,z):row()for z in range(4)}
  return expected,observed
 def test_full_and_perimeter_windows_remain_inside_exact_model_and_count(self):
  e,o=self.fixture();first=choices(e,o,[2,74.1,2],grid_origin=[0,0])[0]
  self.assertEqual(16,first['count']);self.assertEqual({(x,72,z)for x in range(4)for z in range(4)},set(map(tuple,first['positions'])))
  del e[(3,72,3)];del e[(3,72,2)];self.assertEqual(14,choices(e,o,[2,74.1,2],grid_origin=[0,0])[0]['count'])
 def test_never_overwrites_occupied_wrong_or_wet_cells(self):
  e,o=self.fixture();o[(1,72,1)]=row('Block{minecraft:oak_leaves}');o[(2,72,2)]={'state':'Block{minecraft:water}','fluid':True,'block_entity':False};e[(3,72,3)]='Block{minecraft:glass}'
  mask=set(map(tuple,choices(e,o,[2,74.1,2],grid_origin=[0,0])[0]['positions']))
  self.assertFalse(mask & {(1,72,1),(2,72,2),(3,72,3)})
 def test_does_not_jump_to_unsupported_isolated_cells(self):
  e,o=self.fixture();o.clear();self.assertEqual([],choices(e,o,[2,74.1,2],grid_origin=[0,0]))
  o[(-1,72,0)]=row();o[(1,72,0)]=row('Block{minecraft:stone}');o[(0,72,1)]=row('Block{minecraft:stone}')
  self.assertEqual([[0,72,0]],choices(e,o,[2,74.1,2],grid_origin=[0,0])[0]['positions'])
 def test_header_obstruction_unknown_or_wet_anchor_prevents_printing(self):
  e,o=self.fixture();o[(1,74,1)]=row('Block{minecraft:oak_leaves}');self.assertEqual([],choices(e,o,[2,74.1,2],grid_origin=[0,0]))
  for bad in [{'state':SLAB},{'state':SLAB,'fluid':True,'block_entity':False},{'state':SLAB,'fluid':False,'block_entity':True}]:
   e,o=self.fixture();o={p:bad for p in o};self.assertEqual([],choices(e,o,[2,74.1,2],grid_origin=[0,0]))
 def test_last_inventory_batch_can_be_smaller_without_duplicate_targets(self):
  e,o=self.fixture();p=choices(e,o,[2,74.1,2],grid_origin=[0,0],limit=5)[0];self.assertEqual(5,len(set(map(tuple,p['positions']))))

 def test_verified_model_double_slab_seeds_a_bottom_slab_across_the_seam(self):
  double='Block{minecraft:cobblestone_slab}[type=double,waterlogged=false]'
  e={(-1,72,0):double,(0,72,0):SLAB,(1,72,0):SLAB}
  o={(-1,72,0):row(double)}
  result=choices(e,o,[2,74.1,2],grid_origin=[0,0])[0]
  self.assertEqual([[0,72,0],[1,72,0]],result['positions'])
  for bad in [row(),row('Block{minecraft:stone}'),{'state':double,'fluid':True,'block_entity':False},{'state':double,'fluid':False,'block_entity':True}]:
   with self.subTest(bad=bad):self.assertEqual([],choices(e,{(-1,72,0):bad},[2,74.1,2],grid_origin=[0,0]))
 def test_a_foreign_double_slab_cannot_seed_an_unsupported_model(self):
  double='Block{minecraft:cobblestone_slab}[type=double,waterlogged=false]'
  self.assertEqual([],choices({(0,72,0):SLAB},{(-1,72,0):row(double)},[2,74.1,2],grid_origin=[0,0]))
