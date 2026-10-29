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
if __name__=='__main__':unittest.main()
