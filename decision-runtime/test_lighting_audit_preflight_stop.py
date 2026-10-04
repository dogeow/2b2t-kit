from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from lighting_regions_cli import RegionsPaused
from potato_farm import ENTITY_SCOPE_AT_SCAN_END
import test_lighting_audit_stop as audit_stop_tests


class KnownAuditPreflightTest(unittest.TestCase):
    def fixture(self,folder):
        worker,current,directory,marker_path,marker,write=audit_stop_tests.AuditStopTest().fixture(folder)
        pending=worker.book['pending'];pending['error']='RegionsPaused: Preload native navigation exceeds the thirty-two-block leg bound'
        worker.save();rid=pending['native_request']['request_id'];saved=Path(folder)/'stop';saved.mkdir()
        before=json.loads(Path(marker['last_status_path']).read_text());before.pop('pending_scan')
        before.update(time=1400,last_request=rid,movement_keys={'forward':False,'jump':False},navigating=False)
        reply=deepcopy(before);reply.update(id=rid,phase='done',scan_cells_read=99,scan_total_cells=99,
            scan_start_revision=8,scan_end_revision=8,scan_started_at=1300,scan_ended_at=1301,
            blocks=[],scan_entities=[],scan_entity_scope=ENTITY_SCOPE_AT_SCAN_END)
        events=[json.loads(v)for v in (directory/'events.jsonl').read_text().splitlines()]
        events.append({'request_id':rid,'op':'scan','phase':'done','world_session':'world-a',
            'params':{'task_session':'old-task','min':[0,70,0],'max':[32,72,0],'details':True},
            'inventory_delta':{},'health_before':20,'health_after':20,'revision_before':8,'revision_after':8})
        (directory/'events.jsonl').write_text(''.join(json.dumps(e)+'\n'for e in events))
        # Actual plain opening reads are scoped, healthy and terminal too.
        p=directory/'opening-survey/events.jsonl';opening=json.loads(p.read_text())
        opening.update(health_before=20,health_after=20);p.write_text(json.dumps(opening)+'\n')
        write(directory/'preload-route.json',{'world_session':'world-a','task_session':'old-task','legs':[{'route':[{
            'phase':'unknown','request_id':None,'native_inflight':None,'request_before':rid,'world_session':'world-a',
            'target':[33.5,88.3,1.5]}]}]})
        current.update(world_session='world-a',control_revision=9)
        current['supervision_lease'].update(id='old-lease',job_session='old-task',world_session='world-a',revision=9,parked_at=1600)
        current['supervision_safety'].update(lease='old-lease',job_session='old-task',cause='heartbeat_lost',time=1600)
        after=deepcopy(current);after['time']=1700
        write(saved/'before.json',before);write(saved/'after-observation.json',after)
        write(saved/'original-pending.json',deepcopy(pending));write(saved/'original-scan-reply.json',reply)
        write(worker.root/('reply-'+rid+'.json'),reply)
        write(worker.root/'supervision-receipt-old-lease.json',{'lease':'old-lease','job_session':'old-task',
            'action':'KEEP_PVE_GUARD','cause':'heartbeat_lost','time':1600})
        stopped={'pid':123,'signal':'SIGINT','time':1500,'reason':'known_pre_dispatch_bound_rejection_after_exact_terminal_read',
                 'request_replayed':False};write(saved/'stop.json',stopped)
        return worker,current,directory,saved/'stop.json',write

    def test_terminal_predispatch_archive_preserves_audit_and_all_progress(self):
        with tempfile.TemporaryDirectory()as folder:
            worker,current,directory,stop,write=self.fixture(folder);before=deepcopy(worker.book)
            raw={p:p.read_bytes()for p in directory.rglob('*')if p.is_file()}
            result=worker.reconcile_network_travel(network_evidence=stop,process_probe=lambda:False)
            record=result['pending_reconciliations'][-1]
            self.assertTrue(record['original_scan_completed']);self.assertFalse(record['navigation_dispatched'])
            self.assertFalse(record['audit_completed']);self.assertFalse(record['request_replayed'])
            for key in ('cursor','audits','batches','dispatch_sequence','campaign'):self.assertEqual(before[key],result[key])
            for path,value in raw.items():self.assertEqual(value,path.read_bytes())

    def test_unknown_dispatch_partial_scan_later_mutation_or_live_worker_preserves_pending(self):
        for change in ('dispatch','inflight','partial','mutation','process','wrong_error'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as folder:
                worker,current,directory,stop,write=self.fixture(folder)
                if change in ('dispatch','inflight'):
                    path=directory/'preload-route.json';plan=json.loads(path.read_text())
                    plan['legs'][0]['route'][0]['request_id'if change=='dispatch'else'native_inflight']='issued'
                    write(path,plan)
                elif change=='partial':
                    path=worker.root/'reply-unknown-read.json';reply=json.loads(path.read_text());reply['scan_cells_read']=98
                    write(path,reply);write(stop.parent/'original-scan-reply.json',reply)
                elif change=='mutation':
                    path=directory/'events.jsonl';events=[json.loads(v)for v in path.read_text().splitlines()]
                    events[-1]['inventory_delta']={'minecraft:torch':-1};path.write_text(''.join(json.dumps(e)+'\n'for e in events))
                elif change=='wrong_error':worker.book['pending']['error']='Other unknown navigation';worker.save()
                before=worker.path.read_bytes()
                with self.assertRaises((RuntimeError,OSError,KeyError)):
                    worker.reconcile_network_travel(network_evidence=stop,process_probe=lambda:change=='process')
                self.assertEqual(before,worker.path.read_bytes())

    def test_foreign_park_world_health_or_keep_receipt_refuses(self):
        for change in ('owner','world','health','receipt'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as folder:
                worker,current,directory,stop,write=self.fixture(folder)
                if change=='owner':current['supervision_lease']['id']='other'
                elif change=='world':current['world_session']='other'
                elif change=='health':current['health']=19
                else:write(worker.root/'supervision-receipt-old-lease.json',{'action':'KEEP_PVE_GUARD','lease':'foreign'})
                with self.assertRaises(RuntimeError):
                    worker.reconcile_network_travel(network_evidence=stop,process_probe=lambda:False)


if __name__=='__main__':unittest.main()
