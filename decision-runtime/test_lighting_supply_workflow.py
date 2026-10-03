import json
from pathlib import Path
import tempfile
import time
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from lighting_supply_workflow import LightingSupplyWorkflow, WorkflowWaiting
from test_lighting_cli import inventory


def state():
    return {'connected':True,'server':'simpcraft.com','dimension':'minecraft:overworld','world_session':'world',
        'time':int(time.time()*1000),'control_revision':5,'manual_movement':False,'health':20,'screen':'',
        'material_task_api_protocol':1,'guard_armed':True,'guard_pve_only':True,'flight':True,
        'material_task':{'occupied':False,'process_alive':False},
        'supervision_lease':{'kind':'parking','world_session':'world','revision':5,'job_session':'native-job'},'inventory':inventory(0)}


class WorkflowTest(unittest.TestCase):
    def fixture(self, root, current=None, sender=None, task_status=None):
        self.current=current or state();self.starts=[]
        worker=SimpleNamespace(root=Path(root)/'automation',out=Path(root)/'output',
             profile={'server':'simpcraft.com','dimension':'minecraft:overworld'},observer=lambda:self.current)
        worker.root.mkdir();worker.out.mkdir()
        def accept(request):
            self.starts.append(request)
            return {'phase':'done','material_task':{'id':'original-job','state':'queued'}}
        return LightingSupplyWorkflow(lambda:worker,observer=lambda:self.current,sender=sender or accept,
                  task_status=task_status or (lambda job:{'phase':'done','material_task':{'id':job,'state':'paused'}}),
                  sleeper=lambda seconds:None)
    def test_start_acceptance_is_not_supply_completion(self):
        with tempfile.TemporaryDirectory() as root:
            flow=self.fixture(root);flow.begin_supply()
            self.assertEqual('original-job',flow.book['pending']['job_id']);self.assertEqual([],flow.book['supplies'])
            self.assertEqual(1,len(self.starts))
            with self.assertRaises(WorkflowWaiting):flow.finish_supply()
            self.assertIsNotNone(flow.book['pending'])
    def test_one_exact_completed_native_job_requires_backpack_count_and_park_owner(self):
        with tempfile.TemporaryDirectory() as root:
            flow=self.fixture(root,task_status=lambda job:{'phase':'done','material_task':{'id':job,'state':'completed',
                              'process_alive':False,'occupied':False,'native_task_session':'native-job'}})
            flow.begin_supply();self.current['inventory']=inventory(64);self.current['inventory'][1].update(item='minecraft:torch',count=64);flow.finish_supply()
            self.assertIsNone(flow.book['pending']);self.assertEqual(128,flow.book['supplies'][0]['backpack_torches'])
            self.assertEqual(1,len(self.starts))
    def test_timeout_preserves_original_start_and_never_replays(self):
        def fail(request):raise RuntimeError('observation timeout')
        with tempfile.TemporaryDirectory() as root:
            flow=self.fixture(root,sender=fail)
            with self.assertRaises(RuntimeError):flow.begin_supply()
            saved=json.loads(flow.path.read_text());self.assertTrue(saved['pending']['request']['id'])
            with self.assertRaises(WorkflowWaiting):flow.begin_supply()
            with self.assertRaises(WorkflowWaiting):flow.finish_supply()
    def test_wrong_world_manual_input_or_other_server_cannot_start_new_supply(self):
        for key,value in (('manual_movement',True),('health',12),('server','other.invalid')):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as root:
                current=state();current[key]=value;flow=self.fixture(root,current)
                with self.assertRaises(WorkflowWaiting):flow.begin_supply()
                self.assertEqual([],self.starts)
    def test_completed_label_without_actual_stock_or_foreign_parking_never_succeeds(self):
        for change in ('stock','owner'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as root:
                flow=self.fixture(root,task_status=lambda job:{'phase':'done','material_task':{'id':job,'state':'completed',
                                  'process_alive':False,'occupied':False,'native_task_session':'native-job'}})
                flow.begin_supply()
                if change=='owner':
                    self.current['inventory']=inventory(64);self.current['inventory'][1].update(item='minecraft:torch',count=64);self.current['supervision_lease']['job_session']='foreign'
                with self.assertRaises(WorkflowWaiting):flow.finish_supply()
                self.assertEqual([],flow.book['supplies']);self.assertIsNotNone(flow.book['pending'])
    def test_foreign_native_reply_and_world_change_do_not_resume_lighting(self):
        for change in ('reply','world'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as root:
                flow=self.fixture(root,task_status=lambda job:{'phase':'done','material_task':{'id':'foreign','state':'completed'}})
                flow.begin_supply()
                if change=='world':self.current['world_session']='other'
                with self.assertRaises(WorkflowWaiting):flow.finish_supply()
                self.assertIsNotNone(flow.book['pending'])
    def test_existing_region_worker_is_joined_without_duplicate_action_controller(self):
        with tempfile.TemporaryDirectory() as root:
            flow=self.fixture(root);worker=flow.factory();polls=[True,False]
            worker.status=lambda:{'worker_running':polls.pop(0)}
            worker.run=lambda resume:{'phase':'audited','pending':None}
            result=flow.run()
            self.assertEqual('audited',result['phase']);self.assertEqual([],self.starts)


if __name__=='__main__':unittest.main()
