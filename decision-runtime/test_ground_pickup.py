import unittest
from ground_pickup import pickup_candidates,clear_segment
class Tests(unittest.TestCase):
 def floor(self):return [{'pos':[x,61,z],'solid':True,'passable':False,'fluid':False} for x in range(9,14) for z in range(831,838)]
 def test_corner_drop_gets_fractional_pose_without_entering_low_ceiling(self):
  rows=self.floor()+[{'pos':[11,63,833],'solid':True,'passable':False,'fluid':False}]
  choices=pickup_candidates([11.6,62,835.5],[11.875,62,833.125],rows)
  self.assertTrue(choices)
  self.assertTrue(all(p[2]>=834.31 for p in choices))
  self.assertTrue(all(abs(p[2]-833.125)<=1.25 for p in choices))
 def test_gap_fluid_and_head_obstruction_disallow_walk(self):
  rows=self.floor();self.assertTrue(clear_segment([11.5,62,835.5],[11.5,62,834.35],rows))
  for change in ('gap','fluid','head'):
   r=[dict(v) for v in rows]
   if change=='gap':r=[v for v in r if v['pos']!=[11,61,834]]
   elif change=='fluid':next(v for v in r if v['pos']==[11,61,834])['fluid']=True
   else:r.append({'pos':[11,63,834],'passable':False,'solid':True,'fluid':False})
   self.assertFalse(clear_segment([11.5,62,835.5],[11.5,62,834.35],r))
 def test_supported_side_step_can_collect_a_drop_on_a_one_block_ledge(self):
  self.assertTrue(pickup_candidates([11.5,62,835.5],[12.875,63,835.125],self.floor()))
 def test_only_a_short_supported_descent_is_allowed(self):
  self.assertTrue(pickup_candidates([11.5,62.7,835.5],[11.875,62,833.125],self.floor()))
  self.assertFalse(pickup_candidates([11.5,64.2,835.5],[11.875,62,833.125],self.floor()))
 def test_live_hover_and_upper_ledge_case_can_land_without_entering_a_wall(self):
  floor=[{'pos':[x,60,z],'solid':True,'passable':False,'fluid':False} for x in range(9,15) for z in range(837,842)]
  walls=[{'pos':[x,y,840],'solid':True,'passable':False,'fluid':False} for x in range(9,15) for y in (61,62)]
  poses=pickup_candidates([12.582,61.878,839.499],[11.125,63,840.875],floor+walls)
  self.assertTrue(poses);self.assertTrue(all(p[1]==61 and p[2]<839.69 for p in poses))
 def test_passable_fire_and_hot_floor_are_rejected(self):
  rows=self.floor()+[{'pos':[11,62,834],'state':'Block{minecraft:fire}','passable':True,'solid':False,'fluid':False}]
  self.assertFalse(clear_segment([11.5,62,835.5],[11.5,62,834.35],rows))
  rows=self.floor();next(v for v in rows if v['pos']==[11,61,834])['state']='Block{minecraft:magma_block}'
  self.assertFalse(clear_segment([11.5,62,835.5],[11.5,62,834.35],rows))
if __name__=='__main__':unittest.main()
