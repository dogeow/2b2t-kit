import json
import math
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from material_jobs.discovery_access import stage
from material_jobs.protocol import JobBlocked


class DiscoveryAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)
        self.state={'world_session':'w','pos':[600.,88.,0.],'health':20,
                    'manual_movement':False,'navigating':False,'native_material_busy':False}
        self.c=SimpleNamespace(world='w',status=lambda:self.state,last='r')
        self.profile={'search_origin':[0.,100.,0.],'search_radius':128}

    def run_stage(self, effect=None):
        def arrive(c,target,*args,**kwargs):self.state['pos']=list(target)
        with patch('material_jobs.navigation.lift_for_travel',return_value=self.state)as lift,\
             patch('material_jobs.acquisition._travel',side_effect=effect or arrive)as travel:
            result=stage(self.c,self.profile,self.out,lambda:None)
        return result,lift,travel

    def test_far_origin_uses_only_bounded_collinear_normal_routes(self):
        result,lift,travel=self.run_stage()
        self.assertTrue(result);self.assertEqual(3,travel.call_count)
        start=[600.,88.,0.]
        for call in travel.call_args_list:
            target=call.args[1]
            self.assertLessEqual(math.hypot(target[0]-start[0],target[2]-start[2]),256)
            self.assertEqual(0,target[2]);self.assertTrue(call.kwargs['keep_cruise'])
            start=target
        self.assertEqual([0.,145.,0.],self.state['pos'])
        book=json.loads((self.out/'discovery-origin-access.json').read_text())
        self.assertTrue(book['complete']);self.assertIsNone(book['pending'])
        self.assertEqual(0,book['source_blocks_credited']);self.assertEqual(128,book['radius'])

    def test_near_origin_adds_no_travel(self):
        self.state['pos']=[20.,145.,0.]
        result,lift,travel=self.run_stage()
        self.assertFalse(result);lift.assert_not_called();travel.assert_not_called()

    def test_completed_access_is_archived_before_a_later_visit(self):
        self.run_stage();path=self.out/'discovery-origin-access.json';original=path.read_bytes()
        self.state['pos']=[600.,88.,0.]
        self.run_stage()
        archives=list(self.out.glob('completed-origin-access-*.json'))
        self.assertEqual(1,len(archives));self.assertEqual(original,archives[0].read_bytes())

    def test_unknown_segment_survives_without_replay_even_when_near_origin(self):
        with self.assertRaises(RuntimeError):self.run_stage(Mock(side_effect=RuntimeError('unknown')))
        path=self.out/'discovery-origin-access.json';original=path.read_bytes()
        self.state['pos']=[0.,145.,0.]
        with patch('material_jobs.navigation.lift_for_travel')as lift,\
             patch('material_jobs.acquisition._travel')as travel:
            with self.assertRaisesRegex(JobBlocked,'不重放'):stage(self.c,self.profile,self.out,lambda:None)
        self.assertEqual(original,path.read_bytes());lift.assert_not_called();travel.assert_not_called()

    def test_arrival_with_changed_world_or_height_never_completes(self):
        for field,value in (('world_session','other'),('pos',[400.,88.,0.])):
            with self.subTest(field=field),tempfile.TemporaryDirectory()as d:
                self.out=Path(d);self.state.update(world_session='w',pos=[600.,88.,0.])
                def bad(c,target,*args,**kwargs):self.state['pos']=list(target);self.state[field]=value
                with self.assertRaises(JobBlocked):self.run_stage(bad)
                book=json.loads((self.out/'discovery-origin-access.json').read_text())
                self.assertFalse(book['complete']);self.assertIsNotNone(book['pending'])

    def test_malformed_scope_and_excessive_distance_never_move(self):
        cases=[{'search_origin':[0,100,0],'search_radius':True},
               {'search_origin':[0,float('nan'),0],'search_radius':128},
               {'search_origin':[5000,100,0],'search_radius':128}]
        for profile in cases:
            with self.subTest(profile=profile),patch('material_jobs.navigation.lift_for_travel')as lift,\
                 patch('material_jobs.acquisition._travel')as travel:
                with self.assertRaises(JobBlocked):stage(self.c,profile,self.out,lambda:None)
                lift.assert_not_called();travel.assert_not_called()


if __name__=='__main__':unittest.main()
