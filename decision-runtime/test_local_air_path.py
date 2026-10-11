from pathlib import Path
from types import SimpleNamespace
import json
import math
import tempfile
import unittest
from unittest.mock import Mock,patch

from material_jobs.local_air_path import plan,move
from material_jobs.protocol import JobBlocked


class LocalAirPathTests(unittest.TestCase):
    def test_existing_vertical_detour_avoids_low_roof_without_excavating(self):
        rows=[{'pos':[1,1,0]},{'pos':[1,2,0]}]
        path=plan(rows,[.5,0,.5],[2.5,0,.5],[0,0,0],[2,5,0])
        self.assertEqual([2.5,0,.5],path[-1]);self.assertTrue(any(p[1]>=3 for p in path))
        for p in path:
            self.assertFalse(p[0]==1.5 and p[1]in (0,1,2))

    def test_one_block_head_gap_is_not_an_air_corridor(self):
        with self.assertRaises(JobBlocked):plan([{'pos':[1,1,0]}],[.5,0,.5],[2.5,0,.5],[0,0,0],[2,1,0])

    def test_straight_stretches_remain_bounded_native_moves(self):
        path=plan([],[.5,0,.5],[.5,60,.5],[0,0,0],[0,63,0])
        self.assertEqual([.5,60,.5],path[-1])
        self.assertTrue(all(math.dist(a,b)<=16 for a,b in zip(path,path[1:])))

    def test_unknown_native_move_is_saved_and_not_replayed(self):
        c=SimpleNamespace(world='w',status=lambda:{'pos':[.5,0,.5]},last='unknown-nav')
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path._air_scan',return_value=[]),\
             patch('material_jobs.local_air_path._air_move',side_effect=RuntimeError('unknown'))as navigate:
            with self.assertRaises(RuntimeError):move(c,[2.5,0,.5],Path(d))
            raw=(Path(d)/'local-air-path.json').read_bytes();book=json.loads(raw)
            self.assertIsNotNone(book['pending']);self.assertFalse(book['complete']);self.assertFalse(book['mining_sent'])
            with self.assertRaises(JobBlocked):move(c,[2.5,0,.5],Path(d))
            self.assertEqual(raw,(Path(d)/'local-air-path.json').read_bytes());self.assertEqual(1,navigate.call_count)


if __name__=='__main__':unittest.main()
