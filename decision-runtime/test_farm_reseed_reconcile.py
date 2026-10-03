"""Only audited exact pre-use rejection can be retired; unknown actions remain locked."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from farm_reseed import run,prepare_journal,read,_TravelClient
from farm_reseed_reconcile import (REJECTION,HOST_VERSION,HOST_CLASS_SHA256,reconcile_rejected)
from test_farm_reseed import RegisteredClient


CONTRACT={'kit_version':HOST_VERSION,'class_sha256':HOST_CLASS_SHA256,'contract':'audited pre-use branch'}


class RejectedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.c=RegisteredClient(self.root);self.out=self.root/'maintenance';self.control=self.out/'reseed-control';self.control.mkdir(parents=True)
        self.c.out=self.control;self.c.last='materials-rejected';self.rid=self.c.last
        self.journal,_=prepare_journal(self.root,self.c.registry,[self.c.cell],self.c.world,self.out,server=self.c.server)
        self.reply=self.c.status()|{'id':self.rid,'phase':'error','detail':REJECTION,'kit_version':HOST_VERSION}
        self.reply['supervision_lease'].update(id='lease',remote_finish='guard')
        self.book=read(self.journal);self.book['pending']={'operation':'plant','pos':self.c.cell,
            'before_counts':{row['item']:sum(r['count'] for r in self.reply['inventory'] if r['slot']<36 and r['item']==row['item']) for row in self.reply['inventory'] if row['slot']<36 and row['count']},
            'hand_before':deepcopy(self.reply['hand']),'expected_state':'Block{minecraft:farmland}[moisture=7]',
            'native_receipt':{key:self.reply[key] for key in ('id','phase','time','detail')}}
        # Real pending holds the selected seed stack, not a hoe.
        self.reply['hand']={'item':'minecraft:wheat_seeds','count':8,'max_stack':64};self.book['pending']['hand_before']=deepcopy(self.reply['hand'])
        self.events=[{'time':self.reply['time']/1000,'request_id':self.rid,'world_session':self.c.world,'op':'interact',
            'params':{'pos':self.c.cell,'face':'up','expected_state':self.book['pending']['expected_state'],'expected_hand':'minecraft:wheat_seeds','task_session':self.c.task},
            'phase':'error','detail':REJECTION,'inventory_delta':{},'revision_before':self.c.rev,'revision_after':self.c.rev,
            'position_before':self.reply['pos'],'position_after':self.reply['pos'],'health_before':20,'health_after':20},
            {'world_session':self.c.world,'op':'material_job_pause','params':{'task_session':self.c.task},'phase':'done','inventory_delta':{}}]
        self.write()
    def write(self):
        self.journal.write_text(json.dumps(self.book));(self.root/('reply-'+self.rid+'.json')).write_text(json.dumps(self.reply))
        (self.control/'events.jsonl').write_text('\n'.join(json.dumps(row) for row in self.events)+'\n')
    def verify(self,archive=False):
        with patch('farm_reseed_reconcile.verify_host',return_value=CONTRACT):
            return reconcile_rejected(self.root,self.c.registry,self.journal,self.control,archive_verified=archive)
    def test_check_is_read_only_and_archive_retains_original_rejection_without_success(self):
        old=self.journal.read_bytes();result=self.verify();self.assertEqual('verified_rejection',result['phase']);self.assertFalse(result['writes_performed'])
        self.assertEqual(old,self.journal.read_bytes());self.assertEqual(0,result['new_reseed'])
        result=self.verify(True);book=read(self.journal);self.assertEqual('rejected_without_use',book['outcome']);self.assertFalse(book['complete'])
        self.assertIsNone(book['pending']);self.assertTrue(book['closed_without_use']);self.assertEqual(0,book['new_reseed'])
        self.assertEqual(old,(Path(result['archive'])/'original-maintenance.json').read_bytes())
        fresh,_=prepare_journal(self.root,self.c.registry,[self.c.cell],self.c.world,self.root/'fresh',server=self.c.server)
        self.assertNotEqual(self.journal,fresh);self.assertEqual(0,read(fresh)['new_reseed'])
    def test_generic_rotation_error_inventory_delta_foreign_identity_or_second_mutation_never_archive(self):
        original_reply=deepcopy(self.reply);original_events=deepcopy(self.events)
        for fault in ('rotation_error','delta','seed_loss','wrong_id','extra_use','foreign_world','wrong_version','event_time'):
            with self.subTest(fault=fault):
                self.reply=deepcopy(original_reply);self.events=deepcopy(original_events)
                if fault=='rotation_error':self.reply['detail']='Interaction became occluded while rotating'
                if fault=='delta':self.events[0]['inventory_delta']={'minecraft:wheat_seeds':-1}
                if fault=='seed_loss':self.reply['inventory'][10]['count']-=1
                if fault=='wrong_id':self.events[0]['request_id']='materials-other'
                if fault=='extra_use':self.events.append({'world_session':self.c.world,'op':'interact','phase':'done','inventory_delta':{}})
                if fault=='foreign_world':self.events[0]['world_session']='foreign'
                if fault=='wrong_version':self.reply['kit_version']='other'
                if fault=='event_time':self.events[0]['time']+=10
                self.write();before=self.journal.read_bytes()
                with self.assertRaises(RuntimeError):self.verify(True)
                self.assertEqual(before,self.journal.read_bytes());self.assertTrue(read(self.journal)['pending'])
    def test_cross_connection_exact_old_no_use_is_retired_without_adopting_current_inventory(self):
        # Verification intentionally uses only old exact evidence. No observer or client is constructed.
        (self.root/'status.json').write_text('{"world_session":"new","connected":false,"inventory":[]}')
        result=self.verify(True);self.assertEqual('archived_rejection',result['phase']);self.assertEqual(0,result['game_actions_sent'])
    def test_corrected_approach_uses_listed_air_cell_center_not_source_water_center(self):
        self.book['pending']=None;self.journal.write_text(json.dumps(self.book));targets=[]
        def arrived(c,target,checkpoint,trace):
            targets.append(target);c.extra['pos']=target[:];trace.append({'target':target,'phase':'done'})
        with patch('material_jobs.acquisition._travel',side_effect=arrived):
            result=run(self.c,self.c.registry,[self.c.cell],allow_move=True,journal=self.journal)
        self.assertEqual('done',result['phase']);self.assertEqual([[self.c.cell[0]+.5,self.c.cell[1]+1.6,self.c.cell[2]+.5]],targets)
        self.assertEqual(1,len(self.c.interact_calls()))
    def test_live_exact_pre_use_rejection_archives_without_second_use(self):
        self.book['pending']=None;self.journal.write_text(json.dumps(self.book));original_request=self.c.request
        def rejected(op,**params):
            if op!='interact':return original_request(op,**params)
            self.c.calls.append((op,deepcopy(params)));self.c.last=self.rid
            reply=self.c.status()|{'id':self.rid,'phase':'error','detail':REJECTION,'kit_version':HOST_VERSION}
            event={'time':reply['time']/1000,'request_id':self.rid,'world_session':self.c.world,'op':op,
                'params':params|{'task_session':self.c.task},'phase':'error','detail':REJECTION,'inventory_delta':{},
                'revision_before':self.c.rev,'revision_after':self.c.rev,'position_before':reply['pos'],
                'position_after':reply['pos'],'health_before':20,'health_after':20}
            (self.control/'events.jsonl').write_text(json.dumps(event)+'\n');return reply
        with patch.object(self.c,'request',side_effect=rejected),patch('farm_reseed_reconcile.verify_host',return_value=CONTRACT):
            result=run(self.c,self.c.registry,[self.c.cell],journal=self.journal)
        self.assertEqual(('REJECTED_WITHOUT_USE',False,0),(result['code'],result['pending'],result['new_reseed']))
        self.assertEqual(1,len(self.c.interact_calls()));book=read(self.journal)
        self.assertTrue(book['closed_without_use']);self.assertFalse(book['complete']);self.assertEqual({},book['receipts'])
    def test_every_navigation_intent_is_saved_before_dispatch_and_unknown_leg_is_retained(self):
        self.book['pending']={'operation':'travel','pos':self.c.cell,'target':[1.5,80,2.5]};self.journal.write_text(json.dumps(self.book))
        before=self.c.status();client=_TravelClient(self.c,self.book,self.journal,lambda:None,before['recent_hurt_at'])
        observed=[]
        def rejected(op,**params):
            observed.append(read(self.journal)['pending']['native_pending']);self.c.last='materials-nav'
            return self.c.status()|{'id':self.c.last,'phase':'waiting','detail':'Unknown arrival'}
        with patch.object(self.c,'request',side_effect=rejected),self.assertRaisesRegex(RuntimeError,'original intent retained'):
            client.request('navigate',target=[1.5,80,2.5],air_only=True,arrival=.25,seconds=90)
        self.assertEqual('navigate',observed[0]['op']);self.assertNotIn('receipt',observed[0])
        self.assertEqual('waiting',read(self.journal)['pending']['native_pending']['receipt']['phase'])
        with self.assertRaisesRegex(RuntimeError,'unresolved'):client.request('navigate',target=[1.5,80,2.5])
    def test_healthy_rejected_wait_parks_before_heartbeat_close_but_unknown_wait_does_not(self):
        from potato_farm_cli import finish_or_yield
        from test_potato_farm_cli import FarmFinishTest
        for pending in (None,{'operation':'plant'}):
            with self.subTest(pending=pending):
                self.journal.write_text(json.dumps({'pending':pending}));client,_=FarmFinishTest().setup_client(self.out);order=[]
                client.checked.side_effect=lambda *args,**kwargs:order.append('park')
                def finished():
                    order.append('finish');(self.out/'stock-safety.json').write_text('{"action":"KEEP_PVE_GUARD","lease":"l"}')
                client.finish.side_effect=finished;client.heartbeat.close.side_effect=lambda:order.append('close')
                finish_or_yield(client,{'phase':'waiting','code':'REJECTED_WITHOUT_USE' if pending is None else 'WAIT_RECONCILE'},
                    self.journal,0,140,False,allow_settled_wait=True)
                self.assertEqual(['park','finish','close'] if pending is None else ['close'],order)
                if pending is not None:client.request.assert_called_once_with('material_job_pause',release=False)


if __name__=='__main__':unittest.main()
