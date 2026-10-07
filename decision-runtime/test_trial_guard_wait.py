import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from singleplayer_trial_bridge import (TrialBridge, TrialGuardBusy, Paused,
                                      GUARD_BUSY_DETAIL, guard_pre_dispatch_refusal)


def context(root):
    save = Path(root) / 'saves/trial'
    save.mkdir(parents=True)
    save = save.resolve()
    registry = {'protocol': 1, 'enabled': True, 'trial_id': 'trial-a', 'run_id': 'run-a',
                'world_id': str(save), 'world_name': 'Trial',
                'goal': 'defeat_ender_dragon', 'allow_death_respawn': True}
    snapshot = {'time': 1, 'connected': True, 'server': 'singleplayer',
                'singleplayer_trial_protocol': 1, 'game_mode': 'survival',
                'dimension': 'minecraft:overworld', 'world_id': str(save), 'world_name': 'Trial',
                'world_session': 'world-a', 'control_revision': 4, 'last_request': 'old',
                'trial_identity': {'registered': True, 'trial_id': 'trial-a',
                                   'run_id': 'run-a', 'world_id': str(save)},
                'phase': 'done', 'pos': [.5, 66, .5], 'health': 20, 'food': 20,
                'player_dead': False, 'manual_movement': False, 'screen': '',
                'guard_armed': True, 'guard_busy': False,
                'movement_keys': {'forward': False, 'back': False, 'jump': False, 'sneak': False}}
    return registry, snapshot


