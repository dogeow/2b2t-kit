import unittest
from lighting_reachable_edges import edge_candidates,ray_clear,observed_exit_route,exterior_surface_support,replaceable_short_grass
from lighting_cli import safe_noncolliding_plant,floor_step_lift

def floor(pos):
 return {'pos':list(pos),'state':'Block{minecraft:dirt}','solid':True,'fluid':False,
 'passable':False,'replaceable':False,'block_entity':False,'zombie_spawn_floor':True,
 'zombie_block_light_risk':True,'spawn_block_light':0,'monster_spawn_block_light_limit':0}

class EdgeLightingTests(unittest.TestCase):
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
