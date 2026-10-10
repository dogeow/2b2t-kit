import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from lighting_reachable_edges import edge_candidates,ray_clear,observed_exit_route,exterior_surface_support,replaceable_short_grass,interaction_surface,blocking_lighting_entities,verified_native_guard_binding,air_light_reach
from lighting_cli import safe_noncolliding_plant,floor_step_lift,LightingBlocked

def floor(pos):
 return {'pos':list(pos),'state':'Block{minecraft:dirt}','solid':True,'fluid':False,
 'passable':False,'replaceable':False,'block_entity':False,'zombie_spawn_floor':True,
 'zombie_block_light_risk':True,'spawn_block_light':0,'monster_spawn_block_light_limit':0}

class EdgeLightingTests(unittest.TestCase):
 def test_surface_torches_cannot_light_a_pocket_through_a_solid_roof(self):
  low=[-4,60,-4];high=[4,72,4];dark=(0,60,0)
  cells={dark:{**floor(dark),'state':'Block{minecraft:oak_planks}'}}
  for x in range(-4,5):
   for z in range(-4,5):
    p=(x,63,z);cells[p]={**floor(p),'zombie_block_light_risk':False,'spawn_block_light':2}
  self.assertNotIn((0,64,0),air_light_reach(cells,[dark],low,high))
  self.assertEqual([],edge_candidates(cells,low,high,[.5,70,.5]))
 def test_a_real_opening_can_connect_different_floor_heights(self):
  low=[-4,60,-4];high=[4,72,4];dark=(0,60,0)
  cells={dark:floor(dark)}
  for x in range(-4,5):
   for z in range(-4,5):
    if (x,z)==(2,0):continue
    p=(x,63,z);cells[p]={**floor(p),'zombie_block_light_risk':False,'spawn_block_light':2}
  self.assertIn((0,64,0),air_light_reach(cells,[dark],low,high))
 def test_light_planning_stays_inside_complete_scan_and_torch_range(self):
  dark=(0,60,0);cells={dark:floor(dark)}
  reachable=air_light_reach(cells,[dark],[0,60,0],[20,61,0])
  self.assertIn((13,61,0),reachable);self.assertNotIn((14,61,0),reachable)
  self.assertNotIn((-1,61,0),reachable);self.assertNotIn((0,62,0),reachable)
 def test_zero_measured_improvement_does_not_spend_the_rest_of_the_batch(self):
  from unittest.mock import patch
  from lighting_reachable_edges import ReachableEdgeLightingRun
  run=ReachableEdgeLightingRun.__new__(ReachableEdgeLightingRun)
  run.reject_unknown_intents=Mock();run.limit=8;run.low=[0,60,0];run.high=[1,70,1]
  run.c=SimpleNamespace(world='w');run.scan=Mock(return_value={'scan_entities':[]})
  counts={'unprotected_dark_floor':30};run.counts=Mock(return_value=counts)
  run.protected=[];run.report={};run.save=Mock();run.fresh=Mock(return_value={'pos':[.5,65,.5]})
  run.surface_only=False;run.place_edge=Mock()
  with patch('lighting_reachable_edges.scan_cells',return_value={}),\
       patch('lighting_reachable_edges.edge_candidates',return_value=[{'support':[0,60,0]}]):
   run.work()
  self.assertEqual(1,run.place_edge.call_count)
  self.assertEqual(30,run.report['remaining_unprotected_risk'])
  self.assertFalse(run.report['placement_without_light_progress']['further_placements_sent'])
 def test_guard_displacement_after_selection_reapproaches_once_before_any_use_intent(self):
  from lighting_reachable_edges import ReachableEdgeLightingRun
  station=[.5,67.3,.5];rows=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(36)]
  rows[0].update(item='minecraft:torch',count=8);good={'pos':station,'inventory':rows}
  displaced={**good,'pos':[.5,72,.5]}
  run=ReachableEdgeLightingRun.__new__(ReachableEdgeLightingRun);run.report={};run.save=Mock()
  run.c=SimpleNamespace(checked=Mock());run.approach_edge_station=Mock()
  run.wait_for_guard=Mock(side_effect=[good,good,displaced,displaced,good,good])
  self.assertIs(good,run.ready_edge_station({'station':station},0))
  self.assertEqual(2,run.approach_edge_station.call_count)
  self.assertEqual(2,run.c.checked.call_count)
  self.assertTrue(all(c.args[0]=='select_item'for c in run.c.checked.call_args_list))
  self.assertFalse(run.report['station_replans'][0]['placement_intent_created'])
 def test_repeated_guard_displacement_or_empty_torch_stock_never_uses_an_item(self):
  from lighting_reachable_edges import ReachableEdgeLightingRun
  station=[.5,67.3,.5];rows=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(36)]
  rows[0].update(item='minecraft:torch',count=8);good={'pos':station,'inventory':rows}
  bad={**good,'pos':[.5,72,.5]}
  run=ReachableEdgeLightingRun.__new__(ReachableEdgeLightingRun);run.report={};run.save=Mock()
  run.c=SimpleNamespace(checked=Mock());run.approach_edge_station=Mock()
  run.wait_for_guard=Mock(side_effect=[good,good,bad,bad,good,bad])
  with self.assertRaises(LightingBlocked):run.ready_edge_station({'station':station},0)
  self.assertEqual(2,run.approach_edge_station.call_count)
  self.assertTrue(all(c.args[0]=='select_item'for c in run.c.checked.call_args_list))
 def test_explicit_exact_model_support_can_light_wood_without_relaxing_default_policy(self):
  from projection_scene_lights import matching_map_support
  pos=(0,64,0);row={**floor(pos),'state':'Block{minecraft:oak_planks}'};cells={pos:row}
  lo=[-4,58,-4];hi=[4,90,4];start=[.5,80,.5]
  self.assertEqual([],edge_candidates(cells,lo,hi,start))
  expected={pos:row['state']};policy=lambda r,dark:matching_map_support(r,expected,64,dark)
  self.assertTrue(edge_candidates(cells,lo,hi,start,support_predicate=policy))
  self.assertEqual([],edge_candidates(cells,lo,hi,start,support_predicate=lambda r,d:None))
 def test_flat_target_neighbour_lights_do_not_fall_back_to_a_lower_floor(self):
  target=(0,64,0);lower=(-3,63,0)
  cells={target:{**floor(target),'state':'Block{minecraft:oak_planks}'},
         lower:{**floor(lower),'zombie_block_light_risk':False,'spawn_block_light':3}}
  planned=edge_candidates(cells,[-5,58,-5],[5,90,5],[.5,80,.5],
      target_bounds={'min':[0,64,0],'max':[0,64,0]})
  self.assertEqual([],planned)
 def test_targeted_dark_floor_can_use_a_lit_support_farther_from_hostiles(self):
  dark=(0,64,0);lit=(-9,64,0)
  cells={dark:floor(dark),lit:{**floor(lit),'zombie_block_light_risk':False,'spawn_block_light':3}}
  mob={'type':'minecraft:zombie','alive':True,'hostile':True,'pos':[2.5,65,.5],
       'bounds':{'min':[2.2,65,.2],'max':[2.8,66.95,.8]}}
  planned=edge_candidates(cells,[-13,62,-4],[5,90,4],[.5,80,.5],entities=[mob],
      target_bounds={'min':[0,62,0],'max':[0,90,0]},hostile_clearance=12)
  self.assertTrue(planned);self.assertTrue(all(r['support']==list(lit)and r['lit_neighbour']for r in planned))
  self.assertTrue(all(__import__('math').hypot(r['station'][0]-2.5,r['station'][2]-.5)>=12 for r in planned))
 def test_targeted_scan_does_not_rank_unrelated_dark_support_as_the_goal(self):
  cells={(0,64,0):floor((0,64,0)),(12,64,0):floor((12,64,0))}
  planned=edge_candidates(cells,[-4,62,-4],[16,90,4],[.5,80,.5],
      target_bounds={'min':[-1,62,-1],'max':[1,90,1]})
  self.assertTrue(planned);self.assertTrue(all(r['support']==[0,64,0]for r in planned))
 def test_hostile_clearance_and_target_bounds_reject_unknown_scope(self):
  for value in (True,-1,41,float('nan')):
   with self.assertRaises(ValueError):edge_candidates({},[-4,62,-4],[4,90,4],[.5,80,.5],hostile_clearance=value)
  with self.assertRaises(ValueError):edge_candidates({},[-4,62,-4],[4,90,4],[.5,80,.5],target_bounds={'min':[-5,62,-4],'max':[4,90,4]})
 def test_native_guard_binding_accepts_only_verified_host_engine_pairs(self):
  state={'kit_version':'2026.10.9.2','runtime_version':'1.7.89','runtime_host_api':3,'guard_busy':False}
  self.assertTrue(verified_native_guard_binding(state))
  self.assertTrue(verified_native_guard_binding({**state,'runtime_version':'1.7.88'}))
  self.assertFalse(verified_native_guard_binding({**state,'kit_version':'2026.10.9.1'}))
  self.assertTrue(verified_native_guard_binding({**state,'runtime_version':'1.7.90'}))
  self.assertTrue(verified_native_guard_binding({**state,'runtime_version':'1.7.91'}))
  self.assertTrue(verified_native_guard_binding({**state,'runtime_version':'1.7.92'}))
  self.assertFalse(verified_native_guard_binding({**state,'runtime_version':'1.7.93'}))
  self.assertTrue(verified_native_guard_binding({**state,'kit_version':'2026.10.10.1','runtime_version':'1.7.95'}))
  self.assertTrue(verified_native_guard_binding({**state,'kit_version':'2026.10.10.1','runtime_version':'1.7.96'}))
  self.assertFalse(verified_native_guard_binding({**state,'kit_version':'2026.10.10.1','runtime_version':'1.7.97'}))
 def test_native_guard_binding_rejects_missing_or_untyped_busy_signal(self):
  state={'kit_version':'2026.10.9.2','runtime_version':'1.7.89','runtime_host_api':3}
  for value in (None,0,1,'false'):
   self.assertFalse(verified_native_guard_binding({**state,'guard_busy':value}))
  self.assertFalse(verified_native_guard_binding(state))
  self.assertFalse(verified_native_guard_binding(None))
 def test_elevated_station_preserves_normal_reach_and_current_clear_route(self):
  cells={(0,64,0):floor((0,64,0))}
  planned=edge_candidates(cells,[-4,62,-4],[4,90,4],[2.5,80,.5],station_height=3.3)
  self.assertTrue(planned)
  self.assertTrue(all(abs(row['station'][1]-67.3)<.0001 for row in planned))
  self.assertTrue(all(ray_clear(cells,[row['station'][0],row['station'][1]+1.42,row['station'][2]],(0,64,0))for row in planned))
 def test_elevated_station_cannot_cross_an_observed_low_ceiling(self):
  cells={(0,64,0):floor((0,64,0))}
  cells.update({(x,67,z):floor((x,67,z))for x in range(-4,5)for z in range(-4,5)})
  planned=edge_candidates(cells,[-4,62,-4],[4,90,4],[2.5,80,.5],station_height=3.3)
  self.assertFalse(any(row['support']==[0,64,0]for row in planned))
 def test_station_height_cannot_extend_reach_or_use_untyped_values(self):
  for value in (0,3.31,True,float('nan'),'3.3'):
   with self.assertRaises(ValueError):edge_candidates({},[-4,62,-4],[4,90,4],[2.5,80,.5],station_height=value)
 def test_station_selection_avoids_a_real_passive_animal_before_flying_to_it(self):
  cells={(0,64,0):floor((0,64,0))};low=[-4,62,-4];high=[4,90,4];start=[2.5,80,.5]
  first=edge_candidates(cells,low,high,start)[0]['station']
  cow={'type':'minecraft:cow','alive':True,'hostile':False,
       'bounds':{'min':[first[0]-.45,65,first[2]-.45],'max':[first[0]+.45,66.4,first[2]+.45]}}
  planned=edge_candidates(cells,low,high,start,entities=[cow])
  self.assertTrue(planned);self.assertNotEqual(planned[0]['station'],first)
  self.assertEqual(edge_candidates(cells,low,high,start,entities=[{'type':'minecraft:cow'}]),[])
 def test_real_drop_beside_torch_face_does_not_block_normal_block_interaction(self):
  item={'type':'minecraft:item','alive':True,'hostile':False,
        'pos':[760810.1187,75.,798071.5811]}
  orb={**item,'type':'minecraft:experience_orb'}
  self.assertEqual(blocking_lighting_entities([item,orb]),[])
  for kind in ('minecraft:zombie','minecraft:cow','minecraft:player','minecraft:armor_stand'):
   row={**item,'type':kind}
   self.assertEqual(blocking_lighting_entities([row]),[row])
 def test_unknown_or_contradictory_drop_details_remain_blocking(self):
  for row in ({'type':'minecraft:item'},None,{'type':'minecraft:item','alive':True,'hostile':True},
              {'type':'minecraft:experience_orb','alive':'true','hostile':False}):
   self.assertEqual(blocking_lighting_entities([row]),[row])
  with self.assertRaises(LightingBlocked):blocking_lighting_entities(None)
 def test_intermediate_short_grass_is_a_ray_obstacle_even_when_walkable(self):
  grass={'pos':[1,65,0],'state':'Block{minecraft:short_grass}','passable':True,'solid':False,'fluid':False,'block_entity':False,'replaceable':True}
  self.assertFalse(ray_clear({(1,65,0):grass},[2.5,66.52,.5],(0,64,0)))
 def test_native_interaction_clicks_replaceable_grass_instead_of_hidden_soil_face(self):
  support=(0,64,0);target=(0,65,0)
  grass={'state':'Block{minecraft:short_grass}','passable':True,'solid':False,'fluid':False,'block_entity':False,'replaceable':True}
  cells={support:floor(support),target:grass}
  self.assertEqual(interaction_surface(cells,support,target),([0,65,0],'Block{minecraft:short_grass}'))
  self.assertEqual(interaction_surface({support:floor(support)},support,target),([0,64,0],'Block{minecraft:dirt}'))
 def test_spawnable_log_can_be_lit_from_neighbouring_soil_without_replacing_log(self):
  log={**floor((0,67,0)),'state':'Block{minecraft:cherry_log}[axis=y]'}
  soil={**floor((1,64,0)),'zombie_block_light_risk':False,'spawn_block_light':2}
  cells={(0,67,0):log,(1,64,0):soil}
  candidates=edge_candidates(cells,[-4,62,-4],[4,90,4],[2.5,80,.5],surface_only=True)
  self.assertTrue(candidates);self.assertTrue(all(v['support']==[1,64,0]and v['lit_neighbour']for v in candidates))
 def test_known_noncolliding_grass_is_walkable_but_tall_grass_can_occlude_ray(self):
  p=(0,63,0);grass={**floor(p),'state':'Block{minecraft:short_grass}','passable':True,'solid':False,'zombie_spawn_floor':False,'zombie_block_light_risk':False}
  self.assertIsNotNone(observed_exit_route({p:grass},[.5,63.1,.5],[-2,62,-2],[2,70,2]))
  tall={**grass,'state':'Block{minecraft:tall_grass}[half=upper]'}
  self.assertFalse(ray_clear({(1,64,0):tall},[2.5,65.5,.5],(0,63,0)))
 def test_surface_mode_keeps_leaf_covered_ground_separate_from_underground_pockets(self):
  p=(0,62,0);leaf={**floor((0,68,0)),'state':'Block{minecraft:cherry_leaves}[distance=3,persistent=false,waterlogged=false]'}
  self.assertTrue(exterior_surface_support({p:floor(p),(0,68,0):leaf},p))
  self.assertFalse(exterior_surface_support({p:floor(p),(0,65,0):floor((0,65,0))},p))
 def test_only_explicitly_replaceable_short_grass_can_be_a_torch_target(self):
  grass={'state':'Block{minecraft:short_grass}','passable':True,'solid':False,'fluid':False,'block_entity':False,'replaceable':True}
  self.assertTrue(replaceable_short_grass(grass))
  self.assertFalse(replaceable_short_grass({**grass,'replaceable':False}))
  self.assertFalse(replaceable_short_grass({**grass,'state':'Block{minecraft:dandelion}'}))
 def test_actual_hover_undershoot_can_lift_before_neighbouring_higher_floor(self):
  row=floor((760822,65,797908));start=[760821.534,65.909,797908.499]
  self.assertEqual(floor_step_lift([row],start,[760822.5,66.1,797908.5]),[start[0],66.195,start[2]])
  self.assertIsNone(floor_step_lift([row],[760822.5,65.909,797908.5],[760823.5,66.1,797908.5]))
  self.assertIsNone(floor_step_lift([row],start,[760822.5,65.1,797908.5]))
  self.assertIsNone(floor_step_lift([{**row,'fluid':True}],start,[760822.5,66.1,797908.5]))
 def test_current_short_grass_can_be_crossed_without_treating_solid_or_fluid_as_air(self):
  plant={'state':'Block{minecraft:short_grass}','passable':True,'solid':False,'fluid':False,'block_entity':False}
  self.assertTrue(safe_noncolliding_plant(plant))
  for change in ({'solid':True},{'fluid':True},{'passable':False},{'block_entity':True},{'state':'Block{minecraft:cobweb}'},{'state':'Block{minecraft:torch}'}):
   self.assertFalse(safe_noncolliding_plant({**plant,**change}))
 def test_roofed_floor_can_use_open_side_column(self):
  cells={(0,62,0):floor((0,62,0)),(0,65,0):floor((0,65,0))}
  candidates=edge_candidates(cells,[-4,60,-4],[4,90,4],[2.5,80,.5])
  self.assertTrue(any(r['support']==[0,62,0] for r in candidates))
  r=next(r for r in candidates if r['support']==[0,62,0]);self.assertNotEqual(r['station'][::2],[.5,.5])
 def test_occupied_target_cannot_be_replaced(self):
  cells={(0,62,0):floor((0,62,0)),(0,63,0):floor((0,63,0))}
  self.assertFalse(any(r['support']==[0,62,0] for r in edge_candidates(cells,[-4,60,-4],[4,90,4],[2.5,80,.5])))
 def test_protected_floor_is_excluded(self):
  cells={(0,62,0):floor((0,62,0))};protected=[{'min':[-1,60,-1],'max':[1,319,1]}]
  self.assertEqual(edge_candidates(cells,[-4,60,-4],[4,90,4],[2.5,80,.5],protected),[])
 def test_wall_blocks_ray_and_long_reach_is_rejected(self):
  cells={(0,62,0):floor((0,62,0)),(1,63,0):floor((1,63,0)),(1,64,0):floor((1,64,0))}
  self.assertFalse(ray_clear(cells,[2.5,64.72,.5],(0,62,0)))
  self.assertFalse(ray_clear({},[10.5,64.72,.5],(0,62,0)))
 def test_two_block_tunnel_has_axis_route_to_known_exit(self):
  cells={(x,65,z):floor((x,65,z))for x in range(-1,2)for z in range(-1,2)}
  route=observed_exit_route(cells,[.5,63.1,.5],[-3,62,-3],[3,70,3])
  self.assertIsNotNone(route);self.assertEqual(route[-1],[.5,63.1,.5])
  self.assertTrue(all(sum(a[i]!=b[i]for i in range(3))==1 for a,b in zip(route,route[1:])))
 def test_sealed_room_has_no_speculative_exit(self):
  cells={(x,y,z):floor((x,y,z))for x in range(-1,2)for y in range(62,67)for z in range(-1,2)if (x,y,z)not in [(0,63,0),(0,64,0)]}
  self.assertIsNone(observed_exit_route(cells,[.5,63.1,.5],[-2,62,-2],[2,70,2]))
if __name__=='__main__':unittest.main()
