"""Native removal reconciliation is read-only and never implies pickup."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_jobs import construction_access_receipts as receipts


class ConstructionAccessReceiptsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.block = {'pos': [760822, 111, 797766], 'expected': 'Block{minecraft:white_concrete}',
                      'item': 'minecraft:white_concrete'}
        self.pending = {'kind': 'open_block', 'world_session': 'old-world', 'created_at_ns': 1_000_000_000_000,
                        'data': {'pos': self.block['pos'], 'item': self.block['item']},
                        'request_records': [{'request_id': 'materials-e05b6d11d3df'}]}
        self.removal = {'time': 1001.25, 'request_id': 'materials-e05b6d11d3df',
                        'world_session': 'old-world', 'op': 'mine_block', 'phase': 'done',
                        'params': {'pos': self.block['pos'], 'expected_state': self.block['expected'],
                                   'task_session': 'materials-task'},
                        'inventory_delta': {}, 'pos': [760823.5, 110, 797766.5]}
        self.drop_id = '33488485-df2a-4c75-883d-4926f0a17290'
        self.pickup = {'time': 1003.5, 'request_id': 'pickup-request', 'world_session': 'old-world',
                       'op': 'collect_item', 'phase': 'waiting', 'pos': [760823.5, 110, 797766.5],
                       'params': {'task_session': 'materials-task', 'expected_item': self.block['item'],
                                  'expected_uuid': self.drop_id, 'expected_count': 1},
                       'inventory_delta': {}}

    def log(self, events, job='job-one', control='control-001', *, mtime=None):
        path = self.root / 'material-jobs' / job / control / 'events.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(json.dumps(event) + '\n' for event in events), encoding='utf-8')
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def find(self):
        return receipts.find_removal_receipt(self.root, self.pending, self.block)

    def test_old_world_native_done_proves_removal_but_waiting_pickup_only_adds_hint(self):
        path = self.log([self.removal, self.pickup])
        before = path.read_bytes()
        pending = deepcopy(self.pending)
        result = self.find()
        self.assertEqual(self.removal, result['native_event'])
        self.assertEqual([self.drop_id], result['owned_drop_ids'])
        self.assertEqual({'native_event', 'owned_drop_ids'}, set(result))
        self.assertEqual({}, result['native_event']['inventory_delta'])
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(pending, self.pending)

    def test_missing_request_id_or_wrong_action_has_no_proof(self):
        self.log([self.removal])
        for change in ({'request_records': []}, {'request_records': [{'request_id': 'different'}]},
                       {'kind': 'restore_block'}, {'world_session': 'new-world'}):
            with self.subTest(change=change):
                self.assertIsNone(receipts.find_removal_receipt(self.root, {**self.pending, **change}, self.block))

    def test_exact_request_world_operation_phase_position_and_state_must_match(self):
        mutations = [({'request_id': 'different'}, None), ({'world_session': 'other'}, None),
                     ({'op': 'interact'}, None), ({'phase': 'waiting'}, None),
                     ({'time': 999.999999999}, None), ({'time': None}, None),
                     ({}, {'pos': [760822, 110, 797766]}),
                     ({}, {'pos': [760822.0, 111, 797766]}),
                     ({}, {'expected_state': 'Block{minecraft:stone}'})]
        for top, params in mutations:
            with self.subTest(top=top, params=params):
                event = deepcopy(self.removal); event.update(top)
                if params: event['params'].update(params)
                self.log([event])
                self.assertIsNone(self.find())

    def test_event_exactly_at_pending_creation_is_allowed_but_one_nanosecond_before_is_not(self):
        event = {**self.removal, 'time': 1000.0}
        self.log([event])
        self.assertIsNotNone(self.find())
        self.pending['created_at_ns'] += 1
        self.assertIsNone(self.find())

    def test_pending_data_cannot_authorize_receipt_for_different_portal(self):
        self.log([self.removal])
        self.pending['data'] = {'pos': [0, 0, 0], 'item': self.block['item']}
        self.assertIsNone(self.find())

    def test_same_id_contradictions_in_another_log_are_rejected(self):
        self.log([self.removal])
        for change in ({'phase': 'error'}, {'world_session': 'other'}, {'op': 'scan'}, {'time': 999}):
            with self.subTest(change=change):
                self.log([{**self.removal, **change}], job='job-two')
                self.assertIsNone(self.find())

    def test_identical_duplicate_receipts_are_allowed_and_hint_ids_deduplicated(self):
        self.log([self.removal, self.removal, self.pickup, self.pickup])
        self.log([self.removal, self.pickup], job='job-two')
        self.assertEqual([self.drop_id], self.find()['owned_drop_ids'])

    def test_multiple_distinct_successful_request_ids_are_ambiguous(self):
        second = {**self.removal, 'request_id': 'second-removal'}
        self.pending['request_records'].append({'request_id': 'second-removal'})
        self.log([self.removal, second])
        self.assertIsNone(self.find())

    def test_drop_hints_require_same_log_task_item_world_time_order_and_distance(self):
        mutations = [({'world_session': 'new-world'}, None), ({'time': 1061.251}, None),
                     ({'time': 1001.249}, None), ({'pos': [760831, 111, 797766]}, None),
                     ({'pos': [760822, 111]}, None), ({'pos': [True, 111, 797766]}, None),
                     ({}, {'task_session': 'other-task'}), ({}, {'expected_item': 'minecraft:stone'}),
                     ({}, {'expected_uuid': 'not-a-uuid'})]
        for top, params in mutations:
            with self.subTest(top=top, params=params):
                event = deepcopy(self.pickup); event.update(top)
                if params: event['params'].update(params)
                self.log([self.removal, event])
                self.assertEqual([], self.find()['owned_drop_ids'])
        self.log([self.pickup, self.removal])
        self.assertEqual([], self.find()['owned_drop_ids'])
        self.log([self.removal])
        self.log([self.pickup], control='control-002')
        self.assertEqual([], self.find()['owned_drop_ids'])

    def test_sixty_seconds_and_eight_blocks_are_inclusive_hint_limits(self):
        event = deepcopy(self.pickup)
        event.update(time=self.removal['time'] + 60, pos=[760830, 111, 797766])
        self.log([self.removal, event])
        self.assertEqual([self.drop_id], self.find()['owned_drop_ids'])

    def test_missing_task_can_prove_removal_but_never_invents_hint_ownership(self):
        self.removal['params'].pop('task_session')
        self.log([self.removal, self.pickup])
        self.assertEqual([], self.find()['owned_drop_ids'])

    def test_malformed_or_oversized_logs_fail_closed_without_writes(self):
        path = self.log([self.removal])
        for payload in ('{broken\n', '[]\n', '{"time":NaN}\n'):
            with self.subTest(payload=payload):
                path.write_text(json.dumps(self.removal) + '\n' + payload)
                before = path.read_bytes()
                self.assertIsNone(self.find())
                self.assertEqual(before, path.read_bytes())
        self.log([self.removal])
        for name in ('MAX_FILE_BYTES', 'MAX_TOTAL_BYTES', 'MAX_LINE_BYTES'):
            with self.subTest(limit=name), patch.object(receipts, name, 8):
                self.assertIsNone(self.find())
        self.log([self.removal, self.pickup])
        with patch.object(receipts, 'MAX_EVENT_LINES', 1):
            self.assertIsNone(self.find())

    def test_reads_only_128_newest_event_files(self):
        self.log([self.removal], job='old-job', mtime=1)
        for index in range(128):
            self.log([{'op': 'scan'}], job='recent-%03d' % index, mtime=100 + index)
        self.assertIsNone(self.find())
        self.log([self.removal], job='newest-job', mtime=1000)
        self.assertEqual(self.removal, self.find()['native_event'])

    def test_invalid_numeric_evidence_fails_closed(self):
        for timestamp in (True, 10 ** 400, float('inf'), float('nan')):
            with self.subTest(timestamp=timestamp):
                self.log([{**self.removal, 'time': timestamp}])
                self.assertIsNone(self.find())

    def test_absent_logs_and_invalid_inputs_do_not_raise(self):
        self.assertIsNone(self.find())
        for pending in (None, [], {'kind': 'open_block'}, {**self.pending, 'created_at_ns': True}):
            with self.subTest(pending=pending):
                self.assertIsNone(receipts.find_removal_receipt(self.root, pending, self.block))


if __name__ == '__main__':
    unittest.main()
