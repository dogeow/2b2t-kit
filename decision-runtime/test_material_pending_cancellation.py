import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from material_client import Client
from material_jobs.protocol import JobCancelled
from material_jobs_backend import owns_material_state
from material_shutdown import drain_pending

class PendingCancellationTest(unittest.TestCase):
    def client(self,root):
        c=Client.__new__(Client);c.root=Path(root);c.out=c.root/'out';c.out.mkdir()
        c.server='simpcraft.com';c.world='world';c.rev=10;c.anchor=[10,90,20];c.last=None;c.native_inflight=None
        c.task='materials-job';c.heartbeat=SimpleNamespace(id='lease');c.owned=False
        c.status=lambda:{'server':c.server,'dimension':'minecraft:overworld','pos':c.anchor,'health':20,
                        'control_revision':10,'world_session':'world','guard_busy':False,'under_water':False,
                        'supervision_lease':{'id':'lease','kind':'materials','job_session':c.task,'revision':10}}
        return c
    def test_cancel_after_publish_preserves_owned_revision_and_drains_without_replay(self):
        with tempfile.TemporaryDirectory()as tmp:
            c=self.client(tmp);c.raw=lambda:(_ for _ in()).throw(JobCancelled('controlled update'))
            with self.assertRaises(JobCancelled):c.request('walk',target=[11,90,20],task_session=c.task)
            request=json.loads((c.root/'request.json').read_text());pending=c.native_inflight
            self.assertIsNotNone(pending);self.assertEqual(request['id'],pending['request_id']);self.assertEqual(11,pending['expected_revision'])
            state={'connected':True,'world_session':c.world,'server':c.server,'dimension':'minecraft:overworld',
             'manual_movement':False,'phase':'running','op':'walk','id':request['id'],'last_request':request['id'],
             'control_revision':11,'health':20,'supervision_lease':{'id':'lease','kind':'materials','world_session':c.world,
                                                                'job_session':c.task,'revision':11}}
            self.assertTrue(owns_material_state(c,state));
            terminal={**state,'phase':'done'};frames=iter([state,terminal]);c.raw=lambda:next(frames)
            with patch('material_shutdown.time.sleep'):result=drain_pending(c)
            self.assertTrue(result['safe_to_cleanup']);self.assertEqual(11,c.rev)
            self.assertEqual(request,json.loads((c.root/'request.json').read_text()))
            for changed in ({'manual_movement':True},{'world_session':'other'},{'last_request':'other'}):
                self.assertFalse(owns_material_state(c,{**state,'control_revision':12,**changed}))
    def test_unpublished_failure_does_not_create_pending_ownership(self):
        with tempfile.TemporaryDirectory()as tmp:
            c=self.client(tmp);c.last='old'
            with patch('pathlib.Path.replace',side_effect=OSError('publish failed')):
                with self.assertRaises(OSError):c.request('walk',target=[11,90,20],task_session=c.task)
            self.assertIsNone(c.native_inflight);self.assertEqual('old',c.last)

if __name__=='__main__':unittest.main()
