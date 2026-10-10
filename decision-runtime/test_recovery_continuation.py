import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from material_client import Handoff
from material_jobs.recovery_continuation import handoff_can_wait


class HandoffTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.request={'context':{'world_session':'w'}}
        self.state={'connected':True,'world_session':'w','health':20,'supervision_lease':None,
                    'safety_hold':{'active':False},'manual_movement':True}

    def check(self,error=None):
        with patch('material_jobs.recovery_continuation.read_fresh',return_value=self.state):
            return handoff_can_wait(self.root,self.request,error or Handoff('Control or world changed; no more commands'),self.root)

    def test_manual_handoff_before_seed_dispatch_returns_to_existing_wait(self):
        self.assertTrue(self.check())

    def test_pending_seed_foreign_owner_world_or_health_never_auto_replays(self):
        for key,value in [('world_session','other'),('health',18),('supervision_lease',{'id':'other'}),('connected',False)]:
            previous=self.state[key];self.state[key]=value
            self.assertFalse(self.check());self.state[key]=previous
        folder=self.root/'current-cell-restoration';folder.mkdir()
        (folder/'current-cell-restoration.json').write_text(json.dumps({'pending':{'kind':'new_seed_use'}}))
        self.assertFalse(self.check())

    def test_generic_action_failures_never_become_stationary_retry(self):
        self.assertFalse(self.check(RuntimeError('unknown movement')))
        self.assertFalse(self.check(Handoff('Another controller has a pending request')))


if __name__=='__main__':unittest.main()
