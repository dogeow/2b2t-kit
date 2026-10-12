import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from material_jobs_backend import Backend

class RegisteredWorkbenchEgressTest(unittest.TestCase):
    def test_hardening_loads_registered_base_before_reading_enclosure(self):
        with tempfile.TemporaryDirectory()as tmp:
            b=self.job(tmp,{});order=[];b.profile['concrete_station']={'support':[10,61,20]}
            @contextmanager
            def action(name):yield object(),Path(tmp)
            b.action=action;b.checkpoint=lambda:None
            b.prepare_travel=lambda:order.append('travel')
            b.stage_near_base=lambda positions:order.append(('load',positions))
            with patch('material_jobs.processing.harden',side_effect=lambda *args:order.append('harden')):
                b.harden('minecraft:black_concrete',42)
            self.assertEqual(['travel',('load',[[10,61,20]]),'harden'],order)
    def job(self,root,state):
        b=Backend.__new__(Backend);b.out=Path(root)
        b.profile={'workbench':[10,65,20],'workbench_exit':[{'kind':'walk','target':[11.5,65,26.5]}]}
        b.ensure_client=lambda:SimpleNamespace(status=lambda:state);b.route=Mock()
        return b
    def test_new_ground_job_near_indoor_workbench_reuses_exit_before_projection_ascent(self):
        with tempfile.TemporaryDirectory()as tmp:
            b=self.job(tmp,{'pos':[10.5,65,22.5],'world_session':'world','flight':False})
            b.close_owned_menu=Mock();order=[];b.route.side_effect=lambda name:order.append(name)
            with patch('material_jobs.construction_access.recover_pending'),patch('material_jobs_backend.leave_quarry',return_value=True),\
                 patch('material_jobs_backend.leave_projection',side_effect=lambda c:order.append('projection_ascent')):
                b.prepare_travel()
            self.assertEqual(['workbench_exit','projection_ascent'],order)
            self.assertTrue((b.out/'registered-workbench-egress.json').exists())
    def test_flying_outside_underwater_or_another_floor_does_not_reenter_workshop(self):
        for state in ({'pos':[10.5,95,20.5],'flight':True},{'pos':[10.5,60,20.5]},
                      {'pos':[10.5,65,28.5]},{'pos':[10.5,65,20.5],'under_water':True}):
            with tempfile.TemporaryDirectory()as tmp:
                b=self.job(tmp,state);self.assertFalse(b.leave_registered_workbench());b.route.assert_not_called()

if __name__=='__main__':unittest.main()
