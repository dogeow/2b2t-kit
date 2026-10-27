from unittest import TestCase
from material_jobs.aquifer_glow_hunt import route_waypoints,wait_viewpoints
from material_jobs.glow_cave_hunt import spawn_viewpoints

class AquiferWaitFloorTests(TestCase):
 def scene(self):
  parents={(0,5,0):None,(0,16,0):None,(25,17,0):None,(23,17,0):None}
  waters=[{'pos':[x,16,0],'state':'Block{minecraft:water}[level=0]',
           'block_light':0,'sky_light':0}for x in(25,23)]
  floor={'pos':[0,15,0],'state':'Block{minecraft:stone}',
         'solid':True,'fluid':False,'block_entity':False}
  return parents,waters,floor
 def test_more_spawn_coverage_cannot_choose_an_unsupported_lower_hover(self):
  parents,waters,floor=self.scene();current=[.5,16.1,.5]
  self.assertEqual([.5,5.1,.5],spawn_viewpoints(parents,waters,current,grid=1)[0]['point'])
  ranked=wait_viewpoints(parents,waters,current,[floor])
  self.assertEqual([[.5,16.1,.5]],[v['point']for v in ranked])
  self.assertTrue(ranked[0]['solid_floor_verified'])
 def test_missing_or_unsafe_wait_floor_does_not_fall_back_to_free_hover(self):
  parents,waters,floor=self.scene();current=[.5,16.1,.5]
  for rows in ([],[{**floor,'solid':False}],[{**floor,'fluid':True}],[{**floor,'block_entity':True}]):
   self.assertEqual([],wait_viewpoints(parents,waters,current,rows))

class AquiferHuntRouteTests(TestCase):
 def parents(self):return {(x,0,0):(x-1,0,0)if x else None for x in range(11)}
 def open_parents(self):return {**{(x,0,z):None for x in range(-1,12)for z in(-1,0,1)},**self.parents()}
 def test_open_tall_air_does_not_stop_every_two_blocks(self):
  path,kept=route_waypoints(self.open_parents(),[10.5,.1,.5],[])
  self.assertEqual([(0,0,0),(8,0,0),(10,0,0)],kept)
 def test_narrow_corridor_retains_two_block_precision(self):
  rows=[{'pos':[x,2,0]}for x in range(11)]
  _,kept=route_waypoints(self.parents(),[10.5,.1,.5],rows)
  self.assertEqual([0,2,4,6,8,10],[p[0]for p in kept])
 def test_headroom_is_checked_between_waypoints_not_only_at_the_goal(self):
  _,kept=route_waypoints(self.open_parents(),[10.5,.1,.5],[{'pos':[5,2,0]}])
  self.assertIn((3,0,0),kept)
  self.assertNotEqual([(0,0,0),(8,0,0),(10,0,0)],kept)
 def test_tall_but_narrow_air_does_not_admit_cruise_turn_side_drift(self):
  _,kept=route_waypoints(self.parents(),[10.5,.1,.5],[])
  self.assertEqual([0,2,4,6,8,10],[p[0]for p in kept])
