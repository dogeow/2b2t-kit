import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from material_jobs.resource_trip import travel
from material_jobs.acquisition import Unavailable


class FakeClient:
    world='w';task='own';last='initial';native_inflight=None
    def __init__(self,*,failed=False,manual=False):
        self.anchor=[0.,140.,0.];self.pos=self.anchor[:];self.actions=[]
        self.failed=failed;self.manual=manual
    def status(self):
        return {'world_session':'w','connected':True,'health':20,'food':20,
            'pos':self.pos[:],'guard_armed':True,'guard_pve_only':True,
            'manual_movement':self.manual,'control_revision':1,'supervision_lease':{
                'world_session':'w','kind':'materials','job_session':'own','revision':1}}
    def checked(self,op,**kw):self.actions.append((op,kw));self.last='guard'
    def request(self,op,**kw):
        self.actions.append((op,kw));self.last='leg-'+str(len(self.actions))
        if self.failed:raise RuntimeError('unknown navigation')
        self.pos=kw['target'][:];return {'phase':'done'}
    def set_progress(self,**kw):pass


class ResourceTripTest(unittest.TestCase):
    def test_finite_owned_segments_do_not_turn_arrival_into_resource_credit(self):
        c=FakeClient()
        with tempfile.TemporaryDirectory()as out,patch('material_jobs.resource_trip.settled_state',side_effect=lambda c,*a:c.status()):
            book=travel(c,[700.,140.,0.],Path(out)/'new-trip',lambda:None,home=[0.,140.,0.],max_radius=900)
            self.assertTrue((Path(out)/'new-trip/resource-trip.json').exists())
        legs=[kw for op,kw in c.actions if op=='navigate']
        self.assertEqual(11,len(legs));self.assertTrue(book['complete'])
        self.assertEqual([64.,140.,0.],legs[0]['target'])
        self.assertFalse(book['source_verified']);self.assertEqual(0,book['inventory_credit'])
        self.assertTrue(all(kw.get('air_only')is True for kw in legs))

    def test_vertical_normalization_does_not_make_a_large_diagonal_body_sweep(self):
        c=FakeClient();c.pos=[0.,110.,0.]
        with tempfile.TemporaryDirectory()as out,patch('material_jobs.resource_trip.settled_state',side_effect=lambda c,*a:c.status()):
            travel(c,[70.,140.,0.],out,lambda:None,home=[0.,140.,0.],max_radius=900)
        legs=[kw for op,kw in c.actions if op=='navigate']
        self.assertEqual([0.,140.,0.],legs[0]['target'])
        self.assertEqual([64.,140.,0.],legs[1]['target'])

    def test_unknown_original_move_is_retained_and_not_retried(self):
        c=FakeClient(failed=True)
        with tempfile.TemporaryDirectory()as out:
            with self.assertRaisesRegex(RuntimeError,'unknown'):
                travel(c,[700.,140.,0.],out,lambda:None,home=[0.,140.,0.],max_radius=900)
            book=json.loads((Path(out)/'resource-trip.json').read_text())
            self.assertTrue(book['pending']['request_id']);self.assertFalse(book['complete'])
            count=len(c.actions)
            with self.assertRaisesRegex(RuntimeError,'Original trip retained'):
                travel(c,[700.,140.,0.],out,lambda:None,home=[0.,140.,0.],max_radius=900)
            self.assertEqual(count,len(c.actions))

    def test_manual_takeover_or_wrong_owner_sends_no_actions(self):
        for kind in ('manual','foreign'):
            c=FakeClient(manual=kind=='manual')
            if kind=='foreign':
                original=c.status
                c.status=lambda:{**original(),'supervision_lease':{'kind':'materials','job_session':'foreign'}}
            with tempfile.TemporaryDirectory()as out,self.assertRaises((RuntimeError,Unavailable)):
                travel(c,[700.,140.,0.],out,lambda:None,home=[0.,140.,0.],max_radius=900)
            self.assertEqual([],c.actions)

    def test_outside_finite_hint_radius_sends_no_actions(self):
        c=FakeClient()
        with tempfile.TemporaryDirectory()as out,self.assertRaises(ValueError):
            travel(c,[1000.,140.,0.],out,lambda:None,home=[0.,140.,0.],max_radius=900)
        self.assertEqual([],c.actions)

if __name__=='__main__':unittest.main()
