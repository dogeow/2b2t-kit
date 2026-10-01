import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from material_client import Client
class ReplyOrderTest(unittest.TestCase):
 def client(self,d):
  c=object.__new__(Client);c.root=Path(d);c.world='w';c.minimum_status_time=20;return c
 def test_old_status_waits_for_own_reply_frame_without_sending_anything(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.client(d);old={'time':10,'world_session':'w'};new={'time':20,'world_session':'w'}
   with patch('live_snapshot.read_fresh',side_effect=[old,new]) as read,patch('material_client.time.sleep'):
    self.assertEqual(new,c.raw());self.assertEqual(2,read.call_count)
   self.assertFalse((Path(d)/'request.json').exists())
 def test_world_change_is_returned_for_handoff_instead_of_waiting_old_frame(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.client(d);new={'time':10,'world_session':'new'}
   with patch('live_snapshot.read_fresh',return_value=new) as read:
    self.assertEqual(new,c.raw());self.assertEqual(1,read.call_count)
 def test_missing_publish_is_waiting_not_operation_replay(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.client(d)
   with patch('live_snapshot.read_fresh',return_value={'time':10,'world_session':'w'}):
    with self.assertRaisesRegex(RuntimeError,'do not replay'):c.raw(wait_seconds=0)
   self.assertFalse((Path(d)/'request.json').exists())
 def test_health_hold_takes_precedence_over_status_publish_wait(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.client(d);(Path(d)/'safety-hold.json').write_text('{"active":true}')
   with patch('live_snapshot.read_fresh',return_value={'time':10,'world_session':'w'}):
    with self.assertRaisesRegex(RuntimeError,'Safety lock'):c.raw()
