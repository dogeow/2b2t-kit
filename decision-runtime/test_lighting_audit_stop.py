from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest

from lighting_regions_cli import RegionsWorker,RegionsPaused
from test_lighting_regions_cli import profile,state


class AuditStopTest(unittest.TestCase):
    def fixture(self,folder):
        root=Path(folder)/'automation';current=state()
        identity={'player_uuid':'same-player','game_mode':'survival','kit_version':'2026.10.4.1',
                  'projection_selection':{'key':'selected','min':[0,64,0],'max':[4,64,4]}}
        current.update(deepcopy(identity));current.update(time=int(time.time()*1000),world_session='world-b',
            control_revision=9,phase='parking',last_request='new-read',movement_keys={'forward':False,'jump':False},
            material_task={'occupied':False,'process_alive':False,'cancelling':False},
            supervision_lease={'id':'new-lease','job_session':'new-task','kind':'parking','world_session':'world-b',
                'revision':9,'remote_finish':'guard','park_target':[1.5,88,1.5]},
            supervision_safety={'lease':'new-lease','job_session':'new-task','action':'KEEP_PVE_GUARD'})
        worker=RegionsWorker(root,profile(),observer=lambda:current)
        directory=worker.out/'audit-'/'00007';(directory/'opening-survey').mkdir(parents=True)
        external=Path(folder)/'preserved';external.mkdir()
        def write(path,value):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value)+'\n')
        native={'request_id':'unknown-read','op':'scan','world_session':'world-a','task_session':'old-task',
                'lease_id':'old-lease','base_revision':8,'expected_revision':8}
        worker.book.update(world_session='world-a',cursor=2,audits=[],dispatch_sequence=7,phase='waiting_unresolved',
            pending={'mode':'audit','stage':'travel','travel_stage':'preload','region_index':0,'directory':str(directory),
                     'world_session':'world-a','task_session':'old-task','lease':'old-lease',
                     'native_request':native,'uncertain_request':deepcopy(native)})
        worker.save()
        baseline=state()|deepcopy(identity)|{'id':'opening','phase':'done','time':900,
            'scan_cells_read':384,'scan_total_cells':384}
        last=state()|deepcopy(identity)|{'time':1300,'control_revision':8,'last_request':'unknown-read',
            'pending_scan':{'id':'unknown-read','world_session':'world-a','control_revision':8,
                           'cells_read':20,'total_cells':336,'reading_complete':False},
            'supervision_lease':{'kind':'materials','id':'old-lease','job_session':'old-task',
                                'world_session':'world-a','revision':8}}
        write(directory/'current-park-column.json',baseline)
        write(directory/'current-park-plan.json',{'world_session':'world-a','park_target':[1.5,88,1.5],
                                               'observed':deepcopy(baseline)})
        write(directory/'run-manifest-old-task.json',{'task_session':'old-task','world_session':'world-a',
            'dimension':'minecraft:overworld','game_mode':'survival','created_at':1000,'complete':False,
            'server_hash':hashlib.sha256(b'example.invalid').hexdigest()[:16],'placement_key':'selected'})
        request={'id':'unknown-read','op':'scan','details':True,'min':[0,70,0],'max':[3,90,3],
            'server':'example.invalid','dimension':'minecraft:overworld','world_session':'world-a',
            'task_session':'old-task','expected_revision':8,'site':[1.5,88,1.5]}
        write(external/'request.json',request);write(external/'status.json',last)
        opening={'request_id':'opening','op':'scan','phase':'done','world_session':'world-a','inventory_delta':{},
                 'params':{'min':[1,-64,1],'max':[1,319,1],'details':True}}
        (directory/'opening-survey/events.jsonl').write_text(json.dumps(opening)+'\n')
        event={'phase':'done','world_session':'world-a','inventory_delta':{},'health_before':20,'health_after':20,
               'revision_before':7,'revision_after':7}
        events=[event|{'request_id':'session','op':'material_session',
            'params':{'task_session':'old-task','supervision_lease':'old-lease'}},
            event|{'request_id':'finished-nav','op':'navigate','revision_after':8,
                'params':{'task_session':'old-task','air_only':True,'target':[2.5,88,1.5]}}]
        (directory/'events.jsonl').write_text(''.join(json.dumps(e)+'\n'for e in events))
        marker={'schema':1,'reason':'worker_and_game_not_running','request_id':'unknown-read','world_session':'world-a',
            'task_session':'old-task','health_exit':False,'previous_worker_process_alive':False,
            'previous_game_process_alive':False,'processes_checked_at':1500,
            'original_request_path':str(external/'request.json'),
            'original_request_sha256':hashlib.sha256((external/'request.json').read_bytes()).hexdigest(),
            'last_status_path':str(external/'status.json'),
            'last_status_sha256':hashlib.sha256((external/'status.json').read_bytes()).hexdigest()}
        path=external/'evidence.json';write(path,marker)
        write(root/'request.json',{'id':'new-read'})
        return worker,current,directory,path,marker,write

    def test_unknown_audit_read_is_archived_without_replay_or_any_progress_credit(self):
        with tempfile.TemporaryDirectory()as folder:
            worker,current,directory,path,marker,write=self.fixture(folder)
            before=deepcopy(worker.book);old={p:p.read_bytes()for p in directory.rglob('*')if p.is_file()}
            result=worker.reconcile_network_travel(network_evidence=path,process_probe=lambda:False)
            record=result['pending_reconciliations'][-1]
            self.assertEqual('previous_audit_read_unknown_after_worker_stop',record['outcome'])
            for flag in ('original_read_completed','audit_completed','region_completed','request_replayed'):
                self.assertFalse(record[flag])
            for key in ('cursor','dispatch_sequence','audits','batches','campaign'):
                self.assertEqual(before[key],result[key])
            self.assertIsNone(result['pending']);self.assertFalse(result['coverage_complete'])
            for p,raw in old.items():self.assertEqual(raw,p.read_bytes())
            self.assertTrue((Path(record['archive'])/'external/request.json').is_file())

    def test_unknown_or_mutating_prefix_and_original_report_preserve_pending(self):
        for change in ('unknown_nav','inventory','interaction','report','read_is_nav','intent','reply'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as folder:
                worker,current,directory,path,marker,write=self.fixture(folder)
                events=[json.loads(v)for v in (directory/'events.jsonl').read_text().splitlines()]
                if change=='unknown_nav':events[-1]['phase']='waiting'
                elif change=='inventory':events[-1]['inventory_delta']={'minecraft:dirt':1}
                elif change=='interaction':events[-1]['op']='interact'
                elif change=='report':write(directory/'report.json',{'placed':[]})
                elif change=='read_is_nav':worker.book['pending']['native_request']['op']='navigate';worker.save()
                elif change=='intent':write(worker.root/'lighting-intents/old.json',{'world_session':'world-a','task_session':'old-task'})
                else:write(worker.root/'reply-unknown-read.json',{'id':'unknown-read','phase':'done'})
                (directory/'events.jsonl').write_text(''.join(json.dumps(e)+'\n'for e in events))
                original=worker.path.read_bytes()
                with self.assertRaises((RuntimeError,ValueError)):
                    worker.reconcile_network_travel(network_evidence=path,process_probe=lambda:False)
                self.assertEqual(original,worker.path.read_bytes());self.assertIsNotNone(worker.book['pending'])

    def test_health_process_identity_stock_and_stale_current_parking_refuse(self):
        for change in ('health','process','player','projection','stock','world','stale','safety'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as folder:
                worker,current,directory,path,marker,write=self.fixture(folder)
                if change=='health':marker['health_exit']=True;write(path,marker)
                elif change=='player':current['player_uuid']='other'
                elif change=='projection':current['projection_selection']['key']='other'
                elif change=='stock':current['inventory'][0]['count']=7
                elif change=='world':current['world_session']='world-a'
                elif change=='stale':current['time']=1
                elif change=='safety':current['supervision_safety']=None
                original=worker.path.read_bytes()
                with self.assertRaises(RuntimeError):
                    worker.reconcile_network_travel(network_evidence=path,process_probe=lambda:change=='process')
                self.assertEqual(original,worker.path.read_bytes())

    def test_new_active_health_hold_or_changed_preserved_bytes_refuse(self):
        for change in ('hold','request','status'):
            with tempfile.TemporaryDirectory()as folder:
                worker,current,directory,path,marker,write=self.fixture(folder)
                if change=='hold':
                    hold=Path(folder)/'hold.json';write(hold,{'active':True,'time':1100})
                    marker['health_hold_paths']=[str(hold)];write(path,marker)
                else:
                    target=Path(marker['original_request_path'if change=='request'else'last_status_path'])
                    data=json.loads(target.read_text());data['changed']=True;write(target,data)
                with self.assertRaises(RuntimeError):
                    worker.reconcile_network_travel(network_evidence=path,process_probe=lambda:False)

    def test_last_status_pending_scan_and_original_material_owner_must_match_request(self):
        for change in ('last_request','scan_id','scan_world','scan_revision','scan_total','lease_id','lease_task','lease_world','lease_revision'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as folder:
                worker,current,directory,path,marker,write=self.fixture(folder)
                saved=Path(marker['last_status_path']);last=json.loads(saved.read_text())
                if change=='last_request':last['last_request']='other'
                elif change.startswith('scan_'):
                    key={'scan_id':'id','scan_world':'world_session','scan_revision':'control_revision','scan_total':'total_cells'}[change]
                    last['pending_scan'][key]='other'
                else:
                    key={'lease_id':'id','lease_task':'job_session','lease_world':'world_session','lease_revision':'revision'}[change]
                    last['supervision_lease'][key]='other'
                write(saved,last);marker['last_status_sha256']=hashlib.sha256(saved.read_bytes()).hexdigest();write(path,marker)
                with self.assertRaises(RuntimeError):
                    worker.reconcile_network_travel(network_evidence=path,process_probe=lambda:False)

    def test_opening_scope_must_match_complete_body_column_and_plan(self):
        for change in ('bounds','details','plan_pose','plan_revision'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as folder:
                worker,current,directory,path,marker,write=self.fixture(folder)
                if change in ('bounds','details'):
                    p=directory/'opening-survey/events.jsonl';event=json.loads(p.read_text())
                    if change=='bounds':event['params']['min'][0]+=1
                    else:event['params']['details']=False
                    p.write_text(json.dumps(event)+'\n')
                else:
                    p=directory/'current-park-plan.json';plan=json.loads(p.read_text())
                    if change=='plan_pose':plan['park_target'][0]+=1
                    else:plan['observed']['control_revision']+=1
                    write(p,plan)
                with self.assertRaises(RuntimeError):
                    worker.reconcile_network_travel(network_evidence=path,process_probe=lambda:False)


if __name__=='__main__':unittest.main()
