"""A persisted health exit blocks even a new explicit resume before any backend exists."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from material_jobs import MaterialJob
from material_jobs_cli import serve
from safety_interlock import record_material_health_exit

class HealthGoalRestartTest(unittest.TestCase):
    def request(self):
        return {'schema':1,'id':'health-stop','mode':'item','targets':{'minecraft:dirt':10},'created_at':1,
                'context':{'server':'example.test','dimension':'minecraft:overworld','world_session':'w',
                           'expected_revision':1,'start_pos':[0,64,0]}}
    def test_recorded_minor_health_exit_blocks_new_goal_before_backend_or_rpc(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);record_material_health_exit(root,{'time':100,'health':19},'owned damage logout')
            factory=Mock();result=serve(self.request(),root,root/'job',factory)
            self.assertEqual('blocked',result['state']);factory.assert_not_called()
    def test_valid_resume_cannot_bypass_health_hold_or_create_a_client(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'job';request=self.request()
            job=MaterialJob(request,out);job._write('paused','health exit',terminal=False)
            (out/'control.json').write_text(json.dumps({'id':request['id'],'action':'resume','created_at':200,
                                                      'context':request['context']}))
            record_material_health_exit(root,{'time':100,'health':19},'owned damage logout')
            factory=Mock();result=serve(request,root,out,factory,poll_seconds=.001)
            self.assertEqual('blocked',result['state']);factory.assert_not_called()

if __name__=='__main__':unittest.main()
