"""End-to-end simulated Kit admission, fishing stop, formal work and idle recovery."""
from copy import deepcopy
import contextlib
import fcntl
import io
import json
import math
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

from farm_caretaker import Caretaker
from idle_priority import ForegroundDemand,demands,foreground,request_foreground
from idle_service import FLAGS,IdleService,IdleYield,busy_reason,default_profile,validate_profile
from idle_service_cli import main
from idle_service_native import IdleJobClient,NativeRunner,free_slots,verify_shore
from test_farm_caretaker import profile as farm_profile
from test_potato_farm import row


class Clock:
    def __init__(self):self.now=time.time()
    def __call__(self):return self.now
    def step(self,seconds):self.now+=seconds


class FakeKit:
    def __init__(self,root,clock,shore):
        self.root,self.clock,self.shore=root,clock,shore;self.calls=[];self.unknown_start=False;self.move_fault=None;self.inject_move=None
        self.state={'connected':True,'server':'example.test','dimension':'minecraft:overworld','world_session':'w',
            'control_revision':1,'phase':'done','screen':'','manual_movement':False,'window_active':False,
            'health':20,'food':20,'under_water':False,'safety_hold':{'active':False},'pos':shore['stand'][:],
            'on_ground':True,'guard_armed':True,'guard_pve_only':True,'flight':True,'guard_busy':False,
            'air_only_navigation_protocol':2,
            'idle_fishing_protocol':1,'fisher_chest_range':8,'fisher_deposit_allowed':False,
            'kill_aura':True,'auto_log':True,'recent_hurt_at':0,'recent_attacker':'','velocity':[0,0,0],
            'idle_activity_protocol':1,'idle_activity':{'busy':False,'conflicts':[],'idle_task_session':''},
            'supervision_lease':{},'material_task':{'occupied':False,'process_alive':False,'cancelling':False},
            'menu':{'type':'InventoryMenu','cursor':{'item':'minecraft:air','count':0}},
            'movement_keys':{'forward':False,'back':False,'jump':False,'sneak':False},
            **{key:False for key in FLAGS}}
        self.state['inventory']=[{'slot':i,'item':'minecraft:air','count':0} for i in range(43)]
        self.state['inventory'][0].update(item='minecraft:fishing_rod',count=1,durability=100)
        self.state['hand']={'item':'minecraft:fishing_rod','count':1,'durability':100}
        foot=[math.floor(v) for v in shore['stand']]
        self.blocks=[row([foot[0],foot[1]-1,foot[2]],'Block{minecraft:stone}'),
                     row(shore['water'],'Block{minecraft:water}[level=0]',False,True)]
    def observe(self):
        self.state['time']=int(self.clock()*1000)
        (self.root/'status.json').write_text(json.dumps(self.state))
        return deepcopy(self.state)
    def host_manual_takeover(self):
        # Required native capability: stop this exact idle owner before publishing manual takeover.
        self.calls.append(('host_idle_stop',{}))
        self.state.update(manual_movement=True,fisher_active=False,supervision_lease={},
                          control_revision=self.state['control_revision']+1)
    def client(self,runner):
        native=self
        class Client:
            world='w';task='idle-materials';server='example.test';native_inflight=None
            def __init__(self):
                self.rev=native.state['control_revision'];self.last=None;self.heartbeat=Mock();self.heartbeat.id='idle-lease';self.job_progress=None
                self.out=runner.out/'fake-control';self.out.mkdir(exist_ok=True);self.root=native.root
                native.state['supervision_lease']={'kind':'materials','id':'idle-lease','job_session':self.task,'world_session':'w','revision':self.rev,'remote_finish':'guard'}
                native.state['idle_activity']['idle_task_session']=self.task
            def status(self,*args,**kwargs):
                if kwargs.get('wait_seconds')==0:native.clock.step(.25)
                state=native.observe()
                if not runner.cleaning:runner.service.checkpoint(state)
                return state
            def _settle_owned_ground_walk(self,state):
                from material_client import MaterialClient
                return MaterialClient._settle_owned_ground_walk(self,state)
            def request(self,op,**params):
                before=native.observe();native.clock.step(.25 if op=='scan' else .03)
                native.calls.append((op,deepcopy(params)));self.last='fake-'+str(len(native.calls));native.state['last_request']=self.last
                native.state['id']=self.last;native.state['phase']='done'
                if op in ('navigate','walk'):
                    self.rev+=1;native.state['control_revision']=self.rev;native.state['supervision_lease']['revision']=self.rev
                    if native.move_fault!=op:native.state['pos']=params['target'][:]
                    native.state.update(navigating=False,on_ground=op=='walk',flight=op=='navigate',velocity=[0,-.0784 if op=='walk' or params.get('target')==native.shore['stand'] else 0,0])
                    if op=='walk' and native.move_fault!='walk':
                        terminal=native.observe()
                        self.last_owned_ground_walk={'request_id':self.last,'world_session':self.world,'task_session':self.task,'revision':self.rev,
                            'op':'walk','phase':'done','params':deepcopy(params),'before_damage':{k:before[k] for k in ('recent_hurt_at','recent_attacker')},
                            'before_safety_hold':deepcopy(before['safety_hold']),'terminal':terminal}
                    if native.inject_move is not None:
                        callback=native.inject_move;native.inject_move=None;callback(self,op)
                if op=='scan':
                    bounded=[r for r in native.blocks if all(low<=value<=high for low,value,high in zip(params['min'],r['pos'],params['max']))]
                    result=native.observe();result.update(blocks=deepcopy(bounded),scan_entities=[],unloaded_chunks=0,
                        scan_entity_scope='current_client_loaded_entities_intersecting_scan_AABB_sampled_at_scan_end_not_whole_herd')
                else:
                    if op=='look':native.state.update(yaw=params['yaw'],pitch=params['pitch'])
                    if op=='fisher_start':native.state['fisher_active']=True
                    if op=='fisher_stop':native.state['fisher_active']=False
                    if op=='material_job_pause':
                        self.rev+=1;native.state.update(control_revision=self.rev,supervision_lease={},fisher_active=False,navigating=False)
                    result=native.observe()
                phase='waiting' if op=='fisher_start' and native.unknown_start or op in ('navigate','walk') and native.move_fault==op else 'done'
                result.update(id=self.last,phase=phase)
                if op=='navigate':
                    result['material_air_navigation']={'phase':'confirmed','outcome':'done','world_session':'w','stable_ticks':8,
                        'restored_ticks':0 if native.move_fault=='restore' and params['target']==native.shore['stand'] else 8,'injury_interrupted':False}
                if phase=='waiting' and op in ('navigate','walk'):result.pop('world_session',None)
                return result
            def finish(self):
                assert not native.state['fisher_active']
                native.calls.append(('finish',{}));native.state['supervision_lease']['kind']='parking'
                native.state.update(pos=runner.farm['park_target'][:],on_ground=False,flight=True,phase='parking',velocity=[0,0,0])
        return Client()


