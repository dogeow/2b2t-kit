import json
import tempfile
import unittest
from pathlib import Path
from safety_interlock import require_unlocked,record_material_health_exit,OwnedHealthExitEvidence

class InterlockTest(unittest.TestCase):
 def test_disk_lock_survives_stale_safe_status(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'safety-hold.json';p.write_text(json.dumps({'active':True}))
   with self.assertRaises(RuntimeError):require_unlocked(d,{'safety_hold':{'active':False}})
 def test_memory_lock_survives_missing_file(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(RuntimeError):require_unlocked(d,{'safety_hold':{'active':True}})
 def test_invalid_or_partial_record_blocks_automation(self):
  with tempfile.TemporaryDirectory() as d:
   for value in ('{bad','{}','null','{"active":"false"}'):
    (Path(d)/'safety-hold.json').write_text(value)
    with self.assertRaises(RuntimeError):require_unlocked(d)
 def test_acknowledged_record_allows_new_user_session(self):
  with tempfile.TemporaryDirectory() as d:
   require_unlocked(d)
   (Path(d)/'safety-hold.json').write_text('{"active":false,"cleared_by":"game_ui"}')
   require_unlocked(d)

 def test_script_health_exit_blocks_even_when_native_emergency_threshold_was_not_reached(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'safety-hold.json';p.write_text('{"active":false,"cleared_by":"game_ui","cleared_at":99}')
   record_material_health_exit(d,{'time':100,'health':18.9,'pos':[1,110,2]},'health reserve lost')
   with self.assertRaisesRegex(RuntimeError,'Material task exited for health'):
    require_unlocked(d,{'safety_hold':{'active':False}})

 def test_newer_explicit_game_acknowledgement_satisfies_script_hold(self):
  with tempfile.TemporaryDirectory() as d:
   record_material_health_exit(d,{'time':100,'health':18.9},'health reserve lost')
   (Path(d)/'safety-hold.json').write_text('{"active":false,"cleared_by":"game_ui","cleared_at":101}')
   require_unlocked(d)
   self.assertTrue(json.loads((Path(d)/'material-health-hold.json').read_text())['active'])


 def test_current_owned_health_decline_does_not_use_historical_hurt_marker(self):
  witness=OwnedHealthExitEvidence('w','t')
  state={'connected':True,'world_session':'w','control_revision':1,'time':100,'health':20,
         'recent_hurt_at':1,'manual_movement':False,
         'supervision_lease':{'kind':'materials','job_session':'t','world_session':'w','revision':1}}
  witness.observe(state);witness.observe({**state,'time':101,'recent_hurt_at':2})
  self.assertIsNone(witness.exit_state())
  witness.observe({**state,'time':102,'health':19})
  self.assertEqual(19,witness.exit_state()['health'])
  witness.observe({**state,'time':103,'health':20})
  self.assertIsNone(witness.exit_state())
 def test_foreign_or_stale_health_observation_cannot_create_exit_cause(self):
  witness=OwnedHealthExitEvidence('w','t')
  state={'connected':True,'world_session':'w','control_revision':1,'time':100,'health':20,
         'supervision_lease':{'kind':'materials','job_session':'t','world_session':'w','revision':1}}
  witness.observe(state)
  for observed in ({**state,'health':17}, {**state,'world_session':'other','time':101,'health':17},
                   {**state,'time':101,'health':17,'manual_movement':True},
                   {**state,'time':101,'health':17,'supervision_lease':{}}):
   witness.observe(observed);self.assertIsNone(witness.exit_state())
 def test_invalid_script_hold_time_cannot_accept_an_old_acknowledgement(self):
  with tempfile.TemporaryDirectory() as d:
   for stamp in (True,-1,100.0):
    (Path(d)/'material-health-hold.json').write_text(json.dumps({'active':True,'time':stamp}))
    with self.assertRaises(RuntimeError):require_unlocked(d)

if __name__=='__main__':unittest.main()

class AssistantControlHoldTest(unittest.TestCase):
 def test_offline_instruction_blocks_automation_without_changing_health_lock(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'assistant-control-hold.json').write_text('{"active":true}')
   (root/'safety-hold.json').write_text('{"active":false}')
   with self.assertRaisesRegex(RuntimeError,'offline Kit work'):require_unlocked(root)
   self.assertFalse(json.loads((root/'safety-hold.json').read_text())['active'])
 def test_later_authorization_does_not_clear_a_health_lock(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'assistant-control-hold.json').write_text('{"active":false}')
   (root/'safety-hold.json').write_text('{"active":true}')
   with self.assertRaisesRegex(RuntimeError,'Safety lock active'):require_unlocked(root)
