import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
from types import SimpleNamespace
from material_client import Handoff
from material_jobs.recovery_continuation import handoff_can_wait,recover_attempt


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

    def test_high_hover_over_registered_field_descends_before_restoration_and_finishes_once(self):
        old=self.root/'old.json';old.write_text(json.dumps({'pending':{'pos':[27,64,70]}}))
        state={'server':'server','dimension':'minecraft:overworld','pos':[29.5,90,69.5],
               'inventory':[{'slot':0,'item':'minecraft:wheat_seeds','count':5}]}
        c=SimpleNamespace(status=lambda:state,task='task',checked=Mock(),finish=Mock(return_value=True))
        center=[29,64,69];layout={'center':center,'cells':[[27,64,70]]}
        with patch('material_jobs.recovery_continuation.MaterialClient',return_value=c), \
             patch('material_jobs.registered_wheat.registered_fields',return_value=iter([({},self.root)])), \
             patch('potato_farm.plan',return_value=layout), \
             patch('material_jobs.recovery_continuation.restore',return_value={'complete':True,'new_reseed':0})as restored, \
             patch('material_jobs.recovery_continuation.local_park',return_value=[29.5,88,69.5]), \
             patch('material_jobs.recovery_continuation.settled_state',return_value={'pos':[29.5,88,69.5]}), \
             patch('material_jobs.recovery_continuation.lift_for_travel')as lift:
            self.assertEqual('task',recover_attempt(self.root,{},old,self.root/'pickup.json',self.root/'attempt',state))
        self.assertEqual([29.5,65.6,69.5],c.checked.call_args_list[0].kwargs['target'])
        self.assertEqual('navigate',c.checked.call_args_list[0].args[0]);lift.assert_not_called()
        restored.assert_called_once();c.finish.assert_called_once()


if __name__=='__main__':unittest.main()
