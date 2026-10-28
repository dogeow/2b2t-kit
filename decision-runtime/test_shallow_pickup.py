import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_jobs.shallow_pickup import collect, plan
from material_jobs.protocol import JobBlocked, JobPaused


def state():
    return {'connected': True, 'world_session': 'w', 'control_revision': 1,
            'supervision_lease': {'kind': 'materials', 'world_session': 'w', 'job_session': 't', 'revision': 1},
            'manual_movement': False, 'screen': '', 'health': 20, 'air_supply': 300,
            'oxygen_bonus': 3, 'guard_armed': True, 'guard_pve_only': True, 'auto_log': True,
            'flight': True, 'under_water': False, 'pos': [.5, 63.15, .5],
            'inventory': [{'item': 'minecraft:dirt', 'count': 3, 'slot': 22}]}


def frame():
    return {'world_session': 'w', 'scan_start_revision': 1, 'scan_end_revision': 1,
            'scan_coherent': True, 'scan_cells_read': 72, 'scan_total_cells': 72,
            'scan_predictions': {'complete': True, 'pending_count': 0},
            'blocks': [{'pos': [0, 60, 0], 'state': 'Block{minecraft:dirt}'},
                       {'pos': [0, 61, 0], 'state': 'Block{minecraft:water}[level=8]'},
                       {'pos': [0, 62, 0], 'state': 'Block{minecraft:water}[level=2]'}]}


class FakeClient:
    world = 'w'; task = 't'; rev = 1

    def __init__(self, pickup=True, handoff=False):
        self.s = state(); self.calls = []; self.pickup = pickup; self.handoff = handoff

    def status(self):
        return copy.deepcopy(self.s)

    def request(self, op, **kw):
        self.calls.append((op, kw))
        if op == 'scan':
            return frame()
        if op == 'navigate':
            if kw['target'][1] < 62:
                self.s['pos'] = [.5, 61, .5]
                if self.pickup:
                    self.s['inventory'][0]['count'] = 6
                if self.handoff:
                    self.s['manual_movement'] = True
            else:
                self.s['pos'] = [.5, 63.65, .5]
            return {'phase': 'done'}
        raise AssertionError(op)

    checked = request


class ShallowPickupTests(unittest.TestCase):
    def test_live_route_keeps_navigation_tolerance_out_of_the_water_return(self):
        p = plan(frame(), state(), [0, 60, 0], 64.3, [-1, 60, -1], [1, 67, 1])
        self.assertEqual([.5, 60.9, .35], p['target'])
        self.assertEqual(61, p['landing_min'])
        self.assertGreaterEqual(p['return_target'][1]-.7, p['dry_min'])

    def test_unknown_partial_predictions_and_foreign_world_fail_before_movement(self):
        variants = []
        for key, value in [('world_session', 'other'), ('scan_cells_read', 71), ('scan_end_revision', 2)]:
            f = frame(); f[key] = value; variants.append(f)
        f = frame(); f['scan_predictions']['pending_count'] = 1; variants.append(f)
        for f in variants:
            with self.subTest(frame=f), self.assertRaises(JobBlocked):
                plan(f, state(), [0, 60, 0], 64.3, [-1, 60, -1], [1, 67, 1])

    def test_ceiling_lava_and_missing_landing_support_are_rejected(self):
        for block in ['Block{minecraft:cobblestone}', 'Block{minecraft:lava}[level=0]']:
            f = frame(); f['blocks'].append({'pos': [0, 64, 0], 'state': block})
            with self.assertRaises(JobBlocked):
                plan(f, state(), [0, 60, 0], 64.3, [-1, 60, -1], [1, 67, 1])
        f = frame(); f['blocks'] = f['blocks'][1:]
        with self.assertRaises(JobBlocked):
            plan(f, state(), [0, 60, 0], 64.3, [-1, 60, -1], [1, 67, 1])

    def test_off_center_and_insufficient_return_height_are_rejected(self):
        s = state(); s['pos'][2] = .3
        with self.assertRaises(JobBlocked):
            plan(frame(), s, [0, 60, 0], 64.3, [-1, 60, -1], [1, 67, 1])
        with self.assertRaises(JobBlocked):
            plan(frame(), state(), [0, 60, 0], 63.8, [-1, 60, -1], [1, 67, 1])

    def test_collected_inventory_and_actual_dry_return_are_both_required(self):
        c = FakeClient()
        with tempfile.TemporaryDirectory() as d:
            r = collect(c, [0, 60, 0], 'minecraft:dirt', 6, Path(d)/'pickup')
        self.assertTrue(r['returned_to_dry_air'])
        self.assertEqual(['scan', 'navigate', 'navigate'], [op for op, _ in c.calls])
        self.assertEqual(63.65, c.s['pos'][1])

    def test_pickup_timeout_returns_to_dry_air_before_raising(self):
        c = FakeClient(pickup=False); now = [0.0]
        def sleep(_):
            now[0] += .2
        with tempfile.TemporaryDirectory() as d, patch('material_jobs.shallow_pickup.time.monotonic', side_effect=lambda: now[0]), patch('material_jobs.shallow_pickup.time.sleep', side_effect=sleep):
            with self.assertRaises(JobBlocked):
                collect(c, [0, 60, 0], 'minecraft:dirt', 6, Path(d)/'pickup', wait_seconds=.1)
        self.assertEqual(63.65, c.s['pos'][1])
        self.assertEqual(2, sum(op == 'navigate' for op, _ in c.calls))

    def test_manual_takeover_never_sends_cleanup_movement_or_claims_return(self):
        c = FakeClient(handoff=True)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(JobPaused):
                collect(c, [0, 60, 0], 'minecraft:dirt', 6, Path(d)/'pickup')
        self.assertEqual(1, sum(op == 'navigate' for op, _ in c.calls))

    def test_low_air_refuses_even_the_first_movement(self):
        c = FakeClient(); c.s['air_supply'] = 280
        with tempfile.TemporaryDirectory() as d, self.assertRaises(JobBlocked):
            collect(c, [0, 60, 0], 'minecraft:dirt', 6, Path(d)/'pickup')
        self.assertEqual([], c.calls)

    def test_already_collected_in_verified_dry_air_does_not_dive(self):
        c = FakeClient(); c.s['pos'][1] = 63.65; c.s['inventory'][0]['count'] = 6
        with tempfile.TemporaryDirectory() as d:
            r = collect(c, [0, 60, 0], 'minecraft:dirt', 6, Path(d)/'pickup')
        self.assertTrue(r['already_collected'])
        self.assertFalse(any(op == 'navigate' for op, _ in c.calls))

    def test_public_material_api_reuses_the_existing_owner(self):
        from material_client import MaterialClient
        c = object.__new__(MaterialClient)
        with tempfile.TemporaryDirectory() as d, patch('material_jobs.shallow_pickup.collect', return_value={'complete': True}) as worker:
            c.out = Path(d)
            self.assertTrue(c.collect_shallow([0, 60, 0], 'minecraft:dirt', 6)['complete'])
            self.assertIs(worker.call_args.args[0], c)
            self.assertEqual(Path(d), worker.call_args.args[4].parent)
