import unittest
from roof_double_slab_plan import choices,DOUBLE,SLAB

def row(state):return {'state':state,'fluid':False,'block_entity':False}
class DoublePlanTest(unittest.TestCase):
 def plan(self,e,o,**kw):return choices(e,o,[2,74.1,0],low=[-10,70,-10],high=[10,83,10],**kw)
 def fixture(self):return {(0,72,0):DOUBLE,(-1,72,0):SLAB,(1,72,0):SLAB},{(-1,72,0):row(SLAB)}
 def test_two_ordinary_uses_add_an_empty_double_then_unlock_its_neighbor(self):
  e,o=self.fixture();p=self.plan(e,o)[0];self.assertEqual([0,72,0],p['target']);self.assertEqual(2,p['item_cost']);self.assertEqual(1,p['unlock_score'])
  self.assertEqual([[-1,72,0],[0,72,0]],[s['support']for s in p['stages']]);self.assertEqual(['east','up'],[s['face']for s in p['stages']]);self.assertEqual(DOUBLE,p['stages'][-1]['expected_after'])
 def test_matching_double_slab_is_a_real_full_side_support(self):
  e,o=self.fixture();e[(-1,72,0)]=DOUBLE;o[(-1,72,0)]=row(DOUBLE);p=self.plan(e,o)[0];self.assertEqual(2,p['item_cost']);self.assertEqual(DOUBLE,p['stages'][0]['expected_support']);self.assertEqual([-1,72,0],p['stages'][0]['support'])
 def test_existing_exact_bottom_needs_only_its_new_merge_use(self):
  e,o=self.fixture();o[(0,72,0)]=row(SLAB);p=self.plan(e,o)[0];self.assertEqual(1,p['item_cost']);self.assertEqual('up',p['stages'][0]['face'])
 def test_top_wrong_wet_container_and_completed_targets_are_never_overwritten(self):
  for bad in [row(DOUBLE),row('Block{minecraft:cobblestone_slab}[type=top,waterlogged=false]'),row('Block{minecraft:oak_log}'),{'state':SLAB,'fluid':True,'block_entity':False},{'state':SLAB,'fluid':False,'block_entity':True}]:
   e,o=self.fixture();o[(0,72,0)]=bad;self.assertEqual([],self.plan(e,o))
 def test_historical_target_and_support_protections_are_retained(self):
  e,o=self.fixture()
  for pos in [[0,72,0],[-1,72,0]]:self.assertEqual([],self.plan(e,o,protected=[pos]))
 def test_unobserved_or_foreign_support_cannot_anchor_a_new_use(self):
  e,o=self.fixture();self.assertEqual([],self.plan(e,{}));e.pop((-1,72,0));self.assertEqual([],self.plan(e,o))
 def test_roof_obstruction_and_incomplete_header_bounds_block_work(self):
  e,o=self.fixture();o[(1,75,0)]=row('Block{minecraft:oak_leaves}');self.assertEqual([],self.plan(e,o))
  e,o=self.fixture();self.assertEqual([],choices(e,o,[2,74.1,0],low=[-10,70,-10],high=[10,75,10]))

 def test_adjacent_pillar_outside_the_actual_body_does_not_block_an_exposed_face(self):
  e,o=self.fixture();o[(2,75,0)]=row('Block{minecraft:cobblestone}');self.assertEqual([0,72,0],self.plan(e,o)[0]['target'])

 def test_clear_hover_route_uses_the_whole_body_including_low_overhangs(self):
  from roof_double_slab_plan import clear_route
  a=[.5,74.1,.5];b=[4.5,74.1,.5];bounds={'low':[-1,70,-1],'high':[6,83,2]}
  self.assertTrue(clear_route(a,b,{},**bounds))
  self.assertFalse(clear_route(a,b,{(2,75,0):row('Block{minecraft:oak_leaves}')},**bounds))
  self.assertFalse(clear_route(a,b,{(2,74,0):row('Block{minecraft:stone}')},**bounds))
 def test_route_does_not_treat_unscanned_source_or_border_as_air(self):
  from roof_double_slab_plan import clear_route
  self.assertFalse(clear_route([.1,74.1,.5],[4.5,74.1,.5],{},low=[0,70,0],high=[6,83,2]))
  self.assertFalse(clear_route([.5,100,.5],[4.5,74.1,.5],{},low=[-1,70,-1],high=[6,83,2]))
  self.assertFalse(clear_route([float('nan'),74,.5],[4.5,74,.5],{},low=[-1,70,-1],high=[6,83,2]))
