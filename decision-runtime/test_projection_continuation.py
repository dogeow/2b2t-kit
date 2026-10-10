from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from material_jobs.projection_continuation import can_continue_after_manual, run


class ManualContinuationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.state={'connected':True,'world_session':'w','health':20,'safety_hold':{'active':False},'supervision_lease':None}

    def check(self,result):
        with patch('material_jobs.projection_continuation.read_fresh',return_value=self.state):
            return can_continue_after_manual(self.root,'w',result)

    def test_exact_manual_control_change_waits_for_new_current_intent(self):
        self.assertTrue(self.check({'state':'failed','detail':'Control revision changed outside the owned request'}))

    def test_early_flight_manual_handoff_without_material_step_returns_to_wait(self):
        result={'state':'blocked','detail':'Control or world changed; no more commands','steps':0,
                'work_detail_before_finish':'Meteor Flight 已关闭，区域飞行已停止'}
        self.assertTrue(self.check(result))
        self.assertFalse(self.check({**result,'steps':1}))
        self.assertFalse(self.check({**result,'work_detail_before_finish':'Native mud action uncertain; no replay'}))

    def test_unknown_action_health_foreign_owner_world_and_completed_never_retry(self):
        self.assertFalse(self.check({'state':'failed','detail':'Native mud action uncertain; no replay'}))
        self.assertFalse(self.check({'state':'completed','detail':'Control revision changed outside the owned request'}))
        for key,value in [('world_session','other'),('health',18),('supervision_lease',{'id':'another'}),('connected',False)]:
            before=self.state[key];self.state[key]=value
            self.assertFalse(self.check({'state':'failed','detail':'Control revision changed outside the owned request'}));self.state[key]=before

    def test_new_authorized_goal_binds_only_exact_idle_parking_task(self):
        first = {**self.state, 'server': 'example.test', 'dimension': 'minecraft:overworld',
                 'control_revision': 7, 'pos': [1, 90, 2], 'projection_selection': {'key': 'ship'}}
        request = {'projection_key': 'ship', 'context': {'server': 'example.test', 'dimension': 'minecraft:overworld'}}
        for kind, world, revision, expected in [('parking', 'w', 7, 'park-task'),
                                               ('materials', 'w', 7, None),
                                               ('parking', 'other', 7, None),
                                               ('parking', 'w', 6, None)]:
            first['supervision_lease'] = {'kind': kind, 'world_session': world,
                                          'revision': revision, 'job_session': 'park-task'}
            seen = []
            def check_wait(job):
                seen.append(job.state.get('native_task_session'))
                raise RuntimeError('stop before any action')
            with self.subTest(kind=kind, world=world, revision=revision), \
                    patch('material_jobs.projection_continuation.read_fresh', return_value=first), \
                    patch('material_jobs.projection_continuation.StationaryResume') as watcher:
                watcher.return_value.poll.side_effect = check_wait
                with self.assertRaisesRegex(RuntimeError, 'stop before any action'):
                    run(self.root, request, self.root / ('%s-%s-%s' % (kind, world, revision)))
            self.assertEqual(seen, [expected])


if __name__=='__main__':unittest.main()
