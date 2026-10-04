import json
from pathlib import Path
import tempfile
import time
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from lighting_supply_workflow import LightingSupplyWorkflow, WorkflowWaiting
from test_lighting_cli import inventory


def state():
    return {'connected':True,'server':'simpcraft.com','dimension':'minecraft:overworld','world_session':'world',
        'time':int(time.time()*1000),'control_revision':5,'manual_movement':False,'health':20,'screen':'',
        'material_task_api_protocol':1,'guard_armed':True,'guard_pve_only':True,'flight':True,
        'material_task':{'occupied':False,'process_alive':False},
        'supervision_lease':{'kind':'parking','world_session':'world','revision':5,'job_session':'native-job'},'inventory':inventory(0)}


class WorkflowTest(unittest.TestCase):
    def fixture(self, root, current=None, sender=None, task_status=None):
        self.current=current or state();self.starts=[]
        worker=SimpleNamespace(root=Path(root)/'automation',out=Path(root)/'output',
             profile={'server':'simpcraft.com','dimension':'minecraft:overworld'},observer=lambda:self.current)
        worker.root.mkdir();worker.out.mkdir()
        def accept(request):
            self.starts.append(request)
            return {'phase':'done','material_task':{'id':'original-job','state':'queued'}}
        return LightingSupplyWorkflow(lambda:worker,observer=lambda:self.current,sender=sender or accept,
                  task_status=task_status or (lambda job:{'phase':'done','material_task':{'id':job,'state':'paused'}}),
                  sleeper=lambda seconds:None)
    def test_start_acceptance_is_not_supply_completion(self):
        with tempfile.TemporaryDirectory() as root:
            flow=self.fixture(root);flow.begin_supply()
            self.assertEqual('original-job',flow.book['pending']['job_id']);self.assertEqual([],flow.book['supplies'])
            self.assertEqual(1,len(self.starts))
            with self.assertRaises(WorkflowWaiting):flow.finish_supply()
            self.assertIsNotNone(flow.book['pending'])
    def test_one_exact_completed_native_job_requires_backpack_count_and_park_owner(self):
        with tempfile.TemporaryDirectory() as root:
            flow=self.fixture(root,task_status=lambda job:{'phase':'done','material_task':{'id':job,'state':'completed',
                              'process_alive':False,'occupied':False,'native_task_session':'native-job'}})
            flow.begin_supply();self.current['inventory']=inventory(64);self.current['inventory'][1].update(item='minecraft:torch',count=64);flow.finish_supply()
            self.assertIsNone(flow.book['pending']);self.assertEqual(128,flow.book['supplies'][0]['backpack_torches'])
            self.assertEqual(1,len(self.starts))
    def test_timeout_preserves_original_start_and_never_replays(self):
        def fail(request):raise RuntimeError('observation timeout')
        with tempfile.TemporaryDirectory() as root:
            flow=self.fixture(root,sender=fail)
            with self.assertRaises(RuntimeError):flow.begin_supply()
            saved=json.loads(flow.path.read_text());self.assertTrue(saved['pending']['request']['id'])
            with self.assertRaises(WorkflowWaiting):flow.begin_supply()
            with self.assertRaises(WorkflowWaiting):flow.finish_supply()
    def test_wrong_world_manual_input_or_other_server_cannot_start_new_supply(self):
        for key,value in (('manual_movement',True),('health',12),('server','other.invalid')):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as root:
                current=state();current[key]=value;flow=self.fixture(root,current)
                with self.assertRaises(WorkflowWaiting):flow.begin_supply()
                self.assertEqual([],self.starts)
    def test_completed_label_without_actual_stock_or_foreign_parking_never_succeeds(self):
        for change in ('stock','owner'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as root:
                flow=self.fixture(root,task_status=lambda job:{'phase':'done','material_task':{'id':job,'state':'completed',
                                  'process_alive':False,'occupied':False,'native_task_session':'native-job'}})
                flow.begin_supply()
                if change=='owner':
                    self.current['inventory']=inventory(64);self.current['inventory'][1].update(item='minecraft:torch',count=64);self.current['supervision_lease']['job_session']='foreign'
                with self.assertRaises(WorkflowWaiting):flow.finish_supply()
                self.assertEqual([],flow.book['supplies']);self.assertIsNotNone(flow.book['pending'])
    def test_foreign_native_reply_and_world_change_do_not_resume_lighting(self):
        for change in ('reply','world'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as root:
                flow=self.fixture(root,task_status=lambda job:{'phase':'done','material_task':{'id':'foreign','state':'completed'}})
                flow.begin_supply()
                if change=='world':self.current['world_session']='other'
                with self.assertRaises(WorkflowWaiting):flow.finish_supply()
                self.assertIsNotNone(flow.book['pending'])
    def test_existing_region_worker_is_joined_without_duplicate_action_controller(self):
        with tempfile.TemporaryDirectory() as root:
            flow=self.fixture(root);worker=flow.factory();polls=[True,False]
            worker.status=lambda:{'worker_running':polls.pop(0)}
            worker.run=lambda resume:{'phase':'audited','pending':None}
            result=flow.run()
            self.assertEqual('audited',result['phase']);self.assertEqual([],self.starts)


class PriorFinishReconciliationTest(WorkflowTest):
    def reconciliation_fixture(self,root):
        from contextlib import nullcontext
        from material_jobs.protocol import fingerprint
        flow=self.fixture(root)
        self.current.update(food=19,under_water=False,native_material_busy=False,native_task_session=None)
        flow.begin_supply();worker=flow.factory();worker.book={'pending':None};worker.worker_lock=nullcontext
        job=flow.root/'material-jobs'/'original-job';control=job/'control-001';control.mkdir(parents=True)
        (job/'receipts').mkdir();native='native-job';world='world'
        task={'id':'original-job','state':'blocked','world_session':world,'native_task_session':native,
              'pid':12345,'occupied':False,'process_alive':False,'cancelling':False}
        self.current['material_task']=deepcopy(task)
        self.current['world_session']='fresh-world';self.current['supervision_lease']=None
        self.current['inventory']=inventory(64)
        self.current['inventory'][1].update(item='minecraft:torch',count=64)
        self.current['pos']=[0,100,0];self.current['last_request']='guard-request'
        def observe():
            self.current['time']+=1
            return deepcopy(self.current)
        flow.observe=observe;flow.task_status=lambda job:{'phase':'done','material_task':deepcopy(task)}
        def write(path,value):
            path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        write(job/'request.json',{'id':'original-job','mode':'item','targets':{'minecraft:torch':128},
            'context':{'world_session':world,'server':'simpcraft.com','dimension':'minecraft:overworld'}})
        write(job/'status.json',{'id':'original-job','state':'blocked','terminal':True,'work_state_before_finish':'completed',
              'done':128,'total':128,'steps':7,'requirements':{},'native_task_session':native})
        write(control/f'run-manifest-{native}.json',{'task_session':native,'world_session':world,
              'dimension':'minecraft:overworld','complete':False})
        events=[]
        for sequence in range(1,8):
            op='fetch' if sequence in (1,2,3) else 'acquire' if sequence==5 else 'craft'
            receipt={'phase':'waiting','missing':{'minecraft:coal':1}} if sequence in (1,3) else {'phase':'done'}
            if op=='craft':receipt.update(complete=True,remaining_targets={},steps=[{'item':'minecraft:torch','state':'crafted','produced':4}])
            record={'job_id':'original-job','sequence':sequence,'operation':op,'args':[{'minecraft:torch':128}],
                    'before':{'stock':{}},'output_targets':{'minecraft:torch':128},'receipt':receipt}
            write(job/'receipts'/f'{sequence:06d}.json',record)
            events.extend([{**{k:v for k,v in record.items() if k!='receipt'},'kind':'action_started','time':sequence},
                           {'kind':'action_receipt','time':sequence+1,'sequence':sequence,'operation':op,'receipt':receipt}])
        events.append({'kind':'finish_failed'})
        (job/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        directory=job/'0008-craft';directory.mkdir()
        write(directory/'result.json',{k:v for k,v in record['receipt'].items() if k!='phase'})
        write(job/'active-operation.json',{'directory':str(directory),'name':'craft',
              'operation_fingerprint':fingerprint({k:v for k,v in record.items() if k!='receipt'})})
        native_events=[{'op':'material_session','request_id':'native-start','phase':'done','world_session':world,
            'params':{'task_session':native,'supervision_lease':'old-lease'}},
            {'op':'material_job_park','request_id':'last-park','phase':'done','world_session':world,'params':{'task_session':native}}]
        (control/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in native_events))
        write(control/'finish-drain.json',{'safe_to_cleanup':True,'reason':'owned_action_settled',
              'observed':{'world_session':world,'last_request':'last-park'}})
        write(flow.root/'supervision-receipt-old-lease.json',{'lease':'old-lease','job_session':native,
              'action':'LOGOUT','cause':'parking_invalid','snapshot':{'world_session':world}})
        boxes=[]
        for slot in (16,15):
            boxes.append({'slot':slot,'stage':'returned','world_session':world,
                'source':{'slot':slot,'count':1,'counts':{'minecraft:coal':2},'position':[1,64,2]},
                'initial_counts':{'minecraft:coal':2},'taken':{'minecraft:coal':1},'remaining_counts':{'minecraft:coal':1},
                'ownership_preflight':{'world_session':world,'cursor_clean':True}})
        (control/'packed-transfers.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in boxes))
        write(control/'packed-transfer-active.json',boxes[-1])
        write(flow.root/'request.json',{'id':'guard-request','op':'guard'})
        return flow,job,control,task

    def test_archive_keeps_original_bytes_and_unknown_finish_and_never_starts_or_replays(self):
        import hashlib
        with tempfile.TemporaryDirectory() as root:
            flow,job,control,task=self.reconciliation_fixture(root)
            original={p:p.read_bytes() for p in job.rglob('*') if p.is_file()}
            pending=deepcopy(flow.book['pending']);raw=flow.path.read_bytes()
            result=flow.reconcile_prior_finish(expected_job='original-job',process_probe=lambda pid:False)
            self.assertEqual('prior_finish_unknown',result['outcome']);self.assertFalse(result['prior_finish_completed'])
            self.assertEqual(pending,result['original_pending']);self.assertEqual([],flow.book['supplies'])
            self.assertIsNone(flow.book['pending']);self.assertEqual(1,len(self.starts))
            self.assertEqual(128,result['fresh_backpack_torches'])
            archive=Path(result['archive']);self.assertEqual(raw,(archive/'original-workflow.json').read_bytes())
            for path,data in original.items():
                self.assertEqual(data,path.read_bytes());self.assertEqual(data,(archive/path.relative_to(job)).read_bytes())
                self.assertEqual(hashlib.sha256(data).hexdigest(),result['evidence_sha256'][str(path.relative_to(job))])
            self.assertEqual('blocked',json.loads((job/'status.json').read_text())['state'])
            self.assertFalse(json.loads((control/'run-manifest-native-job.json').read_text())['complete'])

    def test_failed_journal_save_keeps_pending_and_allows_fresh_archive_retry(self):
        with tempfile.TemporaryDirectory() as root:
            flow,job,control,task=self.reconciliation_fixture(root);before=flow.path.read_bytes()
            with patch.object(flow,'save',side_effect=OSError('disk unavailable')):
                with self.assertRaises(OSError):
                    flow.reconcile_prior_finish(expected_job='original-job',process_probe=lambda pid:False)
            self.assertEqual(before,flow.path.read_bytes());self.assertIsNotNone(flow.book['pending'])
            first=set((flow.out/'supply-reconciliations').iterdir())
            result=flow.reconcile_prior_finish(expected_job='original-job',process_probe=lambda pid:False)
            self.assertEqual('prior_finish_unknown',result['outcome'])
            self.assertEqual(2,len(list((flow.out/'supply-reconciliations').iterdir())))
            self.assertTrue(first.issubset(set((flow.out/'supply-reconciliations').iterdir())))

    def test_explicit_reconcile_cli_calls_only_read_only_reconciliation(self):
        from lighting_supply_workflow import main
        with tempfile.TemporaryDirectory() as root:
            flow,job,control,task=self.reconciliation_fixture(root);worker=flow.factory()
            profile=Path(root)/'profile.json';profile.write_text(json.dumps(worker.profile))
            with patch('lighting_regions_cli.RegionsWorker',return_value=worker),patch.object(
                    LightingSupplyWorkflow,'reconcile_prior_finish',return_value={'outcome':'prior_finish_unknown'}) as method,patch('builtins.print'):
                self.assertEqual(0,main(['reconcile-prior-finish','--profile',str(profile),'--out',str(worker.out),'--job-id','original-job']))
                method.assert_called_once_with(expected_job='original-job',expected_steps=7,expected_boxes=2)
            self.assertFalse(hasattr(worker,'run'));self.assertEqual(1,len(self.starts))

    def test_unreceipted_unknown_or_changed_action_cannot_archive(self):
        cases=('missing_receipt','unknown_phase','event_mismatch','inflight','breadcrumb','native_running','result')
        for case in cases:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                flow,job,control,task=self.reconciliation_fixture(root);path=job/'receipts/000007.json'
                if case=='missing_receipt':path.unlink()
                elif case in ('unknown_phase','event_mismatch'):
                    value=json.loads(path.read_text());value['receipt']['phase']='running' if case=='unknown_phase' else 'done'
                    value['receipt']['unknown']=True;path.write_text(json.dumps(value))
                elif case=='inflight':(job/'inflight.json').write_text('{}')
                elif case=='breadcrumb':
                    value=json.loads((job/'active-operation.json').read_text());value['operation_fingerprint']='unknown';(job/'active-operation.json').write_text(json.dumps(value))
                elif case=='native_running':
                    rows=control/'events.jsonl';rows.write_text(rows.read_text().replace('"phase": "done"','"phase": "running"'))
                else:(job/'0008-craft/result.json').write_text('{"complete": false}')
                before=flow.path.read_bytes()
                with self.assertRaises(WorkflowWaiting):flow.reconcile_prior_finish(expected_job='original-job',process_probe=lambda pid:False)
                self.assertEqual(before,flow.path.read_bytes());self.assertIsNotNone(flow.book['pending'])

    def test_unreturned_boxes_or_living_original_process_cannot_archive(self):
        for case in ('box_missing','box_unreturned','stock','alive','occupied','foreign_task'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                flow,job,control,task=self.reconciliation_fixture(root)
                if case=='box_missing':(control/'packed-transfers.jsonl').write_text('')
                elif case=='box_unreturned':
                    rows=control/'packed-transfers.jsonl';rows.write_text(rows.read_text().replace('"returned"','"recovered"'))
                elif case=='stock':self.current['inventory'][1]['count']=63
                elif case=='occupied':task['occupied']=True
                elif case=='foreign_task':task['id']='foreign'
                before=flow.path.read_bytes()
                with self.assertRaises(WorkflowWaiting):flow.reconcile_prior_finish(expected_job='original-job',process_probe=lambda pid:case=='alive')
                self.assertEqual(before,flow.path.read_bytes())

    def test_manual_hold_changed_world_and_unknown_lighting_pending_block_read_only_archive(self):
        for case in ('manual','guard','hold','lighting','mailbox','stale'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                flow,job,control,task=self.reconciliation_fixture(root)
                if case=='manual':self.current['manual_movement']=True
                elif case=='guard':self.current['guard_armed']=False
                elif case=='hold':(flow.root/'safety-hold.json').write_text('{"active": true}')
                elif case=='lighting':flow.factory().book['pending']={'stage':'lighting','unknown':True}
                elif case=='mailbox':(flow.root/'request.json').write_text('{"id":"unknown","op":"interact"}')
                elif case=='stale':self.current['time']-=10000
                before=flow.path.read_bytes()
                with self.assertRaises(RuntimeError):flow.reconcile_prior_finish(expected_job='original-job',process_probe=lambda pid:False)
                self.assertEqual(before,flow.path.read_bytes());self.assertEqual(1,len(self.starts))


if __name__=='__main__':unittest.main()
