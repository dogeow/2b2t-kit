from unittest import TestCase
from material_jobs.aquifer_roof_access import safe_mine_cell,plan,authorized_targets

def row(pos,name='stone',fluid=False):
 return {'pos':list(pos),'state':'Block{minecraft:'+name+'}'+('[level=0]'if name=='water'else''),'solid':not fluid,'fluid':fluid,'block_entity':False,'passable':False}

class AquiferRoofAccessTests(TestCase):
 def authorization(self):
  return {'world_session':'current','execution_authorized':True,'user_authorization':'exact cells approved',
          'authorization_scope':'only_the_exact_17_new_targets_in_this_plan','maximum_new_mines':17,
          'actual_planned_mines':17,'new_targets':[row((0,y,0))for y in range(3,20)],
          'body_path':[[0,y,0]for y in range(2,20)]}
 def test_exact_exception_does_not_expand_or_cross_worlds(self):
  a=self.authorization();self.assertEqual(len(authorized_targets(a,'current')),17)
  for key,value in [('world_session','old'),('execution_authorized',False),('authorization_scope','whole_box'),('maximum_new_mines',18)]:
   b={**a,key:value}
   with self.assertRaises(ValueError):authorized_targets(b,'current')
 def test_duplicate_or_off_route_exception_cells_are_refused(self):
  a=self.authorization();a['new_targets'][-1]=a['new_targets'][0]
  with self.assertRaises(ValueError):authorized_targets(a,'current')
  a=self.authorization();a['new_targets'][-1]=row((1,19,0))
  with self.assertRaises(ValueError):authorized_targets(a,'current')
 def test_only_stable_water_below_a_roof_opening_is_admitted(self):
  p=(3,3,3);by={p:row(p),(3,2,3):row((3,2,3),'water',True)}
  self.assertTrue(safe_mine_cell(by,p))
  for offset in [(1,0,0),(0,1,0),(0,0,1)]:
   q=tuple(p[i]+offset[i]for i in range(3));self.assertFalse(safe_mine_cell({p:row(p),q:row(q,'water',True)},p))
  self.assertFalse(safe_mine_cell({p:row(p),(3,2,3):row((3,2,3),'lava',True)},p))
 def test_containers_protected_blocks_and_falling_neighbours_are_retained(self):
  p=(3,3,3);r=row(p);r['block_entity']=True;self.assertFalse(safe_mine_cell({p:r},p))
  self.assertFalse(safe_mine_cell({p:row(p)},p,lambda p:True))
  self.assertFalse(safe_mine_cell({p:row(p),(3,4,3):row((3,4,3),'gravel')},p))
  self.assertFalse(safe_mine_cell({p:row(p,'diamond_ore')},p))
 def fixture(self):
  rows=[row((x,y,z))for x in range(9)for y in range(9)for z in range(9)if(x,y,z)not in[(1,2,4),(1,3,4),(5,2,4)]]
  rows.append(row((5,2,4),'water',True))
  return {'phase':'done','time':1000,'world_session':'current','scan_cells_read':729,'scan_total_cells':729,'blocks':rows}
 def test_finite_route_opens_above_the_pool_and_keeps_support_and_water(self):
  p=plan(self.fixture(),[0,0,0],[8,8,8],[1.5,2.1,4.5],[5,2,4],max_mines=16)
  self.assertEqual(p['goal'],[5.5,3.1,4.5]);self.assertLessEqual(p['actual_planned_mines'],16)
  targets=[r['pos']for r in p['new_targets']]
  self.assertNotIn([5,2,4],targets);self.assertNotIn([1,1,4],targets)
  self.assertFalse(p['liquids_removed'])
 def test_no_small_goal_or_budget_is_fabricated_when_scan_or_route_is_insufficient(self):
  scan=self.fixture();scan['scan_cells_read']=728
  with self.assertRaisesRegex(ValueError,'Complete'):plan(scan,[0,0,0],[8,8,8],[1.5,2.1,4.5],[5,2,4])
  with self.assertRaisesRegex(ValueError,'finite'):plan(self.fixture(),[0,0,0],[8,8,8],[1.5,2.1,4.5],[5,2,4],max_mines=1)
 def test_a_protected_plane_cannot_be_excavated_to_reach_the_water(self):
  with self.assertRaisesRegex(ValueError,'finite'):
   plan(self.fixture(),[0,0,0],[8,8,8],[1.5,2.1,4.5],[5,2,4],protected=lambda p:p[0]==3,max_mines=64)
 def test_an_easy_old_shore_does_not_replace_the_named_target_pocket(self):
  scan=self.fixture();by={tuple(r['pos']):r for r in scan['blocks']}
  for x in range(1,6):by[x,2,4]=row((x,2,4),'water',True)
  by.pop((1,3,4),None);by.pop((1,4,4),None);scan['blocks']=list(by.values())
  p=plan(scan,[0,0,0],[8,8,8],[1.5,3.1,4.5],[5,2,4],max_mines=16,target_radius=1)
  self.assertGreaterEqual(p['goal'][0],4.5);self.assertGreater(p['actual_planned_mines'],0)
