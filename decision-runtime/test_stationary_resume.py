import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_jobs import MaterialJob
from material_jobs.stationary_resume import StationaryResume


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=0
        request={'schema':1,'id':'j','mode':'item','targets':{'minecraft:stone':1},'created_at':100,
                 'context':{'server':'server:25565','dimension':'minecraft:overworld','world_session':'w',
                            'expected_revision':1,'start_pos':[.5,64.,.5]}}
        self.job=MaterialJob(request,self.root/'job');self.job._write('paused')
        self.state={'time':200,'connected':True,'manual_movement':False,'screen':'',
                    'server':'server','dimension':'minecraft:overworld','world_session':'w',
                    'control_revision':4,'pos':[.5,64.,.5],'velocity':[0,-.0784,0],'on_ground':True,
                    'health':20.,'food':20,'guard_busy':False,'under_water':False,
                    'menu':{'id':0,'type':'InventoryMenu','cursor':{'count':0}},'supervision_lease':{}}
        self.watch=StationaryResume(self.root,clock=lambda:self.now)
        self.policy={'schema':1,'resume_paused_when_stationary':True}
        self.write_policy()
        self.patch=patch('material_jobs.stationary_resume.read_fresh',side_effect=lambda *_:copy.deepcopy(self.state))
        self.patch.start();self.addCleanup(self.patch.stop)

    def write_policy(self):
        (self.root/'autonomous-policy.json').write_text(json.dumps(self.policy))

    def poll(self,at):
        self.now=at;self.state['time']=200+int(at*1000);return self.watch.poll(self.job)

    def test_standing_authorization_resumes_same_paused_intent_after_actual_stable_frames(self):
        self.assertFalse(self.poll(0));self.assertFalse(self.poll(2.9));self.assertTrue(self.poll(3))
        self.assertEqual(4,self.job.context['expected_revision'])
        saved=json.loads((self.job.out/'resume-context.json').read_text())
        self.assertEqual('standing_stationary_policy',saved['source'])
        self.assertEqual('w',saved['context']['world_session'])
        self.assertIsNone(self.job.backend)

    def test_disabled_missing_or_malformed_policy_never_resumes(self):
        for contents in ('{}','[]','bad'):
            with self.subTest(contents=contents):
                (self.root/'autonomous-policy.json').write_text(contents)
                self.assertFalse(self.poll(0));self.assertFalse(self.poll(9))
        (self.root/'autonomous-policy.json').unlink();self.assertFalse(self.poll(20))

    def test_manual_movement_or_position_drift_restarts_the_whole_quiet_window(self):
        self.assertFalse(self.poll(0));self.state['manual_movement']=True;self.assertFalse(self.poll(2))
        self.state['manual_movement']=False;self.assertFalse(self.poll(3));self.assertFalse(self.poll(5.9))
        self.state['pos'][0]+=.2;self.assertFalse(self.poll(6));self.assertFalse(self.poll(8.9))
        self.assertTrue(self.poll(9))

    def test_revision_change_needs_a_new_stable_window(self):
        self.assertFalse(self.poll(0));self.state['control_revision']=5;self.assertFalse(self.poll(3))
        self.assertFalse(self.poll(5.9));self.assertTrue(self.poll(6))

    def test_foreign_world_health_menu_native_work_and_foreign_owner_never_resume(self):
        changes=[{'world_session':'other'},{'server':'other'},{'dimension':'minecraft:the_nether'},
                 {'health':18.9},{'food':7},{'screen':'InventoryScreen'},{'manual_movement':True},
                 {'guard_busy':True},{'under_water':True},{'navigating':True},
                 {'native_material_busy':True},{'pending_scan':{}},{'velocity':[.1,0,0]},
                 {'menu':{'id':0,'type':'InventoryMenu','cursor':{'count':1}}},
                 {'supervision_lease':{'kind':'parking','job_session':'other','world_session':'w','revision':4}}]
        original=copy.deepcopy(self.state)
        for change in changes:
            with self.subTest(change=change):
                self.state=original|change;self.watch.reset()
                self.assertFalse(self.poll(0));self.assertFalse(self.poll(10))
        self.assertFalse((self.job.out/'resume-context.json').exists())

    def test_only_this_tasks_current_parking_lease_is_eligible(self):
        self.job.state['native_task_session']='own'
        self.state['supervision_lease']={'kind':'parking','job_session':'own','world_session':'w','revision':4}
        self.assertFalse(self.poll(0));self.assertTrue(self.poll(3))

    def test_existing_safety_hold_is_not_cleared_by_standing_resume(self):
        p=self.root/'safety-hold.json';p.write_text(json.dumps({'active':True}));before=p.read_bytes()
        self.assertFalse(self.poll(0));self.assertFalse(self.poll(9));self.assertEqual(before,p.read_bytes())

    def test_projection_selection_must_still_be_the_original_intent(self):
        self.job.request.update(mode='projection',projection_key='map')
        self.state['projection_selection']={'key':'other'}
        self.assertFalse(self.poll(0));self.assertFalse(self.poll(9))
        self.state['projection_selection']={'key':'map'}
        self.assertFalse(self.poll(10));self.assertTrue(self.poll(13))

    def test_unknown_original_receipt_is_left_for_existing_reconciler(self):
        p=self.job.out/'inflight.json';p.write_text('{"sequence":7,"operation":"run_pipeline"}')
        before=p.read_bytes();self.assertFalse(self.poll(0));self.assertTrue(self.poll(3))
        self.assertEqual(before,p.read_bytes())

    def test_one_snapshot_cannot_prove_three_seconds_of_current_observation(self):
        self.assertFalse(self.poll(0));self.now=3
        self.assertFalse(self.watch.poll(self.job))

    def test_cancelled_task_is_not_automatically_reclassified_as_paused(self):
        self.job.state['state']='cancelled'
        self.assertFalse(self.poll(0));self.assertFalse(self.poll(9))


if __name__=='__main__':unittest.main()
