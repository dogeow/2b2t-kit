import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from native_outcome_fence import RetainedUnknownMaterialClient, exact_idle_terminal


class NativeOutcomeFenceTests(TestCase):
    def setup_case(self, op='navigate', phase='done'):
        client=SimpleNamespace(last='rid',task='task',world='world',native_inflight=None,
            heartbeat=SimpleNamespace(id='lease'),unconfirmed_native_request=None,
            last_terminal_evidence={'request_id':'rid','task_session':'task','world_session':'world',
                                    'revision_after':4,'op':op,'phase':phase})
        state={'connected':True,'world_session':'world','last_request':'rid','control_revision':4,
               'manual_movement':False,'supervision_lease':{'id':'lease','kind':'materials',
               'job_session':'task','world_session':'world','revision':4}}
        return client,state

    def test_exact_done_or_returned_snapshot(self):
        for op,phase in [('navigate','done'),('scan','done'),('snapshot',None),('navigate','waiting')]:
            c,s=self.setup_case(op,phase)
            self.assertTrue(exact_idle_terminal(c,s))

    def test_stale_outer_done_does_not_prove_a_new_scan(self):
        c,s=self.setup_case()
        c.last='new_scan';s['last_request']='new_scan';s['phase']='done'
        self.assertFalse(exact_idle_terminal(c,s))

    def test_even_empty_pending_scan_is_unknown(self):
        c,s=self.setup_case();s['pending_scan']={}
        self.assertFalse(exact_idle_terminal(c,s))

    def test_uncertain_mutating_error_cannot_cleanup(self):
        for op in ('slot_click','interact','projection_scaffold_fill','professional_print'):
            c,s=self.setup_case(op,'error')
            self.assertFalse(exact_idle_terminal(c,s))

    def test_world_task_revision_and_owner_are_exact(self):
        c,s=self.setup_case()
        for key,value in [('request_id','other'),('task_session','other'),('world_session','other'),('revision_after',3)]:
            original=c.last_terminal_evidence[key];c.last_terminal_evidence[key]=value
            self.assertFalse(exact_idle_terminal(c,s));c.last_terminal_evidence[key]=original
        s['supervision_lease']['id']='foreign'
        self.assertFalse(exact_idle_terminal(c,s))

    def test_base_timeout_clears_inflight_but_fence_blocks_next_operation(self):
        with TemporaryDirectory() as directory:
            client=RetainedUnknownMaterialClient.__new__(RetainedUnknownMaterialClient)
            client.last='old';client.world='world';client.task='task'
            client.heartbeat=SimpleNamespace(id='lease');client.root=client.out=Path(directory)
            client.last_terminal_evidence={'request_id':'old'};client.native_inflight=None
            client.unconfirmed_native_request=None
            (client.root/'request.json').write_text(json.dumps({'id':'new','world_session':'world','op':'scan'}))
            def timeout(self,op,**params):
                self.last='new';self.native_inflight=None
                raise RuntimeError('Native operation timed out; do not replay it')
            with patch('native_outcome_fence.MaterialClient.request',timeout):
                with self.assertRaisesRegex(RuntimeError,'timed out'):client.request('scan',min=[0,0,0],max=[0,0,0])
            self.assertEqual(client.unconfirmed_native_request['request_id'],'new')
            self.assertEqual(json.loads((client.out/'preserved-original-mailbox.json').read_text())['id'],'new')
            with patch('native_outcome_fence.MaterialClient.request') as native:
                for op in ('scan','material_job_park','safe_logout'):
                    with self.assertRaisesRegex(RuntimeError,'unknown'):client.request(op)
                native.assert_not_called()

    def test_finish_refuses_before_any_base_cleanup(self):
        c,s=self.setup_case();client=RetainedUnknownMaterialClient.__new__(RetainedUnknownMaterialClient)
        client.__dict__.update(c.__dict__);client.raw=Mock(return_value={**s,'pending_scan':{}})
        with patch('native_outcome_fence.MaterialClient.finish') as cleanup:
            with self.assertRaisesRegex(RuntimeError,'unproved'):client.finish()
            cleanup.assert_not_called()
