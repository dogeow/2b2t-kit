import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

from material_jobs.acquisition import (Unavailable,held_resource_route,
                                        _resource_ledger_scope_path)
from material_jobs.bobby_snow_route import (LEDGER_KEY, candidate_key, ledger_state,
                                             mark_candidate, outbound, return_home,
                                             recover_unmoved_first_rejection,
                                             recover_parked_unmoved_first_rejection,
                                             recover_parked_rejection_files,
                                             _idle_movement_samples,
                                             _bind_legacy_unmoved_rejection,
                                             UNLOADED_AIR_ONLY_REJECTION)


CANDIDATE = {'source':'bobby_cache','cache_server':'test',
             'dimension':'minecraft:overworld',
             'chunk': [64, -32], 'tile': [1024, -512],
             'target':[1032.5,200.0,-503.5],'distance_sq':1_310_720.0,
             'region_file': 'r.2.-1.mca', 'fingerprint': 'a' * 64,
             'mtime_ns':100,'ctime_ns':101,'size':8192,'file_id':7,
             'biomes': ['minecraft:snowy_plains']}


class Client:
    world = 'world'

    def __init__(self, *, fail_navigate=None, fail_guard=None,
                 reject_unloaded_first=False,auto_terminal_evidence=False):
        self.pos = [0.5, 145.0, 0.5]
        self.anchor = list(self.pos)
        self.time = 100
        self.rev = 7
        self.task = 'materials-job'
        self.last = None
        self.actions = []
        self.fail_navigate = fail_navigate
        self.fail_guard = fail_guard
        self.navigate_count = 0
        self.guard_count = 0
        self.reject_unloaded_first=reject_unloaded_first
        self.phase='idle';self.detail=''
        self.auto_terminal_evidence=auto_terminal_evidence

    def status(self):
        return {'world_session': self.world, 'server':'test:25565',
                'pos': list(self.pos), 'time': self.time,
                'control_revision': self.rev, 'health': 20, 'food': 20,
                'under_water': False, 'flight': True, 'guard_armed': True,
                'guard_pve_only': True, 'manual_movement': False,
                'safety_hold': {'active': False}, 'navigating': False,
                'native_material_busy': False,
                'last_request':self.last,'id':self.last,
                'phase':self.phase,'detail':self.detail,
                'movement_keys':{'forward':False,'back':False,
                                 'jump':False,'sneak':False},
                'velocity':[0,0,0],
                'supervision_lease': {'kind': 'materials',
                    'job_session': self.task, 'world_session': self.world,
                    'revision': self.rev,'search_origin':[0.5,145.0,0.5],
                    'return_target':{'x':0.5,'z':0.5,'cruise_y':160.0,
                                     'dimension':'minecraft:overworld',
                                     'source':'saved_home'}},
                'dimension':'minecraft:overworld'}

    def checked(self, op, **params):
        reply = self.request(op, **params)
        if reply.get('phase') != 'done':
            raise RuntimeError(reply.get('detail', op + ' failed'))
        return reply

    def request(self, op, **params):
        self.actions.append((op, copy.deepcopy(params), list(self.anchor)))
        self.last = op + '-' + str(len(self.actions)); self.time += 1
        if op == 'guard':
            self.guard_count += 1
            if self.fail_guard == self.guard_count:
                return {'id': self.last, 'world_session': self.world,
                        'phase': 'error', 'detail': 'guard refused'}
            self.phase='done';self.detail=''
            return {'id': self.last, 'world_session': self.world, 'phase': 'done'}
        if op == 'navigate':
            self.navigate_count += 1
            if self.reject_unloaded_first and self.navigate_count==1:
                self.phase='error';self.detail=UNLOADED_AIR_ONLY_REJECTION
                if self.auto_terminal_evidence:
                    self.last_terminal_evidence={
                        'request_id':self.last,'task_session':self.task,
                        'world_session':self.world,'server':'test:25565',
                        'dimension':'minecraft:overworld','op':'navigate',
                        'params':{'air_only':True,'target':list(params['target'])},
                        'phase':'error','detail':self.detail,
                        'position_before':list(self.pos),'terminal_pos':list(self.pos),
                        'revision_before':self.rev,'revision_after':self.rev,
                        'movement_keys':self.status()['movement_keys'],
                        'velocity':[0,0,0],'pre_dispatch_rejected':True}
                return {'id':self.last,'world_session':self.world,
                        'phase':'error','detail':self.detail}
            if self.fail_navigate == self.navigate_count:
                self.pos = [(self.pos[0] + params['target'][0]) / 2,
                            params['target'][1],
                            (self.pos[2] + params['target'][2]) / 2]
                self.phase='waiting';self.detail='server did not confirm'
                return {'id': self.last, 'world_session': self.world,
                        'phase': 'waiting', 'detail': 'server did not confirm'}
            self.pos = list(params['target'])
            self.phase='done';self.detail=''
            return {'id': self.last, 'world_session': self.world, 'phase': 'done'}
        raise AssertionError(op)


