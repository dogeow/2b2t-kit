import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from material_jobs.level_air_route import move
from material_jobs.protocol import JobBlocked


class LevelAirRouteTests(unittest.TestCase):
    def client(self, blocks=None, read=50, world='w'):
        scan = {'world_session': world, 'scan_cells_read': read,
                'scan_total_cells': 50, 'blocks': blocks or [], 'id': 'scan'}
        return SimpleNamespace(world='w', last='nav',
            status=lambda: {'pos': [.5, 65.05, .5]},
            request=Mock(side_effect=[scan, {'phase': 'done'}]))

    def test_sea_search_moves_once_at_work_height_without_rising(self):
        c = self.client()
        with TemporaryDirectory() as d, patch(
                'material_jobs.level_air_route.settled_state',
                return_value={'pos': [24.5, 65.05, .5]}):
            proof = move(c, [24.5, 65.2, .5], d)
        self.assertTrue(proof['complete'])
        self.assertEqual('navigate', c.request.call_args.args[0])
        self.assertEqual([24.5, 65.2, .5], c.request.call_args.kwargs['target'])
        self.assertEqual(2, c.request.call_count)

    def test_observed_land_does_not_dispatch_or_raise_to_cruise_height(self):
        c = self.client(blocks=[{'pos': [12, 65, 0]}])
        with TemporaryDirectory() as d:
            proof = move(c, [24.5, 65.2, .5], d)
        self.assertTrue(proof['blocked'])
        self.assertEqual(1, c.request.call_count)

    def test_partial_or_other_world_scan_never_becomes_clear_air(self):
        for c in (self.client(read=49), self.client(world='old')):
            with TemporaryDirectory() as d, self.assertRaises(JobBlocked):
                move(c, [24.5, 65.2, .5], d)
            self.assertEqual(1, c.request.call_count)

    def test_uncertain_original_move_is_saved_and_cannot_be_replayed(self):
        c = self.client()
        scan = c.request.side_effect
        c.request.side_effect = [next(scan), RuntimeError('unknown')]
        with TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                move(c, [24.5, 65.2, .5], d)
            p = Path(d) / 'level-air-route.json'
            old = p.read_bytes()
            self.assertIsNotNone(json.loads(old)['pending'])
            with self.assertRaises(JobBlocked):
                move(c, [24.5, 65.2, .5], d)
            self.assertEqual(old, p.read_bytes())
        self.assertEqual(2, c.request.call_count)

    def test_new_cruise_height_is_rejected_without_actions(self):
        c = self.client()
        with TemporaryDirectory() as d, self.assertRaises(JobBlocked):
            move(c, [24.5, 96, .5], d)
        c.request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
