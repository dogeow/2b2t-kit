from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from projection_flat_backend import FlatMapBackend
from projection_flat_continuity import NAME, restore, save
from test_projection_flat_jobs import model, layout_for, audit, state, ITEM


class ContinuityTests(unittest.TestCase):
    def test_exact_native_parking_reuses_ledger_without_scan_or_new_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = model(3, 1); layout = layout_for(m)
            backend = SimpleNamespace(root=Path(tmp), out=Path(tmp), flat_layout=layout, flat_model=m,
                                      audit=audit(layout, {(0,64,0): 'Block{minecraft:stone}'}), audit_dirty=False,
                                      request={'projection_key': 'ship', 'flat_map': {'schema': 1,
                                               'content_hash': m['content_hash'], 'reuse_parked_material_ledger': True}})
            client = SimpleNamespace(world='world', task='task', heartbeat=SimpleNamespace(id='lease'))
            parked = {'time': 5000, 'world_session': 'world', 'connected': True, 'control_revision': 7,
                      'manual_movement': False, 'safety_hold': {'active': False},
                      'projection_selection': {'key': 'ship', 'min': [0,64,0], 'max': [2,64,0]},
                      'supervision_lease': {'kind': 'parking', 'id': 'lease', 'job_session': 'task',
                                           'world_session': 'world', 'revision': 7}}
            self.assertTrue(save(backend, client, parked))
            backend.audit = None
            self.assertTrue(restore(backend, parked))
            self.assertEqual((backend.audit['matched'], len(backend.flat_ledger.actual)), (1,1))
            proof = json.loads((Path(tmp)/'parked-ledger-reuse.json').read_text())
            self.assertFalse(proof['fresh_full_scan'])
            self.assertEqual(backend.flat_model, m)
            for key, value in [('world_session', 'other'), ('control_revision', 8), ('manual_movement', True),
                               ('connected', False), ('projection_selection', {'key': 'moved'})]:
                wrong = deepcopy(parked); wrong[key] = value
                self.assertFalse(restore(backend, wrong))
            wrong = deepcopy(parked); wrong['supervision_lease']['kind'] = 'materials'
            self.assertFalse(restore(backend, wrong))
            saved = json.loads((Path(tmp)/NAME).read_text()); saved['model']['expected'][0]['state'] = 'Block{minecraft:dirt}'
            (Path(tmp)/NAME).write_text(json.dumps(saved))
            self.assertFalse(restore(backend, parked))

    def test_direct_registered_route_is_collinear_and_keeps_native_volume_bound(self):
        backend = FlatMapBackend.__new__(FlatMapBackend)
        backend.request = {'projection_key': 'ship', 'flat_map': {'direct_registered_map_routes': True}}
        backend.profile = {'mud_station': {'authorized': True, 'pos': [20, 64, 190]}}
        current = {'pos': [20.5, 90, 190.5], 'projection_selection': {'key': 'ship', 'min': [0,64,0], 'max': [40,64,30]}}
        calls = []
        def request(op, **params):
            self.assertEqual(op, 'navigate'); self.assertTrue(params['air_only'])
            before, after = list(current['pos']), params['target']; calls.append((before, after))
            self.assertLessEqual(sum((b-a)**2 for a,b in zip(before,after)) ** .5, 48.000001)
            volume = (abs(after[0]-before[0])+1.6)*(abs(after[1]-before[1])+2.8)*(abs(after[2]-before[2])+1.6)
            self.assertLess(volume,8192)
            current['pos'] = after
            return {'phase': 'done'}
        client = SimpleNamespace(status=lambda: current, request=request)
        trace = []
        with patch('material_jobs.navigation.settled_state'):
            self.assertTrue(backend.try_direct_registered_travel(client, [5.5,90,15.5], lambda: None, trace, keep_cruise=True))
        self.assertEqual(len(calls), 4)
        for start, end in calls:
            self.assertAlmostEqual((end[0]-20.5)*175, (end[2]-190.5)*15)
        current['pos'] = [500,90,500]
        self.assertFalse(backend.try_direct_registered_travel(client, [5.5,90,15.5], lambda: None, trace, keep_cruise=True))


if __name__ == '__main__': unittest.main()
