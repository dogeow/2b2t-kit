import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from material_jobs.fixed_tree_ground import prepare,ready
from material_jobs.protocol import JobBlocked

class FixedTreeGroundTests(unittest.TestCase):
    def test_hovering_at_exact_floor_height_is_not_a_grounded_native_start(self):
        self.assertFalse(ready({'on_ground':False,'flight':True,'pos':[.5,64,.5]}))
        self.assertFalse(ready({'on_ground':True,'flight':True}))
        self.assertTrue(ready({'on_ground':True,'flight':False}))
    def test_no_ground_walk_is_sent_from_a_higher_unknown_or_unsafe_pose(self):
        c=Mock();c.world='w';c.task='t';c.status.return_value={'world_session':'w','health':20,'guard_armed':True,'guard_pve_only':True,
            'supervision_lease':{'job_session':'t'},'pos':[.5,67.5,.5],'on_ground':False,'flight':True}
        with self.assertRaises(JobBlocked):prepare(c,lambda:None)
        c.checked.assert_not_called()

if __name__=='__main__':unittest.main()
