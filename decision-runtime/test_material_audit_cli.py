import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import kit_cli
import material_audit_cli as module


def state(time=100):
    return {'time': time, 'connected': True, 'server': 'example.test:25565',
            'dimension': 'minecraft:overworld', 'world_session': 'world', 'control_revision': 4,
            'manual_movement': False, 'screen': '', 'health': 20, 'food': 19,
            'inventory': [{'slot': 0, 'item': 'minecraft:dirt', 'count': 1}],
            'projection_selection': {'key': 'chosen', 'min': [1, 64, 1], 'max': [2, 64, 1]}}


def receipt():
    return {'id': 'materials-audit123', 'phase': 'done', 'world_session': 'world', 'control_revision': 4,
            'projection_audit': {'audit_schema': 2, 'observed_at': 110,
                'server': 'example.test', 'dimension': 'minecraft:overworld',
                'placement_key': 'chosen', 'loaded_chunks_verified': True,
                'matched': 1, 'total': 2, 'kinds': {'missing': 1},
                'replacement_items': {'minecraft:dirt': 1},
                'mismatches': [{'pos': [2, 64, 1], 'kind': 'missing',
                    'expected': 'Block{minecraft:dirt}', 'actual': 'Block{minecraft:air}',
                    'fluid': False, 'block_entity': False,
                    'neighbors_loaded': True, 'adjacent_fluid': False}]}}


def model_receipt():
    rows = [{'pos': [x, 64, 1], 'state': 'Block{minecraft:dirt}', 'item': 'minecraft:dirt'} for x in (1, 2)]
    lines = [','.join(map(str, r['pos'])) + '\t' + r['state'] + '\t' + r['item'] for r in rows]
    return {'id': 'materials-model123', 'phase': 'done', 'world_session': 'world', 'control_revision': 4,
            'projection_model': {'model_schema': 1, 'observed_at': 105,
                'loaded_chunks_verified': True,
                'placement_key': 'chosen', 'bounds': {'min': [1, 64, 1], 'max': [2, 64, 1]},
                'total': 2, 'expected': rows,
                'content_hash': hashlib.sha256(''.join(line+'\n' for line in sorted(lines)).encode()).hexdigest()}}


def observed_block(x=1):
    return {'pos': [x, 64, 1], 'state': 'Block{minecraft:dirt}',
            'replaceable': False, 'fluid': False, 'block_entity': False}


