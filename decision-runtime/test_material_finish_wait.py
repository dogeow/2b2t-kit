"""Native finish receipts and async status publication must agree before success."""
import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from test_material_health_exit import FakeClient


class NativeFinishWaitTest(unittest.TestCase):
    def client(self, directory, receipt=True):
        client = FakeClient(directory, health=20)
        client.rev = 284
        client.state.update(time=900, control_revision=284, pos=client.park_target[:])
        client.state['supervision_lease']['revision'] = 284
        client._prepare_guarded_finish = lambda: True
        parked = self.parking(client, time=1001)
        native = {'lease': 'test', 'job_session': 'task', 'action': 'KEEP_PVE_GUARD',
                  'cause': 'controller_finished', 'time': 1000, 'confirmed': False,
                  'server_survival_verified': False, 'snapshot': parked}

        def close():
            client.heartbeat.closed = True
            if receipt:
                self.write_receipt(client, native)

        client.heartbeat.close = close
        return client, native

    def parking(self, client, **changes):
        state = copy.deepcopy(client.state)
        state.update(control_revision=285, **changes)
        state['supervision_lease'].update(kind='parking', revision=285)
        return state

    def write_receipt(self, client, receipt):
        (client.root / 'supervision-receipt-test.json').write_text(json.dumps(receipt))

    def snapshots(self, client, states, publish=None):
        reads = []

        def raw():
            state = copy.deepcopy(states[min(len(reads), len(states) - 1)])
            reads.append((client.rev, state['time']))
            client.state = state
            if publish:
                publish(len(reads))
            return client._observe_owned_health(state)

        client.raw = raw
        return reads

    def finish(self, client):
        clock = [0.0]

        def sleep(seconds):
            clock[0] += seconds

        with patch('material_cleanup.run', return_value=[]), \
                patch('craft_recovery.clear_owned_workbench'), \
                patch('material_client.time.monotonic', side_effect=lambda: clock[0]), \
                patch('material_client.time.sleep', side_effect=sleep):
            client._finish()
        return clock[0]

    def test_native_keep_waits_for_coherent_parking_after_receipt_time(self):
        with tempfile.TemporaryDirectory() as directory:
            client, native = self.client(directory)
            old = copy.deepcopy(client.state)
            transient = copy.deepcopy(old)
            transient.update(control_revision=285, time=950)
            stale_parking = self.parking(client, time=999)
            parked = self.parking(client, time=1001)
            reads = self.snapshots(client, [old, transient, stale_parking, parked])
            self.finish(client)
            proof = json.loads((client.out / 'stock-safety.json').read_text())
            self.assertEqual([(284, 900), (284, 950), (284, 999), (284, 1001)], reads)
            self.assertEqual(285, client.rev)
            self.assertTrue(proof['native_receipt'])
            self.assertEqual(native['time'], proof['time'])
            self.assertEqual(1001, proof['parking_confirmation']['time'])
            self.assertEqual(285, proof['parking_confirmation']['supervision_lease']['revision'])
            self.assertFalse(client.actions)

    def test_parking_publication_before_receipt_does_not_adopt_revision_or_succeed(self):
        with tempfile.TemporaryDirectory() as directory:
            client, native = self.client(directory, receipt=False)
            parked = self.parking(client, time=1001)

            def publish(count):
                self.assertEqual(284, client.rev)
                self.assertFalse((client.out / 'stock-safety.json').exists())
                if count == 3:
                    self.write_receipt(client, native)

            reads = self.snapshots(client, [parked], publish)
            self.finish(client)
            self.assertEqual(4, len(reads))
            self.assertEqual(285, client.rev)
            self.assertTrue((client.out / 'stock-safety.json').exists())
            self.assertFalse(client.actions)

    def test_missing_receipt_past_thirty_seconds_waits_for_original_native_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            client, native = self.client(directory, receipt=False)
            parked = self.parking(client, time=1001)

            def publish(count):
                if count <= 222:
                    self.assertEqual(284, client.rev)
                    self.assertFalse((client.out / 'stock-safety.json').exists())
                if count == 222:
                    self.write_receipt(client, native)

            reads = self.snapshots(client, [parked], publish)
            elapsed = self.finish(client)
            self.assertGreaterEqual(elapsed, 30)
            self.assertEqual(223, len(reads))
            self.assertEqual(285, client.rev)
            self.assertFalse(client.actions)
            self.assertTrue(json.loads((client.out / 'stock-safety.json').read_text())['native_receipt'])
            wait = json.loads((client.out / 'park-ack-wait.json').read_text())
            self.assertFalse(wait['confirmed'])
            self.assertTrue(wait['heartbeat_finished'])
            self.assertTrue(wait['native_lease_retained'])

    def test_matching_receipt_accepts_current_native_reanchored_safe_hover(self):
        with tempfile.TemporaryDirectory() as directory:
            client, native = self.client(directory, receipt=False)
            parked = self.parking(client, time=1001, pos=[12, 115, 2])
            parked['supervision_lease']['park_target'] = [12, 115, 2]
            native['snapshot'] = copy.deepcopy(parked)
            client.heartbeat.close = lambda: self.write_receipt(client, native)
            self.snapshots(client, [parked])
            self.finish(client)
            self.assertEqual([12, 115, 2], client.park_target)
            self.assertEqual(285, client.rev)
            self.assertFalse(client.actions)
            self.assertTrue((client.out / 'stock-safety.json').exists())

    def test_unconfirmed_native_reanchor_is_observed_without_adopting_target_or_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            client, _ = self.client(directory, receipt=False)
            parked = self.parking(client, time=1001, pos=[12, 115, 2])
            parked['supervision_lease']['park_target'] = [12, 115, 2]
            handoff = copy.deepcopy(parked)
            handoff['control_stop'] = {'kind': 'emergency', 'revision': 285}
            self.snapshots(client, [parked] * 221 + [handoff])
            elapsed = self.finish(client)
            self.assertGreaterEqual(elapsed, 30)
            self.assertEqual([1, 110, 2], client.park_target)
            self.assertEqual(284, client.rev)
            self.assertFalse(client.actions)
            self.assertFalse((client.out / 'stock-safety.json').exists())

    def test_health_loss_during_ack_wait_stops_wait_and_records_real_exit_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            client, _ = self.client(directory, receipt=False)
            parked = self.parking(client, time=1001)
            injured = copy.deepcopy(parked)
            injured.update(time=1002, health=17)
            self.snapshots(client, [parked] * 221 + [injured])
            elapsed = self.finish(client)
            self.assertLess(elapsed, 34)
            self.assertEqual(['safe_logout'], client.actions)
            self.assertFalse((client.out / 'stock-safety.json').exists())
            self.assertTrue(json.loads((client.root / 'material-health-hold.json').read_text())['active'])

    def test_handoffs_and_unowned_revisions_stop_before_later_parking(self):
        changes = [
            ('manual movement', lambda s: s.update(manual_movement=True)),
            ('disconnected', lambda s: s.update(connected=False)),
            ('world changed', lambda s: s.update(world_session='other')),
            ('foreign lease', lambda s: s['supervision_lease'].update(id='other')),
            ('foreign job', lambda s: s['supervision_lease'].update(job_session='other')),
            ('foreign lease world', lambda s: s['supervision_lease'].update(world_session='other')),
            ('foreign revision', lambda s: s.update(control_revision=286)),
            ('incoherent parking', lambda s: s['supervision_lease'].update(revision=284)),
            ('missing lease', lambda s: s.pop('supervision_lease')),
            ('emergency stop', lambda s: s.update(control_stop={'kind': 'emergency', 'revision': 285})),
        ]
        for name, change in changes:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                client, _ = self.client(directory)
                parked = self.parking(client, time=1001)
                changed = copy.deepcopy(parked)
                changed['time'] = 950  # Scope changes beat the receipt freshness barrier.
                change(changed)
                reads = self.snapshots(client, [changed, parked])
                self.finish(client)
                self.assertEqual(1, len(reads))
                self.assertEqual(284, client.rev)
                self.assertFalse((client.out / 'stock-safety.json').exists())
                self.assertFalse(client.actions)

    def test_invalid_keep_receipt_keeps_healthy_native_park_unconfirmed_until_handoff(self):
        changes = [
            lambda d: d.update(lease='other'),
            lambda d: d.update(job_session='other'),
            lambda d: d['snapshot'].update(world_session='other'),
            lambda d: d.pop('time'),
            lambda d: d.update(time=True),
            lambda d: d.update(local_verified=True),
            lambda d: d.update(lease_transition_pending=True),
        ]
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                client, native = self.client(directory, receipt=False)
                change(native)
                client.heartbeat.close = lambda: self.write_receipt(client, native)
                parked = self.parking(client, time=1001)
                handoff = copy.deepcopy(parked)
                handoff['manual_movement'] = True
                self.snapshots(client, [parked] * 221 + [handoff])
                elapsed = self.finish(client)
                self.assertGreaterEqual(elapsed, 30)
                self.assertEqual(284, client.rev)
                self.assertFalse((client.out / 'stock-safety.json').exists())
                self.assertFalse(client.actions)
                wait = json.loads((client.out / 'park-ack-wait.json').read_text())
                self.assertFalse(wait['confirmed'])
                self.assertFalse(wait['native_receipt'])

    def test_never_transitioned_materials_cannot_get_synthetic_keep_success(self):
        for receipt in (False, True):
            with self.subTest(receipt=receipt), tempfile.TemporaryDirectory() as directory:
                client, _ = self.client(directory, receipt=receipt)
                client.state['time'] = 1001
                self.snapshots(client, [client.state])
                self.finish(client)
                self.assertFalse((client.out / 'stock-safety.json').exists())
                self.assertEqual(284, client.rev)
                self.assertEqual(['safe_logout'], client.actions)

    def test_stale_parking_cannot_replace_post_receipt_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            client, _ = self.client(directory)
            parked = self.parking(client, time=999)
            handoff = copy.deepcopy(parked)
            handoff['manual_movement'] = True
            self.snapshots(client, [parked] * 221 + [handoff])
            self.finish(client)
            self.assertFalse((client.out / 'stock-safety.json').exists())
            self.assertEqual(284, client.rev)
            self.assertFalse(client.actions)

    def test_late_injury_cannot_succeed_and_timeout_logs_out_once_with_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            client, _ = self.client(directory)
            client.status()
            injured = self.parking(client, time=1001, health=17)
            self.snapshots(client, [injured])
            self.finish(client)
            self.assertFalse((client.out / 'stock-safety.json').exists())
            self.assertEqual(['safe_logout'], client.actions)
            hold = json.loads((client.root / 'material-health-hold.json').read_text())
            self.assertTrue(hold['active'])
            self.assertEqual(17, hold['health'])

    def test_guard_or_pose_loss_cannot_succeed_from_native_receipt_alone(self):
        for changes in ({'flight': False}, {'guard_armed': False}, {'guard_pve_only': False},
                        {'under_water': True}, {'pos': [1, 67, 2]}, {'health': 17}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                client, _ = self.client(directory)
                self.snapshots(client, [self.parking(client, time=1001, **changes)])
                self.finish(client)
                self.assertFalse((client.out / 'stock-safety.json').exists())
                self.assertEqual(284, client.rev)


if __name__ == '__main__':
    unittest.main()
