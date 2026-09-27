import json
from pathlib import Path
import tempfile
import unittest

from material_jobs.acquisition import Unavailable
from material_jobs.quarry_vegetation import clear_entrance


class QuarryVegetationTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'automation';self.root.mkdir()
        self.world='world';self.last=None;self.calls=[];self.cells={};self.uncertain=False
        self.position=[1,69.1,1]
        self.region={'source':'natural_survey','surface_y':66,
                     'access_shaft':{'min':[0,15,0],'max':[1,66,1]}}

    def status(self):
        return {'pos':self.position,'health':20,'food':20,'guard_armed':True,'guard_pve_only':True,'time':1}

    def request(self,op,**p):
        if op=='scan':
            return {'blocks':[r for pos,r in self.cells.items() if all(p['min'][i]<=pos[i]<=p['max'][i] for i in range(3))]}
        self.calls.append(p);self.last='mine-'+str(len(self.calls))
        if self.uncertain:raise RuntimeError('Unknown acknowledgement')
        pos=tuple(p['pos']);self.cells.pop(pos)
        # Real tall plants remove their paired half after the normal hit.
        for other in ((pos[0],pos[1]-1,pos[2]),(pos[0],pos[1]+1,pos[2])):
            if other in self.cells and 'tall_grass' in self.cells[other]['state']:self.cells.pop(other)
        return {'id':self.last,'world_session':self.world,'phase':'done'}

    def plant(self,pos,name='tall_grass',**changes):
        self.cells[tuple(pos)]={'pos':list(pos),'state':'Block{minecraft:'+name+'}',
                               'passable':True,'fluid':False,'block_entity':False,**changes}

    def clear(self):return clear_entrance(self,self.region,[0,49,0],[1,66,1],lambda:None)

    def test_clears_actual_upper_half_once_and_preserves_outside_footprint(self):
        self.plant([0,67,0]);self.plant([0,68,0]);self.plant([2,67,0])
        self.assertEqual(1,self.clear());self.assertEqual([0,68,0],self.calls[0]['pos'])
        self.assertEqual({(2,67,0)},set(self.cells))
        records=list(self.root.parent.glob('quarry-entrance-clearing/*.json'))
        self.assertEqual('confirmed',json.loads(records[0].read_text())['attempts'][0]['state'])

    def test_preserves_flowers_crops_solid_wet_and_container_cells(self):
        for name,changes in [('dandelion',{}),('wheat',{}),('short_grass',{'fluid':True}),
                             ('short_grass',{'passable':False}),('short_grass',{'block_entity':True})]:
            with self.subTest(name=name,changes=changes):
                self.cells.clear();self.plant([0,67,0],name,**changes)
                with self.assertRaises(Unavailable):self.clear()
                self.assertFalse(self.calls)

    def test_unknown_mining_ack_is_journaled_and_never_replayed(self):
        self.plant([0,68,0]);self.uncertain=True
        with self.assertRaises(RuntimeError):self.clear()
        self.uncertain=False
        with self.assertRaisesRegex(Unavailable,'回执不确定'):self.clear()
        self.assertEqual(1,len(self.calls))
        record=json.loads(next(self.root.parent.glob('quarry-entrance-clearing/*.json')).read_text())
        self.assertEqual('mine-1',record['attempts'][0]['request_id'])

    def test_lower_segment_and_unapproved_region_do_not_clear_surface(self):
        self.plant([0,68,0])
        self.assertEqual(0,clear_entrance(self,self.region,[0,31,0],[1,48,1],lambda:None))
        self.region['source']='user_area';self.assertEqual(0,self.clear());self.assertFalse(self.calls)

    def test_out_of_reach_is_not_an_air_mining_request(self):
        self.plant([0,67,0]);self.position=[1,80,1]
        with self.assertRaisesRegex(Unavailable,'距离'):self.clear()
        self.assertFalse(self.calls)


if __name__=='__main__':unittest.main()
