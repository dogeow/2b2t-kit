import unittest
import tempfile,math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from material_jobs.cave_return import route,run
from material_jobs.protocol import JobBlocked


class CaveReturnTest(unittest.TestCase):
    def test_exit_can_detour_outside_the_endpoints_small_box(self):
        # The wall extends beyond the narrow endpoint box; its sole opening
        # is still inside the complete current cave survey.
        rows = [{'pos': [2, y, z]} for y in (2, 3) for z in range(-3, 4)]
        start, target = [.5, 2.2, .5], [4.5, 2.2, .5]
        with self.assertRaises(JobBlocked):
            route(rows, start, target, [0, 2, -3], [4, 3, 3])
        result = route(rows, start, target, [0, 2, -4], [4, 3, 4])
        self.assertEqual(target, result[-1])
        self.assertTrue(any(abs(point[2]) >= 3.5 for point in result))

    def test_missing_route_never_authorizes_wall_removal(self):
        rows = [{'pos': [2, y, z]} for y in (2, 3) for z in range(-4, 5)]
        with self.assertRaises(JobBlocked):
            route(rows, [.5, 2.2, .5], [4.5, 2.2, .5], [0, 2, -4], [4, 3, 4])

    def test_oversized_volume_is_refused(self):
        with self.assertRaises(ValueError):
            route([], [.5, 2.2, .5], [4.5, 2.2, .5], [0, 0, 0], [100, 100, 100])

    def test_complete_return_volume_is_split_without_raising_native_scan_limit(self):
        state={'pos':[.5,2.2,.5]};c=SimpleNamespace(world='w',last='r',status=lambda:state)
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.cave_return._scan',return_value=[])as scan,\
             patch('material_jobs.cave_return.move'):
            run(c,[4.5,2.2,.5],{'min':[0,0,0],'max':[99,19,99]},Path(d)/'exit',lambda:None)
        volumes=[math.prod(b-a+1 for a,b in zip(call.args[1],call.args[2]))for call in scan.call_args_list]
        self.assertEqual(200000,sum(volumes));self.assertTrue(all(v<=50000 for v in volumes));self.assertEqual(4,len(volumes))

    def test_observed_pickup_below_original_source_bounds_can_return_through_air(self):
        state={'pos':[.5,2.2,.5]};c=SimpleNamespace(world='w',last='r',status=lambda:state)
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.cave_return._scan',return_value=[])as scan,\
             patch('material_jobs.cave_return.move'):
            points=run(c,[4.5,5.2,.5],{'min':[0,4,0],'max':[6,9,6]},Path(d)/'exit',lambda:None)
        self.assertLess(scan.call_args.args[1][1],4);self.assertEqual([4.5,5.2,.5],points[-1])


if __name__ == '__main__': unittest.main()
