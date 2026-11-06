import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from material_jobs.profile import _read_kit_config
from material_jobs.protocol import JobBlocked
class KitConfigReadTests(unittest.TestCase):
 def test_transient_partial_write_then_complete_current_value(self):
  with patch.object(Path,'read_text',side_effect=['{"projectionSupplySources": [','{"projectionSupplySources":[{"x":7}]}']) as read,patch('material_jobs.profile.time.sleep') as sleep:
   self.assertEqual(_read_kit_config(Path('kit.json'))['projectionSupplySources'][0]['x'],7)
   self.assertEqual(read.call_count,2);sleep.assert_called_once_with(.1)
 def test_persistent_invalid_blocks_without_fallback(self):
  with patch.object(Path,'read_text',return_value='{"bad":') as read,patch('material_jobs.profile.time.sleep'):
   with self.assertRaises(JobBlocked):_read_kit_config(Path('kit.json'),attempts=3)
   self.assertEqual(read.call_count,3)
 def test_io_error_is_not_hidden_or_retried(self):
  with patch.object(Path,'read_text',side_effect=PermissionError('denied')) as read,patch('material_jobs.profile.time.sleep') as sleep:
   with self.assertRaises(PermissionError):_read_kit_config(Path('kit.json'))
   self.assertEqual(read.call_count,1);sleep.assert_not_called()
 def test_valid_current_config_read_once(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'kit.json';p.write_text(json.dumps({'projectionSupplySources':[]}));self.assertEqual(_read_kit_config(p),{'projectionSupplySources':[]})
if __name__=='__main__':unittest.main()
