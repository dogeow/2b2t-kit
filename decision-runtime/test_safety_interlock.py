import json
import tempfile
import unittest
from pathlib import Path
from safety_interlock import require_unlocked

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

if __name__=='__main__':unittest.main()
