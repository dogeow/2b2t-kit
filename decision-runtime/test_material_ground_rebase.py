import copy
import itertools
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import material_ground_finish as module
from material_client import MaterialClient
from potato_farm import ENTITY_SCOPE


class GroundRebaseTests(unittest.TestCase):
    WALK=[761019.4283174783,64.41999998688698,797850.3709482464]
    AFTER=[761019.7382545668,65.25220334025373,797850.9289817283]
    LANDED=[761019.9,64.0,797851.3]

    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        c=self.c=MaterialClient.__new__(MaterialClient);c.root=c.out=Path(tmp.name)
        c.world='world';c.task='task';c.rev=42;c.last='scan-owned';c.heartbeat=SimpleNamespace(id='lease')
        c.native_inflight=None;c.unconfirmed_native_request=None;c.park_target=[761019.5,88,797850.5]
        inventory=[{'slot':i,'item':'minecraft:dirt'if i==5 else'minecraft:air','count':10 if i==5 else 0}for i in range(36)]
        term={'time':1000,'connected':True,'world_session':'world','control_revision':42,'last_request':'walk-owned',
            'server':'simpcraft.com:25565','dimension':'minecraft:overworld','player_uuid':'player','projection_selection':{'key':'map'},
            'screen':'','health':20,'food':20,'air_supply':300,'inventory':inventory,'flight':False,'on_ground':False,
            'under_water':False,'manual_movement':False,'guard_armed':True,'guard_pve_only':True,'guard_busy':False,
            'kill_aura':True,'auto_log':True,'navigating':False,'native_material_busy':False,
            'recent_hurt_at':123,'recent_attacker':'old','safety_hold':{'active':False},
            'pos':self.WALK,'velocity':[.07419340816407016,.33319999363422365,.13358325743278696],
            'movement_keys':{'forward':False,'back':False,'jump':False,'sneak':False},
            'supervision_lease':{'id':'lease','kind':'materials','world_session':'world','job_session':'task','revision':42,'remote_finish':'guard'}}
        c.last_owned_ground_walk={'pose_rebase_schema':1,'op':'walk','phase':'done','request_id':'walk-owned',
            'world_session':'world','task_session':'task','revision':42,
            'params':{'target':[761019.5,65,797850.5],'arrival':.4,'restore_flight':False},
            'terminal':copy.deepcopy(term),'before_inventory':copy.deepcopy(inventory),
            'before_damage':{'recent_hurt_at':123,'recent_attacker':'old'},'before_safety_hold':{'active':False}}
        c.last_terminal_evidence={'request_id':c.last,'op':'scan','phase':'done','task_session':'task','world_session':'world','revision_after':42}
        self.after={**copy.deepcopy(term),'time':1300,'last_request':c.last,'pos':self.AFTER,
                    'velocity':[.046299078320561404,-.07544406518948656,.08336025869736821]}
        self.landed={**copy.deepcopy(self.after),'time':2000,'pos':self.LANDED,'on_ground':True,'velocity':[.01,-.0784,.01]}
        self.stable={**copy.deepcopy(self.landed),'time':2450}
        self.actions=[]

    def clock(self):return patch('material_ground_finish.time.monotonic',side_effect=itertools.count(step=.1))

    def settle(self):
        states=iter([self.landed,self.stable]);self.c.raw=lambda **kwargs:next(states)
        with self.clock(),patch('material_ground_finish.time.sleep'):
            return module.settle(self.c,self.after)

    def test_real_jump_and_arrival_overshoot_use_actual_stable_pose_without_rewalking(self):
        self.assertGreater(self.AFTER[1]-self.WALK[1],.05)
        self.assertGreater(math.hypot(self.AFTER[0]-761019.5,self.AFTER[2]-797850.5),.4)
        self.assertGreater(math.hypot(self.LANDED[0]-self.WALK[0],self.LANDED[2]-self.WALK[2]),1)
        self.c.request=lambda *args,**kwargs:self.fail('Settlement cannot dispatch any action')
        self.assertEqual(self.LANDED,self.settle()['pos'])
        self.assertEqual(self.LANDED,self.c.ground_finish_rebase['settled']['pos'])

    def test_unknown_identity_manual_health_inventory_and_scope_changes_never_scan(self):
        changes=[{'health':19},{'world_session':'other'},{'manual_movement':True},{'guard_busy':True},
                 {'player_uuid':'other'},{'control_revision':43},{'screen':'ContainerScreen'}]
        for change in changes:
            with self.subTest(change=change):
                self.setUp();self.after.update(change);self.c.request=lambda *a,**k:self.fail('No action')
                with self.assertRaises(module.GroundFinishStop):module.settle(self.c,self.after)
        self.setUp();self.c.last_terminal_evidence['request_id']='old'
        with self.assertRaises(module.GroundFinishStop):module.settle(self.c,self.after)
        self.setUp();self.after['inventory'][5]['count']=9
        with self.assertRaises(module.GroundFinishStop):module.settle(self.c,self.after)

    def test_repeated_frame_airborne_or_unbounded_motion_is_not_current_pose_evidence(self):
        self.c.status=lambda **kwargs:self.landed
        with self.clock(),patch('material_ground_finish.time.sleep'),self.assertRaises(module.GroundFinishStop):
            module.settle(self.c,self.after)
        self.setUp();self.after['pos']=[self.WALK[0]+2,self.WALK[1],self.WALK[2]]
        with self.assertRaises(module.GroundFinishStop):module.settle(self.c,self.after)

    def scan_reply(self,low,high):
        total=math.prod(b-a+1 for a,b in zip(low,high))
        rows=[]
        if low[1]==-64:
            for x in range(low[0],high[0]+1):
                for z in range(low[2],high[2]+1):
                    rows.append({'pos':[x,63,z],'state':'Block{minecraft:grass_block}[snowy=false]',
                                 'solid':True,'fluid':False,'passable':False,'block_entity':False})
        return {'id':self.c.last,'phase':'done','world_session':'world','control_revision':self.c.rev,
                'scan_start_revision':self.c.rev,'scan_end_revision':self.c.rev,
                'scan_cells_read':total,'scan_total_cells':total,'blocks':rows,
                'scan_entities':[],'scan_entity_scope':ENTITY_SCOPE,
                'server':'simpcraft.com:25565','dimension':'minecraft:overworld'}

    def install_requests(self,change=None):
        self.current=copy.deepcopy(self.stable)
        def raw(**kwargs):return copy.deepcopy(self.current)
        def request(op,**params):
            self.actions.append((op,params));self.c.last='request-'+str(len(self.actions));self.current['last_request']=self.c.last
            if op=='material_job_park':
                self.assertIs(self.current['flight'],True,'Native setter requires actual Flight')
                self.assertGreaterEqual(self.current['pos'][1],84)
            if op=='navigate':
                self.c.rev+=1;self.current['control_revision']=self.c.rev;self.current['supervision_lease']['revision']=self.c.rev
                self.current.update(pos=params['target'],flight=True,on_ground=False)
            self.c.last_terminal_evidence={'request_id':self.c.last,'op':op,'phase':'done','task_session':'task','world_session':'world','revision_after':self.c.rev}
            if op=='scan':
                reply=self.scan_reply(params['min'],params['max'])
                if change:change(op,params,reply)
                return reply
            reply={'id':self.c.last,'phase':'done','world_session':'world','control_revision':self.c.rev}
            if change:change(op,params,reply)
            return reply
        self.c.request=request;self.c.raw=raw;self.c.status=lambda **kwargs:raw()

    def test_actual_rebased_multicolumn_and_body_are_scanned_before_one_bounded_ascent(self):
        state=self.settle();self.install_requests()
        result=module.ascend(self.c,state)
        self.assertEqual(['scan','scan','navigate','material_job_park'],[op for op,_ in self.actions])
        low,high=self.actions[0][1]['min'],self.actions[0][1]['max']
        self.assertEqual([761019,-64,797850],low)
        self.assertEqual([761020,319,797851],high)
        self.assertTrue(self.actions[2][1]['air_only']);self.assertLessEqual(math.dist(self.LANDED,result['pos']),31)
        self.assertEqual(10,result['inventory'][5]['count'])

    def test_partial_or_obstructed_column_body_cannot_send_navigation(self):
        for kind in ['partial','roof','fluid','foreign']:
            with self.subTest(kind=kind):
                self.setUp();state=self.settle()
                def change(op,params,reply):
                    if kind=='partial':reply['scan_cells_read']-=1
                    elif kind=='foreign':reply['world_session']='other'
                    elif params['min'][1]!=-64:
                        reply['blocks']=[{'pos':params['min'],'state':'Block{minecraft:stone}',
                            'solid':True,'fluid':kind=='fluid','passable':False,'block_entity':False}]
                self.install_requests(change)
                with self.assertRaises(module.GroundFinishStop):module.ascend(self.c,state)
                self.assertNotIn('navigate',[op for op,_ in self.actions])

    def test_ground_defer_is_recorded_without_falling_into_logout(self):
        c=self.c;c.remote_finish='guard';c.status=lambda **kwargs:self.after
        c._observe_owned_health=lambda s:s;c.park_near=lambda s:False
        c._finish_vertical=lambda *args,**kwargs:(_ for _ in ()).throw(module.GroundFinishStop('unknown retained'))
        c.request=lambda *args,**kwargs:self.fail('Unknown ground finish must not send logout or park')
        self.assertFalse(c._prepare_guarded_finish())
        self.assertTrue((c.out/'park-ground-deferred.json').exists())


    def test_read_failure_and_malformed_original_proof_are_typed_stops(self):
        self.c.raw=lambda **kwargs:(_ for _ in ()).throw(RuntimeError('stale'))
        with self.clock(),patch('material_ground_finish.time.sleep'):
            with self.assertRaises(module.GroundFinishStop):module.settle(self.c,self.after)
        self.c.last_owned_ground_walk['terminal'].pop('time')
        with self.assertRaises(module.GroundFinishStop):module.context(self.c)

    def test_initial_finish_read_failure_never_calls_logout(self):
        c=self.c;c.remote_finish='guard'
        c.status=lambda **kwargs:(_ for _ in ()).throw(RuntimeError('stale'))
        c.request=lambda *args,**kwargs:self.fail('Missing status must not call logout')
        self.assertFalse(c._prepare_guarded_finish())
        self.assertFalse(c.guarded_ground_stop['native_parking_confirmed'])

    def test_wrong_flight_or_original_scan_identity_sends_no_ascent(self):
        self.after['flight']=True
        with self.assertRaises(module.GroundFinishStop):module.settle(self.c,self.after)
        self.after['flight']=False;state=self.settle()
        self.install_requests(lambda op,params,r:r.update(id='foreign') if op=='scan' else None)
        with self.assertRaises(module.GroundFinishStop):module.ascend(self.c,state)
        self.assertNotIn('navigate',[op for op,_ in self.actions])

    def test_unknown_navigation_or_changed_high_owner_never_publishes_park(self):
        for change in ['unknown','uuid','damage','selection','lease','busy','inventory']:
            with self.subTest(change=change):
                self.setUp();state=self.settle()
                def mutate(op,params,reply):
                    if op!='navigate':return
                    if change=='unknown':reply['phase']='waiting'
                    elif change=='uuid':self.current['player_uuid']='other'
                    elif change=='damage':self.current['recent_hurt_at']+=1
                    elif change=='selection':self.current['projection_selection']={'key':'other'}
                    elif change=='lease':self.current['supervision_lease']['id']='other'
                    elif change=='busy':self.current['native_material_busy']=True
                    elif change=='inventory':self.current['inventory'][5]['count']-=1
                self.install_requests(mutate)
                with self.assertRaises(module.GroundFinishStop):module.ascend(self.c,state)
                self.assertNotIn('material_job_park',[op for op,_ in self.actions])

    def test_entity_is_refiltered_after_small_actual_origin_drift(self):
        state=self.settle()
        def mutate(op,params,reply):
            if op!='scan' or params['min'][1]==-64:return
            reply['scan_entities']=[{'type':'minecraft:cow','alive':True,'hostile':False,
                'bounds':{'min':[761020.26,64,797851.1],'max':[761020.6,66,797851.4]}}]
            self.current['pos'][0]+=.04
        self.install_requests(mutate)
        with self.assertRaisesRegex(module.GroundFinishStop,'latest actual'):module.ascend(self.c,state)
        self.assertNotIn('navigate',[op for op,_ in self.actions])


if __name__=='__main__':unittest.main()
