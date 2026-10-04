"""A neighboring tall obstacle must influence the lighting flight corridor."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from test_lighting_regions_cli import state
from material_jobs.acquisition import _travel_once

class FakeClient:
 def __init__(self):
  self.world='world-a';self.current=state();self.current.update(pos=[.5,80,.5],air_only_navigation_protocol=2,guard_busy=False)
  self.moves=[]
  self.rev=7
  self.last=None;self.scans=0
 def status(self):return deepcopy(self.current)
 def request(self,op,**params):
  if op=='scan':
   row={'pos':[8,95,2],'state':'Block{minecraft:stone}','fluid':False,'passable':False,'solid':True,'block_entity':False}
   wall=[{**row,'pos':[8,y,2]}for y in range(80,96)]
   rows=[r for r in wall if all(params['min'][i]<=r['pos'][i]<=params['max'][i]for i in range(3))]
   total=__import__('math').prod(params['max'][i]-params['min'][i]+1 for i in range(3))
   self.scans+=1;self.last='scan-'+str(self.scans)
   return {'id':self.last,'phase':'done','world_session':self.world,'blocks':rows,'scan_cells_read':total,'scan_total_cells':total,
           'control_revision':self.rev,'scan_start_revision':self.rev,'scan_end_revision':self.rev}
  if op=='navigate':
   self.moves.append(params['target']);self.current['pos']=list(params['target']);return {'phase':'done'}
  raise AssertionError(op)

class ClearanceTest(unittest.TestCase):
 def test_lighting_margin_observes_adjacent_rocket_geometry_before_crossing(self):
  c=FakeClient()
  with patch('material_jobs.navigation.settled_state',side_effect=lambda client,target,tolerance:client.status()):
   _travel_once(c,[16.5,80,.5],lambda:None,[],clearance_padding=2.32,obstacle_margin=5.1)
  self.assertAlmostEqual(c.moves[0][1],100.1)
  self.assertEqual(c.moves[-1],[16.5,80,.5])
 def test_existing_default_travel_keeps_its_original_corridor_policy(self):
  c=FakeClient()
  with patch('material_jobs.navigation.settled_state',side_effect=lambda client,target,tolerance:client.status()):
   _travel_once(c,[16.5,80,.5],lambda:None,[])
  self.assertEqual(c.moves,[[16.5,80,.5]])
 def test_invalid_or_boolean_margins_are_rejected_before_native_requests(self):
  for pad,margin in ((True,5.1),(3,5.1),(2.32,7)):
   c=FakeClient()
   with self.assertRaises(ValueError):_travel_once(c,[16.5,80,.5],lambda:None,[],clearance_padding=pad,obstacle_margin=margin)
   self.assertFalse(c.moves)

if __name__=='__main__':unittest.main()
