import unittest
from unittest.mock import patch
import kit_cli
from lighting_regions_cli import compact
class CliTest(unittest.TestCase):
 def test_compact_keeps_incomplete_coverage_and_counts_without_large_profile(self):
  r=compact({'phase':'waiting_materials','cursor':46,'profile':{'regions':[{}]*150},'batches':[{'placed_verified':54},{'placed_verified':25}],'coverage_complete':False,'reason':'No torches','pending':None})
  self.assertEqual(79,r['placed_verified']);self.assertEqual(150,r['total_regions']);self.assertFalse(r['coverage_complete']);self.assertNotIn('profile',r)
 def test_idle_cli_directly_delegates_without_ui(self):
  with patch('idle_service_cli.main',return_value=0) as call:
   self.assertEqual(0,kit_cli.main(['--game-dir','/game','idle','status','--profile','/profile']))
  self.assertEqual(['--game-dir','/game','--profile','/profile','status'],call.call_args.args[0])
if __name__=='__main__':unittest.main()
