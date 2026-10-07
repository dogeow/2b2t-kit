"""Retire an exact SDK unknown only into bounded defense/history review."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from singleplayer_trial_bridge import Paused, TrialBridge
from trial_inventory_audit import file_hash, retired_inventory_metadata, validate_retired_inventory
import test_trial_inventory_audit as audit
import test_singleplayer_trial as scope


class RetiredFixture:
    def __init__(self, temp):
        root = Path(temp).resolve()
        values = audit.fixture(root)
        worker, current, unused, unused_review, output, unused_original, unused_frozen = values
        original, manifest, review, bundle, sdk, native = audit.ambiguous_case(root, values)
        self.root = output.parent.parent / 'automation'
        self.output, self.parent_pid = output, worker.parent_pid
        self.original, self.manifest, self.sdk_ref = original, manifest, sdk
        self.native_ref, self.review_ref = native, review
        pending = self.root / 'trial-sdk-inventory/pending' / (original['id'] + '.json')
        pending.parent.mkdir(parents=True)
        pending.write_bytes(Path(sdk['path']).read_bytes())
        self.pending = pending
        # Bind the fixture's original durable file before freezing the manifest.
        body = audit.record_json(manifest)
        body['sdk_pending'] = {'path': str(pending), 'sha256': file_hash(pending)}
        Path(manifest['path']).write_text(json.dumps(body))
        manifest['sha256'] = file_hash(Path(manifest['path']))
        for target in (Path(review['path']), Path(manifest['path']).parent / 'retirement-review.json'):
            value = json.loads(target.read_text())
            value['manifest'] = manifest
            target.write_text(json.dumps(value))
        game = output.parents[3]
        self.registry = scope.registry(game)
        self.registry.update(world_id=worker.registry['world_id'], trial_id=worker.registry['trial_id'],
                             run_id=worker.registry['run_id'])
        self.current = scope.state(self.registry, **current)
        self.current.update(player_uuid='player-a', kit_version='2026.10.7.9', inventory_click_protocol=1,
                            time=int(time.time() * 1000) - 200, last_request=original['id'], id=original['id'])
        self.current['trial_identity']['process_alive'] = True
        self.metadata = retired_inventory_metadata(output, self.registry, self.current)
        self.sent = []
        self.frozen = {path: path.read_bytes() for path in
            (pending, Path(manifest['path']), Path(body['original_intent']['path']),
             Path(body['native_unknown_reply']['path']))}

    def reader(self, unused):
        self.current['time'] += 2
        request = json.loads((self.root / 'request.json').read_text())
        if request['id'] != self.original['id'] and request['id'] not in self.sent:
            self.sent.append(request['id'])
            self.current.update(id=request['id'], last_request=request['id'], phase='done', op=request['op'])
            if request['op'] == 'guard':
                self.current.update(guard_armed=True, guard_pve_only=True, guard_busy=False,
                                    detail='guard modules enabled')
            elif request['op'] == 'inventory_probe':
                side = {'id': 0, 'type': 'InventoryMenu', 'state_id': 1, 'quickcraft_status': 0,
                    'player_uuid': self.current['player_uuid'], 'world_id': self.current['world_id'],
                    'dimension': self.current['dimension'], 'observed_at': self.current['time'], 'game_time': 100,
                    'cursor': copy.deepcopy(self.current['menu']['cursor']),
                    'slots': copy.deepcopy(self.current['menu']['slots']),
                    'inventory': copy.deepcopy(self.current['inventory'])}
                for row in [side['cursor'], *side['slots'], *side['inventory']]:
                    row['stack_data'] = {'id': row['item'], 'count': row['count']}
                self.current['inventory_probe'] = {'protocol': 1, 'request_id': request['id'],
                    'world_session': self.current['world_session'], 'control_revision': self.current['control_revision'],
                    'scope_current': True, 'server_observed': True,
                    'audit_scope': 'current_state_only_not_historical_dispatch',
                    'server': copy.deepcopy(side), 'client': copy.deepcopy(side)}
            (self.root / ('reply-' + request['id'] + '.json')).write_text(json.dumps(self.current))
        return copy.deepcopy(self.current)

    def bridge(self, *, metadata=True, alive=lambda unused: False):
        real = validate_retired_inventory
        with patch('trial_inventory_audit.validate_retired_inventory',
                   side_effect=lambda meta, reg, state, parent: real(meta, reg, state, parent, pid_alive=alive)):
            return TrialBridge(self.root, self.registry, self.registry['run_id'], reader=self.reader,
                               retired_inventory=self.metadata if metadata else None, parent_pid=self.parent_pid)


class InventoryRetirementTests(unittest.TestCase):
    def assert_frozen(self, case):
        for path, original in case.frozen.items(): self.assertEqual(original, path.read_bytes())
        self.assertFalse(list((case.root / 'trial-sdk-inventory/receipts').glob('*.json')))

    def test_exact_retired_new_start_is_defense_only_keeps_all_original_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            case = RetiredFixture(temp)
            bridge = case.bridge()
            self.assertFalse(bridge.halted)
            self.assertFalse(bridge.pending_mutations)
            self.assertEqual({case.original['id']}, set(bridge.historical_inventory_pending))
            bridge.request('guard', pve_only=True)
            bridge.request('inventory_probe')
            frozen_mailbox = (case.root / 'request.json').read_bytes()
            for op in ('slot_click', 'mine_block', 'interact', 'walk', 'chop', 'select_item'):
                with self.subTest(op=op), self.assertRaisesRegex(Paused, 'defense and current review'):
                    bridge.request(op)
            self.assertEqual(frozen_mailbox, (case.root / 'request.json').read_bytes())
            self.assertNotIn(case.original['id'], case.sent)
            self.assert_frozen(case)

    def test_no_retirement_or_same_scope_never_admits_original_unknown(self):
        for change in ('missing', 'same_run', 'same_session', 'old_alive', 'foreign_world', 'missing_save', 'changed_pending'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                case = RetiredFixture(temp)
                if change == 'missing':
                    bridge = case.bridge(metadata=False)
                    self.assertTrue(bridge.halted)
                    self.assertTrue(bridge.pending_mutations)
                    continue
                if change == 'same_run':
                    case.registry['run_id'] = case.original['run_id']
                    case.current['trial_identity']['run_id'] = case.original['run_id']
                elif change == 'same_session': case.current['world_session'] = case.original['world_session']
                elif change == 'foreign_world':
                    case.registry['world_id'] += '-other'
                    Path(case.registry['world_id']).mkdir()
                    case.current['world_id'] = case.registry['world_id']
                    case.current['trial_identity']['world_id'] = case.registry['world_id']
                elif change == 'missing_save':
                    ref = audit.record_json(case.metadata[0]['retirement_review'])['artifacts']['before_save']
                    Path(ref['path']).unlink()
                elif change == 'changed_pending': case.pending.write_text(case.pending.read_text() + ' ')
                with self.assertRaises(Paused):
                    case.bridge(alive=lambda pid: change == 'old_alive' and pid == 502)
                self.assertFalse(case.sent)

    def test_fresh_replan_needs_new_probe_each_review_id_and_preserves_unknown(self):
        for failure in (None, 'missing_probe', 'missing_id', 'claim_completed', 'foreign_scope', 'components'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                case = RetiredFixture(temp)
                bridge = case.bridge()
                if failure != 'missing_probe': bridge.request('inventory_probe')
                current = bridge.read()
                baseline = {'schema': 1, 'source': 'fresh_kit_physical_baseline', 'newbaseline_id': 'baseline-new',
                    **{key: current[key] for key in ('world_id', 'world_session', 'dimension', 'control_revision')},
                    'trial_id': case.registry['trial_id'], 'run_id': case.registry['run_id'],
                    'observed_at': current['time'], 'historical_effects_unresolved': True,
                    'old_action_completed': False, 'old_action_replayed': False,
                    'legacy_pending': [{'id': case.original['id'], 'op': 'slot_click'}],
                    'forbidden_request_ids': [case.original['id']],
                    'inventory_review_verified_ids': [case.original['id']],
                    'menu': current['menu'], 'inventory': current['inventory']}
                if failure == 'missing_id': baseline['inventory_review_verified_ids'] = []
                elif failure == 'claim_completed': baseline['old_action_completed'] = True
                elif failure == 'foreign_scope': baseline['world_session'] = 'other'
                elif failure == 'components':
                    bridge.last_inventory_probe['result']['inventory_probe']['server']['slots'][11]['stack_data']['custom_name'] = 'changed'
                if failure:
                    with self.assertRaises(Paused): bridge.authorize_inventory_replan(baseline)
                    self.assertIsNone(bridge.inventory_replan)
                else:
                    bridge.authorize_inventory_replan(baseline)
                    self.assertTrue(bridge._inventory_replan_current())
                    self.assertEqual({case.original['id']}, set(bridge.historical_inventory_pending))
                self.assert_frozen(case)

    def test_changes_after_admission_stop_even_readonly_work_without_replaying(self):
        with tempfile.TemporaryDirectory() as temp:
            case = RetiredFixture(temp)
            bridge = case.bridge()
            Path(case.native_ref['path']).write_text('{}')
            with self.assertRaisesRegex(Paused, 'evidence changed'): bridge.read()
            self.assertTrue(bridge.halted)
            self.assertFalse(case.sent)


if __name__ == '__main__': unittest.main()
