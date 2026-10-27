import unittest
from material_jobs.glow_cave_hunt import component,points_for,spawn_wait_poses,spawn_viewpoints,follow,supported_recenter
class DryCaveGraphTest(unittest.TestCase):
 def test_full_grid_keeps_odd_coordinate_wait_positions_in_a_narrow_cave(self):
  parents={(1,17,1):None,(28,17,1):None}
  water=[{'pos':[28,16,1],'state':'Block{minecraft:water}','block_light':0,'sky_light':0}]
  self.assertEqual([],spawn_viewpoints(parents,water,[1.5,17.1,1.5]))
  ranked=spawn_viewpoints(parents,water,[1.5,17.1,1.5],grid=1)
  self.assertEqual([1.5,17.1,1.5],ranked[0]['point'])
  self.assertEqual(1,ranked[0]['huntable_dark_spawn_cells_25_to_32'])
 def test_viewpoint_counts_only_dark_surface_cells_with_reachable_dry_air(self):
  parents={(x,26,0):None for x in range(41)}
  water=[{'pos':[x,25,0],'state':'Block{minecraft:water}','block_light':0,'sky_light':0}for x in(28,29,30)]
  ranked=spawn_viewpoints(parents,water,[.5,26.1,.5])
  self.assertEqual(3,next(v for v in ranked if v['point']==[.5,26.1,.5])['huntable_dark_spawn_cells_25_to_32'])
  parents.pop((30,26,0));ranked=spawn_viewpoints(parents,water,[.5,26.1,.5])
  self.assertEqual(2,next(v for v in ranked if v['point']==[.5,26.1,.5])['huntable_dark_spawn_cells_25_to_32'])
  with self.assertRaises(ValueError):spawn_viewpoints(parents,[{**water[0],'block_light':1}],[.5,26.1,.5])
  floor={'pos':[0,25,0],'solid':True,'fluid':False,'block_entity':False}
  supported=spawn_viewpoints(parents,water,[.5,26.1,.5],floor_rows=[floor])
  self.assertEqual([[.5,26.1,.5]],[v['point']for v in supported]);self.assertTrue(supported[0]['solid_floor_verified'])
  self.assertEqual([],spawn_viewpoints(parents,water,[.5,26.1,.5],floor_rows=[{**floor,'fluid':True}]))
 def test_air_above_or_beside_lava_is_excluded_despite_clear_body_cells(self):
  row={'pos':[0,24,0],'state':'Block{minecraft:lava}[level=0]'}
  parents=component([row],[-3,23,-3],[3,30,3],[2.5,26.1,.5])
  self.assertNotIn((0,25,0),parents);self.assertNotIn((1,25,0),parents)
  self.assertNotIn((0,26,0),parents)
  with self.assertRaisesRegex(RuntimeError,'hazard clearance'):component([row],[-3,23,-3],[3,30,3],[.5,25.1,.5])
 def test_lava_four_blocks_below_still_excludes_an_exposed_descent_column(self):
  lava={'pos':[0,4,0],'state':'Block{minecraft:lava}[level=4]','fluid':True,'solid':False}
  low=[-3,3,-3];high=[3,18,3];start=[2.5,16.1,.5]
  exposed=component([lava],low,high,start)
  self.assertNotIn((0,8,0),exposed);self.assertNotIn((0,16,0),exposed)
  with self.assertRaisesRegex(RuntimeError,'hazard clearance'):component([lava],low,high,[.5,8.1,.5])
  floor={'pos':[0,7,0],'state':'Block{minecraft:stone}','solid':True,'fluid':False,'block_entity':False}
  roof=[{**floor,'pos':[x,7,z]}for x in(-1,0,1)for z in(-1,0,1)]
  covered=component([lava,*roof],low,high,start)
  self.assertIn((0,8,0),covered)
  for change in ({'solid':False},{'fluid':True},{'block_entity':True}):
   self.assertNotIn((0,8,0),component([lava,*[{**r,**change}for r in roof]],low,high,start))
 def test_only_lit_campfires_exclude_nearby_air_and_unknown_edges_are_not_clear(self):
  base={'pos':[0,24,0],'state':'Block{minecraft:campfire}[lit=false]'}
  self.assertIn((0,25,0),component([base],[-3,23,-3],[3,30,3],[2.5,26.1,.5]))
  self.assertNotIn((0,25,0),component([{**base,'state':base['state'].replace('false','true')}],[-3,23,-3],[3,30,3],[2.5,26.1,.5]))
  with self.assertRaises(RuntimeError):component([],[-3,23,-3],[3,30,3],[-2.5,26.1,.5])
 def test_actual_water_and_stone_stay_blocked_while_air_above_can_be_reached(self):
  rows=[{'pos':[0,24,0],'state':'Block{minecraft:water}[level=0]','fluid':True},{'pos':[1,24,0],'state':'Block{minecraft:stone}'}]
  parents=component(rows,[-1,24,-1],[2,29,2],[.5,26.1,.5])
  self.assertNotIn((0,24,0),parents);self.assertNotIn((1,24,0),parents);self.assertIn((0,25,0),parents)
  poses=points_for(parents,{'pos':[.5,24.5,.5]});self.assertTrue(poses)
  self.assertTrue(all((int(p[0]//1),int(p[1]//1),int(p[2]//1))in parents for p in poses))
 def test_unconfirmed_start_never_becomes_an_air_route(self):
  with self.assertRaisesRegex(RuntimeError,'not fully observed'):component([{'pos':[0,25,0]}],[-1,24,-1],[2,29,2],[.5,25.1,.5])
 def test_spawn_wait_excludes_every_water_cell_and_keeps_pool_in_range(self):
  rows=[{'pos':[0,25,0],'state':'Block{minecraft:water}'},{'pos':[4,25,0],'state':'Block{minecraft:water}'}]
  parents={(x,26,0):None for x in (10,28,30,99)}
  self.assertEqual(spawn_wait_poses(parents,rows,[10.5,26.1,.5]),[[30.5,26.1,.5]])
 def test_cache_or_nonwater_row_cannot_define_spawn_wait(self):
  with self.assertRaises(ValueError):spawn_wait_poses({(30,26,0):None},[{'pos':[0,25,0],'state':'Block{minecraft:stone}'}],[30.5,26.1,.5])
 def test_invalid_step_rejected_before_any_navigation(self):
  with self.assertRaises(ValueError):follow(None,{},None,None,None,max_straight=0)
 def test_hover_recenter_needs_current_full_natural_floor_and_two_air_cells(self):
  floor={'pos':[0,10,0],'state':'Block{minecraft:stone}','solid':True,'fluid':False,'block_entity':False}
  self.assertEqual([.5,11.,.5],supported_recenter([floor],[.704,11.095,.61]))
  for change in ({'solid':False},{'fluid':True},{'block_entity':True},{'state':'Block{minecraft:magma_block}'}):self.assertIsNone(supported_recenter([{**floor,**change}],[.704,11.095,.61]))
  self.assertIsNone(supported_recenter([floor],[.704,11.3,.61]))
  self.assertIsNone(supported_recenter([floor,{'pos':[0,12,0]}],[.704,11.095,.61]))
 def test_short_cave_legs_also_bound_fresh_local_detours(self):
  from pathlib import Path
  from types import SimpleNamespace
  from unittest.mock import patch
  import tempfile
  parents={(0,0,0):None,(1,0,0):(0,0,0),(2,0,0):(1,0,0),(3,0,0):(2,0,0)}
  with tempfile.TemporaryDirectory()as d,patch('material_jobs.glow_cave_hunt.move')as move:
   follow(SimpleNamespace(world='w'),parents,[3.5,.1,.5],Path(d)/'route',lambda:{'pos':[.5,.1,.5]},max_straight=2)
   self.assertEqual([2,2],[v.kwargs['max_straight']for v in move.call_args_list])