class BobbySnowRouteTest(unittest.TestCase):
    def test_every_durable_movement_sample_must_be_unmoved_and_idle(self):
        terminal=[1.5,80.0,2.5];idle={'pos':terminal,
            'movement_keys':{'forward':False,'back':False,'jump':False,'sneak':False},
            'velocity':[0,0,0]}
        self.assertTrue(_idle_movement_samples([idle,copy.deepcopy(idle)],terminal))
        for field,value in (('pos',[1.6,80,2.5]),
                            ('movement_keys',{'forward':True}),
                            ('velocity',[.01,0,0])):
            rows=[copy.deepcopy(idle),copy.deepcopy(idle)];rows[0][field]=value
            self.assertFalse(_idle_movement_samples(rows,terminal))

    @staticmethod
    def rejection_evidence(client,route):
        segment=route['current_segment']
        return {'route_id':route['route_id'],'task_session':route['task_session'],
            'world_session':route['world_session'],'server':'test:25565',
            'dimension':'minecraft:overworld','request_id':client.last,
            'op':'navigate','phase':'error','detail':UNLOADED_AIR_ONLY_REJECTION,
            'pre_dispatch_rejected':True,
            'params':{'air_only':True,'target':list(segment['target'])},
            'position_before':list(segment['from']),'terminal_pos':list(segment['from']),
            'revision_before':7,'revision_after':7,
            'movement_keys':client.status()['movement_keys'],'velocity':[0,0,0]}

    @staticmethod
    def parking_finish(client,route,lease):
        current=client.status()
        fields=('world_session','server','dimension','pos','health','flight',
                'guard_armed','guard_pve_only','control_revision')
        snapshot={key:copy.deepcopy(current.get(key)) for key in fields}
        snapshot['supervision_lease']=copy.deepcopy(lease)
        return {'action':'KEEP_PVE_GUARD','lease':lease['id'],
                'job_session':route['task_session'],'snapshot':snapshot}

    def route(self, directory, client=None):
        client = client or Client()
        path = Path(directory) / 'resource.json'
        ledger = {'schema': 1, 'item': 'minecraft:snow', 'tiles': {}}
        state = ledger_state(ledger, 'test:25565', 'minecraft:overworld')
        path.write_text(json.dumps(ledger))
        route = outbound(client, CANDIDATE, 'test:25565', 'minecraft:overworld',
                         path, ledger, lambda: None,
                         lambda candidate: candidate == CANDIDATE,
                         lambda candidate: candidate == CANDIDATE)
        return client, path, ledger, state, route

    def rejected(self,directory):
        client=Client(reject_unloaded_first=True)
        path=Path(directory)/'resource.json';ledger={
            'schema':1,'item':'minecraft:snow','tiles':{}}
        ledger_state(ledger,'test','minecraft:overworld');path.write_text(json.dumps(ledger))
        with self.assertRaises(Unavailable):outbound(
            client,CANDIDATE,'test','minecraft:overworld',path,ledger,
            lambda:None,lambda row:True,lambda row:True)
        saved=json.loads(path.read_text());route=saved[LEDGER_KEY]['active_route']
        return client,path,saved,route,self.rejection_evidence(client,route)

    def parked(self,directory):
        client,path,saved,route,proof=self.rejected(directory)
        terminal=list(client.pos);client.pos=[terminal[0],200.0,terminal[2]]
        client.rev=9;client.phase='parking'
        lease=client.status()['supervision_lease'];lease.update(
            kind='parking',id='lease-a',revision=9)
        original=client.status;client.status=lambda:{**original(),'supervision_lease':lease}
        return client,path,saved,route,proof,lease,self.parking_finish(client,route,lease)

    def test_outbound_and_return_use_bounded_guarded_same_route_segments(self):
        with tempfile.TemporaryDirectory() as directory:
            client, path, ledger, state, route = self.route(directory)
            outbound_segments = [row for row in route['recent_segments']
                                 if row['direction'] == 'outbound']
            self.assertEqual(4, len(outbound_segments))
            self.assertTrue(all(((row['target'][0]-row['from'][0]) ** 2
                                 + (row['target'][2]-row['from'][2]) ** 2) ** .5 <= 320
                                for row in outbound_segments))
            actions = [op for op, _, _ in client.actions]
            self.assertEqual(['guard', 'navigate'] * 4, actions)
            self.assertTrue(all('air_only' not in params for op,params,_ in client.actions
                                if op=='navigate'))
            for index in range(0, len(client.actions), 2):
                self.assertEqual(client.actions[index][2],
                                 outbound_segments[index // 2]['from'])
            mark_candidate(client, path, ledger, 'live_verified')
            result = return_home(client, lambda: None)
            self.assertEqual((5, 'saved_home', [0.5, 160.0, 0.5]),
                             (result['segments'], result['return_source'], client.pos))
            saved = json.loads(path.read_text())[LEDGER_KEY]
            self.assertIsNone(saved['active_route'])
            self.assertEqual('home_arrived', saved['routes'][-1]['state'])
            returned=[row['target'] for row in saved['routes'][-1]['recent_segments']
                      if row['direction']=='return']
            self.assertNotIn([0.5,145.0,0.5],returned)
            self.assertEqual('live_verified', saved['visited'][candidate_key(CANDIDATE)]['state'])
            self.assertNotIn('hash', json.dumps(saved).lower())

    def test_failed_segment_is_held_and_never_switches_or_replays(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Client(fail_navigate=2)
            path = Path(directory) / 'resource.json'
            ledger = {'schema': 1, 'item': 'minecraft:snow', 'tiles': {}}
            ledger_state(ledger, 'test', 'minecraft:overworld')
            path.write_text(json.dumps(ledger))
            with self.assertRaises(Unavailable):
                outbound(client, CANDIDATE, 'test', 'minecraft:overworld', path,
                         ledger, lambda: None, lambda candidate: True)
            saved = json.loads(path.read_text())[LEDGER_KEY]
            self.assertEqual('outbound_uncertain', saved['active_route']['state'])
            self.assertEqual(2, client.navigate_count)
            with self.assertRaises(Unavailable):
                outbound(client, dict(CANDIDATE, chunk=[65, -32], tile=[1040, -512],
                                      target=[1048.5,200.0,-503.5],distance_sq=1_343_744.0),
                         'test', 'minecraft:overworld', path, ledger,
                         lambda: None, lambda candidate: True)
            self.assertEqual(2, client.navigate_count)

    def test_guard_failure_stops_before_the_matching_navigation(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Client(fail_guard=2)
            path = Path(directory) / 'resource.json'
            ledger = {'schema': 1, 'item': 'minecraft:snow', 'tiles': {}}
            ledger_state(ledger, 'test', 'minecraft:overworld')
            path.write_text(json.dumps(ledger))
            with self.assertRaises(RuntimeError):
                outbound(client, CANDIDATE, 'test', 'minecraft:overworld', path,
                         ledger, lambda: None, lambda candidate: True)
            self.assertEqual((2, 1), (client.guard_count, client.navigate_count))
            saved = json.loads(path.read_text())[LEDGER_KEY]
            self.assertEqual('outbound_uncertain', saved['active_route']['state'])

    def test_guard_reanchor_that_makes_actual_segment_over_320_never_navigates(self):
        class GuardMovesClient(Client):
            def request(self,op,**params):
                reply=super().request(op,**params)
                if op=='guard' and self.guard_count==1:self.pos[0]-=9
                return reply
        with tempfile.TemporaryDirectory() as directory:
            client=GuardMovesClient();path=Path(directory)/'resource.json'
            ledger={'schema':1,'item':'minecraft:snow','tiles':{}}
            ledger_state(ledger,'test','minecraft:overworld');path.write_text(json.dumps(ledger))
            far=dict(CANDIDATE,chunk=[58,0],tile=[928,0],
                     target=[936.5,200.0,8.5],distance_sq=936.0**2,
                     region_file='r.1.0.mca')
            with self.assertRaises(Unavailable):outbound(
                client,far,'test','minecraft:overworld',path,ledger,
                lambda:None,lambda row:True,lambda row:True)
            self.assertEqual(0,client.navigate_count)
            route=json.loads(path.read_text())[LEDGER_KEY]['active_route']
            self.assertEqual('outbound_uncertain',route['state'])
            self.assertNotIn('request_id',route['current_segment'])

    def test_persisted_segment_over_320_is_rejected_even_with_arrival_tolerance(self):
        with tempfile.TemporaryDirectory() as directory:
            client,path,ledger,_,_=self.route(directory)
            saved=json.loads(path.read_text());active=saved[LEDGER_KEY]['active_route']
            row=active['recent_segments'][-1]
            row['from']=[row['target'][0]-320.0001,row['from'][1],row['target'][2]]
            with self.assertRaises(RuntimeError):ledger_state(
                saved,'test','minecraft:overworld')

    def test_return_failure_is_not_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            client, path, ledger, _, route = self.route(directory)
            client.fail_navigate = client.navigate_count + 2
            mark_candidate(client, path, ledger, 'server_mismatch')
            with self.assertRaises(Unavailable):
                return_home(client, lambda: None, reason='server_mismatch')
            saved = json.loads(path.read_text())[LEDGER_KEY]
            self.assertEqual('return_uncertain', saved['active_route']['state'])
            before = len(client.actions)
            self.assertIsNone(return_home(client, lambda: None))
            self.assertEqual(before, len(client.actions))

    def test_route_beyond_old_81920_limit_is_lazy_and_ledger_stays_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Client();path=Path(directory)/'resource.json'
            ledger={'schema':1,'item':'minecraft:snow','tiles':{}}
            ledger_state(ledger,'test','minecraft:overworld');path.write_text(json.dumps(ledger))
            far=dict(CANDIDATE,chunk=[5200,0],tile=[83200,0],
                     target=[83208.5,200.0,8.5],distance_sq=83208.0**2,
                     region_file='r.162.0.mca')
            route=outbound(client,far,'test','minecraft:overworld',path,ledger,
                           lambda:None,lambda candidate:True,
                           lambda candidate:True)
            self.assertGreater(route['segment_count'],256)
            self.assertEqual(route['segment_count'],route['outbound_confirmed'])
            self.assertEqual(24,len(route['recent_segments']))
            self.assertNotIn('waypoints',route)
            self.assertLess(path.stat().st_size,32_000)

    def test_host_search_origin_is_the_only_fallback_when_saved_home_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Client()
            client.status=lambda original=client.status: {
                **original(), 'supervision_lease':{
                    **original()['supervision_lease'],
                    'return_target':{'x':float('nan'),'z':0,'cruise_y':160,
                        'dimension':'minecraft:the_nether','source':'saved_home'}}}
            path=Path(directory)/'resource.json';ledger={
                'schema':1,'item':'minecraft:snow','tiles':{}}
            ledger_state(ledger,'test','minecraft:overworld');path.write_text(json.dumps(ledger))
            route=outbound(client,CANDIDATE,'test','minecraft:overworld',path,ledger,
                           lambda:None,lambda candidate:True,lambda candidate:True)
            self.assertEqual(('search_origin',[0.5,145.0,0.5]),
                             (route['return_source'],route['return_target']))

    def test_tampered_persisted_home_or_derived_route_is_never_navigated(self):
        with tempfile.TemporaryDirectory() as directory:
            client,path,ledger,_,_=self.route(directory)
            saved=json.loads(path.read_text())
            active=saved[LEDGER_KEY]['active_route']
            active['return_target']=[500.5,160.0,500.5]
            path.write_text(json.dumps(saved));before=len(client.actions)
            with self.assertRaises(RuntimeError):return_home(client,lambda:None)
            self.assertEqual(before,len(client.actions))

    def test_exact_unmoved_first_air_only_rejection_can_be_archived_once(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Client(reject_unloaded_first=True)
            path=Path(directory)/'resource.json';ledger={
                'schema':1,'item':'minecraft:snow','tiles':{}}
            ledger_state(ledger,'test','minecraft:overworld');path.write_text(json.dumps(ledger))
            with self.assertRaises(Unavailable):
                outbound(client,CANDIDATE,'test','minecraft:overworld',path,ledger,
                         lambda:None,lambda candidate:True,lambda candidate:True)
            saved=json.loads(path.read_text());route=saved[LEDGER_KEY]['active_route']
            segment=route['current_segment']
            self.assertEqual((client.last,7,'error',UNLOADED_AIR_ONLY_REJECTION,
                              UNLOADED_AIR_ONLY_REJECTION,list(client.pos)),
                (segment['request_id'],segment['pre_dispatch_control_revision'],
                 segment['native_phase'],segment['native_detail'],segment['detail'],
                 segment['terminal_pos']))
            evidence=self.rejection_evidence(client,route)
            receipt=recover_unmoved_first_rejection(client,path,saved,evidence)
            self.assertEqual(('outbound_rejected_unmoved',False),
                             (receipt['state'],receipt['moved']))
            closed=json.loads(path.read_text())[LEDGER_KEY]
            self.assertIsNone(closed['active_route'])
            self.assertEqual('outbound_rejected_unmoved',closed['routes'][-1]['state'])

    def test_outbound_catches_exact_legacy_predispatch_rejection_before_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Client(reject_unloaded_first=True,auto_terminal_evidence=True)
            path=Path(directory)/'resource.json';ledger={
                'schema':1,'item':'minecraft:snow','tiles':{}}
            ledger_state(ledger,'test','minecraft:overworld');path.write_text(json.dumps(ledger))
            with self.assertRaises(Unavailable) as recovered:
                outbound(client,CANDIDATE,'test','minecraft:overworld',path,ledger,
                         lambda:None,lambda candidate:True,lambda candidate:True)
            self.assertEqual('route_rejected_unmoved',recovered.exception.code)
            saved=json.loads(path.read_text())[LEDGER_KEY]
            self.assertIsNone(saved['active_route'])
            self.assertEqual('outbound_rejected_unmoved',saved['routes'][-1]['state'])

    def test_recovery_never_clears_moved_or_generic_uncertain_route(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Client(fail_navigate=1)
            path=Path(directory)/'resource.json';ledger={
                'schema':1,'item':'minecraft:snow','tiles':{}}
            ledger_state(ledger,'test','minecraft:overworld');path.write_text(json.dumps(ledger))
            with self.assertRaises(Unavailable):
                outbound(client,CANDIDATE,'test','minecraft:overworld',path,ledger,
                         lambda:None,lambda candidate:True,lambda candidate:True)
            saved=json.loads(path.read_text());route=saved[LEDGER_KEY]['active_route']
            evidence=self.rejection_evidence(client,route)
            with self.assertRaises(RuntimeError):
                recover_unmoved_first_rejection(client,path,saved,evidence)
            self.assertIsNotNone(json.loads(path.read_text())[LEDGER_KEY]['active_route'])

    def test_recovery_rejects_every_request_scope_or_input_mismatch(self):
        mutations={
            'request':lambda row:row.update(request_id='wrong'),
            'task':lambda row:row.update(task_session='wrong'),
            'world':lambda row:row.update(world_session='other'),
            'server':lambda row:row.update(server='other.example'),
            'dimension':lambda row:row.update(dimension='minecraft:the_nether'),
            'target':lambda row:row['params'].update(target=[999.5,220,999.5]),
            'revision_before':lambda row:row.update(revision_before=8),
            'revision_after':lambda row:row.update(revision_after=8),
            'keys':lambda row:row['movement_keys'].update(forward=True),
            'velocity':lambda row:row.update(velocity=[.01,0,0]),
            'air_only':lambda row:row['params'].update(air_only=False),
        }
        for name,mutate in mutations.items():
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                client,path,saved,route,proof=self.rejected(directory)
                bad=copy.deepcopy(proof);mutate(bad)
                with self.assertRaises(RuntimeError):recover_unmoved_first_rejection(
                    client,path,saved,bad)
                self.assertIsNotNone(json.loads(path.read_text())[LEDGER_KEY]['active_route'])

    def test_legacy_binding_rejects_mismatched_revision_without_mutating_segment(self):
        with tempfile.TemporaryDirectory() as directory:
            client,path,saved,route,proof=self.rejected(directory)
            segment=route['current_segment']
            for field in ('request_id','pre_dispatch_control_revision','native_phase',
                          'native_detail','terminal_pos'):
                segment.pop(field,None)
            segment['detail']='legacy generic uncertainty'
            before=copy.deepcopy(segment);bad=copy.deepcopy(proof);bad['revision_after']=8
            self.assertFalse(_bind_legacy_unmoved_rejection(route,bad))
            self.assertEqual(before,segment)

    def test_parked_recovery_rejects_lease_snapshot_or_home_mismatch(self):
        mutations={
            'top_lease':lambda finish:finish.update(lease='wrong'),
            'top_job':lambda finish:finish.update(job_session='wrong'),
            'snapshot_id':lambda finish:finish['snapshot']['supervision_lease'].update(id='wrong'),
            'snapshot_job':lambda finish:finish['snapshot']['supervision_lease'].update(job_session='wrong'),
            'snapshot_world':lambda finish:finish['snapshot']['supervision_lease'].update(world_session='other'),
            'snapshot_kind':lambda finish:finish['snapshot']['supervision_lease'].update(kind='materials'),
            'snapshot_revision':lambda finish:finish['snapshot']['supervision_lease'].update(revision=8),
            'snapshot_home':lambda finish:finish['snapshot']['supervision_lease']['return_target'].update(x=999.5),
        }
        for name,mutate in mutations.items():
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                client,path,saved,route,proof,lease,finish=self.parked(directory)
                bad=copy.deepcopy(finish);mutate(bad)
                with self.assertRaises(RuntimeError):recover_parked_unmoved_first_rejection(
                    client,path,saved,proof,bad)
                self.assertIsNotNone(json.loads(path.read_text())[LEDGER_KEY]['active_route'])

    def test_legacy_unmoved_rejection_can_clear_after_exact_vertical_safe_park(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Client(reject_unloaded_first=True)
            path=Path(directory)/'resource.json';ledger={
                'schema':1,'item':'minecraft:snow','tiles':{}}
            ledger_state(ledger,'test','minecraft:overworld');path.write_text(json.dumps(ledger))
            with self.assertRaises(Unavailable):
                outbound(client,CANDIDATE,'test','minecraft:overworld',path,ledger,
                         lambda:None,lambda candidate:True,lambda candidate:True)
            saved=json.loads(path.read_text());route=saved[LEDGER_KEY]['active_route']
            evidence=self.rejection_evidence(client,route);terminal=list(client.pos)
            client.pos=[terminal[0],200.0,terminal[2]];client.rev=9
            client.phase='parking';client.detail='高空安全待命，防护持续'
            lease=client.status()['supervision_lease'];lease.update(
                kind='parking',id='lease-a',revision=9)
            original=client.status
            client.status=lambda:{**original(),'supervision_lease':lease}
            finish=self.parking_finish(client,route,lease)
            receipt=recover_parked_unmoved_first_rejection(
                client,path,saved,evidence,finish)
            self.assertEqual('outbound_rejected_unmoved',receipt['state'])
            self.assertIsNone(json.loads(path.read_text())[LEDGER_KEY]['active_route'])

    def test_parked_recovery_rejects_horizontal_finish_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Client(reject_unloaded_first=True)
            path=Path(directory)/'resource.json';ledger={
                'schema':1,'item':'minecraft:snow','tiles':{}}
            ledger_state(ledger,'test','minecraft:overworld');path.write_text(json.dumps(ledger))
            with self.assertRaises(Unavailable):
                outbound(client,CANDIDATE,'test','minecraft:overworld',path,ledger,
                         lambda:None,lambda candidate:True,lambda candidate:True)
            saved=json.loads(path.read_text());route=saved[LEDGER_KEY]['active_route']
            evidence=self.rejection_evidence(client,route);client.pos[0]+=1
            client.phase='parking';client.rev=9
            lease=client.status()['supervision_lease'];lease.update(
                kind='parking',id='lease-a',revision=9)
            original=client.status;client.status=lambda:{**original(),'supervision_lease':lease}
            finish=self.parking_finish(client,route,lease)
            with self.assertRaises(RuntimeError):recover_parked_unmoved_first_rejection(
                client,path,saved,evidence,finish)
            self.assertIsNotNone(json.loads(path.read_text())[LEDGER_KEY]['active_route'])

    def test_durable_files_drive_one_exact_post_finish_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Client(reject_unloaded_first=True)
            path=Path(directory)/'resource.json';ledger={
                'schema':1,'item':'minecraft:snow','tiles':{}}
            ledger_state(ledger,'test','minecraft:overworld');path.write_text(json.dumps(ledger))
            with self.assertRaises(Unavailable):
                outbound(client,CANDIDATE,'test','minecraft:overworld',path,ledger,
                         lambda:None,lambda candidate:True,lambda candidate:True)
            route=json.loads(path.read_text())[LEDGER_KEY]['active_route']
            proof=self.rejection_evidence(client,route);terminal=list(client.pos)
            client.pos=[terminal[0],200.0,terminal[2]];client.rev=9
            client.phase='parking';lease=client.status()['supervision_lease']
            lease.update(kind='parking',id='lease-a',revision=9)
            original=client.status;client.status=lambda:{**original(),'supervision_lease':lease}
            current=client.status();request_id=proof['request_id']
            movement=Path(directory)/f'movement-failure-{request_id}.json'
            movement.write_text(json.dumps({'op':'navigate','params':proof['params'],
                'detail':proof['detail'],'terminal_pos':terminal,
                'last_inflight':[{'pos':terminal,'movement_keys':proof['movement_keys'],
                                  'velocity':proof['velocity']}]}))
            events=Path(directory)/'events.jsonl';events.write_text(json.dumps({
                'request_id':request_id,'world_session':client.world,'op':'navigate',
                'params':proof['params'],'phase':'error','detail':proof['detail'],
                'position_before':terminal,'position_after':terminal,
                'revision_before':7,'revision_after':7})+'\n')
            finish=self.parking_finish(client,route,lease)
            finish_path=Path(directory)/'stock-safety.json';finish_path.write_text(json.dumps(finish))
            result=recover_parked_rejection_files(
                client,path,movement,events,finish_path)
            self.assertEqual('outbound_rejected_unmoved',result['state'])
            self.assertIsNone(json.loads(path.read_text())[LEDGER_KEY]['active_route'])

    def test_production_hold_gate_auto_recovers_exact_parked_legacy_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);automation=base/'config/twob2tkit/automation'
            automation.mkdir(parents=True);client=Client(reject_unloaded_first=True)
            client.root=automation
            profile={'server':'test:25565','dimension':'minecraft:overworld',
                     'resource_regions':[]}
            resource=_resource_ledger_scope_path(
                automation.parent/'material-resource-ledger',profile['server'],
                profile['dimension'],'minecraft:snow')
            ledger={'schema':1,'item':'minecraft:snow','tiles':{}}
            ledger_state(ledger,'test','minecraft:overworld');resource.parent.mkdir()
            resource.write_text(json.dumps(ledger))
            legacy_candidate=dict(CANDIDATE,chunk=[118,0],tile=[1888,0],
                target=[1896.5,200.0,8.5],region_file='r.3.0.mca',
                distance_sq=1896.0**2)
            with self.assertRaises(Unavailable):outbound(
                client,legacy_candidate,'test','minecraft:overworld',resource,ledger,
                lambda:None,lambda row:True,lambda row:True)
            stored=json.loads(resource.read_text());route=stored[LEDGER_KEY]['active_route']
            new_count=route['segment_count'];route.pop('planning_step')
            old_count=math.ceil(math.hypot(
                route['target'][0]-route['origin'][0],
                route['target'][2]-route['origin'][2])/320.0)
            self.assertNotEqual(new_count,old_count)
            route['segment_count']=old_count
            route['return_segment_count']=old_count+1
            ratio=1/old_count
            route['current_segment']['target']=[
                route['origin'][0]+(route['target'][0]-route['origin'][0])*ratio,
                route['target'][1],
                route['origin'][2]+(route['target'][2]-route['origin'][2])*ratio]
            proof=self.rejection_evidence(client,route);terminal=list(client.pos)
            segment=route['current_segment']
            for field in ('request_id','pre_dispatch_control_revision','native_phase',
                          'native_detail','terminal_pos'):
                segment.pop(field,None)
            segment['detail']='Bobby 雪地分段巡航回执不确定；不重放该段'
            resource.write_text(json.dumps(stored))
            client.pos=[terminal[0],200.0,terminal[2]];client.rev=9;client.phase='parking'
            lease=client.status()['supervision_lease'];lease.update(
                kind='parking',id='lease-a',revision=9)
            original=client.status;client.status=lambda:{**original(),'supervision_lease':lease}
            current=client.status();jobs=automation/'material-jobs'
            old_job=jobs/'material-job-old';job=jobs/'material-job-new'
            control=old_job/'control-001'
            control.mkdir(parents=True);(job/'acquisition').mkdir(parents=True)
            (control/f"run-manifest-{route['task_session']}.json").write_text(json.dumps({
                'task_session':route['task_session'],'world_session':route['world_session'],
                'dimension':'minecraft:overworld'}))
            request_id=proof['request_id'];params=proof['params']
            (control/f'movement-failure-{request_id}.json').write_text(json.dumps({
                'op':'navigate','params':params,'detail':proof['detail'],
                'terminal_pos':terminal,'last_inflight':[{'pos':terminal,
                    'movement_keys':proof['movement_keys'],'velocity':[0,0,0]}]}))
            (control/'events.jsonl').write_text(json.dumps({
                'request_id':request_id,'world_session':route['world_session'],
                'op':'navigate','params':params,'phase':'error','detail':proof['detail'],
                'position_before':terminal,'position_after':terminal,
                'revision_before':7,'revision_after':7})+'\n')
            (control/'stock-safety.json').write_text(json.dumps(
                self.parking_finish(client,route,lease)))
            held=held_resource_route(automation,route['world_session'],'minecraft:snow',
                                     profile,job/'acquisition',current=current)
            self.assertIsNone(held)
            self.assertIsNone(json.loads(resource.read_text())[LEDGER_KEY]['active_route'])
            self.assertTrue((job/'bobby-route-auto-recovery.json').is_file())

        with tempfile.TemporaryDirectory() as directory:
            client,path,ledger,_,_=self.route(directory)
            saved=json.loads(path.read_text())
            saved[LEDGER_KEY]['active_route']['target'][0]+=16
            path.write_text(json.dumps(saved));before=len(client.actions)
            with self.assertRaises(RuntimeError):return_home(client,lambda:None)
            self.assertEqual(before,len(client.actions))


if __name__ == '__main__':
    unittest.main()
