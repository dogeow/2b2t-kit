from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from material_jobs.projection_continuation import can_continue_after_manual


class ManualContinuationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.state={'connected':True,'world_session':'w','health':20,'safety_hold':{'active':False},'supervision_lease':None}

    def check(self,result):
        with patch('material_jobs.projection_continuation.read_fresh',return_value=self.state):
            return can_continue_after_manual(self.root,'w',result)

    def test_exact_manual_control_change_waits_for_new_current_intent(self):
        self.assertTrue(self.check({'state':'failed','detail':'Control revision changed outside the owned request'}))

    def test_unknown_action_health_foreign_owner_world_and_completed_never_retry(self):
        self.assertFalse(self.check({'state':'failed','detail':'Native mud action uncertain; no replay'}))
        self.assertFalse(self.check({'state':'completed','detail':'Control revision changed outside the owned request'}))
        for key,value in [('world_session','other'),('health',18),('supervision_lease',{'id':'another'}),('connected',False)]:
            before=self.state[key];self.state[key]=value
            self.assertFalse(self.check({'state':'failed','detail':'Control revision changed outside the owned request'}));self.state[key]=before


if __name__=='__main__':unittest.main()
