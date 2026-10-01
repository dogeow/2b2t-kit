"""Offline persistent-cycle, takeover and no-replay regressions."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import threading
from unittest.mock import Mock, patch

from farm_caretaker import Caretaker, CaretakerPaused, NativeStages, STAGES, validate_profile
from safety_interlock import record_material_health_exit


def profile():
    return {'schema':1,'authorized':True,'server':'EXAMPLE.test:25565','dimension':'minecraft:overworld',
            'potato_fields':[{'authorized':True,'center':[0,63,0],'radius':2}],
            'livestock_region':{'min':[3,63,0],'max':[7,67,4]},
            'depots':[[10,64,0]],'park_target':[0.5,110,0.5]}


def state():
    return {'time':100,'connected':True,'server':'example.test','dimension':'minecraft:overworld',
            'world_session':'w','control_revision':1,'manual_movement':False,'health':20,'food':20,
            'under_water':False,'screen':'','pos':[.5,110,.5], 'safety_hold':{'active':False},
            'supervision_lease':{},'inventory':[{'slot':0,'item':'minecraft:potato','count':4}]}


class Fixture:
    def __init__(self):
        self.now=10;self.state=state();self.calls=[];self.opens=[];self.closes=[]
        self.reply={'phase':'done','pending':False,'receipts':[{'actual':True}]}
        self.hook=None;self.parked=True
    def factory(self,root,config,cycle,checkpoint,initial):
        self.opens.append(deepcopy(cycle)); fixture=self
        class Adapter:
            client=None
            def run(self,stage,config,cycle,out,checkpoint):
                fixture.calls.append((stage,str(out),cycle['id']))
                if fixture.hook:fixture.hook(stage,checkpoint)
                checkpoint();return deepcopy(fixture.reply)
            def close(self,*,normal):
                fixture.closes.append(normal)
                if normal and fixture.parked:
                    fixture.state.update(control_revision=fixture.state['control_revision']+1,
                                         supervision_lease={'kind':'parking','id':'park'})
                return {'parked':fixture.parked,'parking_lease':'park','revision':fixture.state['control_revision']}
        return Adapter()


class CaretakerTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)/'automation';self.fixture=Fixture()
        self.c=self.make()
    def make(self,out=None,config=None):
        return Caretaker(self.root,config or profile(),out,observer=lambda:deepcopy(self.fixture.state),
                         adapter_factory=self.fixture.factory,clock=lambda:self.fixture.now)
    def start(self):self.c.resume()
    def cycle(self):
        for _ in STAGES:self.c.tick()
    def test_defaults_real_policies_and_bounded_registered_profile(self):
        p=validate_profile(profile());self.assertEqual(300,p['interval_seconds']);self.assertEqual(20,p['adult_keep'])
        self.assertEqual(4,p['potato_reserve']);self.assertEqual(8,p['cooked_food_reserve'])
        self.assertEqual(['minecraft:cow','minecraft:sheep'],p['livestock_types'])
        self.assertEqual('example.test',p['server'])
        for key,value in [('adult_keep',1),('adult_keep',True),('potato_reserve',3),('cooked_food_reserve',7),('interval_seconds',0)]:
            with self.subTest(key=key),self.assertRaises(ValueError):validate_profile({**profile(),key:value})
        for change in ({'authorized':False},{'dimension':'minecraft:the_nether'},{'depots':[[100,64,0]]},
                       {'livestock_region':{'min':[0,0,0],'max':[33,100,33]}}, {'potato_fields':[{}]}):
            with self.assertRaises(ValueError):validate_profile({**profile(),**change})
    def test_same_scope_cannot_change_profile_or_output_to_skip_receipt(self):
        with self.assertRaisesRegex(ValueError,'output'):self.make(self.root/'other')
        with self.assertRaisesRegex(ValueError,'different'):self.make(config={**profile(),'adult_keep':3})
        self.assertEqual(self.c.out,self.make().out)
    def test_simultaneous_first_registration_cannot_overwrite_winner_pending(self):
        root=self.root/'race';entered=threading.Event();release=threading.Event();second_done=threading.Event();created=[];errors=[]
        from kit_runtime.journal import write_json as real_write
        def writer(path,data):
            if Path(path).name=='caretaker.json' and threading.current_thread().name=='first' and not entered.is_set():
                entered.set();release.wait(2)
            real_write(path,data)
        def construct(first):
            try:
                c=Caretaker(root,profile(),observer=lambda:deepcopy(self.fixture.state),adapter_factory=self.fixture.factory,clock=lambda:10)
                created.append(c)
                if not first:second_done.set()
            except BaseException as error:errors.append(error)
        with patch('farm_caretaker.write_json',side_effect=writer):
            first=threading.Thread(target=construct,args=(True,),name='first');first.start();self.assertTrue(entered.wait(2))
            second=threading.Thread(target=construct,args=(False,),name='second');second.start()
            self.assertFalse(second_done.wait(.05));release.set();first.join(2);second.join(2)
        self.assertEqual([],errors);self.assertEqual(2,len(created))
        winner=created[0];self.fixture.reply={'phase':'waiting','pending':True,'receipts':[]};winner.resume();winner.tick()
        saved=winner.path.read_text();Caretaker(root,profile());self.assertEqual(saved,winner.path.read_text())
    def test_status_constructor_never_overwrites_worker_progress(self):
        stale=self.make();self.start();self.c.tick();saved=self.c.path.read_text()
        self.make();self.assertEqual(saved,self.c.path.read_text())
        self.assertNotEqual(stale.book,self.c.book)
    def test_cycle_uses_one_adapter_fixed_dirs_and_next_due_then_new_cycle(self):
        self.start();self.cycle()
        self.assertEqual(list(STAGES),[row[0] for row in self.fixture.calls]);self.assertEqual(1,len(self.fixture.opens))
        self.assertEqual([True],self.fixture.closes);self.assertIsNone(self.c.book['current_cycle'])
        self.assertEqual(310,self.c.book['next_due']);self.assertEqual(0,self.c.book['ai_calls'])
        receipt=self.c.out/'cycle-000001'/'receipt.json';self.assertTrue(receipt.exists())
        self.assertEqual(4,_read(receipt)['baseline']['minecraft:potato'])
        self.fixture.now=309;self.c.tick();self.assertEqual(4,len(self.fixture.calls))
        self.fixture.now=310;self.c.tick();self.assertEqual(2,len(self.fixture.opens));self.assertEqual(2,self.c.book['cycle'])
    def test_interval_can_be_changed_in_initial_profile(self):
        root=Path(self.folder.name)/'other';p={**profile(),'interval_seconds':7}
        c=Caretaker(root,p,observer=lambda:self.fixture.state,adapter_factory=self.fixture.factory,clock=lambda:10)
        c.resume()
        for _ in STAGES:c.tick()
        self.assertEqual(17,c.book['next_due'])
    def test_unknown_reply_persists_and_restart_resume_never_replays(self):
        self.fixture.reply={'phase':'waiting','pending':True,'receipts':[]};self.start();result=self.c.tick()
        pending=deepcopy(result['pending']);self.assertEqual('WAIT_RECONCILE',result['reason'])
        self.assertEqual([False],self.fixture.closes)
        recovered=self.make();recovered.tick();self.assertEqual(1,len(self.fixture.calls))
        with self.assertRaisesRegex(CaretakerPaused,'WAIT_RECONCILE'):recovered.resume()
        self.assertEqual(pending,recovered.book['pending']);self.assertEqual(1,recovered.book['cycle'])
    def test_missing_pending_or_receipts_is_unknown_not_fake_success(self):
        for index,reply in enumerate(({'phase':'done','receipts':[]},{'phase':'done','pending':False})):
            f=Fixture();f.reply=reply
            c=Caretaker(self.root/str(index),profile(),observer=lambda:deepcopy(f.state),adapter_factory=f.factory,clock=lambda:10)
            c.resume();c.tick()
            self.assertIsNotNone(c.book['pending']);self.assertEqual('harvest_store',c.book['stage'])
    def test_known_unavailable_wait_has_no_pending_but_needs_explicit_resume_same_dir(self):
        self.fixture.reply={'phase':'waiting','code':'WAIT_CAPABILITY','pending':False,'receipts':[]}
        self.start();self.c.tick();first=self.fixture.calls[0][1]
        self.assertTrue(self.c.book['paused']);self.assertIsNone(self.c.book['pending']);self.c.tick()
        self.assertEqual(1,len(self.fixture.calls));self.assertEqual([True],self.fixture.closes)
        self.fixture.reply={'phase':'done','pending':False,'receipts':[]};self.c.resume();self.c.tick()
        self.assertEqual(first,self.fixture.calls[1][1]);self.assertEqual(1,self.c.book['cycle'])
    def test_exception_after_intent_never_gets_a_new_cycle_or_auto_retry(self):
        self.fixture.hook=lambda *_:(_ for _ in ()).throw(RuntimeError('unknown transfer'))
        self.start();self.c.tick();self.c.tick();self.assertEqual(1,len(self.fixture.calls))
        self.assertEqual(1,self.c.book['cycle']);self.assertEqual('harvest_store',self.c.book['pending']['stage'])
    def test_missing_park_proof_blocks_next_cycle(self):
        self.fixture.parked=False;self.start();self.cycle()
        self.assertEqual('parking',self.c.book['pending']['stage']);self.assertEqual('WAIT_PARK_RECEIPT',self.c.book['reason'])
        self.fixture.now=1000;self.c.tick();self.assertEqual(4,len(self.fixture.calls))
        with self.assertRaises(CaretakerPaused):self.c.resume()
    def test_health_hold_blocks_even_explicit_resume_before_factory(self):
        record_material_health_exit(self.root,{'time':100,'health':19},'health logout')
        with self.assertRaises(CaretakerPaused):self.c.resume()
        self.c.tick();self.assertEqual([],self.fixture.opens);self.assertFalse(self.c.book['enabled'])
    def test_disconnect_dimension_health_and_emergency_disable_no_auto_recovery(self):
        for change in ({'connected':False},{'dimension':'minecraft:the_nether'},{'health':19},
                       {'control_revision':2,'control_stop':{'kind':'emergency','revision':2}}):
            with self.subTest(change=change):
                root=Path(self.folder.name)/str(len(list(Path(self.folder.name).iterdir())))
                f=Fixture();c=Caretaker(root,profile(),observer=lambda:deepcopy(f.state),adapter_factory=f.factory,clock=lambda:10)
                c.resume();f.state.update(change);c.tick();self.assertFalse(c.book['enabled']);self.assertEqual([],f.opens)
                f.state=state();c.tick();self.assertEqual([],f.opens)
    def test_disconnect_also_disables_a_user_paused_schedule(self):
        self.start();self.c.command('pause');self.c.tick();self.fixture.state['connected']=False
        self.c.tick();self.assertFalse(self.c.book['enabled']);self.assertEqual('DISCONNECTED',self.c.book['reason'])
    def test_foreign_material_lease_prevents_client_factory(self):
        self.fixture.state['supervision_lease']={'kind':'materials','id':'foreign'}
        with self.assertRaises(CaretakerPaused):self.start()
        self.assertEqual([],self.fixture.opens)
    def test_explicit_resume_can_acknowledge_control_change_but_never_health_hold_or_world_change(self):
        self.fixture.reply={'phase':'waiting','pending':False,'receipts':[]};self.start();self.c.tick()
        self.fixture.state.update(control_revision=7,control_stop={'kind':'emergency','revision':7})
        self.c.tick();self.assertFalse(self.c.book['enabled'])
        self.c.resume();self.assertTrue(self.c.book['enabled']);self.assertEqual(7,self.c.book['last_revision'])
        self.assertEqual(1,self.c.book['cycle']);self.assertIsNone(self.c.book['pending'])
        self.c.tick();self.assertTrue(self.c.book['enabled'])
        self.fixture.state.update(control_revision=8,control_stop={'kind':'emergency','revision':8})
        self.c.tick();self.assertFalse(self.c.book['enabled'])
    def test_new_world_during_partial_cycle_cannot_be_adopted_by_resume(self):
        self.fixture.reply={'phase':'waiting','pending':False,'receipts':[]};self.start();self.c.tick()
        self.fixture.state['world_session']='new'
        with self.assertRaises(CaretakerPaused):self.c.resume()
        self.assertEqual(1,self.c.book['cycle'])
    def test_manual_yields_then_typed_witness_allows_three_idle_seconds(self):
        self.start();self.fixture.state.update(manual_movement=True,control_revision=2,
                                              control_stop={'kind':'manual','revision':2})
        self.c.tick();self.assertEqual('MANUAL_INPUT',self.c.book['reason']);self.assertEqual([],self.fixture.opens)
        self.fixture.state['manual_movement']=False;self.c.tick();self.fixture.now+=2;self.c.tick()
        self.assertEqual([],self.fixture.opens);self.fixture.now+=1;self.c.tick();self.assertEqual(1,len(self.fixture.opens))
    def test_manual_without_stop_witness_or_new_emergency_cannot_autoresume(self):
        self.start();self.fixture.state.update(manual_movement=True,control_revision=2)
        self.c.tick();self.assertEqual('WAIT_STOP_WITNESS',self.c.book['reason']);self.assertFalse(self.c.book['enabled'])
        self.fixture.state.update(manual_movement=False,control_stop={'kind':'manual','revision':2})
        self.fixture.now+=4;self.c.tick();self.assertEqual([],self.fixture.opens)
    def test_manual_with_unchanged_revision_still_needs_typed_stop_witness(self):
        self.start();self.fixture.state['manual_movement']=True;self.c.tick()
        self.assertEqual('WAIT_STOP_WITNESS',self.c.book['reason']);self.assertFalse(self.c.book['enabled'])
        self.fixture.state['manual_movement']=False;self.fixture.now+=4;self.c.tick()
        self.assertEqual([],self.fixture.opens)
    def test_manual_witness_disappearing_during_idle_never_auto_reclaims(self):
        self.start();self.fixture.state.update(manual_movement=True,control_revision=2,
                                              control_stop={'kind':'manual','revision':2})
        self.c.tick();self.fixture.state['manual_movement']=False;self.c.tick()
        self.fixture.state.pop('control_stop');self.fixture.now+=4;self.c.tick()
        self.assertEqual('WAIT_STOP_WITNESS',self.c.book['reason']);self.assertFalse(self.c.book['enabled'])
        self.assertEqual([],self.fixture.opens)
    def test_missing_native_survival_and_control_metadata_is_unavailable_not_guessed(self):
        for field,reason in [('connected','WORLD_UNAVAILABLE'),('health','HEALTH_UNAVAILABLE'),
                             ('food','SURVIVAL_UNAVAILABLE'),('under_water','SURVIVAL_UNAVAILABLE'),
                             ('control_revision','CONTROL_UNAVAILABLE')]:
            with self.subTest(field=field):
                f=Fixture();root=self.root/field
                c=Caretaker(root,profile(),observer=lambda:deepcopy(f.state),adapter_factory=f.factory)
                c.resume();f.state.pop(field);c.tick()
                self.assertEqual(reason,c.book['reason']);self.assertFalse(c.book['enabled']);self.assertEqual([],f.opens)
    def test_emergency_after_manual_wait_stops_before_three_second_reclaim(self):
        self.start();self.fixture.state.update(manual_movement=True,control_revision=2,control_stop={'kind':'manual','revision':2})
        self.c.tick();self.fixture.state.update(manual_movement=False,control_revision=3,control_stop={'kind':'emergency','revision':3})
        self.fixture.now+=4;self.c.tick();self.assertFalse(self.c.book['enabled']);self.assertEqual([],self.fixture.opens)
    def test_external_pause_stop_and_resume_controls_are_durable_and_idempotent(self):
        self.start();request=self.c.command('pause');self.c.tick();self.assertEqual('USER_PAUSE',self.c.book['reason'])
        self.c.tick();self.assertEqual([],self.fixture.opens);self.assertEqual(request['id'],self.c.book['last_control'])
        self.c.command('resume');self.c.tick();self.assertEqual(1,len(self.fixture.opens))
        self.c.command('stop');self.c.tick();self.assertFalse(self.c.book['enabled']);self.assertEqual([False],self.fixture.closes)
    def test_control_during_stage_preserves_intent_and_does_not_finish_normally(self):
        self.start()
        def hook(stage,checkpoint):self.c.command('stop');checkpoint()
        self.fixture.hook=hook;self.c.tick();self.assertFalse(self.c.book['enabled'])
        self.assertIsNotNone(self.c.book['pending']);self.assertEqual([False],self.fixture.closes)
    def test_worker_os_lock_prevents_two_controllers(self):
        other=self.make()
        with self.c.worker_lock():
            self.assertTrue(other.worker_running())
            with self.assertRaisesRegex(RuntimeError,'Another'): 
                with other.worker_lock():pass
        self.assertFalse(other.worker_running())
    def test_worker_interruption_closes_lease_preserves_intent_and_stops_schedule(self):
        self.start()
        def interrupt(_):raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.c.run(sleep=interrupt)
        self.assertEqual([False],self.fixture.closes);self.assertFalse(self.c.book['enabled'])
        self.assertEqual('WORKER_INTERRUPTED',self.c.book['reason']);self.assertEqual('breed',self.c.book['stage'])
        self.assertTrue(self.c.lock_path.exists());self.assertFalse(self.c.worker_running())
    def test_unknown_pending_still_observes_and_stops_for_persisted_health_hold(self):
        self.fixture.reply={'phase':'waiting','pending':True,'receipts':[]};self.start();self.c.tick()
        original=deepcopy(self.c.book['pending']);record_material_health_exit(self.root,{'time':100,'health':19},'exit')
        self.c.tick();self.assertFalse(self.c.book['enabled']);self.assertEqual(original,self.c.book['pending'])
        self.assertEqual(1,len(self.fixture.calls))
    def test_control_revision_change_without_manual_witness_disables(self):
        self.start();self.fixture.state['control_revision']=2;self.c.tick()
        self.assertEqual('CONTROL_CHANGED',self.c.book['reason']);self.assertFalse(self.c.book['enabled'])
    def test_old_hurt_marker_full_health_does_not_disable(self):
        self.fixture.state['recent_hurt_at']=5;self.start();self.c.tick()
        self.assertFalse(self.c.book['paused']);self.assertEqual(1,len(self.fixture.calls))


def _read(path):return json.loads(path.read_text())


class NativeAdapterTests(unittest.TestCase):
    def test_binds_one_existing_backend_client_and_approved_profile_before_actions(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cycle={'id':1,'directory':str(root/'cycle')}
            backend=Mock();backend.profile={'depots':[[10,64,0]]};backend.out=root/'backend';backend.client=Mock()
            backend.ensure_client.return_value=backend.client
            stages={name:Mock(return_value={'phase':'idle','pending':False,'receipts':[]}) for name in STAGES}
            module=Mock();module.create_stages.return_value=stages
            with patch('material_jobs_backend.create_backend',return_value=backend),patch.dict('sys.modules',{'farm_caretaker_stages':module}):
                a=NativeStages(root,validate_profile(profile()),cycle,Mock(),state())
                module.create_stages.assert_called_once_with(backend.client,backend)
                backend.ensure_client.assert_called_once();a.run('breed',profile(),cycle,root,Mock())
                stages['breed'].assert_called_once();self.assertIs(a.client,backend.client)
    def test_acquired_client_binding_failure_closes_its_lease(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);backend=Mock();backend.profile={'depots':[[10,64,0]]};backend.out=root/'backend'
            backend.client=Mock();backend.ensure_client.return_value=Mock()
            with patch('material_jobs_backend.create_backend',return_value=backend),patch.dict('sys.modules',{'farm_caretaker_stages':Mock()}),patch.object(NativeStages,'close') as close:
                with self.assertRaisesRegex(RuntimeError,'existing Backend client'):
                    NativeStages(root,validate_profile(profile()),{'id':1,'directory':str(root/'cycle')},Mock(),state())
                close.assert_called_once_with(normal=False)
    def test_unapproved_destination_is_rejected_before_ensure_client(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);backend=Mock();backend.profile={'depots':[]}
            with patch('material_jobs_backend.create_backend',return_value=backend),patch.dict('sys.modules',{'farm_caretaker_stages':Mock()}):
                with self.assertRaisesRegex(ValueError,'approved'):
                    NativeStages(root,validate_profile(profile()),{'id':1,'directory':str(root/'cycle')},Mock(),state())
            backend.ensure_client.assert_not_called()


class RealStageStopTests(unittest.TestCase):
    """Use NativeStages and create_stages; fake only native I/O and cleanup."""
    def setUp(self):
        from test_potato_harvest import HarvestClient
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)/'automation';self.client=HarvestClient(age=0,potatoes=4)
        self.client.world='w';self.client.server='example.test';self.client.rev=1;self.client.last=None
        self.client.extra.update(world_session='w',server='example.test',control_revision=1,supervision_lease={})
        self.backend=Mock();self.backend.profile={'depots':[[10,64,0]]};self.backend.out=self.root/'backend'
        self.backend.client=self.client;self.change=lambda:None;self.closes=[];self.close_error=False
        def acquire():
            self.client.extra['supervision_lease']={'kind':'materials','id':self.client.heartbeat.id,
                'job_session':self.client.task,'world_session':'w','revision':self.client.rev,'remote_finish':'guard'}
            self.change();return self.client
        self.backend.ensure_client.side_effect=acquire
        def close(adapter,*,normal):
            self.closes.append(normal)
            if self.close_error:raise RuntimeError('cleanup observation unavailable')
            if normal:
                self.client.rev+=1;self.client.extra.update(control_revision=self.client.rev,
                    supervision_lease={'kind':'parking','id':self.client.heartbeat.id})
            return {'parked':normal,'parking_lease':self.client.heartbeat.id,'revision':self.client.rev}
        factory=patch('material_jobs_backend.create_backend',return_value=self.backend);factory.start();self.addCleanup(factory.stop)
        cleanup=patch.object(NativeStages,'close',autospec=True,side_effect=close);cleanup.start();self.addCleanup(cleanup.stop)
        self.c=Caretaker(self.root,profile(),observer=self.client.status,clock=lambda:10)
        self.c.resume()
    def test_real_stage_manual_checkpoint_keeps_reason_intent_and_yields_without_parking(self):
        self.change=lambda:self.client.extra.update(manual_movement=True,control_revision=2,
                                                     control_stop={'kind':'manual','revision':2})
        self.close_error=True;self.c.tick();pending=deepcopy(self.c.book['pending'])
        self.assertEqual('MANUAL_INPUT',self.c.book['reason']);self.assertEqual([False],self.closes)
        self.assertEqual('WAIT_FINISH',self.c.book['cleanup_wait']['code']);self.assertIsNotNone(pending)
        self.client.extra['manual_movement']=False;self.c.tick()
        self.assertEqual('MANUAL_INPUT',self.c.book['reason']);self.assertEqual(pending,self.c.book['pending'])
        self.assertEqual([],self.client.calls);self.backend.finish.assert_not_called()
    def test_real_stage_emergency_checkpoint_disables_and_unknown_intent_cannot_resume(self):
        self.change=lambda:self.client.extra.update(control_revision=2,control_stop={'kind':'emergency','revision':2})
        self.c.tick();pending=deepcopy(self.c.book['pending'])
        self.assertEqual('EMERGENCY_STOP',self.c.book['reason']);self.assertFalse(self.c.book['enabled'])
        self.assertEqual([False],self.closes);self.assertEqual([],self.client.calls)
        self.c.command('resume');self.c.tick()
        self.assertEqual('EMERGENCY_STOP',self.c.book['reason']);self.assertEqual(pending,self.c.book['pending'])
        self.assertIn('WAIT_RECONCILE',self.c.book['resume_wait']);self.assertFalse(self.c.book['enabled'])
    def test_real_stage_health_hold_disables_without_normal_finish_or_pending_loss(self):
        self.change=lambda:record_material_health_exit(self.root,{'time':100,'health':19},'exit')
        self.close_error=True;self.c.tick();pending=deepcopy(self.c.book['pending'])
        self.assertEqual('SAFETY_HOLD',self.c.book['reason']);self.assertFalse(self.c.book['enabled'])
        self.assertEqual([False],self.closes);self.assertEqual([],self.client.calls)
        self.c.tick();self.assertEqual(pending,self.c.book['pending']);self.assertEqual('SAFETY_HOLD',self.c.book['reason'])
    def test_real_stage_missing_age_metadata_waits_without_marking_breed_complete(self):
        self.client.entities=[{'uuid':'cow','id':1,'type':'minecraft:cow','pos':[4,64,2],
                               'alive':True,'visible':True}]
        self.c._cycle(self.client.status());self.c.book['stage']='breed';self.c.save();self.c.tick()
        self.assertEqual('WAIT_SCAN',self.c.book['reason']);self.assertEqual('breed',self.c.book['stage'])
        receipt=self.c.book['current_cycle']['receipts']['breed']
        self.assertEqual('waiting',receipt['phase']);self.assertFalse(receipt['pending'])
        self.assertFalse(_read(Path(receipt['journal'])).get('complete',False))
        self.c.tick();self.assertEqual(1,len(self.client.calls));self.assertEqual('scan',self.client.calls[0][0])
    def test_real_stage_known_attack_rejection_never_completes_or_auto_replays(self):
        p=profile();p['livestock_region']={'min':[0,63,0],'max':[15,65,15]}
        self.client.extra.update(on_ground=False,attack_strength=1,material_slaughter_protocol=1)
        self.client.inv[0].update(item='minecraft:iron_sword',count=1)
        self.client.entities=[{'uuid':'cow-'+str(n),'id':n+1,'type':'minecraft:cow',
            'pos':[1,64,1] if n==0 else [4+(n-1)%4*2,64,4+(n-1)//4*2],
            'alive':True,'visible':True,'is_baby':False,'has_custom_name':False,'health':20} for n in range(21)]
        original=self.client.request;attacks=[]
        def request(op,**params):
            if op!='material_slaughter_attack':return original(op,**params)
            attacks.append(params)
            self.client.last='reject-1'
            return {**self.client.status(),'id':'reject-1','phase':'error','detail':'native cooldown changed',
                'slaughter_attack':{'id':'reject-1','world_session':'w','expected_uuid':params['expected_uuid'],
                    'result_scope':'normal_attack_dispatch_only','action_sent':False,'pre_dispatch_rejected':True}}
        self.client.request=request
        c=Caretaker(self.root/'reject',p,observer=self.client.status,clock=lambda:10);c.resume()
        c._cycle(self.client.status());c.book['stage']='surplus';c.save();c.tick()
        self.assertEqual('WAIT_ATTACK_REJECTED',c.book['reason']);self.assertTrue(c.book['paused'])
        self.assertEqual('surplus',c.book['stage']);self.assertIsNone(c.book['pending']);self.assertEqual(1,len(attacks))
        reply=c.book['current_cycle']['receipts']['surplus'];self.assertEqual('waiting',reply['phase'])
        self.assertFalse(_read(Path(reply['journal'])).get('complete',False))
        c.tick();self.assertEqual(1,len(attacks));self.assertEqual(1,c.book['cycle'])


if __name__=='__main__':unittest.main()
