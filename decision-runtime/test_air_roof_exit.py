import copy,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from material_jobs.air_roof_exit import escape
from material_jobs.protocol import JobBlocked
class RoofExitTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.s=dict(world_session='w',pos=[10.5,155.2,20.5],flight=True,on_ground=False,health=20,manual_movement=False,screen='',under_water=False,guard_busy=False,guard_armed=True,guard_pve_only=True,air_only_navigation_protocol=2)
  self.c=SimpleNamespace(world='w',out=Path(self.tmp.name),checked=Mock(),last='request-original')
  self.ground=[{'pos':[14,63,20],'fluid':False,'passable':False}]
 def test_airborne_builder_uses_horizontal_flight_then_caller_must_prove_parking(self):
  final={**self.s,'pos':[14.5,155.2,20.5]}
  with patch('material_jobs.navigation.settled_state',side_effect=[self.s,self.s,final]),patch('material_jobs.navigation._air_scan',side_effect=[self.ground,[]]),patch('material_jobs.acquisition._safe'):
   self.assertEqual(final,escape(self.c,self.s))
  self.c.checked.assert_called_once_with('navigate',target=final['pos'],arrival=.25,air_only=True,seconds=45)
  import json
  r=json.loads(next(self.c.out.glob('air-roof-exit-*.json')).read_text());self.assertFalse(r['pending']);self.assertFalse(r['ground_walk_sent']);self.assertFalse(r['parking_confirmed'])
 def test_grounded_or_non_flying_keeps_original_ground_policy(self):
  for s in [{**self.s,'on_ground':True},{**self.s,'flight':False}]:self.assertIsNone(escape(self.c,s))
  self.c.checked.assert_not_called()
 def test_roof_or_water_on_candidate_column_never_moves(self):
  for row in [{'pos':[14,200,20],'passable':False},{'pos':[14,155,20],'fluid':True}]:
   with patch('material_jobs.navigation.settled_state',return_value=self.s),patch('material_jobs.navigation._air_scan',return_value=[row]),patch('material_jobs.acquisition._safe'):
    with self.assertRaises(JobBlocked):escape(self.c,self.s)
  self.c.checked.assert_not_called()
 def test_blocked_horizontal_corridor_never_moves(self):
  with patch('material_jobs.navigation.settled_state',return_value=self.s),patch('material_jobs.navigation._air_scan',side_effect=lambda c,lo,hi:self.ground if lo[1]==-64 else [{'pos':[12,155,20],'passable':False}]),patch('material_jobs.acquisition._safe'):
   with self.assertRaises(JobBlocked):escape(self.c,self.s)
  self.c.checked.assert_not_called()
 def test_unknown_scan_does_not_become_empty_air(self):
  with patch('material_jobs.navigation.settled_state',return_value=self.s),patch('material_jobs.navigation._air_scan',side_effect=JobBlocked('unknown scan')),patch('material_jobs.acquisition._safe'):
   with self.assertRaisesRegex(JobBlocked,'unknown scan'):escape(self.c,self.s)
  self.c.checked.assert_not_called()
 def test_unknown_navigation_retains_single_intent_and_never_tries_next_candidate(self):
  self.c.checked.side_effect=RuntimeError('unknown ACK')
  with patch('material_jobs.navigation.settled_state',return_value=self.s),patch('material_jobs.navigation._air_scan',side_effect=[self.ground,[]]),patch('material_jobs.acquisition._safe'):
   with self.assertRaisesRegex(RuntimeError,'unknown ACK'):escape(self.c,self.s)
  self.assertEqual(1,self.c.checked.call_count)
  import json
  r=json.loads(next(self.c.out.glob('air-roof-exit-*.json')).read_text());self.assertTrue(r['pending']);self.assertEqual('request-original',r['request_id'])
 def test_manual_health_world_and_missing_flight_fail_before_any_movement(self):
  for changes in [{'manual_movement':True},{'health':18},{'world_session':'other'},{'flight':False},{'guard_armed':False},{'guard_busy':True}]:
   with patch('material_jobs.navigation.settled_state',return_value={**self.s,**changes}),patch('material_jobs.acquisition._safe'):
    with self.assertRaises(JobBlocked):escape(self.c,self.s)
  self.c.checked.assert_not_called()
if __name__=='__main__':unittest.main()
