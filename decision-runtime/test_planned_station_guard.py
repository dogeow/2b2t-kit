import unittest,math
from planned_station_guard import require_safe_planned_station,UnsafePlannedStation
from goal_workflow import build_phase

CELLS=[{'pos':[761392,61,793982],'expected':'Block{minecraft:magma_block}'},
       {'pos':[761392,61,793983],'expected':'Block{minecraft:magma_block}'},
       {'pos':[761391,61,793984],'expected':'Block{minecraft:magma_block}'}]
class StationTests(unittest.TestCase):
 def test_recorded_short_hover_above_planned_magma_is_rejected(self):
  with self.assertRaises(UnsafePlannedStation):require_safe_planned_station({'pos':[761392.5,63.5,793983.5]},CELLS)
 def test_side_station_and_high_travel_remain_available(self):
  require_safe_planned_station({'pos':[761391.5,63.4,793985.5]},CELLS)
  require_safe_planned_station({'pos':[761392.5,98.15,793983.5]},CELLS)
 def test_body_edge_overlap_is_not_treated_as_a_safe_adjacent_cell(self):
  with self.assertRaises(UnsafePlannedStation):require_safe_planned_station({'pos':[761391.9,63.5,793983.5]},CELLS)
 def test_nonhazard_and_legacy_unbounded_calls_are_unchanged(self):
  require_safe_planned_station({},None)
  require_safe_planned_station({},[{'pos':[1,2,3],'expected':'Block{minecraft:cobblestone}'}])
 def test_unknown_or_invalid_pose_cannot_start_hazard_work(self):
  for pos in [None,[1,2],[1,math.nan,3],[1,math.inf,3],[True,2,3]]:
   with self.subTest(pos=pos),self.assertRaises(UnsafePlannedStation):require_safe_planned_station({'pos':pos},CELLS)
 def test_bad_hazard_coordinates_are_not_silently_ignored(self):
  with self.assertRaises(UnsafePlannedStation):require_safe_planned_station({'pos':[0.5,4,0.5]},[{'pos':[0,1.5,0],'expected':'Block{minecraft:magma_block}'}])
 def test_workflow_rejects_before_start_or_inventory_swap(self):
  class Client:
   calls=[]
   def status(self):return {'pos':[761392.5,63.5,793983.5],'projection_selection':{'key':'k'}}
   def checked(self,op,**kw):self.calls.append(op);raise AssertionError('No game mutation may run')
  c=Client()
  with self.assertRaises(UnsafePlannedStation):build_phase(c,'k',complete_cells=CELLS)
  self.assertEqual([],c.calls)
 def test_recorded_campfire_hover_is_rejected_before_any_print_command(self):
  cells=[{'pos':[761429,59,793982],'expected':'Block{minecraft:soul_campfire}[facing=west,lit=true,signal_fire=false,waterlogged=false]'}]
  class Client:
   def __init__(self):self.calls=[]
   def status(self):return {'pos':[761429.5438381253,61.1,793982.5004957044],'projection_selection':{'key':'k'}}
   def checked(self,op,**kw):self.calls.append(op);raise AssertionError('No game input may be sent')
  c=Client()
  with self.assertRaises(UnsafePlannedStation):build_phase(c,'k',complete_cells=cells)
  self.assertEqual([],c.calls)
 def test_both_lit_campfire_types_need_side_stations_and_allow_high_travel(self):
  for kind in ['campfire','soul_campfire']:
   cells=[{'pos':[10,59,20],'expected':'Block{minecraft:'+kind+'}[facing=west,lit=true,signal_fire=false,waterlogged=false]'}]
   with self.subTest(kind=kind),self.assertRaises(UnsafePlannedStation):require_safe_planned_station({'pos':[10.5,61.1,20.5]},cells)
   require_safe_planned_station({'pos':[11.5,60.1,20.5]},cells)
   require_safe_planned_station({'pos':[10.5,98.15,20.5]},cells)
   with self.assertRaises(UnsafePlannedStation):require_safe_planned_station({'pos':[10.9,61.1,20.5]},cells)
 def test_extinguished_or_waterlogged_campfire_is_not_a_planned_heat_source(self):
  for properties in ['lit=false,waterlogged=false','lit=true,waterlogged=true']:
   require_safe_planned_station({'pos':[10.5,60.1,20.5]},[{'pos':[10,59,20],'expected':'Block{minecraft:campfire}['+properties+']'}])
 def test_missing_campfire_heat_properties_fail_closed(self):
  with self.assertRaises(UnsafePlannedStation):require_safe_planned_station({'pos':[10.5,61.1,20.5]},[{'pos':[10,59,20],'expected':'Block{minecraft:soul_campfire}'}])
if __name__=='__main__':unittest.main()
