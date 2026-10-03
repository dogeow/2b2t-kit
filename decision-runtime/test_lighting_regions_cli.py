"""Fixed registry/ownership/uncertainty tests; no actual game or model calls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lighting_regions_cli import RegionsWorker, RegionsPaused, NativeBatch, validate_profile


def profile():
    return {'schema': 1, 'authorized': True, 'server': 'example.invalid:25565',
            'dimension': 'minecraft:overworld', 'batch_torches': 8, 'max_batches_per_region': 2,
            'movement_bounds': {'min': [-10, 60, -10], 'max': [40, 100, 40]},
            'protected': [{'min': [3, 64, 3], 'max': [4, 80, 4]}],
            'regions': [{'name': 'field', 'min': [0, 60, 0], 'max': [4, 90, 4]},
                        {'name': 'beach', 'min': [10, 60, 0], 'max': [14, 90, 4]}]}


def state():
    return {'connected': True, 'server': 'example.invalid', 'dimension': 'minecraft:overworld',
            'world_session': 'world-a', 'manual_movement': False, 'health': 20, 'food': 20,
            'under_water': False, 'guard_armed': True, 'guard_pve_only': True, 'flight': True,
            'control_revision': 7, 'screen': '', 'supervision_lease': {}, 'pos': [1.5, 88, 1.5],
            'inventory': [{'slot': i, 'item': 'minecraft:torch' if i == 0 else 'minecraft:air',
                           'count': 8 if i == 0 else 0} for i in range(36)]}


class Batch:
    def __init__(self, current, *, risk=0):
        self.current, self.calls, self.risk = current, [], risk
    def __call__(self, region, directory, *, audit):
        self.calls.append((region['name'], audit, directory))
        self.current['control_revision'] += 1
        lease = 'owned-parking-' + str(self.current['control_revision'])
        self.current['supervision_lease'] = {'kind': 'parking', 'id': lease}
        return {'park_native_confirmed': True, 'parking_lease': lease,
                'control_revision': self.current['control_revision'], 'placed_verified': 2,
                'eligible_remaining': 0, 'unprotected_dark_floor': self.risk, 'observed_at': 123}


class RegionsTest(unittest.TestCase):
    def test_profile_requires_explicit_scope_budgets_and_unique_regions(self):
        self.assertEqual(validate_profile(profile())['server'], 'example.invalid')
        for change in ({'authorized': False}, {'dimension': 'minecraft:the_nether'},
                       {'batch_torches': True}, {'max_batches_per_region': 0}, {'regions': []}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_profile({**profile(), **change})
        bad = profile(); bad['regions'].append(deepcopy(bad['regions'][0]))
        with self.assertRaises(ValueError): validate_profile(bad)

    def test_registry_prevents_new_output_or_profile_bypass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = RegionsWorker(root, profile(), root/'original', observer=state)
            first.book['pending'] = {'stage': 'unknown'}; first.save()
            with self.assertRaisesRegex(ValueError, 'Changing output'):
                RegionsWorker(root, profile(), root/'different', observer=state)
            changed = profile(); changed['regions'][0]['min'][0] = 1
            with self.assertRaisesRegex(ValueError, 'different lighting profile'):
                RegionsWorker(root, changed, observer=state)
            same = RegionsWorker(root, profile(), observer=state)
            self.assertEqual(same.out, first.out)
            with self.assertRaisesRegex(RegionsPaused, 'pending batch'): same.run(resume=True)

    def test_real_file_lock_blocks_concurrent_workers(self):
        with tempfile.TemporaryDirectory() as folder:
            first = RegionsWorker(folder, profile(), observer=state)
            second = RegionsWorker(folder, profile(), observer=state)
            with first.worker_lock():
                self.assertTrue(second.status()['worker_running'])
                with self.assertRaisesRegex(RegionsPaused, 'active'): second.run()
            self.assertFalse(second.status()['worker_running'])

    def test_queue_requires_separate_current_audit_and_never_claims_island_goal(self):
        with tempfile.TemporaryDirectory() as folder:
            current = state(); batch = Batch(current, risk=1)
            worker = RegionsWorker(folder, profile(), observer=lambda: current, batch=batch)
            result = worker.run()
            self.assertEqual([(name, audit) for name, audit, _ in batch.calls],
                             [('field', False), ('beach', False), ('field', True), ('beach', True)])
            self.assertEqual(result['phase'], 'audited_with_remaining_risk')
            self.assertTrue(result['coverage_complete'])
            self.assertFalse(result['ordinary_zombie_light_clear'])
            self.assertFalse(result['goal_complete'])
            self.assertIsNone(result['pending'])
            self.assertFalse(result['worker_running'])
            self.assertEqual(result['ai_calls'], 0)
            again = worker.run(audit_only=True)
            self.assertEqual(again['phase'], 'audited_with_remaining_risk')
            self.assertEqual(again['dispatch_sequence'], 6)

    def test_interruption_keeps_pending_and_resume_cannot_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = []
            def uncertain(region, directory, *, audit):
                calls.append(region['name']); raise RuntimeError('Torch outcome unknown')
            worker = RegionsWorker(folder, profile(), observer=state, batch=uncertain)
            result = worker.run()
            self.assertEqual(result['phase'], 'waiting')
            original = deepcopy(result['pending'])
            self.assertIsNotNone(original)
            with self.assertRaisesRegex(RegionsPaused, 'pending batch'): worker.run(resume=True)
            self.assertEqual(calls, ['field'])
            self.assertEqual(worker.book['pending'], original)

    def test_unproven_park_keeps_batch_and_does_not_advance(self):
        with tempfile.TemporaryDirectory() as folder:
            current = state(); batch = Batch(current)
            def unproven(*args, **kwargs): return {**batch(*args, **kwargs), 'park_native_confirmed': False}
            worker = RegionsWorker(folder, profile(), observer=lambda: current, batch=unproven)
            result = worker.run()
            self.assertEqual(result['phase'], 'waiting')
            self.assertEqual(result['cursor'], 0)
            self.assertEqual(result['batches'], [])
            self.assertIsNotNone(result['pending'])

    def test_manual_health_native_lease_foreign_revision_stop_before_control(self):
        for change in ({'manual_movement': True}, {'health': 19}, {'connected': False},
                       {'safety_hold': {'active': True}}, {'borer_active': True},
                       {'supervision_lease': {'kind': 'materials', 'id': 'foreign'}}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                current = {**state(), **change}
                worker = RegionsWorker(folder, profile(), observer=lambda: current, batch=Batch(current))
                with self.assertRaises(RuntimeError): worker.run()
                self.assertIsNone(worker.book['pending'])
        with tempfile.TemporaryDirectory() as folder:
            worker = RegionsWorker(folder, profile(), observer=state)
            worker.book['last_revision'] = 6
            with self.assertRaisesRegex(RegionsPaused, 'controller'): worker.gate(state())

    def test_async_stop_is_recorded_without_game_rpc(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = RegionsWorker(folder, profile(), observer=state)
            command = worker.command('stop')
            with self.assertRaisesRegex(RegionsPaused, 'Requested stop'): worker.gate(state())
            self.assertEqual(worker.book['last_control'], command['id'])
            self.assertIsNone(worker.book['pending'])

    def test_status_does_not_replace_current_journal(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = RegionsWorker(folder, profile(), observer=state)
            current = deepcopy(worker.book); current['pending'] = {'stage': 'external_latest'}
            worker.path.write_text(json.dumps(current))
            reopened = RegionsWorker(folder, profile(), observer=state)
            self.assertEqual(reopened.book['pending'], current['pending'])
            self.assertEqual(json.loads(worker.path.read_text()), current)

    def test_no_torch_supply_waits_without_creating_uncertain_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            current = state(); current['inventory'][0]['count'] = 0
            batch = Batch(current)
            worker = RegionsWorker(folder, profile(), observer=lambda: current, batch=batch)
            result = worker.run()
            self.assertEqual(result['phase'], 'waiting_materials')
            self.assertIsNone(result['pending'])
            self.assertEqual(batch.calls, [])
            current['inventory'][0]['count'] = 8
            result = worker.run(resume=True)
            self.assertEqual(result['phase'], 'audited')

    def test_explicit_new_run_rechecks_regions_without_erasing_old_batches(self):
        with tempfile.TemporaryDirectory() as folder:
            current = state(); batch = Batch(current)
            worker = RegionsWorker(folder, profile(), observer=lambda: current, batch=batch)
            first = worker.run()
            second = worker.run()
            self.assertEqual((first['campaign'], second['campaign']), (1, 2))
            self.assertEqual(len(second['batches']), 4)
            self.assertEqual([entry['campaign'] for entry in second['batches']], [1, 1, 2, 2])

    def test_kit_cli_uses_same_explicit_profile_without_ui(self):
        from kit_cli import main
        with patch('lighting_regions_cli.main', return_value=0) as handler:
            self.assertEqual(main(['--game-dir', '/tmp/game', 'lighting', 'status',
                                   '--profile', '/tmp/profile.json']), 0)
            self.assertEqual(handler.call_args.args[0], ['--game-dir', '/tmp/game',
                             '--profile', '/tmp/profile.json', 'status'])

    def test_unknown_wait_keeps_heartbeat_and_lock_without_new_actions(self):
        with tempfile.TemporaryDirectory() as folder:
            owner = RegionsWorker(folder, profile(), observer=state)
            owner.book['pending'] = {'stage': 'unknown', 'original': 'request-a'}
            same = {**state(), 'phase': 'running', 'navigating': True, 'guard_busy': True,
                    'supervision_lease': {'id': 'lease-a', 'job_session': 'task-a'}, 'last_request': 'request-a'}
            manual = {**same, 'manual_movement': True}
            class Client:
                world, task = 'world-a', 'task-a'
                heartbeat = type('Beat', (), {'id': 'lease-a', 'close': lambda self: None})()
                def __init__(self): self.calls = 0
                def raw(self):
                    self.calls += 1
                    return same if self.calls < 3 else manual
                def _record_health_stop(self, reason): pass
                def park_near(self, s): return False
                def finish(self): raise AssertionError('Must not finish uncertain work')
                def _owned_guarded_finish_state(self, s, kind): return False
            client = Client()
            with owner.worker_lock(), patch('lighting_regions_cli.time.sleep'):
                NativeBatch(owner).wait_unresolved(client)
            self.assertEqual(client.calls, 3)
            self.assertEqual(owner.book['pending']['original'], 'request-a')
            self.assertEqual(owner.book['pending']['handoff'], 'world_manual_or_lease_changed')

    def test_late_verified_parking_is_read_only_and_does_not_clear_unknown_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            owner = RegionsWorker(folder, profile(), observer=state)
            owner.book['pending'] = {'stage': 'unknown', 'original': 'request-a'}
            parked = {**state(), 'phase': 'stopped', 'supervision_lease': {'id': 'lease-a', 'job_session': 'task-a'},
                      'supervision_safety': {'lease': 'lease-a', 'job_session': 'task-a', 'action': 'KEEP_PVE_GUARD'}}
            class Client:
                world, task = 'world-a', 'task-a'
                heartbeat = type('Beat', (), {'id': 'lease-a', 'close': lambda self: None})()
                def raw(self): return parked
                def park_near(self, s): return True
                def _owned_guarded_finish_state(self, s, kind): return kind == 'parking'
                def finish(self): raise AssertionError('Late parking must not replay finish')
            NativeBatch(owner).wait_unresolved(Client())
            self.assertEqual(owner.book['pending']['original'], 'request-a')
            self.assertEqual(owner.book['pending']['handoff'], 'late_owned_native_parking_observed_read_only')


if __name__ == '__main__': unittest.main()
