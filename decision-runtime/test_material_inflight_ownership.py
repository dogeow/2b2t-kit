"""Exact in-flight native ownership, callback ordering, and no-replay lifecycle."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from material_client import Client, Handoff
from material_jobs_backend import JobClient, owns_material_state
from material_jobs.protocol import JobPaused


def snapshot(revision=13, **fields):
    return {'connected':True,'manual_movement':False,'world_session':'world',
            'control_revision':revision,'server':'example.test:25565','dimension':'minecraft:overworld',
            'time':100,'pos':[.5,110,.5],'screen':'','health':20,'food':20,'inventory':[],
            'guard_busy':False,'under_water':False,'recent_hurt_at':0,'safety_hold':{'active':False},
            'supervision_lease':{'kind':'materials','id':'lease-a','job_session':'task-a',
                                 'world_session':'world','revision':revision}, **fields}


def descriptor(rid='request-a', op='navigate', expected=14):
    return {'request_id':rid,'op':op,'world_session':'world','task_session':'task-a',
            'lease_id':'lease-a','base_revision':13,'request_revision':13,'expected_revision':expected,
            'server':'example.test:25565','dimension':'minecraft:overworld'}


class InflightOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.client=SimpleNamespace(world='world',task='task-a',rev=13,last='request-a',
                                    heartbeat=SimpleNamespace(id='lease-a'),native_inflight=descriptor())
        self.state=snapshot(14,id='request-a',last_request='request-a',op='navigate',phase='running')

    def test_exact_own_running_navigation_accepts13_to14_without_adopting_revision(self):
        self.assertTrue(owns_material_state(self.client,self.state));self.assertEqual(13,self.client.rev)
        self.client.native_inflight=None
        self.assertFalse(owns_material_state(self.client,self.state))

    def test_foreign_missing_manual_offline_and_unexpected_revision_are_rejected(self):
        changes=[('id','foreign'),('last_request','foreign'),('op','walk'),('world_session','foreign'),
                 ('control_revision',15),('connected',False),('connected',None),('manual_movement',True),
                 ('manual_movement',None),('phase','queued'),('server','foreign.test'),
                 ('dimension','minecraft:the_nether'),('op',None)]
        for field,value in changes:
            with self.subTest(field=field,value=value):
                state=copy.deepcopy(self.state);state[field]=value
                if field=='control_revision':state['supervision_lease']['revision']=value
                self.assertFalse(owns_material_state(self.client,state))
        for field,value in [('id','foreign'),('job_session','foreign'),('world_session','foreign'),
                            ('kind','parking'),('revision',13)]:
            with self.subTest(lease=field):
                state=copy.deepcopy(self.state);state['supervision_lease'][field]=value
                self.assertFalse(owns_material_state(self.client,state))
        for kind in ('manual','emergency'):
            state=copy.deepcopy(self.state);state['control_stop']={'kind':kind,'revision':14}
            self.assertFalse(owns_material_state(self.client,state))

    def test_descriptor_must_match_actual_request_base_expected_world_task_and_lease(self):
        changes=[('request_id','foreign'),('op','walk'),('world_session','foreign'),('task_session','foreign'),
                 ('lease_id','foreign'),('base_revision',12),('request_revision',14),('expected_revision',15),
                 ('base_revision',True),('request_revision',True),('expected_revision',True),
                 ('server','foreign.test'),('dimension','minecraft:the_nether')]
        for field,value in changes:
            with self.subTest(field=field,value=value):
                client=copy.deepcopy(self.client);client.native_inflight[field]=value
                self.assertFalse(owns_material_state(client,self.state))
        for field in descriptor():
            with self.subTest(missing=field):
                client=copy.deepcopy(self.client);client.native_inflight.pop(field)
                self.assertFalse(owns_material_state(client,self.state))
        client=copy.deepcopy(self.client);client.last='previous-request'
        self.assertFalse(owns_material_state(client,self.state))
        client=copy.deepcopy(self.client);client.native_inflight['op']='unknown-operation'
        state={**self.state,'op':'unknown-operation'}
        self.assertFalse(owns_material_state(client,state))
        for invalid in (None,{},[],False):
            client=copy.deepcopy(self.client);client.native_inflight=invalid
            self.assertFalse(owns_material_state(client,self.state))

    def test_existing_terminal_timeout_stop_and_current_revision_rules_remain(self):
        self.client.native_inflight=None
        for phase in ('done','waiting','stopped','error'):
            with self.subTest(phase=phase):
                state=snapshot(15,id='request-a',last_request='request-a',op='navigate',phase=phase)
                self.assertTrue(owns_material_state(self.client,state))
                state['manual_movement']=True;self.assertFalse(owns_material_state(self.client,state))
        self.assertTrue(owns_material_state(self.client,snapshot()))
        self.client.native_inflight=descriptor(op='stop',expected=15)
        state=snapshot(15,id='request-a',last_request='request-a',op='stop',phase='running')
        self.assertTrue(owns_material_state(self.client,state))
        self.client.native_inflight['expected_revision']=14
        self.assertFalse(owns_material_state(self.client,state))


class InflightLifecycleTests(unittest.TestCase):
    def make_client(self,root):
        client=JobClient.__new__(JobClient)
        client.root=client.out=root;client.world='world';client.rev=13;client.anchor=[.5,110,.5]
        client.server='example.test';client.task='task-a';client.owned=False;client.last=None
        client.native_inflight=None;client.heartbeat=SimpleNamespace(id='lease-a',touch=Mock())
        client.owner=SimpleNamespace(latest=None,cleaning=False);client.observations=[]
        def poll():
            state=client.owner.latest
            client.observations.append((client.rev,copy.deepcopy(state),copy.deepcopy(client.native_inflight)))
            if not owns_material_state(client,state):raise JobPaused('foreign control')
        client.owner.poll_control=poll
        return client

    def reader(self,client,terminal='done',fail=None):
        client.polls=0;client.seen_ids=set()
        def read(*args,**kwargs):
            path=client.root/'request.json'
            if not path.exists():return snapshot()
            req=json.loads(path.read_text());client.seen_ids.add(req['id']);client.polls+=1
            if fail=='interrupt':raise KeyboardInterrupt('stop callback')
            if fail=='world':return snapshot(14,world_session='foreign',id=req['id'],last_request=req['id'],op=req['op'],phase='running')
            phase='running' if client.polls==1 or fail=='timeout' else terminal
            revision=14 if phase in ('running','done','error') else 15
            return snapshot(revision,id=req['id'],last_request=req['id'],op=req['op'],phase=phase,
                            time=100+client.polls,detail='normal native operation observation')
        return read

    def test_real_jobclient_poll_callback_sees_running_descriptor_before_terminal_revision_adoption(self):
        with tempfile.TemporaryDirectory() as folder:
            client=self.make_client(Path(folder))
            with patch('live_snapshot.read_fresh',side_effect=self.reader(client)), \
                 patch('safety_interlock.require_unlocked'),patch('material_client.time.sleep'):
                result=client.request('navigate',target=[1.5,110,.5])
            running=[row for row in client.observations if row[1].get('phase')=='running']
            self.assertEqual(1,len(running));rev,state,inflight=running[0]
            self.assertEqual((13,14),(rev,state['control_revision']))
            self.assertEqual(state['id'],inflight['request_id']);self.assertEqual('navigate',inflight['op'])
            self.assertEqual('done',result['phase']);self.assertEqual(14,client.rev)
            self.assertIsNone(client.native_inflight);self.assertEqual(1,len(client.seen_ids))

    def test_jobclient_status_forwards_positional_and_keyword_options_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            client=self.make_client(Path(folder));state=snapshot()
            with patch.object(Client,'status',return_value=state) as status:
                self.assertIs(state,client.status(.5,wait_interface=False))
            status.assert_called_once_with(.5,wait_interface=False)

    def test_real_jobclient_stop_logout_and_pause_forward_status_options_before_dispatch(self):
        for op,revision in (('stop',15),('safe_logout',15),('material_job_pause',13)):
            with self.subTest(op=op),tempfile.TemporaryDirectory() as folder:
                client=self.make_client(Path(folder));calls=[];ids=set();polls=0
                original_status=Client.status
                def status(target,*args,**kwargs):
                    self.assertIs(target,client);calls.append((args,kwargs.copy()))
                    return original_status(target,*args,**kwargs)
                def read(*args,**kwargs):
                    nonlocal polls
                    path=client.root/'request.json'
                    if not path.exists():return snapshot()
                    req=json.loads(path.read_text());ids.add(req['id']);polls+=1
                    self.assertEqual(op,req['op']);self.assertEqual('task-a',req['task_session'])
                    if op=='material_job_pause':self.assertIs(req['release'],False)
                    phase='running' if polls==1 else 'stopped' if op=='stop' else 'done'
                    return snapshot(revision,id=req['id'],last_request=req['id'],op=op,phase=phase,time=100+polls)
                with patch('live_snapshot.read_fresh',side_effect=read), \
                     patch('safety_interlock.require_unlocked'),patch('material_client.time.sleep'), \
                     patch.object(Client,'status',status):
                    result=client.request(op,**({'release':False} if op=='material_job_pause' else {}))
                self.assertEqual([((),{'wait_interface':False})],calls)
                self.assertEqual(1,len(ids));self.assertEqual(2,polls)
                self.assertEqual('stopped' if op=='stop' else 'done',result['phase'])
                self.assertEqual(revision,client.rev);self.assertIsNone(client.native_inflight)
                self.assertTrue(any(row[1].get('phase')=='running' for row in client.observations))

    def test_descriptor_and_last_are_visible_before_atomic_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            client=self.make_client(Path(folder));original=Path.replace;seen=[]
            def replace(path,destination):
                if path.name=='request.materials.tmp':
                    req=json.loads(path.read_text());seen.append(req)
                    self.assertEqual(req['id'],client.native_inflight['request_id'])
                    self.assertEqual(req['id'],client.last)
                    self.assertEqual(req['expected_revision'],client.native_inflight['request_revision'])
                    self.assertFalse(Path(destination).exists())
                return original(path,destination)
            with patch('live_snapshot.read_fresh',side_effect=self.reader(client)), \
                 patch('safety_interlock.require_unlocked'),patch('material_client.time.sleep'),patch.object(Path,'replace',replace):
                client.request('navigate',target=[1.5,110,.5])
            self.assertEqual(1,len(seen));self.assertIsNone(client.native_inflight)

    def test_interrupt_during_descriptor_publication_clears_it_before_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            client=self.make_client(Path(folder));client.last='previous-request';armed=True
            def publish(target,name,value):
                nonlocal armed
                object.__setattr__(target,name,value)
                if target is client and name=='last' and value != 'previous-request' and armed:
                    armed=False;raise KeyboardInterrupt('publication interrupted')
            with patch('live_snapshot.read_fresh',return_value=snapshot()), \
                 patch('safety_interlock.require_unlocked'),patch.object(JobClient,'__setattr__',publish):
                with self.assertRaisesRegex(KeyboardInterrupt,'publication interrupted'):
                    client.request('navigate',target=[1.5,110,.5])
            self.assertIsNone(client.native_inflight);self.assertEqual('previous-request',client.last)
            self.assertFalse((client.root/'request.json').exists())

    def test_atomic_dispatch_failure_clears_descriptor_and_restores_prior_last(self):
        with tempfile.TemporaryDirectory() as folder:
            client=self.make_client(Path(folder));client.last='previous-request'
            with patch('live_snapshot.read_fresh',return_value=snapshot()), \
                 patch('safety_interlock.require_unlocked'),patch.object(Path,'replace',side_effect=OSError('dispatch failed')):
                with self.assertRaisesRegex(OSError,'dispatch failed'):client.request('navigate',target=[1.5,110,.5])
            self.assertIsNone(client.native_inflight);self.assertEqual('previous-request',client.last)
            self.assertFalse((client.root/'request.json').exists())

    def test_owned_terminal_timeout_and_stopped_revisions_are_returned_once_and_cleared(self):
        for terminal in ('waiting','stopped','error'):
            with self.subTest(terminal=terminal),tempfile.TemporaryDirectory() as folder:
                client=self.make_client(Path(folder))
                with patch('live_snapshot.read_fresh',side_effect=self.reader(client,terminal)), \
                     patch('safety_interlock.require_unlocked'),patch('material_client.time.sleep'):
                    result=client.request('navigate',target=[1.5,110,.5])
                self.assertEqual(terminal,result['phase']);self.assertIsNone(client.native_inflight)
                self.assertEqual(1,len(client.seen_ids))
                self.assertEqual(14 if terminal=='error' else 15,client.rev)

    def test_dispatched_callback_failure_or_interrupt_keeps_mailbox_and_never_replays(self):
        for fail,error in (('world',JobPaused),('interrupt',KeyboardInterrupt)):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as folder:
                client=self.make_client(Path(folder))
                with patch('live_snapshot.read_fresh',side_effect=self.reader(client,fail=fail)), \
                     patch('safety_interlock.require_unlocked'),patch('material_client.time.sleep'):
                    with self.assertRaises(error):client.request('navigate',target=[1.5,110,.5])
                req=json.loads((client.root/'request.json').read_text())
                self.assertEqual(req['id'],client.last);self.assertIsNone(client.native_inflight)
                self.assertEqual(13,client.rev);self.assertEqual(1,len(client.seen_ids))

    def test_python_timeout_clears_short_lived_authority_but_retains_unresolved_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            client=self.make_client(Path(folder));clock=iter(range(1000))
            with patch('live_snapshot.read_fresh',side_effect=self.reader(client,fail='timeout')), \
                 patch('safety_interlock.require_unlocked'),patch('material_client.time.sleep'), \
                 patch('material_client.time.monotonic',side_effect=lambda:next(clock)):
                with self.assertRaisesRegex(RuntimeError,'do not replay'):client.request('navigate',target=[1.5,110,.5],seconds=0)
            req=json.loads((client.root/'request.json').read_text())
            self.assertEqual(req['id'],client.last);self.assertIsNone(client.native_inflight)
            self.assertEqual(13,client.rev);self.assertEqual(1,len(client.seen_ids))
            self.assertFalse(owns_material_state(client,client.owner.latest))

    def test_terminal_logging_failure_still_clears_descriptor(self):
        with tempfile.TemporaryDirectory() as folder:
            client=self.make_client(Path(folder));(client.out/'events.jsonl').mkdir()
            with patch('live_snapshot.read_fresh',side_effect=self.reader(client)), \
                 patch('safety_interlock.require_unlocked'),patch('material_client.time.sleep'):
                with self.assertRaises(IsADirectoryError):client.request('navigate',target=[1.5,110,.5])
            self.assertEqual(14,client.rev);self.assertIsNone(client.native_inflight)
            self.assertEqual(1,len(client.seen_ids))

    def test_logout_offline_early_return_clears_descriptor_without_claiming_offline_ownership(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            class Fake(Client):
                def raw(self):
                    if not (root/'request.json').exists():return snapshot()
                    req=json.loads((root/'request.json').read_text())
                    return snapshot(15,id=req['id'],last_request=req['id'],op='safe_logout',connected=False)
            client=Fake.__new__(Fake);client.root=client.out=root;client.world='world';client.rev=13
            client.anchor=[.5,110,.5];client.last=None;client.owned=False;client.native_inflight=None
            result=client.request('safe_logout')
            self.assertFalse(result['connected']);self.assertIsNone(client.native_inflight)
            self.assertEqual(json.loads((root/'request.json').read_text())['id'],client.last)


if __name__=='__main__':unittest.main()
