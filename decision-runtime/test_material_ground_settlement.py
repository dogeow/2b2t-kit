"""Only a proved owned completed walk may settle its tiny gravity/inertia landing."""
import copy
import itertools
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from material_client import Client,MaterialClient,Handoff


class GroundSettlementTest(unittest.TestCase):
    ORIGIN=[761019.2065748374,64.1212968405392,797849.9672616947]
    LANDED=[761019.4158723903,64.0,797850.3472809161]
    TARGET=[761019.5,65,797850.5]

    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        c=self.client=MaterialClient.__new__(MaterialClient)
        c.root=c.out=Path(temp.name);c.world='world';c.rev=42;c.task='task';c.last='walk-owned'
        c.heartbeat=SimpleNamespace(id='lease');c.park_target=[761019.5,140,797850.5]
        self.terminal={'time':1000,'connected':True,'world_session':'world','control_revision':42,
            'server':'simpcraft.com','dimension':'minecraft:overworld','screen':'','last_request':c.last,
            'health':20,'flight':False,'on_ground':False,'under_water':False,'manual_movement':False,
            'guard_armed':True,'guard_pve_only':True,'guard_busy':False,'kill_aura':True,'auto_log':True,
            'navigating':False,'native_material_busy':False,'recent_hurt_at':123,'recent_attacker':'old damage',
            'safety_hold':{'active':False,'time':123},'pos':self.ORIGIN,'velocity':[.07,-.0784,.08],
            'movement_keys':{'forward':False,'back':False,'jump':False,'sneak':False},
            'supervision_lease':{'id':'lease','job_session':'task','world_session':'world','revision':42,
                'kind':'materials','remote_finish':'guard'}}
        c.last_owned_ground_walk={'request_id':c.last,'world_session':c.world,'task_session':c.task,
            'revision':42,'op':'walk','phase':'done','params':{'target':self.TARGET,'arrival':.7,'restore_flight':False},
            'before_damage':{'recent_hurt_at':123,'recent_attacker':'old damage'},
            'before_safety_hold':copy.deepcopy(self.terminal['safety_hold']),'terminal':copy.deepcopy(self.terminal)}
        self.state=copy.deepcopy(self.terminal);self.actions=[];self.reads=[]
        self.landed={**copy.deepcopy(self.terminal),'time':2000,'pos':self.LANDED,
            'velocity':[.01,-.0784,.01],'on_ground':True}

    def clock(self):
        return patch('material_client.time.monotonic',side_effect=itertools.count(step=.1))

    def test_tiny_gravity_and_inertia_landing_rebases_before_fresh_column_scan_and_takeoff(self):
        c=self.client
        settled={**self.landed,'time':3000}
        reached={**settled,'time':4000,'pos':[self.LANDED[0],140,self.LANDED[2]],'flight':True}
        states=iter([self.landed,settled,settled,reached])
        def status(wait_seconds=None):
            self.reads.append(wait_seconds);return next(states)
        def request(op,**params):
            self.actions.append((op,params))
            if op=='scan':
                self.assertEqual(761019,params['min'][0], 'Scan must use the landed body column, not the falling pose')
                return {'phase':'done','world_session':c.world,'blocks':[]}
            self.assertEqual('navigate',op);self.assertTrue(params['air_only'])
            self.assertEqual([self.LANDED[0],140,self.LANDED[2]],params['target'])
            return {'phase':'done'}
        c.status=status;c.request=request
        with self.clock(),patch('material_client.time.sleep'):
            self.assertIs(reached,c._finish_vertical(self.state))
        self.assertEqual([0,0,None,None],self.reads)
        self.assertEqual(['scan','navigate'],[op for op,_ in self.actions])
        evidence=json.loads((c.out/'park-ground-settlement.json').read_text())
        self.assertEqual(self.LANDED,evidence['settled']);self.assertGreaterEqual(evidence['observed_span_ms'],400)

    def test_repeated_same_snapshot_is_not_ground_settlement_and_wait_is_bounded(self):
        c=self.client;c.status=lambda wait_seconds=None:copy.deepcopy(self.landed)
        with self.clock(),patch('material_client.time.sleep') as sleeping:
            with self.assertRaisesRegex(RuntimeError,'two seconds'):c._settle_owned_ground_walk(self.state)
        self.assertFalse(self.actions);self.assertLessEqual(sleeping.call_count,21)
        self.assertFalse((c.out/'park-ground-settlement.json').exists())

    def test_foreign_unfinished_manual_damage_drop_and_unbounded_motion_fail_before_action(self):
        cases={
            'no_owned_walk':lambda:setattr(self.client,'last_owned_ground_walk',None),
            'not_done':lambda:self.client.last_owned_ground_walk.update(phase='waiting'),
            'flight_restored':lambda:self.client.last_owned_ground_walk['params'].update(restore_flight=True),
            'foreign_world':lambda:self.state.update(world_session='foreign'),
            'foreign_revision':lambda:self.state.update(control_revision=43),
            'foreign_request':lambda:self.state.update(last_request='foreign'),
            'foreign_lease':lambda:self.state['supervision_lease'].update(id='foreign'),
            'manual_takeover':lambda:self.state.update(manual_movement=True),
            'drop':lambda:self.state.update(pos=[self.ORIGIN[0],self.ORIGIN[1]-1,self.ORIGIN[2]]),
            'over_one_block':lambda:self.state.update(pos=[self.ORIGIN[0]+1.1,self.ORIGIN[1],self.ORIGIN[2]]),
            'outside_arrival':lambda:self.state.update(pos=[self.TARGET[0],self.ORIGIN[1],self.TARGET[2]+.8]),
            'injured':lambda:self.state.update(health=19),
            'absorbed_damage':lambda:self.state.update(recent_hurt_at=124),
            'damaged_during_walk':lambda:self.client.last_owned_ground_walk['before_damage'].update(recent_hurt_at=122),
            'guard_busy':lambda:self.state.update(guard_busy=True),
            'guard_disabled':lambda:self.state.update(guard_armed=False),
            'aura_disabled':lambda:self.state.update(kill_aura=False),
            'autolog_disabled':lambda:self.state.update(auto_log=False),
            'safety_hold':lambda:self.state['safety_hold'].update(active=True),
            'changed_hold':lambda:self.state['safety_hold'].update(time=124),
            'menu_opened':lambda:self.state.update(screen='ContainerScreen'),
            'water':lambda:self.state.update(under_water=True),
            'human_key':lambda:self.state['movement_keys'].update(forward=True),
            'unknown_velocity':lambda:self.state.pop('velocity'),
        }
        for name,mutate in cases.items():
            with self.subTest(name=name):
                self.setUp();mutate()
                self.client.status=lambda **kwargs:(_ for _ in ()).throw(AssertionError('Unsafe ownership must not poll further'))
                self.client.request=lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('No action before settlement proof'))
                with self.assertRaises(RuntimeError):self.client._settle_owned_ground_walk(self.state)
                self.assertFalse((self.client.out/'park-ground-settlement.json').exists())

    def test_changed_protection_during_wait_does_not_scan_or_enable_flight(self):
        for change in ({'health':19},{'guard_busy':True},{'manual_movement':True},{'world_session':'foreign'}):
            with self.subTest(change=change):
                self.setUp();fresh={**copy.deepcopy(self.landed),**change}
                self.client.status=lambda **kwargs:fresh
                self.client.request=lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('No action after protection changed'))
                with self.clock(),patch('material_client.time.sleep'):
                    with self.assertRaises(RuntimeError):self.client._finish_vertical(self.state)

    def test_unowned_falling_pose_keeps_the_existing_ascent_refusal(self):
        c=self.client;c.last_owned_ground_walk=None;c.status=lambda:self.landed
        def request(op,**params):
            self.actions.append(op);self.assertEqual('scan',op)
            return {'world_session':c.world,'blocks':[]}
        c.request=request
        with self.assertRaisesRegex(RuntimeError,'position or protection changed'):c._finish_vertical(self.state)
        self.assertEqual(['scan'],self.actions)


