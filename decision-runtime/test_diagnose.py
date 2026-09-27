import json,tempfile,unittest
from pathlib import Path
from diagnose import diagnose,summarize_run
class DiagnoseTest(unittest.TestCase):
 def test_recent_summary_separates_failed_actions_and_timing(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);events=[{'op':'slot_click','duration_ms':400,'phase':'done'}, {'op':'navigate','duration_ms':9000,'phase':'waiting','detail':'unsafe drop ahead; apikey_example_12345678'}]
   (p/'events.jsonl').write_text('\n'.join(json.dumps(v) for v in events))
   result=summarize_run(p);self.assertEqual('navigate',result['slow_operations'][0]['op']);self.assertEqual({'navigation':1},result['failure_counts']);self.assertNotIn('apikey_example',json.dumps(result))
 def test_missing_snapshot_is_unknown_not_healthy_or_connected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'assistant-control-hold.json').write_text('{"active":true}')
   result=diagnose(p);self.assertIsNone(result['game']['connected']);self.assertIsNone(result['game']['health']);self.assertTrue(result['game']['assistant_offline_only']);self.assertFalse(result['performed_game_or_network_actions'])
if __name__=='__main__':unittest.main()