class SimulatedRunner(NativeRunner):
    def _open(self,state,profile):
        self.client=self.service.fake.client(self);self.backend=None


class IdleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)/'automation';self.root.mkdir()
        self.clock=Clock();self.farm=Caretaker(self.root,farm_profile());self.farm.lock_path.touch()
        self.farm_path=self.root.parent/'farm-profile.json';self.farm_path.write_text(json.dumps(self.farm.profile))
        shore={'authorized':True,'stand':[8.5,64,.5],'water':[8,63,3],'yaw':0,'pitch':math.degrees(math.atan2(1.82,3))}
        self.config=default_profile(str(self.farm_path));self.config.update(authorized=True,server='example.test',jobs=['fish'],quiet_seconds=5)
        self.config['cooldowns']['fish']=10;self.config['fishing'].update(enabled=True,shore=shore,duration_seconds=90)
        self.fake=FakeKit(self.root,self.clock,shore)
        self.service=IdleService(self.root,self.config,observer=self.fake.observe,runner_factory=SimulatedRunner,clock=self.clock)
        self.service.fake=self.fake
        self.addCleanup(lambda:self.service._finish('TEST_FINISH'))
    def activate(self):
        self.service.start();self.service.tick();self.clock.step(5.1);self.service.tick()
        self.assertTrue(self.fake.state['fisher_active']);self.assertEqual('fish',self.service.book['active_job'])
    def op_count(self,op):return sum(name==op for name,_ in self.fake.calls)

    def test_busy_stops_idle_input_before_formal_admission_then_waits_and_resumes_after_idle(self):
        with self.service.worker_lock():
            self.activate();self.assertEqual(1,self.op_count('fisher_start'))
            priority=ForegroundDemand(self.root,'formal-construction','w')
            try:
                self.service.tick()
                self.assertFalse(self.fake.state['fisher_active']);self.assertEqual({},self.fake.state['supervision_lease'])
                ops=[op for op,_ in self.fake.calls]
                self.assertLess(ops.index('fisher_stop'),ops.index('material_job_pause'))
                self.fake.observe();priority.wait(.1,now_ms=lambda:int(self.clock()*1000))
                self.fake.state['borer_active']=True;self.fake.state['idle_activity'].update(busy=True,conflicts=['formal-borer'])
                self.clock.step(4);self.service.tick();self.assertEqual(1,self.op_count('fisher_start'))
                self.assertTrue(self.service.book['reason'].startswith('OTHER_INPUT_OWNER'))
            finally:priority.close()
            self.fake.state['borer_active']=False;self.fake.state['idle_activity'].update(busy=False,conflicts=[])
            self.clock.step(10);self.service.tick();self.clock.step(5.1);self.service.tick()
            self.assertEqual(2,self.op_count('fisher_start'));self.assertTrue(self.fake.state['fisher_active'])
            self.assertEqual(0,self.service.book['ai_calls'])
    def test_unknown_native_start_is_stopped_and_original_intent_never_replayed(self):
        self.fake.unknown_start=True;self.service.start();self.service.tick();self.clock.step(5.1);self.service.tick()
        self.assertFalse(self.fake.state['fisher_active']);self.assertTrue(self.service.book['pending'])
        self.assertEqual(1,self.op_count('fisher_start'))
        directory=Path(self.service.book['pending']['directory']);ledger=json.loads((directory/'runner.json').read_text())
        self.assertEqual('fisher_start',ledger['pending']['op']);before=(directory/'runner.json').read_bytes()
        for _ in range(4):self.clock.step(30);self.service.tick()
        self.assertEqual(1,self.op_count('fisher_start'));self.assertEqual(before,(directory/'runner.json').read_bytes())
        with self.assertRaisesRegex(RuntimeError,'Unknown original'):self.service.start()
    def test_busy_and_missing_native_activity_metadata_never_acquire_control(self):
        self.fake.state.pop('idle_activity_protocol');self.service.start()
        for _ in range(4):self.service.tick();self.clock.step(10)
        self.assertEqual([],self.fake.calls);self.assertEqual('WAIT_ACTIVITY_CAPABILITY',self.service.book['reason'])
        self.fake.state['idle_activity_protocol']=1;self.fake.state['material_task']['occupied']=True
        self.service.tick();self.assertEqual('FORMAL_MATERIAL_TASK',self.service.book['reason']);self.assertEqual([],self.fake.calls)
    def test_all_reported_busy_flags_and_foreign_lease_block_idle(self):
        state=self.fake.observe()
        for flag in FLAGS:
            with self.subTest(flag=flag):
                changed={**state,flag:True}
                self.assertTrue(busy_reason(self.root,self.service.profile,changed,now_ms=state['time']).startswith('BUSY:'))
        for field in ('build_job','concrete','professional_printer','gravel','projection_batch'):
            self.assertTrue(busy_reason(self.root,self.service.profile,{**state,field:{'active':True}},now_ms=state['time']).startswith('BUSY:'))
        self.assertEqual('FOREIGN_LEASE',busy_reason(self.root,self.service.profile,{**state,'supervision_lease':{'kind':'materials','job_session':'foreign'}},now_ms=state['time']))
    def test_actual_game_movement_and_safety_holds_have_priority_without_unlocking(self):
        self.fake.state.update(window_active=True,manual_movement=True);self.service.start();self.service.tick();self.clock.step(5);self.service.tick()
        self.assertEqual([],self.fake.calls);self.assertEqual('PLAYER_INPUT',self.service.book['reason'])
        hold=self.root/'material-health-hold.json';hold.write_text('{"active":true,"time":1}')
        before=hold.read_bytes();self.service.tick();self.assertEqual('SAFETY_HOLD',self.service.book['reason']);self.assertEqual(before,hold.read_bytes())
    def test_foreground_without_wasd_starts_after_five_seconds_without_hid_provider(self):
        self.fake.state['window_active']=True
        with patch('physical_idle.mac_hid_idle_seconds',side_effect=AssertionError('Global OS input must not be queried')):
            self.service.start();self.service.tick();self.clock.step(4.9);self.service.tick()
            self.assertEqual(0,self.op_count('fisher_start'))
            self.clock.step(.2);self.service.tick()
        self.assertEqual(1,self.op_count('fisher_start'));self.assertTrue(self.fake.state['fisher_active'])
    def test_cmdtab_does_not_reset_game_quiet_timer(self):
        self.fake.state['window_active']=True;self.service.start();self.service.tick()
        self.clock.step(3);self.fake.state['window_active']=False;self.service.tick()
        self.clock.step(1.8);self.fake.state['window_active']=True;self.service.tick()
        self.assertEqual(0,self.op_count('fisher_start'))
        self.clock.step(.3);self.service.tick();self.assertEqual(1,self.op_count('fisher_start'))
    def test_foreground_real_wasd_immediately_yields_and_restarts_quiet_timer(self):
        self.fake.state['window_active']=True;self.activate();self.fake.host_manual_takeover();self.service.tick()
        self.assertFalse(self.fake.state['fisher_active']);self.assertEqual('PLAYER_INPUT',self.service.book['reason'])
        before=self.op_count('fisher_start');self.clock.step(20);self.service.tick();self.assertEqual(before,self.op_count('fisher_start'))
        self.fake.state['manual_movement']=False;self.service.tick();self.clock.step(4.9);self.service.tick()
        self.assertEqual(before,self.op_count('fisher_start'))
        self.clock.step(.2);self.service.tick();self.assertEqual(before+1,self.op_count('fisher_start'))
    def test_manual_input_causes_scoped_stop_and_world_change_never_reconnects(self):
        self.activate();self.fake.host_manual_takeover();self.service.tick()
        self.assertFalse(self.fake.state['fisher_active']);self.assertEqual(0,self.op_count('material_job_pause'))
        self.assertEqual(1,self.op_count('host_idle_stop'))
        self.fake.state.update(manual_movement=False,world_session='new-world');self.service.tick()
        self.assertFalse(self.service.book['enabled']);self.assertEqual('WORLD_SESSION_CHANGED',self.service.book['reason'])
        self.assertFalse(any(op in ('safe_logout','reconnect','unlock') for op,_ in self.fake.calls))
    def test_no_rod_or_unregistered_shore_does_not_start_fishing(self):
        for missing in ('rod','location'):
            with self.subTest(missing=missing):
                self.service.book.update(enabled=False,paused=False,pending=None,active_job=None,due={});self.service.quiet_since=None
                self.fake.state['inventory'][0].update(item='minecraft:air',count=0)
                if missing=='location':self.fake.state['pos']=[20,64,0]
                self.service.start();self.service.tick();self.clock.step(5.1);self.service.tick()
                self.assertEqual(0,self.op_count('fisher_start'));self.assertEqual([],self.fake.calls)
    def test_shore_containers_lava_or_wrong_water_are_rejected(self):
        shore=self.config['fishing']['shore'];state=self.fake.observe();scan={'blocks':deepcopy(self.fake.blocks),'scan_entities':[],
            'scan_entity_scope':'current_client_loaded_entities_intersecting_scan_AABB_sampled_at_scan_end_not_whole_herd'}
        verify_shore(state,scan,shore)
        for fault in ('container','lava','water','support','entity'):
            changed=deepcopy(scan)
            if fault=='container':changed['blocks'].append({**row([7,64,0],'Block{minecraft:chest}'),'block_entity':True})
            if fault=='lava':changed['blocks'].append(row([7,63,0],'Block{minecraft:lava}[level=0]',False,True))
            if fault=='water':changed['blocks'][1]['state']='Block{minecraft:water}[level=1]'
            if fault=='support':changed['blocks'][0]['solid']=False
            if fault=='entity':changed['scan_entities']=[{'type':'minecraft:cow'}]
            with self.subTest(fault=fault),self.assertRaises(RuntimeError):verify_shore(state,changed,shore)
    def test_actual_fisher_range_and_no_deposit_capability_are_required(self):
        self.fake.state.pop('idle_fishing_protocol');self.service.start();self.service.tick();self.clock.step(5.1);self.service.tick()
        self.assertEqual('WAIT_NO_DEPOSIT_FISHING_CAPABILITY',self.service.book['reason']);self.assertFalse(self.fake.calls)
        self.fake.state['idle_fishing_protocol']=1;self.service.book['due']={};self.service.quiet_since=None
        self.fake.state['fisher_chest_range']=12
        self.service.tick();self.clock.step(5.1);self.service.tick();self.assertTrue(self.fake.state['fisher_active'])
        scans=[p for op,p in self.fake.calls if op=='scan'];self.assertTrue(any(p['min'][0]==-4 and p['max'][0]==20 for p in scans))
        self.assertFalse(self.fake.state['fisher_deposit_allowed'])
    def test_far_harmless_animal_is_allowed_but_body_cast_entity_and_near_hostile_block(self):
        shore=self.config['fishing']['shore'];state=self.fake.observe()
        entity={'type':'minecraft:cow','alive':True,'hostile':False,'bounds':{'min':[15,64,6],'max':[16,66,7]}}
        scan={'blocks':deepcopy(self.fake.blocks),'scan_entities':[entity],
            'scan_entity_scope':'current_client_loaded_entities_intersecting_scan_AABB_sampled_at_scan_end_not_whole_herd'}
        verify_shore(state,scan,shore)
        for low,high,hostile in (([8.3,64,.3],[8.8,65,.8],False),([8.3,64,1.5],[8.8,66,2],False),([13,64,2],[14,66,3],True)):
            changed=deepcopy(scan);changed['scan_entities'][0].update(hostile=hostile,bounds={'min':low,'max':high})
            with self.assertRaises(RuntimeError):verify_shore(state,changed,shore)
    def test_fishing_stops_before_inventory_full_and_returns_to_guarded_park(self):
        self.activate()
        for slot in range(1,34):self.fake.state['inventory'][slot].update(item='minecraft:cod',count=1)
        self.service.tick();self.assertFalse(self.fake.state['fisher_active']);self.assertEqual(1,self.op_count('fisher_stop'))
        self.assertEqual(1,self.op_count('finish'));self.assertEqual('parking',self.fake.state['supervision_lease']['kind'])
        self.assertEqual(self.farm.profile['park_target'],self.fake.state['pos'])
    def test_high_farm_park_autonomously_reaches_registered_shore_lands_restores_flight_and_fishes(self):
        self.fake.state.update(pos=self.farm.profile['park_target'][:],on_ground=False,velocity=[0,0,0])
        self.activate()
        ops=[op for op,_ in self.fake.calls];self.assertIn('navigate',ops);self.assertIn('walk',ops)
        self.assertLess(ops.index('navigate'),ops.index('walk'));self.assertLess(ops.index('walk'),ops.index('fisher_start'))
        self.assertEqual(self.config['fishing']['shore']['stand'],self.fake.state['pos'])
        self.assertTrue(self.fake.state['flight']);self.assertFalse(self.fake.state['on_ground'])
        directory=Path(self.service.book['pending']['directory']);ledger=json.loads((directory/'runner.json').read_text())
        moves=[r for r in ledger['receipts'] if r['op'] in ('navigate','walk')]
        self.assertEqual(self.op_count('navigate')+self.op_count('walk'),len(moves))
        self.assertTrue(all(r['outcome']=='observed_arrival' for r in moves))
        arrival=json.loads((directory/'shore-arrival.json').read_text())
        self.assertGreaterEqual(arrival['ground_proof']['observed_span_ms'],400);self.assertFalse(arrival['on_ground_observed'])
        self.clock.step(91);self.service.tick();self.assertFalse(self.fake.state['fisher_active'])
        self.assertEqual(self.farm.profile['park_target'],self.fake.state['pos'])
        self.clock.step(11);self.service.tick();self.clock.step(5.1);self.service.tick()
        self.assertEqual(2,self.op_count('fisher_start'))
    def test_unknown_navigation_walk_or_flight_restore_keeps_original_move_and_never_replays(self):
        for fault in ('navigate','walk','restore'):
            with self.subTest(fault=fault):
                self.service.book.update(enabled=False,paused=False,pending=None,active_job=None,due={});self.service.runner=None;self.service.quiet_since=None
                self.fake.state.update(pos=self.farm.profile['park_target'][:],on_ground=False,flight=True,velocity=[0,0,0],supervision_lease={})
                self.fake.move_fault=fault;before=len(self.fake.calls)
                self.service.start();self.service.tick();self.clock.step(5.1);self.service.tick()
                self.assertFalse(self.fake.state['fisher_active']);self.assertTrue(self.service.book['pending'])
                path=Path(self.service.book['pending']['directory'])/'runner.json';ledger=json.loads(path.read_text())
                self.assertEqual('walk' if fault=='walk' else 'navigate',ledger['pending']['op']);raw=path.read_bytes()
                sent=len(self.fake.calls)
                for _ in range(3):self.clock.step(30);self.service.tick()
                self.assertEqual(sent,len(self.fake.calls));self.assertEqual(raw,path.read_bytes())
                self.assertFalse(any(op=='fisher_start' for op,_ in self.fake.calls[before:]))
    def test_foreground_demand_during_shore_navigation_stops_scope_without_opening_fisher(self):
        self.fake.state.update(pos=self.farm.profile['park_target'][:],on_ground=False);token=[]
        def demand(client,op):
            token.append(ForegroundDemand(self.root,'formal-construction','w'));self.service.checkpoint(self.fake.observe())
        self.fake.inject_move=demand
        try:
            self.service.start();self.service.tick();self.clock.step(5.1);self.service.tick()
            self.assertEqual(1,self.op_count('navigate'));self.assertEqual(1,self.op_count('material_job_pause'))
            self.assertEqual(0,self.op_count('fisher_start'));self.assertEqual({},self.fake.state['supervision_lease'])
            self.assertTrue(self.service.book['pending'])
            raw=(Path(self.service.book['pending']['directory'])/'runner.json').read_bytes()
            self.clock.step(10);self.service.tick();self.assertEqual(1,self.op_count('navigate'))
            self.assertEqual(raw,(Path(self.service.book['pending']['directory'])/'runner.json').read_bytes())
        finally:
            for item in token:item.close()
    def test_single_worker_and_original_caretaker_flock_are_enforced(self):
        with self.service.worker_lock():
            with self.assertRaisesRegex(RuntimeError,'Another idle worker'):
                with self.service.worker_lock():pass
        with self.farm.lock_path.open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);self.service.start();self.service.tick();self.clock.step(5.1);self.service.tick()
        self.assertFalse(self.fake.calls);self.assertEqual('CARETAKER_BUSY',self.service.book['reason'])
        self.assertFalse(self.service.book['paused'])
    def test_unchanged_waiting_state_does_not_spam_events(self):
        self.fake.state['borer_active']=True;self.service.start();self.service.tick()
        path=self.service.home/'events.jsonl';before=path.read_bytes()
        for _ in range(10):self.clock.step(.3);self.service.tick()
        self.assertEqual(before,path.read_bytes())
    def test_unconfigured_template_has_no_implicit_region_fishing_or_new_livestock_policy(self):
        value=default_profile();self.assertFalse(value['authorized']);self.assertIsNone(value['caretaker_profile']);self.assertEqual([],value['plant_registries'])
        self.assertFalse(value['fishing']['enabled']);self.assertEqual(20,self.farm.profile['adult_keep'])
        with self.assertRaises(ValueError):validate_profile(value)
    def test_registered_idle_plant_call_uses_existing_farmland_policy_and_missing_feed_food_waits(self):
        from potato_farm import plan
        layout=plan({'authorized':True,'center':[1,63,1]})
        directory=self.root/'farms'/'registered';directory.mkdir(parents=True);journal=directory/'journal';journal.mkdir()
        registry=directory/'registry.json';registry.write_text(json.dumps({'scope':{'server':'example.test','dimension':'minecraft:overworld','layout':layout},'world_session':'w','directory':str(journal)}))
        self.service.profile['plant_registries']=[str(registry)]
        out=self.service.home/'plant-test';out.mkdir();runner=SimulatedRunner(self.service,'plant',out)
        try:
            with patch('idle_service_native.plant',return_value={'phase':'idle'}) as plant:
                runner.run(self.fake.observe());self.assertTrue(plant.call_args.kwargs['existing_farmland_only'])
        finally:runner.stop('TEST_FINISH')
        self.fake.calls.clear();out=self.service.home/'feed-test';out.mkdir();runner=SimulatedRunner(self.service,'breed',out)
        try:
            result=runner.run(self.fake.observe());self.assertEqual('WAIT_ACTUAL_FEED_FOOD',result['code'])
            self.assertFalse(self.fake.calls);self.assertEqual(20,runner.farm['adult_keep'])
        finally:runner.stop('TEST_FINISH')
    def flight_client(self):
        self.service.start();directory=self.service.home/'flight-test';directory.mkdir()
        runner=NativeRunner(self.service,'harvest_store',directory);self.service.runner=runner
        self.service.book.update(active_job='harvest_store',pending={'job':'harvest_store','directory':str(directory),'world_session':'w'})
        client=IdleJobClient.__new__(IdleJobClient);client.idle_runner=runner;client.idle_service_id=self.service.key
        client.owner=Mock();client.owner.checking=False;client.owner.cleaning=False
        client.world='w';client.task='idle-materials';client.rev=1;client.last='materials-nav';client.heartbeat=Mock();client.heartbeat.id='idle-lease';client.job_progress=None
        client.native_inflight={'request_id':'materials-nav','op':'navigate','world_session':'w','task_session':client.task,
            'lease_id':'idle-lease','base_revision':1,'request_revision':1,'expected_revision':2,'server':'example.test','dimension':'minecraft:overworld'}
        runner.client=client
        self.fake.state.update(control_revision=2,phase='running',op='navigate',id=client.last,last_request=client.last,navigating=True,
            supervision_lease={'kind':'materials','id':'idle-lease','job_session':client.task,'world_session':'w','revision':2},
            idle_activity={'busy':True,'conflicts':['navigate'],'idle_task_session':''})
        return runner,client
    def test_inflight_foreground_stop_uses_exact_envelope_before_parent_finally_can_clear_it(self):
        runner,client=self.flight_client();envelope=client.native_inflight;priority=ForegroundDemand(self.root,'formal-mining','w')
        def cancelled(c,op,**params):
            self.assertIs(envelope,c.native_inflight);self.assertEqual(2,c.rev);self.assertEqual('material_job_pause',op)
            self.assertTrue(params['release']);self.fake.calls.append((op,params))
            c.rev=3;self.fake.state.update(control_revision=3,phase='done',navigating=False,supervision_lease={})
            return {'id':'pause-receipt','phase':'done','time':int(self.clock()*1000)}
        try:
            with patch('material_jobs_backend.JobClient.raw',side_effect=self.fake.observe),patch('material_client.MaterialClient.request',new=cancelled):
                with self.assertRaises(IdleYield):client.raw()
            self.assertTrue(runner.stop_result['released']);self.assertEqual(1,self.op_count('material_job_pause'))
            self.service._finish('FOREGROUND_DEMAND');self.assertEqual(1,self.op_count('material_job_pause'))
        finally:priority.close()
    def test_owned_revision_advance_publishes_marker_and_reads_next_frame_without_self_stopping(self):
        runner,client=self.flight_client();initial=self.fake.observe();frames=[]
        def host_frame():
            marker=json.loads((self.root/'idle-service-owner.json').read_text())
            self.assertEqual(2,marker['revision']);self.assertEqual(client.task,marker['task_session'])
            self.clock.step(.01);frames.append(True)
            if len(frames)>=2:self.fake.state['idle_activity']={'busy':False,'conflicts':[],'idle_task_session':client.task}
            return self.fake.observe()
        self.service.observer=host_frame
        with patch('material_jobs_backend.JobClient.raw',return_value=initial),patch.object(runner,'stop') as stop:
            self.assertEqual(2,client.raw()['control_revision']);stop.assert_not_called()
        self.assertEqual([],self.fake.calls)
        self.assertGreaterEqual(len(frames),2)
        self.service.runner=None  # This test owns no native input or OS worker lock.


