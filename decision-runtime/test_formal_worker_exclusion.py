from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from material_client import MaterialClient, Handoff, formal_worker_allows_controller


class FormalWorkerExclusionTests(unittest.TestCase):
    def test_busy_formal_job_admits_only_its_existing_backend(self):
        for field in ('occupied','process_alive','cancelling'):
            state={'material_task':{'id':'formal',field:True}}
            self.assertFalse(formal_worker_allows_controller(state))
            self.assertFalse(formal_worker_allows_controller(state,'other'))
            self.assertTrue(formal_worker_allows_controller(state,'formal'))
        self.assertTrue(formal_worker_allows_controller({'material_task':{'occupied':False}}))

    def test_ad_hoc_client_cannot_preempt_or_open_a_second_controller(self):
        s={'world_session':'world','material_task':{'id':'formal','occupied':True}}
        with tempfile.TemporaryDirectory()as d,patch('live_snapshot.read_fresh',return_value=s),\
             patch('safety_interlock.require_unlocked'),patch('idle_priority.request_foreground')as foreground,\
             patch.object(MaterialClient,'_init_material')as initialize:
            with self.assertRaises(Handoff):MaterialClient(Path(d),Path(d)/'out')
            foreground.assert_not_called();initialize.assert_not_called()

    def test_same_job_backend_reuses_the_formal_worker_scope(self):
        s={'world_session':'world','material_task':{'id':'formal','occupied':True}}
        c=object.__new__(MaterialClient);c.owner=SimpleNamespace(request={'id':'formal'})
        with tempfile.TemporaryDirectory()as d,patch('live_snapshot.read_fresh',return_value=s),\
             patch('safety_interlock.require_unlocked'),patch('idle_priority.request_foreground',return_value=Mock()),\
             patch.object(MaterialClient,'_init_material')as initialize:
            MaterialClient.__init__(c,Path(d),Path(d)/'out');initialize.assert_called_once()