class FakeClient:
    def __init__(self, root, out, *, server):
        self.states = [state(), state(120)]
        self.receipt = receipt()
        self.model = model_receipt()
        self.scan = {'id': 'materials-scan123', 'phase': 'done', 'world_session': 'world',
                     'scan_cells_read': 36, 'scan_total_cells': 36,
                     'scan_start_revision': 4, 'scan_end_revision': 4,
                     'scan_started_at': 115, 'scan_ended_at': 119,
                     'blocks': [observed_block()]}
        self.calls = []
        Path(out).mkdir(parents=True, exist_ok=True)

    def status(self):
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]

    def request(self, op, **params):
        self.calls.append(op)
        reply = {'projection_model': self.model, 'projection_audit': self.receipt, 'scan': self.scan}[op]
        self.last = reply['id']
        self.last_terminal_evidence = {'request_id': self.last, 'op': op,
            'world_session': reply['world_session'], 'revision_after': 4, 'phase': reply['phase']}
        return reply


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.out = Path(self.temporary.name) / 'audit'
        self.client = None

    def execute(self, change=None, initial=None):
        def factory(*args, **kwargs):
            self.client = FakeClient(*args, **kwargs)
            if change:
                change(self.client)
            return self.client
        with patch('live_snapshot.read_fresh', return_value=initial or state()):
            return module.run('/unused/automation', self.out, client_factory=factory)

    def test_complete_fresh_receipt_saved_with_inventory_without_finish_or_lease(self):
        result = self.execute()
        self.assertEqual(['projection_model', 'projection_audit', 'scan'], self.client.calls)
        self.assertEqual(119, self.client.minimum_status_time)
        self.assertEqual((1, 2, 1), (result['matched'], result['total'], result['remaining']))
        self.assertEqual(receipt(), json.loads(Path(result['receipt_path']).read_text()))
        saved = json.loads(Path(result['audit_path']).read_text())
        self.assertEqual(receipt()['projection_audit']['mismatches'], saved['mismatches'])
        self.assertTrue(saved['loaded_server_chunks_verified'])
        self.assertEqual('world', json.loads(Path(result['inventory_path']).read_text())['world_session'])

    def test_native_phase_less_reads_keep_original_receipts_and_still_require_server_scan(self):
        def change(c):
            c.model.pop('phase'); c.receipt.pop('phase')
        # The native read protocol omits phase; the fake models that same shape.
        original = FakeClient.request
        def request(c, op, **params):
            if op in ('projection_model','projection_audit'):
                row = c.model if op == 'projection_model' else c.receipt
                c.calls.append(op); c.last = row['id']
                c.last_terminal_evidence = {'request_id': c.last, 'op': op,
                    'world_session': row['world_session'], 'revision_after':4, 'phase':None}
                return row
            return original(c, op, **params)
        with patch.object(FakeClient,'request',request):
            result=self.execute(change)
        self.assertTrue(result['loaded_server_chunks_verified'])
        self.assertEqual(['projection_model','projection_audit','scan'],self.client.calls)
        self.assertNotIn('phase',json.loads(Path(result['model_receipt_path']).read_text()))
        self.assertNotIn('phase',json.loads(Path(result['receipt_path']).read_text()))

    def test_phase_less_result_with_old_request_identity_cannot_start_another_read(self):
        original=FakeClient.request
        def request(c,op,**params):
            result=original(c,op,**params)
            c.last_terminal_evidence['request_id']='old-request'
            return result
        with patch.object(FakeClient,'request',request),self.assertRaises(module.AuditBlocked):
            self.execute()
        self.assertEqual(['projection_model'],self.client.calls)
        self.assertTrue((self.out/'projection-model-receipt-materials-model123.json').exists())

    def test_model_with_unverified_loaded_chunks_is_rejected(self):
        with self.assertRaises(module.AuditBlocked):
            self.execute(lambda c:c.model['projection_model'].update(loaded_chunks_verified=False))
        self.assertEqual(['projection_model'],self.client.calls)

    def test_changed_world_or_selection_preserves_exact_receipt_without_publishing_current(self):
        for key, value in [('world_session', 'new-world'), ('control_revision', 5)]:
            with self.subTest(key=key):
                with self.assertRaises(module.AuditBlocked):
                    self.execute(lambda c: c.states[-1].update({key: value}))
                self.assertFalse((self.out/'current-projection.json').exists())
                self.assertTrue((self.out/'projection-audit-receipt-materials-audit123.json').exists())
        with self.assertRaises(module.AuditBlocked):
            self.execute(lambda c: c.states[-1]['projection_selection'].update(key='changed'))

    def test_incomplete_counts_unloaded_chunks_and_stale_time_are_rejected(self):
        for changes in ({'total': 3}, {'loaded_chunks_verified': False}, {'observed_at': 90},
                        {'observed_at': 130}, {'kinds': {'unloaded': 1}},
                        {'mismatches': [{'pos': [9, 64, 1], 'kind': 'missing'}]}):
            with self.subTest(changes=changes), self.assertRaises(module.AuditBlocked):
                self.execute(lambda c: c.receipt['projection_audit'].update(changes))
        self.assertFalse((self.out/'current-projection.json').exists())

    def test_unknown_native_terminal_preserved_and_never_replayed(self):
        with self.assertRaises(module.AuditBlocked):
            self.execute(lambda c: c.receipt.update(phase='waiting', detail='unfinished'))
        self.assertEqual(['projection_model', 'projection_audit'], self.client.calls)
        saved = json.loads((self.out/'projection-audit-receipt-materials-audit123.json').read_text())
        self.assertEqual('waiting', saved['phase'])

    def test_active_worker_and_manual_control_reject_before_native_call(self):
        for extra in ({'material_task': {'process_alive': True}}, {'manual_movement': True},
                      {'professional_printer': {'enabled': True}}, {'gravel': {'active': True}},
                      {'planter_active': True}, {'feeder_active': True}, {'fisher_active': True},
                      {'concrete': {'active': True}}, {'printing': True}):
            with self.subTest(extra=extra), self.assertRaises(module.AuditBlocked):
                self.execute(initial=state() | extra)
        self.assertIsNone(self.client)

    def test_completed_projection_accepts_zero_mismatches(self):
        def change(c):
            c.receipt['projection_audit'].update(matched=2, mismatches=[], kinds={}, replacement_items={})
            c.scan['blocks'].append(observed_block(2))
        result = self.execute(change)
        self.assertEqual(0, result['remaining'])

    def test_cached_loaded_audit_is_rejected_when_server_scan_cannot_load_chunk(self):
        with self.assertRaises(module.AuditBlocked):
            self.execute(lambda c: c.scan.update(phase='waiting', scan_cells_read=0,
                detail='Server chunk is not loaded', blocks=[]))
        self.assertFalse((self.out/'current-projection.json').exists())
        saved = json.loads((self.out/'server-scan-receipt-materials-scan123.json').read_text())
        self.assertEqual('waiting', saved['phase'])
        self.assertEqual(1, self.client.calls.count('scan'))

    def test_real_server_quantity_difference_rejects_cached_projection_count(self):
        with self.assertRaises(module.AuditBlocked):
            self.execute(lambda c: c.scan['blocks'].append(observed_block(2)))
        self.assertFalse((self.out/'current-projection.json').exists())
        self.assertTrue((self.out/'server-scan-receipt-materials-scan123.json').is_file())

    def test_model_hash_and_partial_server_cell_coverage_rejected(self):
        with self.assertRaises(module.AuditBlocked):
            self.execute(lambda c: c.model['projection_model'].update(content_hash='wrong'))
        self.assertEqual(['projection_model'], self.client.calls)
        with self.assertRaises(module.AuditBlocked):
            self.execute(lambda c: c.scan.update(scan_cells_read=35))

    def test_scan_tiling_covers_large_envelope_once_with_native_limit(self):
        boxes = list(module._scan_boxes([0, 0, 0], [129, 2, 130]))
        cells = set()
        for low, high in boxes:
            volume = (high[0]-low[0]+1)*(high[1]-low[1]+1)*(high[2]-low[2]+1)
            self.assertLessEqual(volume, 50000)
            for x in range(low[0], high[0]+1):
                for y in range(low[1], high[1]+1):
                    for z in range(low[2], high[2]+1):
                        self.assertNotIn((x,y,z), cells)
                        cells.add((x,y,z))
        self.assertEqual(130*3*131, len(cells))

    def test_central_cli_routes_audit_without_material_task_start(self):
        with patch.object(module, 'main', return_value=0) as main:
            result = kit_cli.main(['--game-dir', '/game', 'materials', 'audit', '--out', '/out'])
        self.assertEqual(0, result)
        main.assert_called_once_with(['--game-dir', '/game', '--out', '/out'])


if __name__ == '__main__':
    unittest.main()
