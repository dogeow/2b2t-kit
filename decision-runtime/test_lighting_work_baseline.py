"""Directed work preserves native evidence/progress; all fixtures are offline."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from lighting_cli import risk_counts
from lighting_regions_cli import RegionsWorker, RegionsPaused
from lighting_work_baseline import WorkBaselineBlocked, validate
from potato_farm import ENTITY_SCOPE_AT_SCAN_END
from test_lighting_regions_cli import profile, state


class DirectedWorkTests(unittest.TestCase):
    def fixture(self, folder, dark=(1,)):
        current = state() | {'time': int(time.time()*1000), 'player_uuid': 'same-player',
            'game_mode': 'survival', 'kit_version': '2026.10.4.1', 'phase': 'parking',
            'projection_selection': {'key': 'same-projection', 'min': [0,64,0], 'max': [4,64,4]},
            'movement_keys': {'forward': False, 'jump': False},
            'material_task': {'occupied': False, 'process_alive': False, 'cancelling': False},
            'supervision_lease': {'kind': 'parking', 'id': 'current-park', 'job_session': 'current-task',
                'world_session': 'world-a', 'revision': 7, 'remote_finish': 'guard', 'park_target': [1.5,88,1.5]},
            'supervision_safety': {'lease': 'current-park', 'job_session': 'current-task', 'action': 'KEEP_PVE_GUARD'}}
        calls = []
        def batch(region, directory, *, audit):
            calls.append((region['name'], audit))
            current['control_revision'] += 1
            current['supervision_lease']['revision'] = current['control_revision']
            return {'park_native_confirmed': True, 'parking_lease': 'current-park',
                    'control_revision': current['control_revision'], 'placed_verified': 2,
                    'eligible_remaining': 0, 'unprotected_dark_floor': 1, 'observed_at': current['time']}
        path = Path(folder)/'retained-baseline.json'
        worker = RegionsWorker(Path(folder)/'automation', profile(), observer=lambda: deepcopy(current),
                               batch=batch, work_baseline=path)
        worker.book.update(world_session='world-a', campaign=2, cursor=0, dispatch_sequence=2)
        worker.save()
        book = {'schema': 1, 'profile': deepcopy(worker.profile), 'world_session': 'world-a', 'campaign': 1,
                'cursor': 2, 'pending': None, 'ai_calls': 0, 'phase': 'audited_with_remaining_risk',
                'coverage_complete': True, 'goal_complete': False, 'audits': []}
        def write(p, value):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(value)+'\n')
        for index, region in enumerate(worker.profile['regions']):
            directory = worker.out/'audit-'/f'{index+1:05d}'
            low, high = region['min'], region['max']
            pos = [low[0], 63, low[2]]
            row = {'pos': pos, 'state': 'Block{minecraft:grass_block}[snowy=false]',
                   'solid': True, 'replaceable': False, 'passable': False, 'fluid': False,
                   'block_entity': False, 'zombie_spawn_floor': True,
                   'zombie_block_light_risk': index in dark, 'spawn_block_light': 0 if index in dark else 3,
                   'monster_spawn_block_light_limit': 0}
            cells = {tuple(pos): row}
            count = (high[0]-low[0]+1)*(high[1]-low[1]+1)*(high[2]-low[2]+1)
            owner = {'kind': 'materials', 'id': f'old-lease-{index}', 'job_session': f'old-task-{index}',
                     'world_session': 'world-a', 'revision': 5, 'remote_finish': 'guard'}
            raw = deepcopy(current) | {'id': f'old-scan-{index}', 'time': 1001, 'phase': 'done',
                'control_revision': 5, 'supervision_lease': owner, 'scan_start_revision': 5, 'scan_end_revision': 5,
                'scan_started_at': 1000, 'scan_ended_at': 1002, 'scan_cells_read': count, 'scan_total_cells': count,
                'scan_coherent': False, 'blocks': [row], 'scan_entity_scope': ENTITY_SCOPE_AT_SCAN_END, 'scan_entities': []}
            final = deepcopy(current) | {'time': 1003, 'control_revision': 6,
                'supervision_lease': {**owner, 'kind': 'parking', 'revision': 6}}
            event = {'request_id': raw['id'], 'world_session': 'world-a', 'op': 'scan', 'phase': 'done',
                     'inventory_delta': {}, 'revision_before': 5, 'revision_after': 5,
                     'health_before': 20, 'health_after': 20,
                     'params': {'min': low, 'max': high, 'details': True, 'task_session': owner['job_session']}}
            write(directory/'current-region-audit.json', raw)
            write(directory/'final-snapshot.json', final)
            write(directory/'events.jsonl', event)
            book['audits'].append(risk_counts(cells, worker.profile['protected']) | {
                'observed_at': 1002, 'region_index': index, 'campaign': 1, 'park_native_confirmed': True,
                'parking_lease': owner['id'], 'control_revision': 6, 'directory': str(directory)})
        write(path, book)
        return worker, current, calls, path, book, write

    def test_all_dark_regions_only_work_and_skips_do_not_credit_scans_or_placement(self):
        with tempfile.TemporaryDirectory() as folder:
            worker, current, calls, path, baseline, write = self.fixture(folder)
            raw = path.read_bytes()
            result = worker.run(resume=True)
            self.assertEqual(calls, [('beach',False), ('field',True), ('beach',True)])
            self.assertEqual(result['campaign'], 2)
            self.assertEqual(len(result['batches']), 1)
            self.assertEqual(result['batches'][0]['placed_verified'], 2)
            self.assertEqual(result['work_selection']['selected_indices'], [1])
            skip = result['work_skips'][0]
            self.assertEqual(skip['region_index'], 0)
            self.assertFalse(skip['new_scan_performed']); self.assertFalse(skip['region_completed'])
            self.assertEqual(skip['placement_credit'], 0); self.assertEqual(skip['placed_verified'], 0)
            self.assertEqual([a['region_index'] for a in result['audits']], [0,1])
            self.assertTrue(result['coverage_complete']); self.assertFalse(result['goal_complete'])
            self.assertEqual(path.read_bytes(), raw)

    def test_resume_keeps_cursor_completed_batches_and_torches_without_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            worker, current, calls, path, baseline, write = self.fixture(folder, dark=(0,))
            prior = {'region_index': 0, 'campaign': 2, 'placed_verified': 3, 'original': 'retained'}
            worker.book.update(cursor=1, batches=[deepcopy(prior)])
            worker.save(); before_inventory = deepcopy(current['inventory'])
            result = worker.run(resume=True)
            self.assertEqual(calls, [('field',True), ('beach',True)])
            self.assertEqual(result['batches'], [prior]); self.assertEqual(result['campaign'], 2)
            self.assertEqual(current['inventory'], before_inventory)
            self.assertEqual(result['work_skips'][0]['region_index'], 1)

    def test_persisted_selection_is_revalidated_when_resume_omits_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            worker, current, calls, path, baseline, write = self.fixture(folder)
            proof = validate(path, worker.profile, worker.out, current)
            worker.book['work_selection'] = {**proof, 'campaign': 2}
            worker.save(); worker.work_baseline = None
            result = worker.run(resume=True)
            self.assertEqual(calls[0], ('beach',False))
            self.assertEqual(result['work_selection']['baseline_sha256'], proof['baseline_sha256'])

    def test_missing_persisted_selection_metadata_does_not_fall_back_to_full_work(self):
        for key in ('campaign', 'identity', 'baseline_path', 'selected_indices'):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as folder:
                worker,current,calls,path,baseline,write=self.fixture(folder)
                proof=validate(path,worker.profile,worker.out,current)
                worker.book['work_selection']={**proof,'campaign':2}
                del worker.book['work_selection'][key]
                worker.save();worker.work_baseline=None;raw=worker.path.read_bytes()
                with self.assertRaisesRegex(RegionsPaused,'no fallback'):worker.run(resume=True)
                self.assertEqual(calls,[]);self.assertEqual(worker.path.read_bytes(),raw)

    def test_pending_unknown_always_refuses_without_changing_any_record(self):
        with tempfile.TemporaryDirectory() as folder:
            worker, current, calls, path, baseline, write = self.fixture(folder)
            worker.book['pending'] = {'stage': 'unknown', 'request_id': 'original'}; worker.save()
            raw = worker.path.read_bytes()
            with self.assertRaisesRegex(RegionsPaused, 'pending batch'): worker.run(resume=True)
            self.assertEqual(calls, []); self.assertEqual(worker.path.read_bytes(), raw)

    def test_native_mailbox_and_original_unknown_torch_intent_refuse_without_clearing(self):
        for change in ('empty_pending', 'native_request', 'torch_intent'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                worker,current,calls,path,baseline,write=self.fixture(folder)
                if change=='empty_pending': worker.book['pending']={}; worker.save()
                elif change=='native_request': write(worker.root/'request.json',{'id':'unacknowledged-original'})
                else: write(worker.root/'lighting-intents/original.json',{'world_session':'world-a','state':'interaction_intent','target':[0,64,0]})
                old={p:p.read_bytes()for p in worker.root.rglob('*.json')}
                with self.assertRaises(RegionsPaused): worker.run(resume=True)
                self.assertEqual(calls,[])
                for p,raw in old.items(): self.assertEqual(p.read_bytes(),raw)

    def test_empty_null_foreign_or_malformed_mailbox_never_counts_as_acknowledged(self):
        for request in ({}, {'id':None}, {'id':''}, [],
                        {'id':'ack','world_session':'foreign'}, {'id':'ack'}):
            with self.subTest(request=request), tempfile.TemporaryDirectory() as folder:
                worker,current,calls,path,baseline,write=self.fixture(folder)
                current['last_request']='ack' if isinstance(request,dict) and request.get('id')=='ack' else None
                write(worker.root/'request.json',request);raw=worker.path.read_bytes()
                with self.assertRaises(RegionsPaused):worker.run(resume=True)
                self.assertEqual(calls,[]);self.assertEqual(worker.path.read_bytes(),raw)
                self.assertEqual(json.loads((worker.root/'request.json').read_text()),request)

    def test_exact_same_world_acknowledged_mailbox_allows_directed_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            worker,current,calls,path,baseline,write=self.fixture(folder)
            current['last_request']='ack'
            write(worker.root/'request.json',{'id':'ack','world_session':'world-a'})
            result=worker.run(resume=True)
            self.assertEqual(calls[0],('beach',False))
            self.assertEqual(result['work_selection']['selected_indices'],[1])

    def test_new_pending_or_changed_identity_during_baseline_validation_refuses(self):
        for change in ('request', 'identity'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                worker,current,calls,path,baseline,write=self.fixture(folder)
                observations = 0
                def observe():
                    nonlocal observations
                    observations += 1
                    if observations == 2:
                        if change=='request': write(worker.root/'request.json',{'id':'new-unknown'})
                        else: current['projection_selection']['key']='changed-after-proof'
                    return deepcopy(current)
                worker.observer=observe; raw=worker.path.read_bytes()
                with self.assertRaises((WorkBaselineBlocked,RegionsPaused)): worker.run(resume=True)
                self.assertEqual(calls,[]); self.assertEqual(worker.path.read_bytes(),raw)

    def test_incomplete_forged_or_changed_baseline_refuses_before_any_progress(self):
        cases = ('world','profile','missing_index','duplicate_index','raw_missing','raw_partial','raw_revision',
                 'raw_player','raw_projection','old_host','raw_details','counts','event_bounds','event_mutation',
                 'event_unknown','event_request','final_owner','outside_directory','mutable_current_journal')
        for change in cases:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                worker, current, calls, path, baseline, write = self.fixture(folder)
                audit = baseline['audits'][0]; directory = Path(audit['directory'])
                q = directory/'current-region-audit.json'; scan = json.loads(q.read_text())
                events = json.loads((directory/'events.jsonl').read_text())
                if change=='world': baseline['world_session']='other'
                elif change=='profile': baseline['profile']['regions'][0]['name']='other'
                elif change=='missing_index': baseline['audits'].pop()
                elif change=='duplicate_index': baseline['audits'][1]['region_index']=0
                elif change=='raw_missing': q.unlink()
                elif change=='raw_partial': scan['scan_cells_read']-=1; write(q,scan)
                elif change=='raw_revision': scan['scan_end_revision']+=1; write(q,scan)
                elif change=='raw_player': scan['player_uuid']='other'; write(q,scan)
                elif change=='raw_projection': scan['projection_selection']['key']='other'; write(q,scan)
                elif change=='old_host': scan['kit_version']='2026.10.4.0'; write(q,scan)
                elif change=='raw_details': del scan['blocks'][0]['zombie_block_light_risk']; write(q,scan)
                elif change=='counts': audit['unprotected_dark_floor']=1
                elif change=='event_bounds': events['params']['max'][0]+=1; write(directory/'events.jsonl',events)
                elif change=='event_mutation': events['op']='interact'; write(directory/'events.jsonl',events)
                elif change=='event_unknown': events['phase']='waiting'; write(directory/'events.jsonl',events)
                elif change=='event_request': events['request_id']='other'; write(directory/'events.jsonl',events)
                elif change=='final_owner':
                    final=json.loads((directory/'final-snapshot.json').read_text()); final['supervision_lease']['id']='other'; write(directory/'final-snapshot.json',final)
                elif change=='outside_directory': audit['directory']=str(Path(folder)/'foreign/audit-/00001')
                else: worker.work_baseline=worker.path
                write(path,baseline); raw=worker.path.read_bytes()
                with self.assertRaises((WorkBaselineBlocked,RuntimeError,OSError,KeyError)):
                    worker.run(resume=True)
                self.assertEqual(calls, []); self.assertEqual(worker.path.read_bytes(), raw)

    def test_current_world_identity_control_and_stale_park_refuse(self):
        for change in ('world_session','player_uuid','projection','health','stale','controller','parking','pending_scan'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                worker,current,calls,path,baseline,write=self.fixture(folder)
                if change in ('world_session','player_uuid'): current[change]='other'
                elif change=='projection': current['projection_selection']['key']='other'
                elif change=='health': current['health']=19
                elif change=='stale': current['time']=1
                elif change=='controller': current['navigating']=True
                elif change=='parking': current['supervision_safety']['lease']='other'
                else: current['pending_scan']={'id':'unknown'}
                raw=worker.path.read_bytes()
                with self.assertRaises(WorkBaselineBlocked): worker.run(resume=True)
                self.assertEqual(calls, []); self.assertEqual(worker.path.read_bytes(),raw)

    def test_missing_identity_or_canonical_parking_metadata_never_uses_a_fallback(self):
        for key in ('server', 'player_uuid', 'world_session', 'dimension', 'game_mode', 'projection_selection',
                    'movement_keys', 'material_task', 'pos', 'supervision_safety', 'park_target'):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as folder:
                worker,current,calls,path,baseline,write=self.fixture(folder)
                if key=='park_target': del current['supervision_lease'][key]
                else: del current[key]
                raw=worker.path.read_bytes()
                with self.assertRaises((WorkBaselineBlocked,RuntimeError)): worker.run(resume=True)
                self.assertEqual(calls,[]); self.assertEqual(worker.path.read_bytes(),raw)

    def test_baseline_never_restricts_explicit_full_audit_and_cli_forwards_option(self):
        with tempfile.TemporaryDirectory() as folder:
            worker,current,calls,path,baseline,write=self.fixture(folder)
            with self.assertRaisesRegex(ValueError,'final full audit'): worker.run(audit_only=True)
            self.assertEqual(calls,[])
        from kit_cli import main
        with patch('lighting_regions_cli.main',return_value=0) as handler:
            self.assertEqual(main(['--game-dir','/tmp/game','lighting','resume','--profile','/tmp/profile',
                                   '--out','/tmp/original','--work-baseline','/tmp/baseline']),0)
            self.assertIn('--work-baseline',handler.call_args.args[0])
            self.assertIn('/tmp/baseline',handler.call_args.args[0])


if __name__=='__main__': unittest.main()