class TrialGuardWaitTest(unittest.TestCase):
    def test_armed_busy_waits_before_mailbox_and_sends_once_after_native_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, snapshot = context(root)
            snapshot['guard_busy'] = True
            sleeps, events, reads = [], [], [0]
            def reader(unused):
                reads[0] += 1
                mailbox = root / 'request.json'
                if mailbox.exists():
                    request = json.loads(mailbox.read_text())
                    return {**snapshot, 'id': request['id'], 'last_request': request['id'], 'phase': 'done'}
                return dict(snapshot)
            def sleeper(seconds):
                self.assertFalse((root / 'request.json').exists())
                sleeps.append(seconds)
                snapshot['guard_busy'] = False
                snapshot['time'] += 1
            bridge = TrialBridge(root, registry, 'run-a', reader=reader, sleeper=sleeper,
                                 events=lambda event, **data: events.append((event, data)))
            result = bridge.request('walk', target=[1.5, 66, .5])
            self.assertEqual([.1], sleeps)
            self.assertEqual(1, sum(event == 'native_request' for event, _ in events))
            self.assertEqual(result['id'], json.loads((root / 'request.json').read_text())['id'])
            self.assertFalse(bridge.halted)

    def test_busy_budget_expires_without_request_or_pending_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, snapshot = context(root)
            snapshot['guard_busy'] = True
            clock = [0.0]
            def sleeper(unused): clock[0] += 20
            with patch('singleplayer_trial_bridge.time.monotonic', side_effect=lambda: clock[0]):
                bridge = TrialBridge(root, registry, 'run-a', reader=lambda _: dict(snapshot), sleeper=sleeper)
                with self.assertRaises(TrialGuardBusy) as caught:
                    bridge.request('select_item', item='minecraft:stone_axe', seconds=0)
            self.assertIsNone(caught.exception.receipt)
            self.assertFalse((root / 'request.json').exists())
            self.assertFalse(bridge.pending_mutations)
            self.assertFalse(bridge.halted)

    def test_scope_manual_revision_and_control_pause_still_stop_during_guard_wait(self):
        for changed in ('manual', 'revision', 'run', 'control'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                registry, snapshot = context(root)
                snapshot['guard_busy'] = True
                paused = [False]
                def sleeper(unused):
                    if changed == 'manual': snapshot['manual_movement'] = True
                    elif changed == 'revision': snapshot['control_revision'] += 1
                    elif changed == 'run': snapshot['trial_identity'] = {**snapshot['trial_identity'], 'run_id': 'other'}
                    else: paused[0] = True
                def control():
                    if paused[0]: raise Paused('Kit trial pause')
                bridge = TrialBridge(root, registry, 'run-a', reader=lambda _: dict(snapshot),
                                     sleeper=sleeper, check_control=control)
                with self.assertRaises(Paused) as caught:
                    bridge.request('walk', target=[1.5, 66, .5])
                self.assertNotIsInstance(caught.exception, TrialGuardBusy)
                self.assertFalse((root / 'request.json').exists())

    def test_exact_generic_predispatch_refusal_keeps_bridge_ready_without_replay(self):
        for operation, arguments in (('walk', {'target': [1.5, 66, .5]}),
                                     ('select_item', {'item': 'minecraft:stone_axe'}),
                                     ('slot_click', {'slot': 9, 'menu_id': 0})):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                registry, snapshot = context(root)
                sent = []
                def reader(unused):
                    mailbox = root / 'request.json'
                    if not mailbox.exists(): return dict(snapshot)
                    request = json.loads(mailbox.read_text())
                    result = {**snapshot, 'id': request['id'], 'last_request': request['id'],
                              'phase': 'error', 'detail': GUARD_BUSY_DETAIL, 'guard_busy': True}
                    # Exactly as AutomationBridge's generic error snapshot:
                    # no op or native sequence has been installed yet.
                    (root / ('reply-' + request['id'] + '.json')).write_text(json.dumps(result))
                    return result
                bridge = TrialBridge(root, registry, 'run-a', reader=reader,
                    events=lambda event, **data: sent.append(data['id']) if event == 'native_request' else None)
                with self.assertRaises(TrialGuardBusy) as caught:
                    bridge.request(operation, **arguments)
                self.assertEqual(1, len(sent))
                self.assertEqual(sent[0], caught.exception.receipt['request_id'])
                self.assertEqual('native_guard_busy_before_dispatch', caught.exception.receipt['receipt_class'])
                self.assertEqual(sent[0], bridge.last)
                self.assertIsNone(bridge.active)
                self.assertFalse(bridge.halted)
                self.assertFalse(bridge.pending_mutations)
                self.assertEqual(sent[0], json.loads((root / 'request.json').read_text())['id'])

    def test_dispatched_unknown_mismatched_revision_or_generic_error_is_not_guard_recovery(self):
        invalid = ({'detail': 'defending'}, {'phase': 'waiting'}, {'native_sequence': 0},
                   {'server_ack_sequence': 2}, {'outcome_pending': True},
                   {'outcome_pending': 'false'}, {'server_confirmed': True},
                   {'guard_armed': False}, {'guard_busy': False}, {'op': 'other'})
        for change in invalid:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                registry, snapshot = context(root)
                def reader(unused):
                    mailbox = root / 'request.json'
                    if not mailbox.exists(): return dict(snapshot)
                    request = json.loads(mailbox.read_text())
                    return {**snapshot, 'id': request['id'], 'last_request': request['id'],
                            'phase': 'error', 'detail': GUARD_BUSY_DETAIL, 'guard_busy': True, **change}
                bridge = TrialBridge(root, registry, 'run-a', reader=reader)
                with self.assertRaises(Paused) as caught:
                    bridge.request('select_item', item='minecraft:stone_axe')
                self.assertNotIsInstance(caught.exception, TrialGuardBusy)
                self.assertTrue(bridge.halted)
                self.assertTrue(bridge.pending_mutations)
        # A fully matching generic message still cannot adopt a changed owner.
        result = {**snapshot, 'phase': 'error', 'detail': GUARD_BUSY_DETAIL, 'guard_busy': True,
                  'control_revision': 5}
        self.assertFalse(guard_pre_dispatch_refusal('select_item', result, 4))

    def test_guard_and_read_only_scan_are_not_delayed_by_busy_defense(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, snapshot = context(root)
            snapshot['guard_busy'] = True
            sleeps = []
            def reader(unused):
                mailbox = root / 'request.json'
                if not mailbox.exists(): return dict(snapshot)
                request = json.loads(mailbox.read_text())
                result = {**snapshot, 'id': request['id'], 'last_request': request['id'], 'phase': 'done'}
                if request['op'] == 'scan':
                    result.update(blocks=[], scan_cells_read=1, scan_total_cells=1,
                                  scan_start_revision=4, scan_end_revision=4)
                return result
            bridge = TrialBridge(root, registry, 'run-a', reader=reader, sleeper=lambda value: sleeps.append(value))
            bridge.request('guard', pve_only=True)
            bridge.request('scan', min=[0, 66, 0], max=[0, 66, 0])
            self.assertEqual([], sleeps)
            self.assertFalse(bridge.halted)


if __name__ == '__main__': unittest.main()
