import copy
import math
import unittest
from unittest.mock import patch

from kit_runtime.volume_scan import complete_blocks,IncompleteVolumeScan


class Client:
    world='w'
    def __init__(self):
        self.calls=[];self.revision=9;self.bad=None;self.clock=0
        self.blocks=[{'pos':[1,1,1],'state':'Block{minecraft:wall_torch}[facing=north]',
                      'solid':False,'fluid':False,'block_entity':False,'passable':True},
                     {'pos':[58,1,1],'state':'Block{minecraft:chest}[facing=south,type=single,waterlogged=false]',
                      'solid':False,'fluid':False,'block_entity':True,'passable':False}]
    def status(self):return {'world_session':self.world,'control_revision':self.revision}
    def request(self,op,**kw):
        assert op=='scan';self.calls.append(kw);lo,hi=kw['min'],kw['max']
        assert math.prod(b-a+1 for a,b in zip(lo,hi))<=50000
        rows=[copy.deepcopy(r)for r in self.blocks if all(lo[i]<=r['pos'][i]<=hi[i]for i in range(3))]
        r={'phase':'done','world_session':'w','blocks':rows,
           'scan_cells_read':math.prod(b-a+1 for a,b in zip(lo,hi)),
           'scan_start_revision':9,'scan_end_revision':9}
        if len(self.calls)==2:
            if self.bad=='partial':r['scan_cells_read']-=1
            if self.bad=='world':r['world_session']='other'
            if self.bad=='phase':r['phase']='waiting'
            if self.bad=='metadata':r.pop('scan_cells_read')
            if self.bad=='row':r['blocks'].append(copy.deepcopy(rows[0]))
            if self.bad=='revision':self.revision+=1
            if self.bad=='time':self.clock=13
            if self.bad=='measured_duration':self.clock=9
        return r


class VolumeScanTest(unittest.TestCase):
    low=[0,0,0];high=[59,26,43]
    def test_whole_71280_cell_projection_is_read_as_complete_disjoint_native_tiles(self):
        c=Client();result=complete_blocks(c,self.low,self.high)
        self.assertEqual(c.blocks,result);self.assertEqual(2,len(c.calls))
        self.assertEqual(71280,sum(math.prod(b-a+1 for a,b in zip(k['min'],k['max']))for k in c.calls))
        self.assertLess(c.calls[0]['max'][0],c.calls[1]['min'][0])
    def test_failed_second_tile_never_returns_a_partial_scene(self):
        for why in ('partial','world','phase','metadata','row','revision'):
            with self.subTest(why=why):
                c=Client();c.bad=why
                with self.assertRaises(IncompleteVolumeScan):complete_blocks(c,self.low,self.high)
    def test_time_spent_waiting_for_interface_cannot_make_old_tiles_fresh(self):
        c=Client();c.bad='time'
        with patch('kit_runtime.volume_scan.time.monotonic',side_effect=lambda:c.clock):
            with self.assertRaisesRegex(IncompleteVolumeScan,'过时'):complete_blocks(c,self.low,self.high)
    def test_measured_two_tile_duration_fits_the_bounded_window_when_scope_is_stable(self):
        c=Client();c.bad='measured_duration'
        with patch('kit_runtime.volume_scan.time.monotonic',side_effect=lambda:c.clock):
            self.assertEqual(c.blocks,complete_blocks(c,self.low,self.high))
    def test_unbounded_or_malformed_request_does_not_send_any_scan(self):
        for lo,hi in (([0,0,0],[99,99,99]),([0,0,0],[True,2,3]),([1,0,0],[0,1,1])):
            c=Client()
            with self.assertRaises(IncompleteVolumeScan):complete_blocks(c,lo,hi)
            self.assertEqual([],c.calls)
    def test_air_routes_may_ignore_retained_light_but_access_survey_keeps_its_attachment(self):
        from material_jobs.navigation import _air_scan
        from material_jobs.construction_access import _scan
        self.assertEqual([Client().blocks[1]],_air_scan(Client(),self.low,self.high))
        self.assertEqual(Client().blocks,_scan(Client(),self.low,self.high))
    def test_old_small_native_read_envelope_remains_compatible(self):
        class Small:
            world='w'
            def request(self,*a,**k):return {'world_session':'w','blocks':[]}
        self.assertEqual([],complete_blocks(Small(),[0,0,0],[1,1,1]))


if __name__=='__main__':unittest.main()