class PriorityCliTests(unittest.TestCase):
    def test_all_idle_jobs_use_durable_movement_wrapper(self):
        from types import SimpleNamespace
        c=IdleJobClient.__new__(IdleJobClient);runner=SimpleNamespace(job='cook_store',dispatching_movement=False,_send_movement=Mock(return_value={'phase':'done'}))
        c.idle_runner=runner
        self.assertEqual({'phase':'done'},c.request('navigate',target=[0,140,0],air_only=True))
        runner._send_movement.assert_called_once_with('navigate',target=[0,140,0],air_only=True)
    def test_session_intent_precedes_dispatch_and_unconfirmed_admission_is_never_replayed(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'job';out.mkdir()
            service=SimpleNamespace(root=root,key='idle',clock=time.time,profile={'plant_registries':[]})
            runner=NativeRunner(service,'breed',out);c=IdleJobClient.__new__(IdleJobClient);runner.client=c
            c.idle_runner=runner;c.idle_service_id='idle';c.world='w';c.rev=1;c.task='new-task';c.last=None;c.heartbeat=Mock();c.heartbeat.id='new-lease'
            calls=[]
            def dispatch(client,op,**params):
                calls.append(op);saved=json.loads(runner.ledger_path.read_text())
                self.assertEqual('intent_before_dispatch',saved['opening_pending']['stage']);self.assertEqual('new-task',saved['opening_pending']['task_session'])
                client.last='session-request';return {'id':client.last,'phase':'waiting','world_session':'w','time':1}
            with patch('material_jobs_backend.JobClient.request',new=dispatch),patch.object(runner,'wait_opening_release')as retained:
                with self.assertRaisesRegex(RuntimeError,'unconfirmed'):c.request('material_session',supervision_lease='new-lease')
                with self.assertRaisesRegex(RuntimeError,'cannot be replayed'):c.request('material_session',supervision_lease='new-lease')
            self.assertEqual(['material_session'],calls);self.assertTrue(runner.has_unknown())
            retained.assert_called_once();c.heartbeat.close.assert_not_called()
    def test_session_cancellation_waits_for_exact_admission_before_releasing_new_lease(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'job';out.mkdir();stage=[]
            old={'connected':True,'world_session':'w','control_revision':1,'manual_movement':False,'fisher_active':False,'navigating':False,
                'menu':{'cursor':{'count':0}},'supervision_lease':{'kind':'parking','id':'old','world_session':'w','revision':1}}
            admitted=deepcopy(old);admitted['supervision_lease']={'kind':'materials','id':'new','job_session':'task','world_session':'w','revision':1}
            states=[old,admitted];latest=deepcopy(admitted);polls=[]
            def observe():
                polls.append(True);return deepcopy(states.pop(0) if states else latest)
            service=SimpleNamespace(root=root,clock=time.time,observer=observe,profile={'plant_registries':[]},publish_owner=lambda state,**kw:stage.append('owner'))
            runner=NativeRunner(service,'breed',out);c=SimpleNamespace(root=root,world='w',rev=1,task='task',heartbeat=Mock(),job_progress=None,last='session',native_inflight=None)
            c.heartbeat.id='new';runner.client=c;runner.opening_state=deepcopy(old)
            runner.ledger['opening_pending']={'op':'material_session','request_envelope':{'request_id':'session'},'world_session':'w','task_session':'task','lease_id':'new'}
            def pause(op,**params):
                self.assertEqual('material_job_pause',op);self.assertTrue(params['release']);stage.append('pause')
                latest.update(supervision_lease={},control_revision=2);return {'id':'pause','phase':'done','world_session':'w','time':2}
            c.request=pause;result=runner.stop('TEST_CONSTRUCTOR_CANCEL')
            self.assertTrue(result['released']);self.assertFalse(result['unknown']);self.assertGreaterEqual(len(polls),3)
            self.assertEqual(['owner','pause'],stage);self.assertIsNone(runner.ledger['opening_pending']);c.heartbeat.close.assert_called_once()
    def test_late_session_admission_keeps_heartbeat_until_exact_scoped_release(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'job';out.mkdir();calls=[]
            state={'time':int(time.time()*1000),'connected':True,'world_session':'w','control_revision':1,'manual_movement':False,
                'fisher_active':False,'navigating':False,'menu':{'cursor':{'count':0}},'supervision_lease':{'kind':'parking','id':'old'}}
            service=SimpleNamespace(root=root,clock=time.time,observer=lambda:deepcopy(state),profile={'plant_registries':[]},publish_owner=lambda *args,**kwargs:None)
            runner=NativeRunner(service,'breed',out);runner.opening_state=deepcopy(state)
            c=SimpleNamespace(root=root,world='w',rev=1,task='task',heartbeat=Mock(),job_progress=None,last='session',native_inflight=None)
            c.heartbeat.id='new';runner.client=c;runner.ledger['opening_pending']={'op':'material_session','world_session':'w','request_envelope':{'request_id':'session'}}
            with patch('idle_service_native.time.monotonic',side_effect=[0,4]):result=runner.stop('SESSION_NOT_YET_ADMITTED')
            self.assertFalse(result['released']);self.assertTrue(result['unknown']);c.heartbeat.close.assert_not_called()
            state['supervision_lease']={'kind':'materials','id':'new','job_session':'task','world_session':'w','revision':1}
            def released(op,**params):
                calls.append(op);self.assertTrue(params['release']);c.heartbeat.close.assert_not_called()
                state.update(supervision_lease={},control_revision=2,last_request='pause');return {'id':'pause','phase':'done','world_session':'w','time':2}
            c.request=released;runner.wait_opening_release('LATE_ADMISSION')
            self.assertEqual(['material_job_pause'],calls);self.assertTrue(runner.stop_result['released']);self.assertFalse(runner.stop_result['unknown'])
            c.heartbeat.touch.assert_called();c.heartbeat.close.assert_called_once()
    def test_constructor_uses_current_verified_parking_target_until_session_is_admitted(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'job';out.mkdir()
            service=SimpleNamespace(root=root,key='idle',book={'sequence':1},checkpoint=lambda:None,clock=time.time)
            runner=NativeRunner(service,'breed',out)
            state={'time':int(time.time()*1000),'server':'example.test','dimension':'minecraft:overworld','world_session':'w','control_revision':1,
                'pos':[0,140,0],'supervision_lease':{'kind':'parking','world_session':'w','park_target':[0,140,0]}}
            profile={'cooked_food_reserve':8,'depots':[],'park_target':[8,140,8]}
            backend=SimpleNamespace(profile={'depots':[]},sequence=0,out=out/'backend',experience_state=lambda:{})
            client=SimpleNamespace()
            with patch('idle_service_native.create_backend',return_value=backend),patch('idle_service_native.IdleJobClient',return_value=client)as factory:
                runner._open(state,profile)
            self.assertEqual([0,140,0],factory.call_args.kwargs['park_target']);self.assertEqual([8,140,8],client.park_target)
    def test_only_exact_owned_read_only_initialization_scan_may_be_busy(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);clock=Clock();shore={'stand':[0,140,0]};fake=FakeKit(root,clock,shore|{'water':[1,139,1]})
            state=fake.observe();state.update(phase='running',last_request='own-scan')
            state['idle_activity']={'busy':True,'conflicts':['scan']};state['supervision_lease']={'kind':'parking','id':'old', 'world_session':'w','revision':1}
            c=SimpleNamespace(world='w',rev=1,last='own-scan',native_inflight={'op':'scan','request_id':'own-scan','world_session':'w','expected_revision':1})
            runner=SimpleNamespace(client=c,owns=lambda state:False)
            profile=default_profile();profile.update(authorized=True,server='example.test')
            self.assertIsNone(busy_reason(root,profile,state,runner=runner,now_ms=state['time']))
            c.last='new-session';c.last_terminal_evidence={'phase':'done','op':'scan','request_id':'own-scan','world_session':'w','revision_after':1}
            c.native_inflight={'op':'material_session','request_id':'new-session','world_session':'w','base_revision':1}
            runner.opening_state=deepcopy(state)
            self.assertIsNone(busy_reason(root,profile,state,runner=runner,now_ms=state['time']))
            state['last_request']='foreign-scan';self.assertEqual('OTHER_INPUT_OWNER:scan',busy_reason(root,profile,state,runner=runner,now_ms=state['time']))
            state['last_request']='own-scan';state['manual_movement']=True
            self.assertEqual('PLAYER_INPUT',busy_reason(root,profile,state,runner=runner,now_ms=state['time']))
    def test_pre_lease_initialization_stop_releases_no_input_without_touching_prior_park(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'job';out.mkdir()
            state={'world_session':'w','control_revision':1,'navigating':False,'fisher_active':False,
                'menu':{'cursor':{'count':0}},'supervision_lease':{'kind':'parking','id':'old'}}
            service=SimpleNamespace(root=root,clock=time.time,observer=lambda:deepcopy(state),profile={'plant_registries':[]})
            runner=NativeRunner(service,'plant',out);runner.opening_state=deepcopy(state)
            runner.client=SimpleNamespace(heartbeat=None,job_progress=None);result=runner.stop('OWN_READ_STOP')
            self.assertTrue(result['released']);self.assertFalse(result['unknown']);self.assertEqual('old',state['supervision_lease']['id'])
    def test_native_backend_output_exists_before_starting_inventory_factory(self):
        from types import SimpleNamespace
        from idle_service_native import NativeRunner
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'job-000001-plant';out.mkdir()
            service=SimpleNamespace(root=root,key='registered-idle',book={'sequence':1},checkpoint=lambda:None,clock=time.time)
            runner=NativeRunner(service,'plant',out)
            state={'time':int(time.time()*1000),'server':'example.test','dimension':'minecraft:overworld',
                'world_session':'w','control_revision':2,'pos':[0,140,0]}
            profile={'cooked_food_reserve':8,'depots':[],'park_target':[0,140,0]}
            def factory(request,automation,directory,checkpoint):
                self.assertTrue(directory.is_dir());(directory/'starting-inventory.json').write_text('{}')
                raise RuntimeError('factory intercepted before game client')
            with patch('idle_service_native.create_backend',side_effect=factory),patch('idle_service_native.IdleJobClient')as client:
                with self.assertRaisesRegex(RuntimeError,'factory intercepted'):runner._open(state,profile)
            client.assert_not_called();self.assertTrue((out/'backend/starting-inventory.json').exists())
    def test_priority_tokens_hold_until_exit_and_expire_after_dead_controller(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with foreground(root,'formal-task','w') as token:
                self.assertEqual(1,len(demands(root,'w')));self.assertEqual(0,len(demands(root,'other')))
                self.assertEqual([],demands(root,'w',now_ms=int(time.time()*1000)+20000))
            self.assertFalse(token.path.exists())
    def test_template_and_status_do_not_create_worker_or_game_client(self):
        with tempfile.TemporaryDirectory() as folder:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(0,main(['--game-dir',folder,'template']))
            self.assertFalse(json.loads(output.getvalue())['authorized']);self.assertEqual([],list(Path(folder).rglob('*')))
    def test_init_only_uses_existing_registered_farm_and_keeps20_adults(self):
        with tempfile.TemporaryDirectory() as folder:
            game=Path(folder);root=game/'config/twob2tkit/automation';caretaker=Caretaker(root,farm_profile())
            p=root.parent/'farm-caretaker-profile.json';p.write_text(json.dumps(caretaker.profile))
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(0,main(['--game-dir',folder,'init']))
            result=json.loads(output.getvalue());self.assertFalse(result['worker_started']);self.assertEqual(20,result['adult_keep'])
            self.assertFalse(json.loads(Path(result['profile']).read_text())['fishing']['enabled'])


if __name__=='__main__':unittest.main()
