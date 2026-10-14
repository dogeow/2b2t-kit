import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
from unittest.mock import patch,Mock
from material_jobs.storage_exit import center_target,center


class StorageExitTest(unittest.TestCase):
    def state(self,**changes):
        return {'world_session':'world','pos':[100.60,64,100.68],
            'air_only_navigation_protocol':2,'on_ground':True,'flight':False,
            'health':20,'food':20,'manual_movement':False,'screen':'',
            'guard_busy':False,'under_water':False,'guard_armed':True,
            'guard_pve_only':True,'inventory':[{'slot':0,'item':'minecraft:red_terracotta','count':42}],**changes}
    def test_warehouse_edge_uses_same_height_center_not_another_ground_walk(self):
        self.assertEqual([100.5,64,100.5],center_target(self.state()))
        self.assertIsNone(center_target(self.state(pos=[100.5,64,100.5])))
    def test_manual_ui_health_or_unsupported_protocol_never_centres(self):
        for change in ({'manual_movement':True},{'screen':'InventoryScreen'},{'health':19},
                       {'guard_busy':True},{'air_only_navigation_protocol':1},{'under_water':True}):
            self.assertIsNone(center_target(self.state(**change)))
    def test_settled_actual_pose_is_used_and_inventory_is_preserved(self):
        with tempfile.TemporaryDirectory()as t:
            initial=self.state();stopped=self.state(pos=[100.39,64,100.30])
            actual=self.state(pos=[100.49,64,100.48],flight=True)
            c=SimpleNamespace(world='world',out=Path(t),status=lambda:deepcopy(initial),checked=Mock(return_value={'phase':'done'}))
            with patch('material_jobs.navigation.settled_state',side_effect=[stopped,actual]):
                self.assertTrue(center(c))
            c.checked.assert_called_once_with('navigate',target=[100.5,64,100.5],arrival=.15,air_only=True,seconds=25)
            self.assertTrue(list(Path(t).glob('warehouse-exit-center-*.json')))
    def test_unknown_native_arrival_never_creates_a_success_record_or_retry(self):
        with tempfile.TemporaryDirectory()as t:
            state=self.state();c=SimpleNamespace(world='world',out=Path(t),status=lambda:state,checked=Mock(side_effect=RuntimeError('unknown')))
            with patch('material_jobs.navigation.settled_state',return_value=state):
                with self.assertRaisesRegex(RuntimeError,'unknown'):center(c)
            c.checked.assert_called_once();self.assertEqual([],list(Path(t).iterdir()))

if __name__=='__main__':unittest.main()
