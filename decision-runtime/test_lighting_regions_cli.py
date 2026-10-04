"""Fixed registry/ownership/uncertainty tests; no actual game or model calls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lighting_regions_cli import RegionsWorker, RegionsPaused, NativeBatch, validate_profile


def profile():
    return {'schema': 1, 'authorized': True, 'server': 'example.invalid:25565',
            'dimension': 'minecraft:overworld', 'batch_torches': 8, 'max_batches_per_region': 2,
            'movement_bounds': {'min': [-10, 60, -10], 'max': [40, 100, 40]},
            'protected': [{'min': [3, 64, 3], 'max': [4, 80, 4]}],
            'regions': [{'name': 'field', 'min': [0, 60, 0], 'max': [4, 90, 4]},
                        {'name': 'beach', 'min': [10, 60, 0], 'max': [14, 90, 4]}]}


def state():
    return {'connected': True, 'server': 'example.invalid', 'dimension': 'minecraft:overworld',
            'world_session': 'world-a', 'manual_movement': False, 'health': 20, 'food': 20,
            'under_water': False, 'guard_armed': True, 'guard_pve_only': True, 'flight': True,
            'control_revision': 7, 'screen': '', 'supervision_lease': {}, 'pos': [1.5, 88, 1.5],
            'inventory': [{'slot': i, 'item': 'minecraft:torch' if i == 0 else 'minecraft:air',
                           'count': 8 if i == 0 else 0} for i in range(36)]}


class Batch:
    def __init__(self, current, *, risk=0):
        self.current, self.calls, self.risk = current, [], risk
    def __call__(self, region, directory, *, audit):
        self.calls.append((region['name'], audit, directory))
        self.current['control_revision'] += 1
        lease = 'owned-parking-' + str(self.current['control_revision'])
        self.current['supervision_lease'] = {'kind': 'parking', 'id': lease}
        return {'park_native_confirmed': True, 'parking_lease': lease,
                'control_revision': self.current['control_revision'], 'placed_verified': 2,
                'eligible_remaining': 0, 'unprotected_dark_floor': self.risk, 'observed_at': 123}


class RegionsTest(unittest.TestCase):
    def test_profile_requires_explicit_scope_budgets_and_unique_regions(self):
        self.assertEqual(validate_profile(profile())['server'], 'example.invalid')
        for change in ({'authorized': False}, {'dimension': 'minecraft:the_nether'},
                       {'batch_torches': True}, {'max_batches_per_region': 0}, {'regions': []}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_profile({**profile(), **change})
        bad = profile(); bad['regions'].append(deepcopy(bad['regions'][0]))
        with self.assertRaises(ValueError): validate_profile(bad)

    def test_registry_prevents_new_output_or_profile_bypass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = RegionsWorker(root, profile(), root/'original', observer=state)
            first.book['pending'] = {'stage': 'unknown'}; first.save()
            with self.assertRaisesRegex(ValueError, 'Changing output'):
                RegionsWorker(root, profile(), root/'different', observer=state)
            changed = profile(); changed['regions'][0]['min'][0] = 1
            with self.assertRaisesRegex(ValueError, 'different lighting profile'):
                RegionsWorker(root, changed, observer=state)
            same = RegionsWorker(root, profile(), observer=state)
            self.assertEqual(same.out, first.out)
            with self.assertRaisesRegex(RegionsPaused, 'pending batch'): same.run(resume=True)

    def test_real_file_lock_blocks_concurrent_workers(self):
        with tempfile.TemporaryDirectory() as folder:
            first = RegionsWorker(folder, profile(), observer=state)
            second = RegionsWorker(folder, profile(), observer=state)
            with first.worker_lock():
                self.assertTrue(second.status()['worker_running'])
                with self.assertRaisesRegex(RegionsPaused, 'active'): second.run()
            self.assertFalse(second.status()['worker_running'])

    def test_queue_requires_separate_current_audit_and_never_claims_island_goal(self):
        with tempfile.TemporaryDirectory() as folder:
            current = state(); batch = Batch(current, risk=1)
            worker = RegionsWorker(folder, profile(), observer=lambda: current, batch=batch)
            result = worker.run()
            self.assertEqual([(name, audit) for name, audit, _ in batch.calls],
                             [('field', False), ('beach', False), ('field', True), ('beach', True)])
            self.assertEqual(result['phase'], 'audited_with_remaining_risk')
            self.assertTrue(result['coverage_complete'])
            self.assertFalse(result['ordinary_zombie_light_clear'])
            self.assertFalse(result['goal_complete'])
            self.assertIsNone(result['pending'])
            self.assertFalse(result['worker_running'])
            self.assertEqual(result['ai_calls'], 0)
            again = worker.run(audit_only=True)
            self.assertEqual(again['phase'], 'audited_with_remaining_risk')
            self.assertEqual(again['dispatch_sequence'], 6)

    def test_interruption_keeps_pending_and_resume_cannot_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = []
            def uncertain(region, directory, *, audit):
                calls.append(region['name']); raise RuntimeError('Torch outcome unknown')
            worker = RegionsWorker(folder, profile(), observer=state, batch=uncertain)
            result = worker.run()
            self.assertEqual(result['phase'], 'waiting')
            original = deepcopy(result['pending'])
            self.assertIsNotNone(original)
            with self.assertRaisesRegex(RegionsPaused, 'pending batch'): worker.run(resume=True)
            self.assertEqual(calls, ['field'])
            self.assertEqual(worker.book['pending'], original)

    def test_unproven_park_keeps_batch_and_does_not_advance(self):
        with tempfile.TemporaryDirectory() as folder:
            current = state(); batch = Batch(current)
            def unproven(*args, **kwargs): return {**batch(*args, **kwargs), 'park_native_confirmed': False}
            worker = RegionsWorker(folder, profile(), observer=lambda: current, batch=unproven)
            result = worker.run()
            self.assertEqual(result['phase'], 'waiting')
            self.assertEqual(result['cursor'], 0)
            self.assertEqual(result['batches'], [])
            self.assertIsNotNone(result['pending'])

    def test_manual_health_native_lease_foreign_revision_stop_before_control(self):
        for change in ({'manual_movement': True}, {'health': 19}, {'connected': False},
                       {'safety_hold': {'active': True}}, {'borer_active': True},
                       {'supervision_lease': {'kind': 'materials', 'id': 'foreign'}}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                current = {**state(), **change}
                worker = RegionsWorker(folder, profile(), observer=lambda: current, batch=Batch(current))
                with self.assertRaises(RuntimeError): worker.run()
                self.assertIsNone(worker.book['pending'])
        with tempfile.TemporaryDirectory() as folder:
            worker = RegionsWorker(folder, profile(), observer=state)
            worker.book['last_revision'] = 6
            with self.assertRaisesRegex(RegionsPaused, 'controller'): worker.gate(state())

    def test_async_stop_is_recorded_without_game_rpc(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = RegionsWorker(folder, profile(), observer=state)
            command = worker.command('stop')
            with self.assertRaisesRegex(RegionsPaused, 'Requested stop'): worker.gate(state())
            self.assertEqual(worker.book['last_control'], command['id'])
            self.assertIsNone(worker.book['pending'])

    def test_status_does_not_replace_current_journal(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = RegionsWorker(folder, profile(), observer=state)
            current = deepcopy(worker.book); current['pending'] = {'stage': 'external_latest'}
            worker.path.write_text(json.dumps(current))
            reopened = RegionsWorker(folder, profile(), observer=state)
            self.assertEqual(reopened.book['pending'], current['pending'])
            self.assertEqual(json.loads(worker.path.read_text()), current)

    def test_explicit_resume_consumes_prior_pause_but_respects_later_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            current = state(); batch = Batch(current)
            worker = RegionsWorker(folder, profile(), observer=lambda: current, batch=batch)
            prior = worker.command('pause')
            result = worker.run(resume=True)
            self.assertEqual(result['phase'], 'audited')
            self.assertEqual(result['last_control'], prior['id'])
        with tempfile.TemporaryDirectory() as folder:
            current = state(); batch = Batch(current)
            worker = RegionsWorker(folder, profile(), observer=lambda: current, batch=batch)
            worker.command('pause')
            observed = []
            def observer():
                if not observed:
                    observed.append(worker.command('stop'))
                return current
            worker.observer = observer
            with self.assertRaisesRegex(RegionsPaused, 'Requested stop'):
                worker.run(resume=True)
            self.assertEqual(batch.calls, [])
            self.assertIsNone(worker.book['pending'])

    def test_no_torch_supply_waits_without_creating_uncertain_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            current = state(); current['inventory'][0]['count'] = 0
            batch = Batch(current)
            worker = RegionsWorker(folder, profile(), observer=lambda: current, batch=batch)
            result = worker.run()
            self.assertEqual(result['phase'], 'waiting_materials')
            self.assertIsNone(result['pending'])
            self.assertEqual(batch.calls, [])
            current['inventory'][0]['count'] = 8
            result = worker.run(resume=True)
            self.assertEqual(result['phase'], 'audited')

    def test_explicit_new_run_rechecks_regions_without_erasing_old_batches(self):
        with tempfile.TemporaryDirectory() as folder:
            current = state(); batch = Batch(current)
            worker = RegionsWorker(folder, profile(), observer=lambda: current, batch=batch)
            first = worker.run()
            second = worker.run()
            self.assertEqual((first['campaign'], second['campaign']), (1, 2))
            self.assertEqual(len(second['batches']), 4)
            self.assertEqual([entry['campaign'] for entry in second['batches']], [1, 1, 2, 2])

    def test_kit_cli_uses_same_explicit_profile_without_ui(self):
        from kit_cli import main
        with patch('lighting_regions_cli.main', return_value=0) as handler:
            self.assertEqual(main(['--game-dir', '/tmp/game', 'lighting', 'status',
                                   '--profile', '/tmp/profile.json']), 0)
            self.assertEqual(handler.call_args.args[0], ['--game-dir', '/tmp/game',
                             '--profile', '/tmp/profile.json', 'status'])

    def test_unknown_wait_keeps_heartbeat_and_lock_without_new_actions(self):
        with tempfile.TemporaryDirectory() as folder:
            owner = RegionsWorker(folder, profile(), observer=state)
            owner.book['pending'] = {'stage': 'unknown', 'original': 'request-a'}
            same = {**state(), 'phase': 'running', 'navigating': True, 'guard_busy': True,
                    'supervision_lease': {'id': 'lease-a', 'job_session': 'task-a'}, 'last_request': 'request-a'}
            manual = {**same, 'manual_movement': True}
            class Client:
                world, task = 'world-a', 'task-a'
                heartbeat = type('Beat', (), {'id': 'lease-a', 'close': lambda self: None})()
                def __init__(self): self.calls = 0
                def raw(self):
                    self.calls += 1
                    return same if self.calls < 3 else manual
                def _record_health_stop(self, reason): pass
                def park_near(self, s): return False
                def finish(self): raise AssertionError('Must not finish uncertain work')
                def _owned_guarded_finish_state(self, s, kind): return False
            client = Client()
            with owner.worker_lock(), patch('lighting_regions_cli.time.sleep'):
                NativeBatch(owner).wait_unresolved(client)
            self.assertEqual(client.calls, 3)
            self.assertEqual(owner.book['pending']['original'], 'request-a')
            self.assertEqual(owner.book['pending']['handoff'], 'world_manual_or_lease_changed')

    def test_late_verified_parking_is_read_only_and_does_not_clear_unknown_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            owner = RegionsWorker(folder, profile(), observer=state)
            owner.book['pending'] = {'stage': 'unknown', 'original': 'request-a'}
            parked = {**state(), 'phase': 'stopped', 'supervision_lease': {'id': 'lease-a', 'job_session': 'task-a'},
                      'supervision_safety': {'lease': 'lease-a', 'job_session': 'task-a', 'action': 'KEEP_PVE_GUARD'}}
            class Client:
                world, task = 'world-a', 'task-a'
                heartbeat = type('Beat', (), {'id': 'lease-a', 'close': lambda self: None})()
                def raw(self): return parked
                def park_near(self, s): return True
                def _owned_guarded_finish_state(self, s, kind): return kind == 'parking'
                def finish(self): raise AssertionError('Late parking must not replay finish')
            NativeBatch(owner).wait_unresolved(Client())
            self.assertEqual(owner.book['pending']['original'], 'request-a')
            self.assertEqual(owner.book['pending']['handoff'], 'late_owned_native_parking_observed_read_only')


class OpeningReconciliationTest(unittest.TestCase):
    def fixture(self,folder):
        import time
        current=state();current.update(time=int(time.time()*1000),phase='parking',control_revision=9,last_request='current-scan',pos=[11.5,88,1.5],
            material_task={'occupied':False,'process_alive':False,'cancelling':False},
            supervision_lease={'kind':'parking','id':'parking-current','job_session':'task-current','world_session':'world-a',
                               'revision':9,'remote_finish':'guard'})
        worker=RegionsWorker(folder,profile(),observer=lambda:current)
        directory=worker.out/'batch-'/'00007';(directory/'opening-survey').mkdir(parents=True)
        worker.book.update(world_session='world-a',cursor=1,dispatch_sequence=7,phase='waiting',
            pending={'region_index':1,'mode':'lighting','directory':str(directory),'stage':'before_native_control',
                     'error':'LightingBlocked: Complete loaded detailed scan unavailable','uncertain_request':None})
        worker.book['batches']=[{'region_index':0,'placed_verified':3}];worker.save()
        detail='scan stopped; partial records retained: Server chunk is not loaded: 12 2'
        event={'request_id':'original-scan','world_session':'world-a','op':'scan','phase':'waiting','detail':detail,
            'params':{'min':[12,-64,2],'max':[12,319,2],'details':True},'revision_before':7,'revision_after':7,
            'position_before':[1.5,88,1.5],'position_after':[1.5,88,1.5],'inventory_delta':{},'health_before':20,'health_after':20}
        event_path=directory/'opening-survey/events.jsonl';event_path.write_text(json.dumps(event)+'\n')
        reply={'id':'original-scan','world_session':'world-a','phase':'waiting','detail':detail,'control_revision':7,
            'scan_start_revision':7,'scan_end_revision':7,'scan_cells_read':0,'scan_total_cells':384,'scan_coherent':False,
            'blocks':[],'pending_scan':{'id':'original-scan','world_session':'world-a','control_revision':7,
                'cells_read':0,'total_cells':384,'reading_complete':False}}
        reply_path=worker.root/'reply-original-scan.json';reply_path.write_text(json.dumps(reply,indent=2)+'\n')
        (worker.root/'request.json').write_text('{"id":"current-scan","op":"scan"}')
        return worker,current,directory,event_path,reply_path

    def test_original_unloaded_scan_stays_incomplete_without_cursor_or_torch_change(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            worker,current,directory,events,reply=self.fixture(folder)
            before=deepcopy(worker.book);raw_book=worker.path.read_bytes();raw_events=events.read_bytes();raw_reply=reply.read_bytes()
            result=worker.reconcile_opening();record=result['pending_reconciliations'][-1]
            self.assertIsNone(result['pending']);self.assertEqual(1,result['cursor'])
            self.assertEqual(before['batches'],result['batches']);self.assertEqual(before['campaign'],result['campaign'])
            self.assertEqual(before['dispatch_sequence'],result['dispatch_sequence']);self.assertFalse(record['original_scan_completed'])
            self.assertFalse(record['region_completed']);self.assertFalse(record['request_replayed'])
            self.assertEqual(before['pending'],record['original_pending'])
            for name,data in [('original-regions.json',raw_book),('original-events.jsonl',raw_events),('original-reply.json',raw_reply)]:
                self.assertEqual(data,(Path(record['archive'])/name).read_bytes())
                self.assertEqual(hashlib.sha256(data).hexdigest(),record['evidence_sha256'][name])
            self.assertEqual(raw_events,events.read_bytes());self.assertEqual(raw_reply,reply.read_bytes())
            self.assertEqual(8,current['inventory'][0]['count'])

    def test_mutation_unknown_receipt_loading_progress_and_identity_are_refused(self):
        for case in ('mutating_op','inventory_delta','revision','world','reply_id','reply_world','reply_done','cells_read',
                     'reply_reading_complete','cells_bool','manifest','placement','inflight','extra_event','uncertain','task','lease','native_request','cursor'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as folder:
                worker,current,directory,events,reply=self.fixture(folder)
                event=json.loads(events.read_text());native=json.loads(reply.read_text())
                if case=='mutating_op':event['op']='interact'
                elif case=='inventory_delta':event['inventory_delta']={'minecraft:torch':-1}
                elif case=='revision':event['revision_after']=8
                elif case=='world':event['world_session']='world-b'
                elif case=='reply_id':native['id']='foreign-scan'
                elif case=='reply_world':native['world_session']='world-b'
                elif case=='reply_done':native['phase']='done'
                elif case=='cells_read':native['scan_cells_read']=1
                elif case=='cells_bool':native['scan_cells_read']=False
                elif case=='reply_reading_complete':native['pending_scan']['reading_complete']=True
                elif case in ('manifest','placement','inflight'):(directory/({'manifest':'run-manifest-native.json','placement':'report.json','inflight':'inflight.json'}[case])).write_text('{}')
                elif case=='uncertain':worker.book['pending']['uncertain_request']={'op':'interact'}
                elif case in ('task','lease','native_request'):worker.book['pending'][{'task':'task_session','lease':'lease','native_request':'native_request'}[case]]='original-native'
                elif case=='cursor':worker.book['cursor']=0
                events.write_text(json.dumps(event)+'\n'+(json.dumps(event)+'\n' if case=='extra_event' else ''))
                reply.write_text(json.dumps(native));worker.save();before=worker.path.read_bytes()
                with self.assertRaises(RegionsPaused):worker.reconcile_opening()
                self.assertEqual(before,worker.path.read_bytes())
                self.assertIsNotNone(worker.book['pending'])

    def test_fresh_guard_world_worker_and_human_control_are_required(self):
        for case in ('world','manual','health','outside','stale','guard','native_task','process','occupied','mailbox','hold','human_stop','active_scan','running'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as folder:
                worker,current,directory,events,reply=self.fixture(folder)
                if case=='world':current['world_session']='world-b'
                elif case=='manual':current['manual_movement']=True
                elif case=='health':current['health']=19
                elif case=='outside':current['pos']=[-100,88,1.5]
                elif case=='stale':current['time']-=10000
                elif case=='guard':current['guard_pve_only']=False
                elif case=='native_task':current['native_task_session']='active-material'
                elif case=='process':current['material_task']['process_alive']=True
                elif case=='occupied':current['material_task']['occupied']=True
                elif case=='mailbox':(worker.root/'request.json').write_text('{"id":"inflight-interact"}')
                elif case=='hold':(worker.root/'safety-hold.json').write_text('{"active":true}')
                elif case=='active_scan':current['pending_scan']={'id':'unsettled-read'}
                elif case=='running':current['phase']='running'
                else:worker.command('stop')
                before=worker.path.read_bytes()
                with self.assertRaises(RuntimeError):worker.reconcile_opening()
                self.assertEqual(before,worker.path.read_bytes());self.assertIsNotNone(worker.book['pending'])

    def test_active_worker_lock_and_changed_original_file_prevent_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            first,*_=self.fixture(folder);second=RegionsWorker(folder,profile(),observer=first.observer)
            before=first.path.read_bytes()
            with first.worker_lock(),self.assertRaisesRegex(RegionsPaused,'active'):second.reconcile_opening()
            self.assertEqual(before,first.path.read_bytes())
            changed=deepcopy(first.book);changed['cursor']=0;first.path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(RegionsPaused,'journal changed'):first.reconcile_opening()
            self.assertEqual(changed,json.loads(first.path.read_text()))

    def test_cli_reconcile_opening_uses_registered_journal_without_game_actions(self):
        from lighting_regions_cli import main
        with tempfile.TemporaryDirectory() as folder:
            worker,*_=self.fixture(folder);profile_path=Path(folder)/'profile.json';profile_path.write_text(json.dumps(profile()))
            with patch('builtins.print'):
                with patch('lighting_regions_cli.RegionsWorker',return_value=worker):
                    self.assertEqual(0,main(['--game-dir',folder,'--profile',str(profile_path),'reconcile-opening']))


class NetworkReconciliationTest(unittest.TestCase):
    def fixture(self,folder,partial=False):
        import time,hashlib
        from test_lighting_cli import inventory
        from potato_farm import ENTITY_SCOPE_AT_SCAN_END
        root=Path(folder)/'game/config/twob2tkit/automation'
        current=state();current.update(time=int(time.time()*1000),world_session='world-b',phase='parking',
            control_revision=9,last_request='current-scan',inventory=inventory(7 if partial else 8),
            material_task={'occupied':False,'process_alive':False,'cancelling':False},
            supervision_lease={'kind':'parking','id':'new-lease','job_session':'new-task','world_session':'world-b','revision':9,'remote_finish':'guard'})
        worker=RegionsWorker(root,profile(),observer=lambda:current)
        directory=worker.out/'batch-'/'00007';(directory/'opening-survey').mkdir(parents=True)
        native={'request_id':'old-nav','op':'navigate','world_session':'world-a','task_session':'old-task','lease_id':'old-lease','base_revision':7,'expected_revision':8}
        worker.book.update(world_session='world-a',cursor=1,dispatch_sequence=7,phase='waiting',pending={
            'region_index':1,'mode':'lighting','directory':str(directory),'stage':'lighting' if partial else 'travel',
            'world_session':'world-a','task_session':'old-task','lease':'old-lease','native_request':native,
            'uncertain_request':deepcopy(native),'handoff':'world_manual_or_lease_changed'})
        worker.save()
        def write(path,value):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        request={'id':'old-nav','op':'navigate','air_only':True,'server':'example.invalid','dimension':'minecraft:overworld',
            'site':[1.5,88,1.5],'target':[2.5,88,1.5],'world_session':'world-a','task_session':'old-task','expected_revision':7}
        write(directory/'network-navigation-request.json',request)
        baseline={**state(),'id':'opening-scan','phase':'done','inventory':inventory(8),'scan_cells_read':384,'scan_total_cells':384}
        write(directory/'arrival-height-plan.json',{'actual_column':baseline})
        write(directory/'run-manifest-old-task.json',{'task_session':'old-task','world_session':'world-a','dimension':'minecraft:overworld',
            'server_hash':hashlib.sha256(b'example.invalid').hexdigest()[:16],'complete':False})
        event={'request_id':'session-request','op':'material_session','phase':'done','world_session':'world-a',
            'params':{'task_session':'old-task','supervision_lease':'old-lease'},'revision_before':7,'revision_after':7,
            'health_before':20,'health_after':20,'inventory_delta':{}}
        events=[event]
        (directory/'opening-survey/events.jsonl').write_text(json.dumps({'request_id':'opening-scan','op':'scan','phase':'done',
            'world_session':'world-a','params':{'min':[12,-64,2],'max':[12,319,2],'details':True},'inventory_delta':{}})+'\n')
        (root/'lighting-intents').mkdir(exist_ok=True)
        if partial:
            owned={'id':'old-lease','job_session':'old-task','world_session':'world-a'}
            placed={'world_session':'world-a','task_session':'old-task','support':[12,63,2],'target':[12,64,2],'state':'verified',
                'before_stock':8,'after_stock':7,'before_time':1000,'after_time':1002,'interaction_request':'old-interact','later_verified_frames':2}
            write(directory/'report.json',{'world_session':'world-a','task_session':'old-task','placed':[placed]})
            write(directory/'inventory-before-0.json',{'world_session':'world-a','time':1000,'inventory':inventory(8),'supervision_lease':owned})
            write(directory/'interaction-0.json',{'id':'old-interact','world_session':'world-a','phase':'done','supervision_lease':owned})
            for frame in (1,2):
                write(directory/f'actual-torch-0-frame-{frame}.json',{'world_session':'world-a','phase':'done',
                    'blocks':[{'pos':[12,64,2],'state':'Block{minecraft:torch}'}],'scan_entities':[],'scan_entity_scope':ENTITY_SCOPE_AT_SCAN_END})
                write(directory/f'inventory-after-0-frame-{frame}.json',{'world_session':'world-a','time':1000+frame,
                    'inventory':inventory(7),'supervision_lease':owned})
            key=hashlib.sha256(b'world-a:12,64,2').hexdigest();write(root/'lighting-intents'/(key+'.json'),placed)
            events.append({**event,'request_id':'old-interact','op':'interact','params':{'task_session':'old-task','pos':[12,63,2],'face':'up','expected_state':'Block{minecraft:sand}','expected_hand':'minecraft:torch'},
                           'inventory_delta':{'minecraft:torch':-1}})
        (directory/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        network={'reason':'连接超时','request_id':'old-nav','world_session':'world-a','task_session':'old-task','health_exit':False,
            'last_disconnect_log':'[00:08:22] [Render thread/WARN]: Client disconnected with reason: 连接超时','last_owned_health':20,
            'original_request_sha256':hashlib.sha256((directory/'network-navigation-request.json').read_bytes()).hexdigest(),
            'worker_exit_code':2,'worker_process_alive':False}
        network_path=worker.out/'network-disconnect-evidence-old-nav.json';write(network_path,network)
        write(root/'request.json',{'id':'current-scan','op':'scan'})
        return worker,current,directory,network_path,write

    def test_unknown_network_navigation_is_archived_without_completion_cursor_or_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            worker,current,directory,network,write=self.fixture(folder)
            before=deepcopy(worker.book);original={p:p.read_bytes() for p in directory.rglob('*') if p.is_file()}
            result=worker.reconcile_network_travel(process_probe=lambda:False);record=result['pending_reconciliations'][-1]
            self.assertEqual('previous_network_navigation_unknown',record['outcome']);self.assertFalse(record['navigation_completed'])
            self.assertFalse(record['request_replayed']);self.assertEqual('missing',record['original_reply'])
            self.assertEqual(before['cursor'],result['cursor']);self.assertEqual(before['batches'],result['batches'])
            self.assertEqual(before['pending'],record['original_pending']);self.assertEqual('world-a',result['world_session'])
            self.assertIsNone(result['pending']);self.assertEqual(8,current['inventory'][0]['count'])
            for p,data in original.items():
                self.assertEqual(data,p.read_bytes());self.assertEqual(data,(Path(record['archive'])/p.relative_to(directory)).read_bytes())

    def test_verified_partial_counts_once_with_exact_receipt_intent_and_two_frames(self):
        with tempfile.TemporaryDirectory() as folder:
            worker,current,directory,network,write=self.fixture(folder,partial=True)
            result=worker.reconcile_network_travel(process_probe=lambda:False)
            self.assertEqual(1,result['batches'][-1]['placed_verified']);self.assertFalse(result['batches'][-1]['region_completed'])
            self.assertEqual(1,result['cursor']);self.assertEqual(7,current['inventory'][0]['count'])
            with self.assertRaises(RegionsPaused):worker.reconcile_network_travel(process_probe=lambda:False)
            self.assertEqual(1,len(worker.book['batches']))

    def test_original_unknown_mutation_wrong_scope_health_exit_or_incomplete_inventory_blocks(self):
        cases=('request_world','air_only','manifest','lease','mine','craft','interact','opening_mutation','health','health_logout',
               'reply_done','inflight','baseline_inventory','current_inventory','same_world','current_action','process_alive','unknown_intent')
        for case in cases:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as folder:
                worker,current,directory,network,write=self.fixture(folder)
                if case in ('request_world','air_only'):
                    p=directory/'network-navigation-request.json';v=json.loads(p.read_text());v['world_session' if case=='request_world' else 'air_only']='world-x' if case=='request_world' else False;write(p,v)
                elif case=='manifest':
                    p=directory/'run-manifest-old-task.json';v=json.loads(p.read_text());v['task_session']='foreign';write(p,v)
                elif case=='lease':worker.book['pending']['lease']='foreign-lease';worker.save()
                elif case in ('mine','craft','interact','health'):
                    p=directory/'events.jsonl';v=json.loads(p.read_text());v['op']=case if case!='health' else 'material_session';v['health_after']=13 if case=='health' else 20;p.write_text(json.dumps(v)+'\n')
                elif case=='opening_mutation':
                    p=directory/'opening-survey/events.jsonl';v=json.loads(p.read_text());v['op']='interact';p.write_text(json.dumps(v)+'\n')
                elif case=='health_logout':v=json.loads(network.read_text());v['health_exit']=True;write(network,v)
                elif case=='reply_done':write(worker.root/'reply-old-nav.json',{'id':'old-nav','world_session':'world-a','phase':'done'})
                elif case=='inflight':write(directory/'inflight.json',{})
                elif case=='baseline_inventory':
                    p=directory/'arrival-height-plan.json';v=json.loads(p.read_text());v['actual_column']['inventory'].pop();write(p,v)
                elif case=='current_inventory':current['inventory'].pop()
                elif case=='same_world':current['world_session']='world-a';current['supervision_lease']['world_session']='world-a'
                elif case=='current_action':current['pending_scan']={'id':'inflight-read'}
                elif case=='unknown_intent':write(worker.root/'lighting-intents/unknown.json',{'world_session':'world-a','task_session':'old-task','state':'intent'})
                before=worker.path.read_bytes()
                with self.assertRaises(RuntimeError):worker.reconcile_network_travel(process_probe=lambda:case=='process_alive')
                self.assertEqual(before,worker.path.read_bytes());self.assertIsNotNone(worker.book['pending'])

    def test_missing_receipt_frame_or_unverified_partial_never_counts(self):
        for case in ('receipt','frame','intent','interaction_mismatch','other_delta','receipt_world'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as folder:
                worker,current,directory,network,write=self.fixture(folder,partial=True)
                if case=='receipt':(directory/'interaction-0.json').unlink()
                elif case=='frame':(directory/'actual-torch-0-frame-2.json').unlink()
                elif case=='intent':
                    p=next((worker.root/'lighting-intents').glob('*.json'));v=json.loads(p.read_text());v['state']='intent';write(p,v)
                elif case=='receipt_world':
                    p=directory/'interaction-0.json';v=json.loads(p.read_text());v['supervision_lease']['world_session']='foreign';write(p,v)
                else:
                    p=directory/'events.jsonl';rows=[json.loads(r) for r in p.read_text().splitlines()]
                    if case=='interaction_mismatch':rows[-1]['params']['expected_hand']='minecraft:dirt'
                    else:rows[-1]['inventory_delta']['minecraft:coal']=-1
                    p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
                before=worker.path.read_bytes()
                with self.assertRaises((RuntimeError,OSError)):worker.reconcile_network_travel(process_probe=lambda:False)
                self.assertEqual(before,worker.path.read_bytes());self.assertEqual([],worker.book['batches'])


if __name__ == '__main__': unittest.main()
