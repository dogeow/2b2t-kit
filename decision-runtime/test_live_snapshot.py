import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from live_snapshot import read_fresh
class LiveSnapshotTest(unittest.TestCase):
 def test_transient_stall_reobserves_without_replaying_a_request(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'status.json';p.write_text(json.dumps({'time':9000,'control_revision':1}));clock=[0]
   def sleep(n):
    clock[0]+=n
    if clock[0]>=.3:p.write_text(json.dumps({'time':13000,'control_revision':2}))
   with patch('live_snapshot.time.time',return_value=13),patch('live_snapshot.time.monotonic',side_effect=lambda:clock[0]),patch('live_snapshot.time.sleep',side_effect=sleep):
    self.assertEqual(2,read_fresh(d)['control_revision'])
   self.assertFalse((Path(d)/'request.json').exists())
 def test_permanent_stall_still_fails_within_bound(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'status.json';p.write_text('{"time":0}');clock=[0]
   with patch('live_snapshot.time.time',return_value=100),patch('live_snapshot.time.monotonic',side_effect=lambda:clock[0]),patch('live_snapshot.time.sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)):
    with self.assertRaisesRegex(RuntimeError,'bounded observation retry'):read_fresh(d,wait_seconds=.6)
   self.assertLess(clock[0],.8)
 def test_fresh_disconnected_state_is_returned_for_existing_handoff_checks(self):
  with tempfile.TemporaryDirectory() as d:
   (Path(d)/'status.json').write_text('{"time":13000,"connected":false}')
   with patch('live_snapshot.time.time',return_value=13):self.assertFalse(read_fresh(d)['connected'])
if __name__=='__main__':unittest.main()
