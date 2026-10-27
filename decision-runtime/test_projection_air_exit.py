import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from material_jobs.projection_air_exit import plan_exit, leave, door_prefix,supported_door_leg
from material_jobs.protocol import JobBlocked


class ProjectionAirExitTests(unittest.TestCase):
    def test_door_edge_fallback_requires_a_short_same_level_dry_supported_route(self):
        rows=[{'pos':[0,-1,z],'state':'Block{minecraft:stone}','solid':True,'fluid':False,'block_entity':False}for z in(1,2)]
        self.assertEqual([.5,0,2.5],supported_door_leg(rows,[.5,0,1.3],[.5,.2,2.5],[-2,-2,-2],[2,3,5])[-1])
        for change in ({'fluid':True},{'block_entity':True},{'solid':False}):
            changed=[rows[0],{**rows[1],**change}]
            self.assertIsNone(supported_door_leg(changed,[.5,0,1.3],[.5,.2,2.5],[-2,-2,-2],[2,3,5]))
        self.assertIsNone(supported_door_leg(rows,[.5,.5,1.3],[.5,.2,2.5],[-2,-2,-2],[2,3,5]))

    def test_known_pre_move_door_edge_rejection_can_walk_on_observed_floor_then_exit(self):
        from material_jobs.local_air_path import ObservedAirPathBlocked
        state={'pos':[.5,0,-.5],'world_session':'w','control_revision':1,
               'projection_selection':{'min':[0,0,0],'max':[2,2,2]}}
        rows=[{'pos':[x,-1,z],'state':'Block{minecraft:stone}','solid':True,'fluid':False,'block_entity':False}
              for x in range(-2,5)for z in range(-2,7)]
        with tempfile.TemporaryDirectory()as d:
            c=SimpleNamespace(world='w',out=Path(d),rev=1,native_inflight=None,unconfirmed_native_request=None,last='scan')
            steps=[];air_calls=[]
            def crossed(*args):
                c.rev+=1;state.update(pos=[.5,0,1.3],control_revision=c.rev);return {'door':[0,0,0]}
            def ground(op,**kw):
                self.assertEqual('walk',op);self.assertTrue(kw['restore_flight']);steps.append(kw['target'])
                c.rev+=1;c.last='walk';state.update(pos=kw['target'],control_revision=c.rev)
            c.checked=ground
            def air(client,point,out,**kw):
                self.assertEqual(2,kw['max_straight'])
                air_calls.append(point)
                if len(air_calls)==1:
                    out.mkdir(parents=True);p=out/'local-air-path.json'
                    p.write_text(json.dumps({'world_session':'w','pending':None,'blocked_before_next_move':{'target':point}}))
                    raise ObservedAirPathBlocked(p)
                c.rev+=1;state.update(pos=point,control_revision=c.rev)
            with patch('material_jobs.navigation.settled_state',side_effect=lambda *a:state),\
                 patch('material_jobs.navigation._air_scan',return_value=rows),\
                 patch('material_jobs.projection_air_exit.plan_exit',side_effect=[JobBlocked('三维空气出口'),[[.5,.2,1.5],[.5,.2,2.5],[.5,.2,4.5]]]),\
                 patch('material_jobs.projection_air_exit.door_prefix',return_value=([],[0,0,0])),\
                 patch('door_access.cross_door',side_effect=crossed),\
                 patch('material_jobs.local_air_path.move',side_effect=air):
                self.assertTrue(leave(c,state,max_straight=2))
            book=json.loads(next(Path(d).glob('exit-3d-*/route.json')).read_text())
            self.assertTrue(book['complete']);self.assertIsNone(book['pending']);self.assertFalse(book['mining_sent'])
            self.assertEqual(1,len(book['known_air_rejections']));self.assertEqual([.5,0,2.5],steps[-1])
            self.assertEqual(2,len(air_calls))

    def test_door_plan_stops_before_real_door_and_rejects_wet_or_mismatched_pair(self):
        rows=[{'pos':[x,y,z],'state':'Block{minecraft:stone}'}
              for x in range(-1,7) for y in range(-1,5) for z in range(-1,2)
              if z!=0 or y not in (0,1) or x==-1]
        doors=[{'pos':[2,y,0],'fluid':False,'state':
                'Block{minecraft:oak_door}[facing=east,half=%s,hinge=left,open=true,powered=false]'%half}
               for y,half in ((0,'lower'),(1,'upper'))]
        prefix,door=door_prefix(rows+doors,[.5,.2,.5],[0,0,0],[3,2,0],[-1,-1,-1],[6,4,1])
        self.assertEqual([2,0,0],door);self.assertEqual([1.5,.1,.5],prefix[-1])
        self.assertTrue(all(p[0]<2 for p in prefix))
        for change in ({'fluid':True},{'state':doors[1]['state'].replace('open=true','open=false')}):
            with self.subTest(change=change),self.assertRaises(JobBlocked):
                door_prefix(rows+[doors[0],{**doors[1],**change}],[.5,.2,.5],
                            [0,0,0],[3,2,0],[-1,-1,-1],[6,4,1])

    def test_room_exits_via_existing_vertical_shaft_above_sealed_horizontal_slice(self):
        rows = [{'pos':[x,y,z]} for x in range(-1,4) for y in range(5) for z in range(-1,4)
                if x in (-1,3) or z in (-1,3)]
        path = plan_exit(rows,[1.5,0,1.5],[0,0,0],[2,3,2],[-2,0,-2],[4,9,4])
        self.assertTrue(any(p[1]>=5 for p in path))
        self.assertTrue(all(p[0]==1.5 and p[2]==1.5 for p in path))

    def test_two_block_corridor_keeps_headroom_after_native_vertical_settle(self):
        rows=[{'pos':[x,y,z]}for x in range(-1,7)for y in range(-1,4)for z in range(-1,2)
              if z!=0 or y not in(0,1)or x==-1]
        path=plan_exit(rows,[.5,.25,.5],[0,0,0],[3,2,0],[-1,-1,-1],[6,3,1])
        self.assertTrue(path)
        self.assertTrue(all(p[1]+.05+1.8<2 for p in path))

    def test_sealed_room_never_requests_excavation(self):
        rows = [{'pos':[x,y,z]} for x in range(-1,4) for y in range(5) for z in range(-1,4)
                if x in (-1,3) or z in (-1,3) or y==4]
        with self.assertRaises(JobBlocked):
            plan_exit(rows,[1.5,0,1.5],[0,0,0],[2,3,2],[-2,0,-2],[4,9,4])

    def test_unknown_movement_keeps_pending_and_never_tries_other_exit(self):
        state={'pos':[1.5,0,1.5],'world_session':'w','control_revision':1,
               'projection_selection':{'min':[0,0,0],'max':[2,3,2]}}
        with tempfile.TemporaryDirectory() as d:
            c=SimpleNamespace(world='w',out=Path(d))
            with patch('material_jobs.navigation.settled_state',return_value=state), \
                 patch('material_jobs.navigation._air_scan',return_value=[]), \
                 patch('material_jobs.local_air_path.move',side_effect=RuntimeError('unknown')) as nav:
                with self.assertRaisesRegex(RuntimeError,'unknown'): leave(c,state)
            self.assertEqual(1,nav.call_count)
            book=json.loads(next(Path(d).glob('exit-3d-*/route.json')).read_text())
            self.assertIsNotNone(book['pending']);self.assertFalse(book['complete']);self.assertFalse(book['mining_sent'])

    def test_owned_navigation_revision_is_accepted_before_next_leg(self):
        state={'pos':[1.5,0,1.5],'world_session':'w','control_revision':1,
               'projection_selection':{'min':[0,0,0],'max':[2,3,2]}}
        with tempfile.TemporaryDirectory() as d:
            c=SimpleNamespace(world='w',out=Path(d),rev=1)
            def nav(client,point,*args,**kwargs):
                c.rev+=1;state.update(pos=point,control_revision=c.rev)
            with patch('material_jobs.navigation.settled_state',side_effect=lambda *a:state), \
                 patch('material_jobs.navigation._air_scan',return_value=[]), \
                 patch('material_jobs.local_air_path.move',side_effect=nav):
                self.assertTrue(leave(c,state))
            self.assertGreater(c.rev,1)

    def test_projection_change_after_scan_prevents_any_movement(self):
        s={'pos':[1.5,0,1.5],'world_session':'w','control_revision':1,
           'projection_selection':{'min':[0,0,0],'max':[2,3,2]}}
        with patch('material_jobs.navigation.settled_state',return_value={**s,'control_revision':2}), \
             patch('material_jobs.navigation._air_scan',return_value=[]), \
             patch('material_jobs.local_air_path.move') as nav:
            with self.assertRaises(JobBlocked): leave(SimpleNamespace(),s)
        nav.assert_not_called()
