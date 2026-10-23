import unittest
from public_lectern_access import candidate,clear,direct_from_low_top_cap
S='Block{minecraft:lectern}[facing=north,has_book=false,powered=false]'
class Tests(unittest.TestCase):
 def rows(self):
  return {(0,66,13):{'state':'Block{minecraft:dark_oak_slab}[type=bottom,waterlogged=false]'},(0,67,13):{'solid':True},(0,64,12):{'solid':True,'fluid':False},(0,64,11):{'solid':True,'fluid':False}}
 def test_low_ground_top_cap_does_not_need_farther_placement_pose(self):
  rows=self.rows();rows[(0,66,13)]['state']='Block{minecraft:oak_trapdoor}[half=top,open=false,waterlogged=false]'
  self.assertTrue(direct_from_low_top_cap(rows,[.5,65,12.5],[0,65,13]))
  for origin in ([.5,65.3,12.5],[.5,65,11.5]):self.assertFalse(direct_from_low_top_cap(rows,origin,[0,65,13]))
  rows[(0,65,12)]={'state':'Block{minecraft:wall_torch}'};self.assertFalse(direct_from_low_top_cap(rows,[.5,65,12.5],[0,65,13]))
 def test_bottom_or_open_cap_keeps_existing_fallback(self):
  rows=self.rows();self.assertFalse(direct_from_low_top_cap(rows,[.5,65,12.5],[0,65,13]));rows[(0,66,13)]['state']='Block{minecraft:oak_trapdoor}[half=top,open=true,waterlogged=false]';self.assertFalse(direct_from_low_top_cap(rows,[.5,65,12.5],[0,65,13]))
 def test_close_public_operator_moves_to_witnessed_farther_placement_pose(self):
  self.assertEqual([.5,65.3,11.5],candidate([.5,65.1,12.5],[0,65,13],S));self.assertTrue(clear(self.rows(),[],[0,65,13],[.5,65.3,11.5],'p'))
 def test_private_and_already_distant_pose_are_not_redirected(self):
  for pos in ([.5,65.1,14.31],[.5,65.1,11.5],[.5,70.2,12.5]):self.assertIsNone(candidate(pos,[0,65,13],S))
 def test_obstacle_water_missing_floor_or_wrong_cap_prevents_routing(self):
  for action in ('wall','water','floor','cap'):
   rows=self.rows()
   if action=='wall':rows[(0,66,11)]={'solid':True}
   if action=='water':rows[(0,64,11)]['fluid']=True
   if action=='floor':del rows[(0,64,11)]
   if action=='cap':rows[(0,66,13)]['state']='Block{minecraft:dark_oak_slab}[type=top,waterlogged=false]'
   self.assertFalse(clear(rows,[],[0,65,13],[.5,65.1,11.5],'p'))
 def test_other_entity_in_public_path_prevents_routing(self):
  entity={'uuid':'v','type':'minecraft:villager','bounds':{'min':[.2,65,11.5],'max':[.8,67,12.1]}}
  self.assertFalse(clear(self.rows(),[entity],[0,65,13],[.5,65.1,11.5],'p'))
 def test_north_counter_mirrors_public_placement_direction(self):
  self.assertEqual([.5,65.3,15.5],candidate([.5,65.1,14.5],[0,65,13],S.replace('north','south')))
 def test_closed_top_cap_is_accepted_but_extra_headroom_is_checked(self):
  rows=self.rows();rows[(0,66,13)]['state']='Block{minecraft:oak_trapdoor}[facing=north,half=top,open=false,powered=false,waterlogged=false]'
  self.assertTrue(clear(rows,[],[0,65,13],[.5,65.3,11.5],'p'))
  rows[(0,67,11)]={'solid':True}
  self.assertFalse(clear(rows,[],[0,65,13],[.5,65.3,11.5],'p'))
  del rows[(0,67,11)];rows[(0,66,13)]['state']=rows[(0,66,13)]['state'].replace('open=false','open=true')
  self.assertFalse(clear(rows,[],[0,65,13],[.5,65.3,11.5],'p'))
if __name__=='__main__':unittest.main()

class ConsecutiveTopCaps(unittest.TestCase):
 def fixture(self,outward=-1):
  target=[0,65,14];rows={}
  for col in [14,14+outward]:
   rows[0,66,col]={'state':'Block{minecraft:oak_trapdoor}[half=top,open=false,waterlogged=false]'};rows[0,67,col]={'solid':True}
  for step in [1,2,3]:rows[0,64,14+step*outward]={'solid':True,'fluid':False}
  origin=[.5,65,14.5+outward*.75];pose=[.5,65.3,14.5+2*outward]
  return rows,origin,target,pose
 def test_closed_low_passage_requires_ground_retreat_before_raising_in_both_directions(self):
  from public_lectern_access import staged_ground_retreat
  for outward in [-1,1]:
   rows,origin,target,pose=self.fixture(outward);ground=staged_ground_retreat(rows,[],origin,target,pose,'p');self.assertIsNotNone(ground);self.assertEqual(ground[1],65);self.assertFalse(clear(rows,[],target,pose,'p'))
 def test_open_cap_water_missing_floor_or_entity_rejects_the_staged_route(self):
  from public_lectern_access import staged_ground_retreat
  for case in ['cap','water','floor','blocked_far','raised_origin','entity']:
   rows,origin,target,pose=self.fixture();entities=[]
   if case=='cap':rows[0,66,13]['state']=rows[0,66,13]['state'].replace('open=false','open=true')
   if case=='water':rows[0,64,12]['fluid']=True
   if case=='floor':del rows[0,64,11]
   if case=='blocked_far':rows[0,66,12]={'solid':True}
   if case=='raised_origin':origin[1]=65.1
   if case=='entity':entities=[{'uuid':'mob','type':'minecraft:villager','bounds':{'min':[.2,65,12.1],'max':[.8,66.95,12.7]}}]
   with self.subTest(case=case):self.assertIsNone(staged_ground_retreat(rows,entities,origin,target,pose,'p'))
 def test_restore_lowers_in_public_column_before_reentering_capped_passage(self):
  from public_lectern_access import restore
  class Builder:
   def __init__(self):self.calls=[]
   def nav(self,p):self.calls.append(('nav',p))
   def n(self,op,**params):self.calls.append((op,params['target']))
   def save(self):pass
  b=Builder();r={'origin':[.5,65,13.75],'placement_pose':[.5,65.3,12.5],'target':[0,65,14],'staged_ground_retreat':[.5,65,12.31],'pending':True};restore(b,r);self.assertEqual(b.calls,[('nav',[.5,65.,12.5]),('walk',[.5,65,13.75])]);self.assertFalse(r['pending'])
