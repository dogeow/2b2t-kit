"""Real trial bridge + SDK regressions for the former timer-done pickup halt."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from kit_runtime.inventory import InventorySession
from singleplayer_trial import _TrialCraftClient
from singleplayer_trial_bridge import (Paused, TrialBridge, TrialInventoryNoEffect,
                                      native_inventory_click_proof)
import test_singleplayer_trial as fixtures


def stack(item='minecraft:air', count=0, slot=None):
    value = {'item': item, 'count': count, 'max_stack': 64 if count else 1}
    if slot is not None: value['slot'] = slot
    return value


def view(state, stamp):
    menu = copy.deepcopy(state['menu'])
    inventory = [dict(row, slot=index) for index, row in enumerate(menu['slots'][9:45])]
    for row in [menu['cursor'], *menu['slots'], *inventory]:
        row['stack_data'] = {'id': row['item'], 'count': row['count'], 'components': {}}
    return {**menu, 'inventory': inventory, 'state_id': 3, 'quickcraft_status': 0,
            'player_uuid': state['player_uuid'], 'dimension': state['dimension'],
            'world_id': state['world_id'], 'observed_at': stamp, 'game_time': stamp // 50}


class NativeInventory:
    def __init__(self, game, mode='confirmed', mutate_proof=None):
        self.root = Path(game) / 'automation'
        self.root.mkdir()
        self.registry = fixtures.registry(game)
        self.mode, self.mutate_proof = mode, mutate_proof
        menu = {'id': 0, 'type': 'InventoryMenu', 'cursor': stack(),
                'slots': [stack(slot=i) for i in range(45)]}
        menu['slots'][11] = stack('minecraft:dark_oak_log', 1, 11)
        stamp = int(time.time() * 1000) - 500
        self.current = fixtures.state(self.registry, kit_version='2026.10.7.9', inventory_click_protocol=1,
            player_uuid='11111111-1111-1111-1111-111111111111', menu=menu,
            inventory=[copy.deepcopy(menu['slots'][11])], safety_hold={'active': False},
            health_recovery_hold=False, guard_busy=False, time=stamp,
            auto_refill_guard={'protocol': 1, 'ipn_present': True, 'hook_seen': True,
                'supported': True, 'active': True, 'suppressed': True, 'suppressed_ticks': 20,
                'last_hook_at': stamp, 'last_suppressed_at': stamp})
        self.current['trial_identity']['process_alive'] = True
        self.sent = []
        self.native_result = None

    def read(self, unused):
        self.current['time'] += 10
        path = self.root / 'request.json'
        if path.exists():
            request = json.loads(path.read_text())
            if request['id'] not in self.sent:
                self.sent.append(request['id'])
                before = copy.deepcopy(self.current)
                if self.mode == 'confirmed' and request['op'] == 'slot_click':
                    row = self.current['menu']['slots'][request['slot']]
                    self.current['menu']['cursor'] = stack(row['item'], row['count'])
                    self.current['menu']['slots'][request['slot']] = stack(slot=request['slot'])
                first = before['time']
                self.current.update(id=request['id'], last_request=request['id'], phase='done', op='settle',
                                    detail='server state available', time=first + 50)
                if request['op'] == 'inventory_probe':
                    probe = {'protocol': 1, 'scope_current': True, 'server_observed': True,
                        'request_id': request['id'], 'world_session': request['world_session'],
                        'control_revision': request['expected_revision'],
                        'audit_scope': 'current_state_only_not_historical_dispatch',
                        'server': view(self.current, first + 30), 'client': view(self.current, first + 40)}
                    if self.mutate_proof: self.mutate_proof(probe)
                    self.current['inventory_probe'] = probe
                elif self.mode != 'timer_done':
                    proof = {'protocol': 1, 'scope_current': True, 'request_id': request['id'],
                        'world_session': request['world_session'], 'control_revision': request['expected_revision'],
                        'slot': request['slot'], 'button': request['button'], 'kind': request['kind'],
                        'native_sequence': 1, 'correlation_ambiguous': False,
                        'server_processed': True, 'server_processed_at': first + 20,
                        'classification': self.mode,
                        'confirmation_scope': 'integrated_server_processed_click_and_matching_final_inventory',
                        'before': view(before, first),
                        'predicted_after': view(self.current, first + 10),
                        'server': view(self.current, first + 30), 'client': view(self.current, first + 40)}
                    if self.mutate_proof:
                        self.mutate_proof(proof)
                    self.current['inventory_click_receipt'] = proof
                self.native_result = copy.deepcopy(self.current)
                (self.root / ('reply-' + request['id'] + '.json')).write_text(json.dumps(self.native_result))
        return copy.deepcopy(self.current)

    def bridge(self):
        return TrialBridge(self.root, self.registry, self.registry['run_id'], reader=self.read)


class TrialInventoryConfirmationTests(unittest.TestCase):
    def click(self, bridge):
        return bridge.request('slot_click', menu_id=0, slot=11,
            expected_item='minecraft:dark_oak_log', expected_count=1,
            expected_cursor='minecraft:air', expected_cursor_count=0, kind='pickup', button=0)

    def test_native_timer_done_keeps_durable_unknown_and_no_second_click(self):
        with tempfile.TemporaryDirectory() as game:
            native = NativeInventory(game, 'timer_done')
            bridge = native.bridge()
            with self.assertRaisesRegex(Paused, 'missing or unknown'):
                self.click(bridge)
            self.assertTrue(bridge.halted)
            self.assertEqual(1, len(bridge.pending_mutations))
            self.assertEqual(1, len(list((native.root / 'trial-sdk-inventory/pending').glob('*.json'))))
            frozen = (native.root / 'request.json').read_bytes()
            with self.assertRaises(Paused): self.click(bridge)
            self.assertEqual(frozen, (native.root / 'request.json').read_bytes())
            self.assertEqual(1, len(native.sent))
            restored = native.bridge()
            self.assertTrue(restored.halted)
            self.assertEqual(set(bridge.pending_mutations), set(restored.pending_mutations))

    def test_old_host_is_refused_before_dispatch_and_has_no_false_pending(self):
        with tempfile.TemporaryDirectory() as game:
            native = NativeInventory(game)
            native.current.update(kit_version='2026.10.7.7', inventory_click_protocol=0)
            bridge = native.bridge()
            with self.assertRaisesRegex(Paused, 'no click sent'): self.click(bridge)
            self.assertFalse((native.root / 'request.json').exists())
            self.assertFalse(bridge.pending_mutations)

    def test_unobserved_or_inactive_auto_refill_isolation_never_dispatches(self):
        for change in ('old_host', 'missing', 'unsupported', 'inactive', 'unseen', 'unsuppressed',
                       'never_suppressed', 'stale_hook', 'stale_state', 'conflicting_presence'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as game:
                native = NativeInventory(game)
                guard = native.current['auto_refill_guard']
                if change == 'old_host': native.current['kit_version'] = '2026.10.7.8'
                elif change == 'missing': native.current.pop('auto_refill_guard')
                elif change == 'unsupported': guard['supported'] = False
                elif change == 'inactive': guard['active'] = False
                elif change == 'unseen': guard['hook_seen'] = False
                elif change == 'unsuppressed': guard['suppressed'] = False
                elif change == 'never_suppressed': guard['suppressed_ticks'] = 0
                elif change == 'stale_hook': guard['last_suppressed_at'] -= 2000
                elif change == 'stale_state': native.current['time'] -= 2000
                else: native.current['inventory_isolation'] = {'ipn_present': False}
                bridge = native.bridge()
                with self.assertRaisesRegex(Paused, 'cursor isolation'): self.click(bridge)
                self.assertFalse((native.root / 'request.json').exists())
                self.assertFalse(bridge.pending_mutations)

    def test_no_ipn_requires_supported_owned_guard_but_no_suppression_claim(self):
        with tempfile.TemporaryDirectory() as game:
            native = NativeInventory(game)
            native.current['auto_refill_guard'].update(ipn_present=False, hook_seen=False,
                                                      suppressed=False, suppressed_ticks=0)
            native.current['inventory_isolation'] = {'ipn_present': False}
            bridge = native.bridge()
            self.click(bridge)
            self.assertTrue(bridge.pending_mutations)

    def test_native_confirmed_keeps_pending_until_sdk_predicate_two_frames(self):
        with tempfile.TemporaryDirectory() as game, patch('kit_runtime.inventory.time.sleep'):
            native = NativeInventory(game)
            bridge = native.bridge()
            client = _TrialCraftClient(bridge, game)
            sdk = InventorySession(client)
            result = sdk.click(client.status(), 11)
            self.assertEqual(1, len(bridge.pending_mutations))
            request = json.loads((native.root / 'request.json').read_text())
            self.assertIs(request['inventory_confirm'], True)
            out = sdk._wait_pickup(result, 0, 11, 'minecraft:dark_oak_log', 1, 0,
                                   full_stack=True, settle_prediction=True)
            self.assertEqual(1, out['menu']['cursor']['count'])
            self.assertFalse(bridge.pending_mutations)
            self.assertFalse(bridge.sdk_inventory_pending)
            pending, receipt_path = bridge._inventory_paths(request['id'])
            self.assertTrue(pending.is_file())
            receipt = json.loads(receipt_path.read_text())
            self.assertEqual('sdk_inventory_click_committed', receipt['receipt_class'])
            self.assertTrue(receipt['sdk_predicate_confirmed'])
            self.assertEqual(2, len(receipt['witness_times']))
            self.assertFalse(receipt['replayed'])
            self.assertFalse(native.bridge().halted)
            self.assertEqual(1, len(native.sent))

    def test_no_effect_is_processed_known_rejection_not_not_sent_or_sdk_success(self):
        with tempfile.TemporaryDirectory() as game:
            native = NativeInventory(game, 'no_effect')
            bridge = native.bridge()
            with self.assertRaises(TrialInventoryNoEffect) as failure:
                self.click(bridge)
            self.assertFalse(bridge.halted)
            self.assertFalse(bridge.pending_mutations)
            receipt = failure.exception.receipt
            self.assertIs(receipt['action_sent'], True)
            self.assertIs(receipt['sdk_predicate_confirmed'], False)
            self.assertEqual('server_processed_inventory_click_no_effect', receipt['receipt_class'])
            self.assertFalse(native.bridge().halted)
            self.assertEqual(1, len(native.sent))

    def test_server_corrected_optimistic_pickup_can_be_processed_no_effect(self):
        def correction(proof):
            proof['before']['quickcraft_status'] = 1
            proof['predicted_after']['cursor'].update(item='minecraft:dark_oak_log', count=1,
                stack_data={'id': 'minecraft:dark_oak_log', 'count': 1, 'components': {}})
            proof['predicted_after']['slots'][11].update(item='minecraft:air', count=0,
                stack_data={'id': 'minecraft:air', 'count': 0, 'components': {}})
        with tempfile.TemporaryDirectory() as game:
            native = NativeInventory(game, 'no_effect', mutate_proof=correction)
            bridge = native.bridge()
            with self.assertRaises(TrialInventoryNoEffect): self.click(bridge)
            self.assertFalse(bridge.halted)
            self.assertFalse(bridge.pending_mutations)

    def test_missing_ambiguous_foreign_or_component_changed_proof_remains_pending(self):
        changes = {
            'no_server_processing': lambda p: p.update(server_processed=False),
            'ambiguous': lambda p: p.update(correlation_ambiguous=True),
            'no_sequence': lambda p: p.pop('native_sequence'),
            'scope': lambda p: p.update(scope_current=False),
            'wrong_scope_name': lambda p: p.update(confirmation_scope='timer'),
            'slot': lambda p: p.update(slot=10),
            'button': lambda p: p.update(button=1),
            'kind': lambda p: p.update(kind='swap'),
            'session': lambda p: p.update(world_session='other'),
            'revision': lambda p: p.update(control_revision=5),
            'classification': lambda p: p.update(classification='unknown'),
            'world': lambda p: p['server'].update(world_id='/tmp/OtherWorld'),
            'uuid': lambda p: p['server'].update(player_uuid='other'),
            'no_stack_data': lambda p: p['server']['cursor'].pop('stack_data'),
            'components': lambda p: p['server']['cursor']['stack_data'].update(components={'custom_name': 'altered'}),
            'predicted_components': lambda p: p['predicted_after']['cursor']['stack_data'].update(components={'custom_name': 'altered'}),
            'processed_before_observation': lambda p: p.update(server_processed_at=p['before']['observed_at'] - 1),
        }
        for label, mutate in changes.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as game:
                native = NativeInventory(game, mutate_proof=mutate)
                bridge = native.bridge()
                with self.assertRaises(Paused): self.click(bridge)
                self.assertTrue(bridge.halted)
                self.assertTrue(bridge.pending_mutations)
                self.assertEqual(1, len(native.sent))

    def test_commit_rejects_called_without_real_predicate_or_two_fresh_frames(self):
        for bad in ('predicate', 'one_frame', 'same_time', 'different_items', 'scope', 'receipt_changed'):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as game:
                native = NativeInventory(game)
                bridge = native.bridge()
                self.click(bridge)
                frames = [bridge.read(), bridge.read()]
                predicate = lambda m: m['cursor']['item'] == 'minecraft:dark_oak_log' and m['cursor']['count'] == 1
                if bad == 'predicate': predicate = lambda unused: False
                elif bad == 'one_frame': frames = frames[:1]
                elif bad == 'same_time': frames[1]['time'] = frames[0]['time']
                elif bad == 'different_items': frames[1]['menu']['cursor']['count'] = 2
                elif bad == 'scope': frames[1]['world_session'] = 'other'
                else: next(iter(bridge.sdk_inventory_pending.values()))['native_result'].pop('inventory_click_receipt')
                with self.assertRaises(Paused): bridge.commit_inventory_click('ingredient_pickup', frames, predicate)
                self.assertTrue(bridge.pending_mutations)
                self.assertFalse(list((native.root / 'trial-sdk-inventory/receipts').glob('*.json')))

    def test_same_millisecond_native_clock_is_legal_with_real_causal_receipt(self):
        def same_clock(proof):
            stamp = proof['before']['observed_at']
            proof['server_processed_at'] = stamp
            for value in ('server', 'client', 'predicted_after'):
                proof[value]['observed_at'] = stamp
        with tempfile.TemporaryDirectory() as game, patch('kit_runtime.inventory.time.sleep'):
            native = NativeInventory(game, mutate_proof=same_clock)
            bridge = native.bridge()
            client = _TrialCraftClient(bridge, game)
            sdk = InventorySession(client)
            result = sdk.click(client.status(), 11)
            sdk._wait_pickup(result, 0, 11, 'minecraft:dark_oak_log', 1, 0,
                             full_stack=True, settle_prediction=True)
            self.assertFalse(bridge.pending_mutations)
            self.assertEqual(1, len(native.sent))

    def test_recipe_result_zero_may_be_server_derived_but_cursor_components_must_match(self):
        def result_slot(proof):
            for label in ('server', 'client'):
                proof[label]['slots'][0] = {**stack('minecraft:dark_oak_planks', 4, 0),
                    'stack_data': {'id': 'minecraft:dark_oak_planks', 'count': 4, 'components': {}}}
        with tempfile.TemporaryDirectory() as game:
            native = NativeInventory(game, mutate_proof=result_slot)
            bridge = native.bridge()
            self.click(bridge)
            record = next(iter(bridge.sdk_inventory_pending.values()))
            self.assertEqual('confirmed', native_inventory_click_proof(record['native_result'], record['envelope'], record['before'])['classification'])
            self.assertTrue(bridge.pending_mutations)

    def test_durable_commit_failure_keeps_pending_and_intent_after_crash(self):
        with tempfile.TemporaryDirectory() as game:
            native = NativeInventory(game)
            bridge = native.bridge()
            self.click(bridge)
            frames = [bridge.read(), bridge.read()]
            with patch.object(bridge, '_durable_json', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    bridge.commit_inventory_click('ingredient_pickup', frames, lambda m: m['cursor']['count'] == 1)
            self.assertTrue(bridge.pending_mutations)
            self.assertTrue(native.bridge().halted)

    def test_other_world_ledger_does_not_bind_to_current_save(self):
        with tempfile.TemporaryDirectory() as game:
            native = NativeInventory(game)
            bridge = native.bridge()
            self.click(bridge)
            path, unused = bridge._inventory_paths(next(iter(bridge.pending_mutations)))
            record = json.loads(path.read_text())
            record['envelope']['world_id'] = '/tmp/OtherSave'
            path.write_text(json.dumps(record))
            self.assertFalse(native.bridge().halted)

    def test_inventory_probe_reads_both_current_views_without_resolving_history(self):
        def differing(probe):
            probe['server']['quickcraft_status'] = 1
            probe['server']['slots'][11]['count'] = 2
            probe['server']['slots'][11]['stack_data']['count'] = 2
        with tempfile.TemporaryDirectory() as game:
            native = NativeInventory(game, mutate_proof=differing)
            bridge = native.bridge()
            original = copy.deepcopy(native.current['menu'])
            result = bridge.request('inventory_probe')
            self.assertEqual(original, native.current['menu'])
            self.assertEqual(2, result['inventory_probe']['server']['slots'][11]['count'])
            self.assertEqual(1, result['inventory_probe']['client']['slots'][11]['count'])
            self.assertEqual('current_inventory_probe_only', bridge.last_receipt['receipt_class'])
            self.assertFalse(bridge.pending_mutations)
            self.assertFalse((native.root / 'trial-sdk-inventory').exists())
            self.assertNotIn('inventory_click_receipt', result)

    def test_inventory_probe_needs_durable_reply_and_complete_current_scope(self):
        for label in ('reply', 'session', 'scope', 'uuid', 'stack', 'audit_scope', 'observed'):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as game:
                def change(p):
                    if label == 'session': p['world_session'] = 'other'
                    elif label == 'scope': p['scope_current'] = False
                    elif label == 'uuid': p['server']['player_uuid'] = 'other'
                    elif label == 'stack': p['client']['cursor'].pop('stack_data')
                    elif label == 'audit_scope': p['audit_scope'] = 'historical_click_ack'
                    elif label == 'observed': p['server_observed'] = False
                native = NativeInventory(game, mutate_proof=change)
                def read(root):
                    value = native.read(root)
                    if label == 'reply' and 'inventory_probe' in value:
                        (native.root / ('reply-' + value['id'] + '.json')).unlink(missing_ok=True)
                    return value
                bridge = TrialBridge(native.root, native.registry, native.registry['run_id'], reader=read)
                with self.assertRaises(Paused): bridge.request('inventory_probe')
                self.assertFalse(bridge.pending_mutations)

    def test_readonly_probe_does_not_bypass_existing_sdk_pending_or_halt(self):
        with tempfile.TemporaryDirectory() as game:
            native = NativeInventory(game)
            bridge = native.bridge()
            self.click(bridge)
            original = (native.root / 'request.json').read_bytes()
            with self.assertRaises(Paused): bridge.request('inventory_probe')
            self.assertEqual(original, (native.root / 'request.json').read_bytes())
            self.assertTrue(bridge.pending_mutations)


if __name__ == '__main__': unittest.main()