class GroundWalkProofLifetimeTest(unittest.TestCase):
    def client(self,directory):
        fixture=GroundSettlementTest();fixture.setUp();self.addCleanup(fixture.doCleanups)
        c=fixture.client;c.root=c.out=Path(directory);c.anchor=fixture.ORIGIN
        c.server='simpcraft.com';c.owned=True;c.rev=41
        state={**copy.deepcopy(fixture.terminal),'control_revision':41,'health':20}
        state['supervision_lease']['revision']=41
        c.status=lambda **kwargs:copy.deepcopy(state)
        def raw(**kwargs):
            request=json.loads((c.root/'request.json').read_text())
            revision=state['control_revision']+(1 if request['op']=='walk' else 0)
            state.update(id=request['id'],last_request=request['id'],control_revision=revision,phase='done')
            state['supervision_lease']['revision']=revision
            return copy.deepcopy(state)
        c.raw=raw
        return c

    def test_completed_walk_proof_survives_owned_scan_but_any_mutating_dispatch_invalidates_it(self):
        with tempfile.TemporaryDirectory() as directory:
            c=self.client(directory)
            Client.request(c,'walk',target=GroundSettlementTest.TARGET,arrival=.7,restore_flight=False)
            proof=copy.deepcopy(c.last_owned_ground_walk)
            self.assertEqual('walk',proof['op']);self.assertEqual(c.last,proof['request_id'])
            Client.request(c,'scan',min=[0,64,0],max=[0,64,0])
            self.assertEqual('scan',c.last_terminal_evidence['op']);self.assertEqual(proof,c.last_owned_ground_walk)
            Client.request(c,'select_item',item='minecraft:diamond_sword')
            self.assertIsNone(c.last_owned_ground_walk)

    def test_world_or_manual_handoff_clears_the_dedicated_proof(self):
        for change in ({'world_session':'foreign'},{'manual_movement':True},{'control_revision':99}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                c=self.client(directory);state=copy.deepcopy(c.last_owned_ground_walk['terminal']);state.update(change)
                c.raw=lambda **kwargs:state
                with self.assertRaises(Handoff):Client.status(c,wait_seconds=0)
                self.assertIsNone(c.last_owned_ground_walk)

    def test_zero_wait_observation_reaches_read_fresh_without_the_six_second_retry(self):
        c=Client.__new__(Client);c.root=Path('/unused')
        with patch('live_snapshot.read_fresh',side_effect=RuntimeError('stale')) as reading:
            with self.assertRaises(RuntimeError):Client.raw(c,wait_seconds=0)
        reading.assert_called_once_with(c.root,wait_seconds=0)


if __name__=='__main__':unittest.main()
