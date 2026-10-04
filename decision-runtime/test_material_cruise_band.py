"""Cruise-only proofs reduce terrain reads without changing real movement gates."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from material_jobs.acquisition import _travel_once, Unavailable
from test_material_loaded_approach import LocalServerClient
from pathlib import Path
import tempfile


class CruiseBandTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.c=LocalServerClient(Path(temp.name));self.c.state['pos']=[.5,95,.5]
        settled=patch('material_jobs.navigation.settled_state',side_effect=lambda c,*args:c.status())
        settled.start();self.addCleanup(settled.stop)
    def go(self,**kwargs):
        trace=[];_travel_once(self.c,[24.5,80,16.5],lambda:None,trace,**kwargs);return trace
    def scans(self):return [r for r in self.c.actions if r['op']=='scan']
    def moves(self):return [r for r in self.c.actions if r['op']=='navigate']
    def stone(self,pos):return {'pos':pos,'state':'Block{minecraft:stone}','fluid':False,'passable':False}

    def test_complete_clear_band_avoids319_and_preserves_cruise_and_final_target(self):
        trace=self.go(clearance_padding=2.32,obstacle_margin=5.1)
        self.assertFalse(any(r['params']['max'][1]==319 for r in self.scans()))
        bands=__import__('json').loads((self.c.out/'cruise-band-latest.json').read_text())['observations']
        self.assertEqual(len(bands),2);self.assertTrue(all(r['clear']for r in bands))
        self.assertTrue(all(r['params']['air_only']for r in self.moves()))
        self.assertTrue(all(abs(r['from'][1]-95)<.001 for r in self.moves()if r['from'][0]!=r['params']['target'][0]or r['from'][2]!=r['params']['target'][2]))
        self.assertEqual(self.c.state['pos'],[24.5,80,16.5])
        self.assertTrue(all(__import__('math').dist(r['from'],r['params']['target'])<=31.000001 for r in self.moves()))
        self.assertEqual({r['id']for r in self.moves()},{r['request_id']for r in trace if r.get('phase')=='done'})

    def test_floating_overhead_outside_body_band_does_not_force_unnecessary_ascent(self):
        self.c.rows=[self.stone([10,170,0])];self.go()
        self.assertFalse(any(r['params']['max'][1]==319 for r in self.scans()))
        self.assertLessEqual(max(r['params']['target'][1]for r in self.moves()),95)

    def test_known_obstacle_or_fluid_uses_original_full_height_fallback(self):
        for fluid in (False,True):
            with self.subTest(fluid=fluid):
                self.c.actions=[];self.c.state['pos']=[.5,95,.5]
                self.c.rows=[{**self.stone([10,y,0]),'fluid':fluid}for y in range(95,121)]
                trace=self.go();self.assertTrue(any(r['params']['max'][1]==319 for r in self.scans()))
                self.assertTrue(any(r.get('clear')is False for r in __import__('json').loads((self.c.out/'cruise-band-latest.json').read_text())['observations']))
                self.assertGreaterEqual(max(r['params']['target'][1]for r in self.moves()),123.1)

    def test_unknown_partial_unloaded_stale_or_incomplete_details_never_fallback_or_move(self):
        original=self.c.request
        for change in ({'phase':'waiting'},{'scan_cells_read':0},{'world_session':'foreign'},
                       {'scan_end_revision':8},{'id':'stale'}, {'blocks':[{'pos':[0,95,0],'state':'Block{minecraft:short_grass}','fluid':False}]}):
            with self.subTest(change=change):
                self.c.actions=[];self.c.state['pos']=[.5,95,.5]
                def request(op,**params):
                    reply=original(op,**params)
                    return reply|change if op=='scan'else reply
                self.c.request=request
                with self.assertRaises(Unavailable):self.go()
                self.assertEqual(len(self.scans()),1);self.assertEqual(self.moves(),[])
                self.assertNotEqual(self.scans()[0]['params']['max'][1],319)
        self.c.request=original

    def test_actual_height_drift_guard_manual_health_or_native_unknown_stops_before_move(self):
        original=self.c.request
        for case in ('height','guard','manual','health','unknown'):
            with self.subTest(case=case):
                self.c.actions=[];self.c.state.update(pos=[.5,95,.5],health=20,manual_movement=False,guard_busy=False,native_material_busy=False)
                self.c.native_inflight=None
                def request(op,**params):
                    reply=original(op,**params)
                    if op=='scan':
                        if case=='height':self.c.state['pos'][1]+=1
                        elif case=='guard':self.c.state['guard_busy']=True
                        elif case=='manual':self.c.state['manual_movement']=True
                        elif case=='health':self.c.state['health']=18
                        else:
                            self.c.native_inflight={'request_id':self.c.last,'op':'scan'}
                            raise RuntimeError('Original read unknown')
                    return reply
                self.c.request=request
                with self.assertRaises((Unavailable,RuntimeError)):self.go()
                self.assertEqual(self.moves(),[]);self.assertEqual(len(self.scans()),1)
                if case=='unknown':self.assertEqual(self.c.native_inflight['request_id'],self.c.last)

    def test_vertical_entry_and_exit_body_still_need_fresh_real_clearance(self):
        self.c.rows=[self.stone([24,85,16])]
        with self.assertRaises(Unavailable):self.go()
        self.assertTrue(self.moves())
        self.assertEqual(self.c.state['pos'],[24.5,95,16.5])
        self.assertTrue(any(r['params']['min'][1]==80 and r['params']['max'][1]>=96 for r in self.scans()))


if __name__=='__main__':unittest.main()
