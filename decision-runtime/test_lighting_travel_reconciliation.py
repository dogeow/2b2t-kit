"""No game actions: strict known-cancelled travel journal reconciliation."""
import json
from pathlib import Path
import tempfile
import unittest
from lighting_regions_cli import RegionsWorker, RegionsPaused
from test_lighting_regions_cli import profile, state

class ReconciliationTests(unittest.TestCase):
    def setup_worker(self, directory):
        current = state()
        current.update(control_revision=9, phase='stopped', detail='手动移动接管', time=1000)
        worker = RegionsWorker(directory, profile(), observer=lambda: current)
        batch = worker.out / 'batch-00001'; batch.mkdir()
        worker.book.update(world_session='world-a', cursor=1, phase='waiting', pending={
            'stage': 'travel', 'handoff': 'world_manual_or_lease_changed',
            'error': 'Unavailable: air-only path changed; no blocks were excavated',
            'directory': str(batch), 'world_session': 'world-a', 'task_session': 'task-a'})
        events = [
            {'op':'scan','world_session':'world-a','params':{},'revision_after':7},
            {'op':'material_session','world_session':'world-a','params':{'task_session':'task-a'},'revision_after':7},
            {'op':'navigate','world_session':'world-a','params':{'task_session':'task-a'},
             'phase':'waiting','detail':'air-only path changed; no blocks were excavated',
             'request_id':'original-move','revision_after':8}]
        (batch/'events.jsonl').write_text('\n'.join(map(json.dumps,events)))
        worker.save()
        return worker, current, batch, events

    def test_known_manual_cancelled_travel_is_archived_without_build_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            worker, _, batch, _ = self.setup_worker(folder)
            original = (batch/'events.jsonl').read_bytes()
            result = worker.reconcile_travel()
            self.assertIsNone(result['pending'])
            self.assertEqual(result['cursor'], 1)
            self.assertEqual(result['phase'], 'waiting_resume')
            record = result['pending_reconciliations'][0]
            self.assertFalse(record['construction_completed'])
            self.assertFalse(record['request_replayed'])
            self.assertEqual(record['native_waiting_request'], 'original-move')
            self.assertEqual((batch/'events.jsonl').read_bytes(), original)
            self.assertFalse(worker.reconcile_travel()['worker_running'])

    def test_construction_or_unknown_interaction_never_clears_pending(self):
        for change in ('lighting', 'interact', 'unknown_failure'):
            with tempfile.TemporaryDirectory() as folder:
                worker, _, batch, events = self.setup_worker(folder)
                if change == 'lighting':worker.book['pending']['stage']='lighting'
                elif change == 'interact':
                    events.append({'op':'interact','world_session':'world-a','params':{'task_session':'task-a'}})
                    (batch/'events.jsonl').write_text('\n'.join(map(json.dumps,events)))
                else:worker.book['pending']['error']='unknown failure'
                with self.assertRaises(RegionsPaused):worker.reconcile_travel()
                self.assertIsNotNone(worker.book['pending'])

    def test_new_world_active_lease_or_unconfirmed_stop_never_clears_pending(self):
        for changes in ({'world_session':'world-b'}, {'supervision_lease':{'id':'other'}},
                        {'control_revision':8}, {'phase':'running'}, {'manual_movement':True}):
            with tempfile.TemporaryDirectory() as folder:
                worker,current,_,_ = self.setup_worker(folder);current.update(changes)
                with self.assertRaises(RegionsPaused):worker.reconcile_travel()
                self.assertIsNotNone(worker.book['pending'])

if __name__ == '__main__':unittest.main()
