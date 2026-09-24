import json
import tempfile
import unittest
from pathlib import Path

from surface_gravel_ledger import SurfaceGravelLedger


class SurfaceGravelLedgerTest(unittest.TestCase):
    def test_persists_world_scoped_coverage_without_revisiting_complete_tiles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'routes.json'
            ledger = SurfaceGravelLedger(path, 'simpcraft.com:25565', 'minecraft:overworld')
            ledger.record([0, 58, 0], [7, 88, 15], 3, 'empty', dry_candidates=0)
            ledger.record([8, 58, 0], [15, 88, 15], 3, 'exhausted', remaining_safe=0)
            restored = SurfaceGravelLedger(path, 'simpcraft.com:25565', 'minecraft:overworld')
            self.assertTrue(restored.covered([0, 58, 0], [15, 88, 15], 3))
            self.assertTrue(restored.visited_xy([0, 58, 0], [15, 88, 15]))
            self.assertFalse(restored.covered([0, 58, 0], [16, 88, 15], 3))
            self.assertFalse(restored.covered([0, 58, 0], [15, 88, 15], 4))
            self.assertFalse(SurfaceGravelLedger(path, 'other.server', 'minecraft:overworld')
                             .covered([0, 58, 0], [15, 88, 15], 3))

    def test_partial_or_interrupted_area_remains_revisitable(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = SurfaceGravelLedger(Path(directory) / 'routes.json', 'server', 'overworld')
            low, high = [10, 58, 20], [25, 88, 35]
            ledger.record(low, high, 3, 'scanned', dry_candidates=4)
            self.assertFalse(ledger.covered(low, high, 3))
            ledger.record(low, high, 3, 'partial', remaining_safe=2)
            self.assertFalse(ledger.covered(low, high, 3))
            self.assertTrue(ledger.visited_xy(low, high))
            ledger.record(low, high, 3, 'exhausted', remaining_safe=0)
            self.assertTrue(ledger.covered(low, high, 3))
            self.assertEqual(1, len(ledger.data['entries']))

    def test_unknown_ledger_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'routes.json'
            path.write_text(json.dumps({'version': 99, 'entries': []}))
            with self.assertRaisesRegex(ValueError, 'refusing to overwrite'):
                SurfaceGravelLedger(path, 'server', 'overworld')
            self.assertEqual(99, json.loads(path.read_text())['version'])

    def test_blocked_route_is_skipped_only_until_retry_time(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger=SurfaceGravelLedger(Path(directory)/'routes.json','server','overworld')
            low,high=[0,58,0],[15,88,15]
            ledger.record(low,high,3,'blocked',retry_after_ms=9999999999999)
            self.assertTrue(ledger.covered(low,high,3))
            ledger.record(low,high,3,'blocked',retry_after_ms=1)
            self.assertFalse(ledger.covered(low,high,3))


if __name__ == '__main__':
    unittest.main()
