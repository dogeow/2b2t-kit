"""Only a complete current post-work native audit prefix may survive resume."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import kit_cli
from lighting_audit_prefix import validate
from lighting_cli import EVIDENCE
from lighting_regions_cli import RegionsPaused
import test_lighting_work_baseline as baseline_tests
from potato_farm import ENTITY_SCOPE_AT_SCAN_END


class AuditPrefixTests(unittest.TestCase):
    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        worker,current,calls,baseline,book,write=baseline_tests.DirectedWorkTests().fixture(temp.name,dark=())
        worker.work_baseline=None
        work=worker.out/'batch-'/'00003';work.mkdir(parents=True)
        old=Path(book['audits'][0]['directory']);directory=worker.out/'audit-'/'00004';old.rename(directory)
        audit=deepcopy(book['audits'][0]);audit.update(campaign=2,directory=str(directory))
        raw=json.loads((directory/'current-region-audit.json').read_text())
        final=json.loads((directory/'final-snapshot.json').read_text());final['time']=1005
        final['supervision_lease'].update(park_target=final['pos'],parked_at=1004,remote_finish='guard')
        native={'lease':raw['supervision_lease']['id'],'job_session':raw['supervision_lease']['job_session'],
                'cause':'controller_finished','action':'KEEP_PVE_GUARD','time':1004,
                'snapshot':deepcopy(final),'confirmed':False,'server_survival_verified':False}
        final['supervision_safety']={k:v for k,v in native.items()if k!='snapshot'}
        write(directory/'final-snapshot.json',final)
        write(directory/'stock-safety.json',{**native,'native_receipt':True,'parking_confirmation':final})
        write(worker.root/('supervision-receipt-'+native['lease']+'.json'),native)
        current.clear();current.update(deepcopy(final));current['time']=int(time.time()*1000)
        current['pending_scan']=None
        worker.book.update(world_session='world-a',campaign=2,cursor=2,dispatch_sequence=4,pending=None,
            phase='waiting',coverage_complete=False,audits=[audit],last_revision=final['control_revision'],
            parking_lease=native['lease'],batches=[{'campaign':2,'region_index':0,'directory':str(work),'placed_verified':0}])
        worker.save();path=Path(temp.name)/'audit-prefix.json';write(path,worker.book);worker.audit_prefix=path
        calls.clear()
        def batch(region,directory,*,audit):
            calls.append((region['name'],audit));current['control_revision']+=1
            lease='new-audit-'+str(current['control_revision']);current['supervision_lease'].update(id=lease,revision=current['control_revision'])
            return {'park_native_confirmed':True,'parking_lease':lease,'control_revision':current['control_revision'],
                    'placed_verified':0,'eligible_remaining':0,'unprotected_dark_floor':0}
        worker.batch=batch
        return worker,current,calls,path,write,directory

    def refuse(self,worker):
        before=worker.path.read_bytes();book=deepcopy(worker.book)
        with self.assertRaises((RuntimeError,ValueError,KeyError,OSError)):worker.run(resume=True)
        self.assertEqual(before,worker.path.read_bytes());self.assertEqual(book,worker.book)

    def test_prefix_preserves_actual_first_audit_and_only_dispatches_remaining_scope(self):
        worker,current,calls,path,write,directory=self.fixture();original=deepcopy(worker.book['audits'])
        result=worker.run(resume=True)
        self.assertEqual([('beach',True)],calls);self.assertEqual(original,result['audits'][:1])
        self.assertEqual([0,1],[row['region_index']for row in result['audits']])
        self.assertEqual(2,result['campaign']);self.assertEqual(2,result['cursor'])
        self.assertTrue(result['coverage_complete']);self.assertFalse(result['goal_complete'])
        self.assertEqual(1,result['audit_resume_prefix']['prefix_count'])
        self.assertEqual(0,result['audit_resume_prefix']['new_scan_credit'])

    def test_explicit_audit_prefix_works_without_resetting_existing_row(self):
        worker,current,calls,path,write,directory=self.fixture();result=worker.run(audit_only=True)
        self.assertEqual([('beach',True)],calls);self.assertEqual(2,len(result['audits']))

    def test_no_flag_keeps_original_full_audit_behavior(self):
        worker,current,calls,path,write,directory=self.fixture();worker.audit_prefix=None
        result=worker.run(resume=True)
        self.assertEqual([('field',True),('beach',True)],calls)
        self.assertEqual(2,len(result['audits']));self.assertNotIn('audit_resume_prefix',result)

    def test_campaign_gap_pending_or_noncurrent_wave_refuses_before_any_progress(self):
        for change in ('campaign','index','pending','empty_pending','sequence','history','mutable_snapshot','old_wave'):
            with self.subTest(change=change):
                worker,current,calls,path,write,directory=self.fixture();saved=json.loads(path.read_text())
                if change=='campaign':saved['campaign']=1
                elif change=='index':saved['audits'][0]['region_index']=1
                elif change in ('pending','empty_pending'):
                    worker.book['pending']={}if change=='empty_pending'else{'id':'unknown'};worker.save()
                elif change=='sequence':saved['dispatch_sequence']=99
                elif change=='history':saved['batches'][0]['placed_verified']=1
                elif change=='mutable_snapshot':worker.audit_prefix=worker.path
                else:
                    worker.book['batches'][0]['directory']=str(worker.out/'batch-'/'00005');worker.save();saved=deepcopy(worker.book)
                write(path,saved);self.refuse(worker);self.assertEqual([],calls)

    def test_missing_partial_foreign_or_malformed_native_evidence_refuses(self):
        for change in ('missing','partial','world','player','model','revision','host','details','counts','event','keep','park'):
            with self.subTest(change=change):
                worker,current,calls,path,write,directory=self.fixture();raw_path=directory/'current-region-audit.json'
                raw=json.loads(raw_path.read_text())
                if change=='missing':raw_path.unlink()
                elif change=='partial':raw['scan_cells_read']-=1;write(raw_path,raw)
                elif change=='world':raw['world_session']='foreign';write(raw_path,raw)
                elif change=='player':raw['player_uuid']='foreign';write(raw_path,raw)
                elif change=='model':raw['projection_selection']['key']='foreign';write(raw_path,raw)
                elif change=='revision':raw['scan_end_revision']+=1;write(raw_path,raw)
                elif change=='host':raw['kit_version']='2026.10.4.0';write(raw_path,raw)
                elif change=='details':raw['blocks'][0].pop('passable');write(raw_path,raw)
                elif change=='counts':
                    worker.book['audits'][0]['unprotected_dark_floor']=99;worker.save();write(path,worker.book)
                elif change=='event':
                    with (directory/'events.jsonl').open('a')as f:f.write(json.dumps({'op':'interact','phase':'done'})+'\n')
                elif change=='keep':(worker.root/'supervision-receipt-old-lease-0.json').unlink()
                else:
                    final=json.loads((directory/'final-snapshot.json').read_text());final['supervision_safety']['lease']='foreign';write(directory/'final-snapshot.json',final)
                self.refuse(worker);self.assertEqual([],calls)

    def test_current_unknown_control_inventory_or_new_request_refuses(self):
        for change in ('pending_scan','owner','inventory','guard','mailbox','intent'):
            with self.subTest(change=change):
                worker,current,calls,path,write,directory=self.fixture()
                if change=='pending_scan':current['pending_scan']={}
                elif change=='owner':current['supervision_lease']['id']='foreign'
                elif change=='inventory':current['inventory'][0]['count']+=1
                elif change=='guard':current['guard_busy']=True
                elif change=='mailbox':write(worker.root/'request.json',{})
                else:write(worker.root/'lighting-intents/unknown.json',{'world_session':'world-a','state':'interaction_intent'})
                self.refuse(worker);self.assertEqual([],calls)

    def torch(self,worker,current,path,write,after_time=900):
        source=Path(worker.book['batches'][0]['directory']);before_time=after_time-100;task='torch-work'
        before=deepcopy(current);before['time']=before_time
        before['supervision_lease'].update(kind='materials',job_session=task)
        intent={'state':'verified','world_session':'world-a','task_session':task,'support':[0,63,0],'target':[0,64,0],
                'before_stock':8,'after_stock':7,'before_time':before_time,'after_time':after_time,
                'evidence_scope':EVIDENCE,'later_verified_frames':2,'interaction_request':'torch-interact'}
        write(source/'report.json',{'world_session':'world-a','task_session':task,'evidence_scope':EVIDENCE,'placed':[intent]})
        ack=deepcopy(before)|{'id':'torch-interact','phase':'done'}
        write(source/'interaction-0.json',ack);write(source/'inventory-before-0.json',before)
        write(source/'events.jsonl',{'request_id':'torch-interact','phase':'done','op':'interact','world_session':'world-a',
                                    'params':{'pos':[0,63,0],'task_session':task,'expected_hand':'minecraft:torch'}})
        for index,stamp in ((1,after_time-50),(2,after_time)):
            frame=deepcopy(before);frame['time']=stamp;frame['inventory'][0]['count']=7
            raw=deepcopy(frame)|{'phase':'done','blocks':[{'pos':[0,64,0],'state':'Block{minecraft:torch}'}],
                'scan_cells_read':1,'scan_total_cells':1,'scan_start_revision':frame['control_revision'],
                'scan_end_revision':frame['control_revision'],'scan_entity_scope':ENTITY_SCOPE_AT_SCAN_END,'scan_entities':[]}
            write(source/f'actual-torch-0-frame-{index}.json',raw);write(source/f'inventory-after-0-frame-{index}.json',frame)
        worker.book['batches'][0]['placed_verified']=1;worker.save();write(path,worker.book)
        return source

    def test_actual_two_frame_torch_epoch_is_verified_and_prefix_must_be_later(self):
        worker,current,calls,path,write,directory=self.fixture();self.torch(worker,current,path,write)
        proof=validate(worker,path,current);self.assertEqual(900,proof['last_actual_torch_at'])
        self.assertEqual(1,len(proof['torch_receipts']))
        worker,current,calls,path,write,directory=self.fixture();self.torch(worker,current,path,write,after_time=1001)
        self.refuse(worker);self.assertEqual([],calls)

    def test_missing_unknown_or_unconserved_torch_frame_refuses_prefix(self):
        for change in ('missing','count','block','interaction','time'):
            with self.subTest(change=change):
                worker,current,calls,path,write,directory=self.fixture();source=self.torch(worker,current,path,write)
                frame=source/'inventory-after-0-frame-2.json'
                if change=='missing':frame.unlink()
                elif change=='count':
                    value=json.loads(frame.read_text());value['inventory'][0]['count']=8;write(frame,value)
                elif change=='block':
                    target=source/'actual-torch-0-frame-2.json';value=json.loads(target.read_text());value['blocks']=[];write(target,value)
                elif change=='interaction':
                    target=source/'interaction-0.json';value=json.loads(target.read_text());value['phase']='waiting';write(target,value)
                else:
                    value=json.loads(frame.read_text());value['time']=850;write(frame,value)
                self.refuse(worker);self.assertEqual([],calls)

    def test_cli_forwards_explicit_flag_and_never_infers_a_prefix_from_length(self):
        with patch('lighting_regions_cli.main',return_value=0)as handler:
            self.assertEqual(kit_cli.main(['lighting','audit','--profile','/tmp/profile','--out','/tmp/out',
                                         '--audit-prefix','/tmp/prefix']),0)
            command=handler.call_args.args[0]
            self.assertIn('--audit-prefix',command);self.assertEqual('audit',command[-1])


if __name__=='__main__':unittest.main()
