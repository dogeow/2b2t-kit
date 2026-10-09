import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from lighting_cli import LightingRun
from lighting_reachable_edges import (ReachableEdgeLightingRun,observed_station_route,
    compress_axis_route,lowest_transit_height,shortcut_observed_route,TRAVEL_FOOT_OFFSET)
from test_lighting_reachable_edges import floor
from potato_farm import ENTITY_SCOPE_AT_SCAN_END


class LocalLightingRouteTests(unittest.TestCase):
 def test_nearby_stations_stay_low_and_merge_the_straight_corridor(self):
  route=observed_station_route({},[.5,65.1,.5],[12.5,65.1,.5],[-1,64,-1],[13,70,1])
  self.assertEqual(route,[[.5,65+TRAVEL_FOOT_OFFSET,.5],[12.5,65+TRAVEL_FOOT_OFFSET,.5]])
 def test_diagonal_known_volume_uses_bounded_search_and_preserves_axis_legs(self):
  route=observed_station_route({},[.5,65.1,.5],[20.5,65.1,20.5],[-1,64,-1],[21,70,21],budget=256)
  self.assertIsNotNone(route);self.assertEqual(route[-1],[20.5,65+TRAVEL_FOOT_OFFSET,20.5])
  self.assertTrue(all(sum(a[i]!=b[i]for i in range(3))==1 for a,b in zip(route,route[1:])))
 def test_trunk_detour_stays_below_the_observed_canopy(self):
  cells={(x,64,z):floor((x,64,z))for x in range(7)for z in range(-2,3)}
  cells.update({(3,y,0):floor((3,y,0))for y in (65,66)})
  cells.update({(x,67,z):floor((x,67,z))for x in range(7)for z in range(-2,3)})
  route=observed_station_route(cells,[.5,65.1,.5],[6.5,65.1,.5],[-1,64,-3],[7,67,3])
  self.assertIsNotNone(route);self.assertTrue(all(p[1]==65+TRAVEL_FOOT_OFFSET for p in route))
  self.assertTrue(any(p[2]!=.5 for p in route))
 def test_sealed_corridor_has_no_inferred_exit_or_high_route(self):
  cells={(x,64,0):floor((x,64,0))for x in range(7)}
  cells.update({(3,y,0):floor((3,y,0))for y in range(65,70)})
  self.assertIsNone(observed_station_route(cells,[.5,65.1,.5],[6.5,65.1,.5],[0,64,0],[6,70,0]))
 def test_fluid_is_not_air_even_when_its_passable_flag_is_true(self):
  water={**floor((3,65,0)),'state':'Block{minecraft:water}','fluid':True,'solid':False,
         'passable':True,'zombie_spawn_floor':False,'zombie_block_light_risk':False}
  self.assertIsNone(observed_station_route({(3,65,0):water},[.5,65.1,.5],[6.5,65.1,.5],[0,65,0],[6,66,0]))
 def test_current_creature_is_avoided_and_unknown_bounds_refuse_the_route(self):
  mob={'type':'minecraft:cow','alive':True,'hostile':False,
       'bounds':{'min':[3.1,65,.1],'max':[3.9,66.8,.9]}}
  route=observed_station_route({},[.5,65.1,.5],[6.5,65.1,.5],[-1,65,-2],[7,66,2],[mob])
  self.assertIsNotNone(route);self.assertTrue(any(p[2]!=.5 for p in route))
  self.assertIsNone(observed_station_route({},[.5,65.1,.5],[6.5,65.1,.5],[-1,65,-2],[7,66,2],[{'type':'minecraft:cow'}]))
 def test_shortcut_keeps_extra_margin_beside_higher_ground(self):
  route=[[.5,65.195,.5],[.5,65.195,-.5],[6.5,65.195,-.5],[6.5,65.195,.5]]
  cells={(x,65,1):floor((x,65,1))for x in range(2,5)}
  planned=shortcut_observed_route(cells,route,[-1,64,-2],[7,70,2],[])
  self.assertNotEqual(planned,[route[0],route[-1]])
 def test_actual_offset_pose_must_connect_to_the_grid_without_cutting_into_ground(self):
  cells={(0,65,1):floor((0,65,1))}
  self.assertIsNone(observed_station_route(cells,[.7,65.04,.75],[6.5,65.1,.5],[-1,64,-2],[7,70,2]))
 def test_compression_keeps_corners_instead_of_cutting_a_diagonal(self):
  route=[[.5,65.1,.5],[1.5,65.1,.5],[2.5,65.1,.5],[2.5,65.1,1.5],[2.5,65.1,2.5]]
  self.assertEqual(compress_axis_route(route),[route[0],route[2],route[4]])
 def test_shortcut_requires_the_whole_actual_volume_to_be_clear(self):
  route=[[.5,65.195,.5],[2.5,65.195,.5],[2.5,65.195,2.5]]
  self.assertEqual(shortcut_observed_route({},route,[-1,65,-1],[3,67,3],[]),[route[0],route[-1]])
  self.assertEqual(shortcut_observed_route({(1,65,1):floor((1,65,1))},route,[-1,65,-1],[3,67,3],[]),route)
  mob={'type':'minecraft:cow','alive':True,'hostile':False,
       'bounds':{'min':[1.1,65,1.1],'max':[1.9,66.8,1.9]}}
  self.assertEqual(shortcut_observed_route({},route,[-1,65,-1],[3,67,3],[mob]),route)
 def test_transit_uses_the_lowest_clear_band_not_a_fixed108_height(self):
  start=[.5,65.1,.5];entry=[6.5,65.1,.5]
  self.assertEqual(lowest_transit_height({},start,entry,108),65.1)
  cells={(3,y,0):floor((3,y,0))for y in range(65,68)}
  self.assertAlmostEqual(lowest_transit_height(cells,start,entry,108),68.1)
  self.assertIsNone(lowest_transit_height(cells,start,entry,67))
  self.assertEqual(lowest_transit_height({(3,100,0):floor((3,100,0))},start,entry,108),65.1)

 def fake_run(self,out,*,positive=False,limit=8):
  class Run(ReachableEdgeLightingRun):
   def __init__(self):
    self.state={'pos':[.5,65.1,.5],'time':100};self.moves=[];self.scans=[];self.planted=False
    self.c=SimpleNamespace(world='w',task='t',status=lambda:self.state)
    self.low=[0,62,0];self.high=[14,90,2];self.move_low=[-20,60,-20];self.move_high=[20,319,20]
    self.surface_only=False;self.protected=[];self.limit=limit;self.out=Path(out);self.last_entry_route=None
    self.report={'placed':[]}
   def fresh(self,**kwargs):return self.state
   def reject_unknown_intents(self):pass
   def save(self):pass
   def scan(self,low,high,name=None):
    self.scans.append(name)
    rows=[]
    if positive:
     row=floor((0,64,0))
     if self.planted:row.update(spawn_block_light=14,zombie_block_light_risk=False)
     rows=[row]
    return {'id':'scan-'+str(len(self.scans)),'phase':'done','world_session':'w','blocks':rows,
            'scan_entity_scope':ENTITY_SCOPE_AT_SCAN_END,'scan_entities':[]}
   def move(self,point):self.moves.append(list(point));self.state['pos']=list(point)
   def place_edge(self,candidate,index):self.planted=True
  return Run()
 def test_actual_route_executor_does_not_insert_an_ascent_for_nearby_work(self):
  with tempfile.TemporaryDirectory()as out:
   run=self.fake_run(out);candidate={'station':[10.5,65.1,.5],'entry_route':[[10.5,65.1,.5]]}
   run.approach_edge_station(candidate,run.state,0)
   self.assertEqual(run.moves,[[10.5,65+TRAVEL_FOOT_OFFSET,.5]])
 def test_zero_result_reuses_exact_complete_scan_without_duplicate_final_scan(self):
  with tempfile.TemporaryDirectory()as out:
   run=self.fake_run(out);run.work()
   self.assertEqual(len(run.scans),1)
   self.assertEqual(json.loads((Path(out)/'edge-final-survey.json').read_text())['id'],'scan-1')
 def test_last_budgeted_placement_still_requires_a_new_complete_final_scan(self):
  with tempfile.TemporaryDirectory()as out:
   run=self.fake_run(out,positive=True,limit=1);run.work()
   self.assertEqual(run.scans,['edge-survey-0.json','edge-final-survey.json'])
   self.assertEqual(run.report['after']['unprotected_dark_floor'],0)
 def test_low_station_leaves_canopy_by_its_route_before_high_parking(self):
  with tempfile.TemporaryDirectory()as out:
   run=self.fake_run(out);run.last_entry_route=[[.5,65.1,.5],[1.5,65.1,.5],[1.5,65.1,1.5]]
   run.state['pos']=list(run.last_entry_route[-1]);observed=[]
   with patch.object(LightingRun,'park',lambda self:observed.append(list(self.state['pos']))):run.park()
   self.assertEqual(observed,[run.last_entry_route[0]])

if __name__=='__main__':unittest.main()
