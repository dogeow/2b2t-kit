from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from material_jobs.protocol import JobBlocked
from material_jobs_backend import Backend
from projection_flat_backend import FlatMapBackend
from projection_flat_cache import FlatMaterialLedger
from test_projection_flat_jobs import ITEM, audit, layout_for, model, state


def record(layout, points, world='world'):
    return {'complete': True, 'pending': None, 'world_session': world,
            'placement_key': layout.key, 'physical_positions': [list(p) for p in points],
            'inventory_before': 64, 'inventory_after': 64 - len(points)}


class FlatCacheTests(unittest.TestCase):
    def test_material_list_decrements_only_committed_cells_and_keeps_baseline_time(self):
        layout = layout_for(model(3, 1))
        baseline = audit(layout, {}); original = deepcopy(baseline)
        ledger = FlatMaterialLedger(layout, baseline, 'world')
        point = (0, 64, 0)
        result = ledger.accept({point: layout.expected[point]['state']}, 1,
                               record(layout, [point]), evidence_path='window/flat-window.json')
        self.assertEqual((result['matched'], result['replacement_items']), (1, {ITEM: 2}))
        self.assertEqual(result['observed_at'], baseline['observed_at'])
        self.assertFalse(result['material_ledger']['full_completion_verified'])
        self.assertEqual(baseline, original)
        with self.assertRaises(JobBlocked):
            ledger.accept({point: layout.expected[point]['state']}, 1,
                          record(layout, [point]), evidence_path='replay')
        self.assertEqual(ledger.audit['matched'], 1)

    def test_unknown_window_wrong_world_and_inconsistent_stock_never_credit(self):
        layout = layout_for(model(2, 1)); point = (0, 64, 0)
        good = record(layout, [point])
        for change in ({'complete': False}, {'pending': 'professional_print'},
                       {'world_session': 'other'}, {'inventory_after': 64},
                       {'physical_positions': []}, {'placement_key': 'other'}):
            ledger = FlatMaterialLedger(layout, audit(layout, {}), 'world')
            with self.subTest(change=change), self.assertRaises(JobBlocked):
                ledger.accept({point: layout.expected[point]['state']}, 1,
                              {**good, **change}, evidence_path='unknown')
            self.assertEqual(ledger.audit['matched'], 0)

    def test_two_build_batches_reuse_one_model_and_baseline_with_exact_deficit(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = model(3, 1); layout = layout_for(m); current = state(4)
            current['projection_selection'].update(min=[0, 64, 0], max=[2, 64, 0])
            client = SimpleNamespace(world='world', status=lambda: current)
            calls = []
            client.request = lambda op: (calls.append(op) or {'world_session': 'world', 'projection_model': m})
            backend = FlatMapBackend.__new__(FlatMapBackend)
            backend.out = Path(tmp); backend.audit = None; backend.audit_dirty = True
            backend.request = {'projection_key': 'ship', 'flat_map': {'schema': 1,
                               'content_hash': m['content_hash'], 'max_cells_per_build': 1}}
            backend.prepare_travel = lambda: None
            backend._safe_flat = lambda c, l: current
            batches = []
            @contextmanager
            def action(name):
                out = Path(tmp) / str(len(batches)); out.mkdir(); batches.append(out)
                yield client, out
            backend.action = action
            def refresh():
                calls.append('projection_audit')
                backend.audit = audit(layout, {}); backend.audit_dirty = False
                return backend.audit
            backend.refresh_audit = refresh
            def window(c, l, actual, plan, out):
                out.mkdir(); points = [tuple(p) for p in plan['positions']]
                (out / 'flat-window.json').write_text(json.dumps(record(l, points)))
                return {p: l.expected[p]['state'] for p in points}, len(points)
            backend._window = window
            self.assertEqual(backend.build('ship')['placed'], 1)
            self.assertEqual(backend.build('ship')['placed'], 1)
            self.assertEqual(calls, ['projection_model', 'projection_audit'])
            self.assertEqual((backend.audit['matched'], backend.audit['replacement_items']), (2, {ITEM: 1}))
            client.world = 'reconnected'
            with self.assertRaises(JobBlocked): backend._ledger(client, layout)
            current['projection_selection']['key'] = 'moved'
            with self.assertRaises(JobBlocked): backend._layout(client, 'ship', Path(tmp))

    def test_completion_requires_fresh_full_native_audit_without_poll_recursion(self):
        layout = layout_for(model(1, 1)); point = (0, 64, 0)
        ledger = FlatMaterialLedger(layout, audit(layout, {}), 'world')
        ledger.accept({point: layout.expected[point]['state']}, 1,
                      record(layout, [point]), evidence_path='complete-window')
        backend = FlatMapBackend.__new__(FlatMapBackend)
        backend.flat_ledger = ledger; backend.busy = False; backend.checking = False; backend.cleaning = False
        # Simulate a full scan discovering a changed cell at final acceptance.
        fresh = audit(layout, {})
        with patch.object(Backend, 'observe', return_value={'projection_audit': ledger.audit}), \
                patch.object(backend, 'refresh_audit', return_value=fresh) as refresh:
            self.assertEqual(backend.observe()['projection_audit']['matched'], 0)
            refresh.assert_called_once()
        backend.flat_ledger = ledger; backend.busy = True
        with patch.object(Backend, 'observe', return_value={}), patch.object(backend, 'refresh_audit') as refresh:
            backend.observe(); refresh.assert_not_called()


if __name__ == '__main__': unittest.main()
