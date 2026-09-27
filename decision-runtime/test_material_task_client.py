from contextlib import redirect_stdout
import fcntl
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch

import material_task_client as api
import kit_cli


def state():
    return {'time':int(time.time()*1000),'connected':True,'server':'example.test:25565',
            'dimension':'minecraft:overworld','world_session':'world-a','control_revision':8,
            'material_task_api_protocol':1,'manual_movement':False,'safety_hold':{'active':False},
            'projection_selection':{'key':'locked-projection'},'last_request':'gameplay-owned'}


def receipt(request,**extra):
    return {'schema':1,'id':request['id'],'op':request['op'],'phase':'done','detail':'accepted only',
            'world_session':request.get('world_session',''),'control_revision':8,'observed_at':int(time.time()*1000),
            'material_task':{'id':request.get('job_id','material-job-new'),'state':'queued','detail':'planning',
                             'done':0,'total':800,'process_alive':True,'pid':1234,'world_session':'world-a'},**extra}


class MaterialTaskClientTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.state=state()
        (self.root/'status.json').write_text(json.dumps(self.state))

    def start(self):return api.make_request('material_task_start',self.state,mode='projection')

    def respond(self,request,*,reply=None,delay=.001):
        failures=[]
        def run():
            until=time.monotonic()+2
            try:
                while time.monotonic()<until:
                    path=self.root/'material-task-request.json'
                    if path.exists() and json.loads(path.read_text()).get('id')==request['id']:
                        time.sleep(delay)
                        value=receipt(request) if reply is None else reply
                        out=self.root/('material-task-reply-'+request['id']+'.json')
                        temp=out.with_suffix('.tmp');temp.write_text(json.dumps(value));temp.replace(out)
                        return
                    time.sleep(.001)
                failures.append('request was not published')
            except Exception as error:failures.append(error)
        thread=threading.Thread(target=run,daemon=True);thread.start()
        return thread,failures

    def send_replied(self,request,reply=None):
        thread,failures=self.respond(request,reply=reply)
        try:return api.send(self.root,request,timeout=1,poll_seconds=.002)
        finally:
            thread.join(timeout=2);self.assertFalse(failures)

    def test_projection_start_uses_selected_projection_fresh_scope_and_explicit_start(self):
        request=self.start()
        self.assertEqual('locked-projection',request['placement_key'])
        self.assertEqual('world-a',request['world_session']);self.assertEqual(8,request['expected_revision'])
        self.assertTrue(request['manual_start']);self.assertEqual('projection',request['mode'])
        self.assertGreater(request['expires_at'],int(time.time()*1000))
        self.assertFalse(set(request)&{'path','worker','python','background_ok','site','key','click'})

    def test_item_request_validates_actual_item_and_integer_quantity(self):
        request=api.make_request('material_task_start',self.state,mode='item',item='minecraft:white_concrete',count=64)
        self.assertEqual(('minecraft:white_concrete',64),(request['item'],request['count']))
        for count in (0,-1,True,1.5,1_000_001):
            with self.assertRaises(api.MaterialTaskError):api.make_request('material_task_start',self.state,mode='item',item='minecraft:stone',count=count)
        for item in ('stone','minecraft:air','minecraft:stone;stop','custom:block'):
            with self.assertRaises(api.MaterialTaskError):api.make_request('material_task_start',self.state,mode='item',item=item,count=1)

    def test_controls_require_job_identity_and_only_resume_is_explicit_start(self):
        for action in ('pause','resume','cancel'):
            with self.assertRaises(api.MaterialTaskError):api.make_request('material_task_'+action,self.state)
            request=api.make_request('material_task_'+action,self.state,job_id='material-job-a')
            self.assertEqual('material-job-a',request['job_id'])
            self.assertEqual(action=='resume',request.get('manual_start',False))

    def test_identifier_limit_matches_the_native_ninety_six_character_limit(self):
        self.assertEqual('a'*96,api.make_request('material_task_status',job_id='a'*96)['job_id'])
        with self.assertRaises(api.MaterialTaskError):api.make_request('material_task_status',job_id='a'*97)
        request=self.start();request['id']='a'*97
        with self.assertRaises(api.MaterialTaskError):api.send(self.root,request,timeout=.02)
        self.assertFalse((self.root/'material-task-request.json').exists())

    def test_request_byte_limit_matches_native_limit_and_counts_utf8_bytes(self):
        request=self.start()
        length=len(api._request_bytes(request))
        request['server']='x'*(api.MAX_REQUEST_BYTES-length+len(request['server']))
        self.assertEqual(16384,len(api._request_bytes(request)))
        self.state['server']=request['server'];(self.root/'status.json').write_text(json.dumps(self.state))
        self.assertEqual('done',self.send_replied(request)['phase'])
        for server in (request['server']+'x','界'*6000):
            oversized={**request,'id':'new-request','server':server}
            # Keep the ID length equal so the first case is exactly one byte over.
            oversized['id']=request['id']
            with self.assertRaisesRegex(api.MaterialTaskError,'16384'):api.send(self.root,oversized,timeout=.02)
        self.assertEqual(16384,(self.root/'material-task-request.json').stat().st_size)

    def test_status_needs_no_world_or_live_status_file(self):
        (self.root/'status.json').unlink()
        request=api.make_request('material_task_status')
        self.assertEqual({'id','op'},set(request))
        result=self.send_replied(request)
        self.assertEqual('done',result['phase'])

    def test_sideband_does_not_touch_even_an_unconsumed_gameplay_request(self):
        gameplay=self.root/'request.json';gameplay.write_text('gameplay bytes deliberately not JSON')
        result=self.send_replied(self.start())
        self.assertEqual('gameplay bytes deliberately not JSON',gameplay.read_text())
        self.assertEqual('queued',result['material_task']['state'])
        self.assertEqual(0,result['material_task']['done'])
        compact=api.compact(result);self.assertTrue(compact['accepted']);self.assertNotIn('completed',compact)

    def test_existing_unconsumed_material_request_is_never_overwritten(self):
        path=self.root/'material-task-request.json';prior=api.make_request('material_task_status');path.write_text(json.dumps(prior))
        original=path.read_bytes()
        with self.assertRaisesRegex(api.MaterialTaskError,'未消费'):api.send(self.root,self.start(),timeout=.02)
        self.assertEqual(original,path.read_bytes())

    def test_matching_consumed_receipt_allows_next_distinct_request(self):
        prior=api.make_request('material_task_status')
        (self.root/'material-task-request.json').write_text(json.dumps(prior))
        (self.root/('material-task-reply-'+prior['id']+'.json')).write_text(json.dumps(receipt(prior)))
        next=self.start();result=self.send_replied(next)
        self.assertEqual(next['id'],result['id'])

    def test_wrong_operation_receipt_does_not_consume_existing_request(self):
        prior=api.make_request('material_task_status');(self.root/'material-task-request.json').write_text(json.dumps(prior))
        (self.root/('material-task-reply-'+prior['id']+'.json')).write_text(json.dumps(receipt(prior,op='material_task_cancel')))
        with self.assertRaisesRegex(api.MaterialTaskError,'未消费'):api.send(self.root,self.start(),timeout=.02)

    def test_timeout_sends_once_and_retains_request_instead_of_replaying(self):
        request=self.start()
        with patch.object(api,'_publish',wraps=api._publish) as publish:
            with self.assertRaises(api.MaterialTaskError) as error:api.send(self.root,request,timeout=.02,poll_seconds=.002)
        publish.assert_called_once();self.assertTrue(error.exception.submitted)
        self.assertEqual(request['id'],error.exception.request_id)
        self.assertEqual(request,json.loads((self.root/'material-task-request.json').read_text()))
        with self.assertRaisesRegex(api.MaterialTaskError,'未消费'):api.send(self.root,self.start(),timeout=.02)

    def test_lock_prevents_concurrent_publish(self):
        with (self.root/'.material-task-client.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(api.MaterialTaskError,'并发'):api.send(self.root,self.start(),timeout=.02)
        self.assertFalse((self.root/'material-task-request.json').exists())

    def test_changed_world_revision_or_projection_rejects_before_publish(self):
        request=self.start()
        for changed in ({'world_session':'other'},{'control_revision':9},{'projection_selection':{'key':'other'}}):
            (self.root/'status.json').write_text(json.dumps({**self.state,**changed}))
            with self.assertRaises(api.MaterialTaskError):api.send(self.root,request,timeout=.02)
            self.assertFalse((self.root/'material-task-request.json').exists())

    def test_old_host_expired_request_manual_input_and_injected_fields_reject(self):
        old={**self.state,'material_task_api_protocol':0}
        with self.assertRaisesRegex(api.MaterialTaskError,'更新主包'):api.make_request('material_task_start',old,mode='projection')
        with self.assertRaises(api.MaterialTaskError):api.make_request('material_task_start',{**self.state,'manual_movement':True},mode='projection')
        request=self.start();request['expires_at']=int(time.time()*1000)-1
        with self.assertRaises(api.MaterialTaskError):api.send(self.root,request,timeout=.02)
        request=self.start();request['worker']='/tmp/other.py'
        with self.assertRaises(api.MaterialTaskError):api.send(self.root,request,timeout=.02)
        self.assertFalse((self.root/'material-task-request.json').exists())

    def test_health_hold_blocks_start_resume_but_never_prevents_owned_cancel(self):
        path=self.root/'safety-hold.json';path.write_text('{"active":true}')
        before=path.read_bytes()
        for request in (self.start(),api.make_request('material_task_resume',self.state,job_id='material-job-a')):
            with self.assertRaises(api.MaterialTaskError):api.send(self.root,request,timeout=.02)
        request=api.make_request('material_task_cancel',self.state,job_id='material-job-a')
        self.assertEqual('done',self.send_replied(request)['phase']);self.assertEqual(before,path.read_bytes())

    def test_native_rejection_is_reported_not_retried(self):
        request=self.start();result=self.send_replied(request,receipt(request,phase='error',detail='another controller owns work'))
        self.assertEqual('error',result['phase']);self.assertFalse(api.compact(result)['accepted'])

    def test_startup_stale_error_without_task_snapshot_is_still_a_valid_receipt(self):
        request=self.start();reply={'schema':1,'id':request['id'],'op':request['op'],'phase':'error','detail':'stale at host startup','observed_at':int(time.time()*1000)}
        result=self.send_replied(request,reply);self.assertEqual('error',result['phase'])
        self.assertEqual({},api.compact(result)['material_task'])

    def test_done_reply_cannot_confirm_a_different_task_or_world(self):
        for wrong in ('task','world'):
            request=api.make_request('material_task_pause',self.state,job_id='material-job-a')
            reply=receipt(request)
            if wrong=='task':reply['material_task']['id']='other'
            else:reply['world_session']='other'
            with self.assertRaises(api.MaterialTaskError):self.send_replied(request,reply)

    def test_cli_projection_and_item_start_print_compact_acceptance_without_completion_claim(self):
        request=self.start();reply=receipt(request)
        for arguments,method,params in ((['start','--projection'],'start_projection',()),
                                       (['start','--item', 'minecraft:white_concrete','--count','64'],'start_item',('minecraft:white_concrete',64))):
            with patch.object(api,'MaterialTaskClient') as client,redirect_stdout(io.StringIO()) as output:
                getattr(client.return_value,method).return_value=reply
                self.assertEqual(0,kit_cli.main(['--game-dir',str(self.root),'materials',*arguments]))
            getattr(client.return_value,method).assert_called_once_with(*params)
            result=json.loads(output.getvalue());self.assertTrue(result['accepted']);self.assertEqual('queued',result['material_task']['state'])

    def test_cli_controls_require_explicit_job_and_preserve_local_error_submission_status(self):
        for action in ('pause','resume','cancel','status'):
            with patch.object(api,'MaterialTaskClient') as client,redirect_stdout(io.StringIO()) as output:
                getattr(client.return_value,action).return_value=receipt(api.make_request('material_task_status'))
                self.assertEqual(0,kit_cli.main(['materials',action,'--job-id','material-job-a']))
            getattr(client.return_value,action).assert_called_once_with('material-job-a')
        with patch.object(api,'MaterialTaskClient') as client,redirect_stdout(io.StringIO()) as output:
            client.return_value.start_projection.side_effect=api.MaterialTaskError('timeout',submitted=True,request_id='pending',op='material_task_start')
            self.assertEqual(2,kit_cli.main(['materials','start','--projection']))
        result=json.loads(output.getvalue());self.assertTrue(result['submitted']);self.assertEqual('pending',result['id'])


if __name__=='__main__':unittest.main()
