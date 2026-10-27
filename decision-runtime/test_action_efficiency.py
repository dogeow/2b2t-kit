import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from action_efficiency import summarize, ActionEfficiency


class EfficiencyTests(unittest.TestCase):
    def test_small_masks_and_excessive_audits_are_visible(self):
        rows = [{'op': 'projection_batch_set', 'elapsed_seconds': .3, 'mask_size': 5} for _ in range(3)]
        rows += [{'op': 'professional_print', 'elapsed_seconds': 2} for _ in range(3)]
        rows += [{'op': 'projection_audit', 'elapsed_seconds': .3} for _ in range(9)]
        report = summarize(rows)
        self.assertEqual(report['actions'], 15)
        self.assertEqual(len(report['warnings']), 2)
        self.assertEqual(report['by_operation']['professional_print']['count'], 3)

    def test_planner_gap_is_not_native_action_time(self):
        report = summarize([{'op': 'navigate', 'elapsed_seconds': 2, 'planner_gap_seconds': 8}])
        self.assertEqual(report['action_seconds'], 2)
        self.assertEqual(report['planner_gap_seconds'], 8)
        self.assertEqual(len(report['warnings']), 1)

    def test_empty_or_large_verified_batches_have_no_small_batch_warning(self):
        self.assertEqual(summarize([])['warnings'], [])
        rows = [{'op': 'projection_batch_set', 'elapsed_seconds': .3, 'mask_size': 15} for _ in range(3)]
        self.assertEqual(summarize(rows)['warnings'], [])

    def test_confirmed_throughput_counts_only_reported_ack_cells(self):
        report = summarize([{'op':'professional_print','elapsed_seconds':10,
                             'planner_gap_seconds':2,'confirmed_print_cells':24}])
        self.assertEqual(report['confirmed_print_cells'], 24)
        self.assertEqual(report['confirmed_print_cells_per_minute'], 120)

    def test_telemetry_failure_never_hides_action_receipt_or_exception(self):
        from village_queue import VillageQueue
        class BrokenMonitor:
            def record(self, *args):
                raise ValueError('broken timing report')
        q = VillageQueue.__new__(VillageQueue)
        q.efficiency = BrokenMonitor()
        q._send = lambda *args, **kwargs: {'id':'original-receipt'}
        self.assertEqual(q.send('native'), {'id':'original-receipt'})
        def fail(*args, **kwargs):
            raise RuntimeError('original unknown action')
        q._send = fail
        with self.assertRaisesRegex(RuntimeError, 'original unknown action'):
            q.send('native')

    def test_gap_between_plans_is_visible_but_another_world_is_not_charged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'action-efficiency-last.json'
            path.write_text(json.dumps({'world_session':'same','monotonic_end':90,'wall_end':990}))
            with patch('action_efficiency.time.monotonic', return_value=100), patch('action_efficiency.time.time', return_value=1000):
                self.assertEqual(ActionEfficiency(directory,'new','same').last_end, 90)
                self.assertEqual(ActionEfficiency(directory,'other','different').last_end, 100)

    def test_stale_monotonic_clock_does_not_invent_a_long_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'action-efficiency-last.json'
            path.write_text(json.dumps({'world_session':'same','monotonic_end':500,'wall_end':990}))
            with patch('action_efficiency.time.monotonic', return_value=100), patch('action_efficiency.time.time', return_value=1000):
                self.assertEqual(ActionEfficiency(directory,'new','same').last_end, 100)


if __name__ == '__main__':
    unittest.main()
