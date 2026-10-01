import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import projection_dry_paving as paving
import terrain_replace_south as terrain
import terrain_replace_south_cli as cli
from test_terrain_replace_south import FakeClient


class SouthTerrainCliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'automation'
        self.root.mkdir()
        self.client = FakeClient(self.root)
        self.client.finish = lambda: None
        self.client.park_target = [terrain.CELLS[0][0] + .5, 110,
                                   terrain.CELLS[0][2] + .5]
        site_patch = patch.object(paving, 'SITE', self.client.area)
        site_patch.start()
        self.addCleanup(site_patch.stop)

    def argv(self, out):
        return ['--root', str(self.root), '--out', str(out), '--park-high',
                *map(str, self.client.park_target)]

    def guard_receipt(self, lease='owned-lease', task=None, world=None,
                      action='KEEP_PVE_GUARD'):
        return {'lease': lease, 'job_session': task or self.client.task,
                'snapshot': {'world_session': world or self.client.world,
                             'pos': self.client.park_target, 'health': 20,
                             'guard_armed': True, 'guard_pve_only': True,
                             'flight': True},
                'action': action, 'confirmed': False, 'time': 42}

    def guarded_state(self):
        state = self.client.status()
        state.update(pos=list(self.client.park_target), supervision_lease=None)
        return state

    def test_default_run_names_only_one_of_the_ten_cells(self):
        self.assertEqual(terrain.CELLS[0], (760994, 62, 797865))
        self.assertEqual(cli.validate_cells(None, 1), [terrain.CELLS[0]])
        with self.assertRaises(ValueError):
            cli.validate_cells([(0, 62, 0)], 1)
        with self.assertRaises(ValueError):
            cli.validate_cells([terrain.CELLS[0]] * 2, 2)

    def test_missing_native_protocol_blocks_before_lease_or_mining(self):
        self.client.protocol = 0
        out = self.root / 'no-protocol'
        output = io.StringIO()
        with (patch.object(cli, 'read_fresh', return_value=self.client.status()),
              patch.object(cli, 'TerrainClient') as owner,
              redirect_stdout(output)):
            code = cli.main(self.argv(out))
        self.assertEqual(code, 2)
        owner.assert_not_called()
        self.assertIn('protocol', json.loads(output.getvalue())['reason'].lower())
        self.assertFalse(out.exists())

    def test_reconcile_evidence_requires_one_explicit_cell_before_preflight(self):
        evidence = self.root / 'reconcile.json'
        evidence.write_text('{}')
        cases = [
            ('implicit', []),
            ('max_two', ['--max-cells', '2', '--cell',
                         *map(str, terrain.CELLS[0]), '--cell',
                         *map(str, terrain.CELLS[1])]),
        ]
        for name, extra in cases:
            with self.subTest(name=name):
                out = self.root / ('reject-' + name)
                output = io.StringIO()
                with (patch.object(cli, 'read_fresh') as read,
                      patch.object(cli, 'TerrainClient') as owner,
                      redirect_stdout(output)):
                    code = cli.main(self.argv(out) + extra + [
                        '--reconcile-pre-send-evidence', str(evidence)])
                self.assertEqual(code, 2)
                read.assert_not_called()
                owner.assert_not_called()
                self.assertIn('one explicit --cell',
                              json.loads(output.getvalue())['reason'])
                self.assertFalse(out.exists())

    def test_malformed_reconcile_evidence_blocks_before_preflight(self):
        evidence = self.root / 'bad-reconcile.json'
        evidence.write_text('{broken')
        out = self.root / 'bad-reconcile'
        output = io.StringIO()
        with (patch.object(cli, 'read_fresh') as read,
              patch.object(cli, 'TerrainClient') as owner,
              redirect_stdout(output)):
            code = cli.main(self.argv(out) + ['--cell', *map(str, terrain.CELLS[0]),
                '--reconcile-pre-send-evidence', str(evidence)])
        self.assertEqual(code, 2)
        read.assert_not_called()
        owner.assert_not_called()
        self.assertFalse(out.exists())

    def test_post_send_evidence_requires_one_explicit_cell_before_preflight(self):
        evidence = self.root / 'post-send-reconcile.json'
        evidence.write_text('{}')
        cases = [
            ('implicit', []),
            ('max_two', ['--max-cells', '2', '--cell',
                         *map(str, terrain.CELLS[0]), '--cell',
                         *map(str, terrain.CELLS[1])]),
        ]
        for name, extra in cases:
            with self.subTest(name=name):
                out = self.root / ('post-send-reject-' + name)
                output = io.StringIO()
                with (patch.object(cli, 'read_fresh') as read,
                      patch.object(cli, 'TerrainClient') as owner,
                      redirect_stdout(output)):
                    code = cli.main(self.argv(out) + extra + [
                        '--reconcile-post-send-evidence', str(evidence)])
                self.assertEqual(code, 2)
                read.assert_not_called()
                owner.assert_not_called()
                self.assertIn('one explicit --cell',
                              json.loads(output.getvalue())['reason'])
                self.assertFalse(out.exists())

    def test_two_reconcile_flags_are_rejected_before_preflight(self):
        evidence = self.root / 'both-evidence.json'
        evidence.write_text('{}')
        out = self.root / 'both-flags'
        output = io.StringIO()
        with (patch.object(cli, 'read_fresh') as read,
              patch.object(cli, 'TerrainClient') as owner,
              redirect_stdout(output)):
            code = cli.main(self.argv(out) + [
                '--cell', *map(str, terrain.CELLS[0]),
                '--reconcile-pre-send-evidence', str(evidence),
                '--reconcile-post-send-evidence', str(evidence)])
        self.assertEqual(code, 2)
        read.assert_not_called()
        owner.assert_not_called()
        self.assertIn('only one', json.loads(output.getvalue())['reason'])

    def test_exact_post_send_evidence_is_passed_to_core(self):
        evidence = {'schema': 1, 'kind': terrain.POST_SEND_LIFT_EVIDENCE_KIND}
        evidence_path = self.root / 'post-send.json'
        evidence_path.write_text(json.dumps(evidence))
        out = self.root / 'post-send'
        output = io.StringIO()
        self.client.heartbeat = SimpleNamespace(id='owned-lease')

        def guarded_finish():
            (out / 'stock-safety.json').write_text(json.dumps(self.guard_receipt()))

        self.client.finish = guarded_finish
        with (patch.object(cli, 'read_fresh', side_effect=[self.client.status(),
                                                           self.guarded_state()]),
              patch.object(cli.paving_cli, 'verify_high_park',
                           return_value={'ground_clearance': 40}),
              patch.object(cli, 'TerrainClient', return_value=self.client),
              patch.object(cli, 'replace_batch', return_value=[
                  {'pos': list(terrain.CELLS[0]), 'result': 'placed',
                   'expected': terrain.DIRT}]) as replace,
              redirect_stdout(output)):
            code = cli.main(self.argv(out) + [
                '--cell', *map(str, terrain.CELLS[0]),
                '--reconcile-post-send-evidence', str(evidence_path)])
        self.assertEqual(code, 0)
        replace.assert_called_once_with(
            self.client, cells=[terrain.CELLS[0]], max_cells=1,
            post_send_evidence=evidence)

    def test_exact_single_cell_reconcile_evidence_is_passed_to_core(self):
        evidence = {'schema': 1, 'immutable': {'request_id': 'old-request'}}
        evidence_path = self.root / 'reconcile.json'
        evidence_path.write_text(json.dumps(evidence))
        out = self.root / 'reconcile'
        output = io.StringIO()
        self.client.heartbeat = SimpleNamespace(id='owned-lease')

        def guarded_finish():
            (out / 'stock-safety.json').write_text(json.dumps(self.guard_receipt()))

        self.client.finish = guarded_finish
        with (patch.object(cli, 'read_fresh', side_effect=[self.client.status(),
                                                           self.guarded_state()]),
              patch.object(cli.paving_cli, 'verify_high_park',
                           return_value={'ground_clearance': 40}),
              patch.object(cli, 'TerrainClient', return_value=self.client),
              patch.object(cli, 'replace_batch', return_value=[
                  {'pos': list(terrain.CELLS[0]), 'result': 'placed',
                   'expected': terrain.DIRT}]) as replace,
              redirect_stdout(output)):
            code = cli.main(self.argv(out) + ['--cell', *map(str, terrain.CELLS[0]),
                '--reconcile-pre-send-evidence', str(evidence_path)])
        self.assertEqual(code, 0)
        replace.assert_called_once_with(self.client, cells=[terrain.CELLS[0]], max_cells=1,
                                        pre_send_evidence=evidence)
        self.assertEqual(json.loads((out / 'progress.json').read_text())['finish']['state'],
                         'high_guard_confirmed')
        self.assertFalse([entry for entry in self.client.actions if entry[0] == 'safe_logout'])

    def test_normal_multi_cell_path_does_not_receive_reconcile_evidence(self):
        out = self.root / 'normal-multi'
        output = io.StringIO()
        self.client.heartbeat = SimpleNamespace(id='owned-lease')

        def guarded_finish():
            (out / 'stock-safety.json').write_text(json.dumps(self.guard_receipt()))

        self.client.finish = guarded_finish
        receipts = [[{'pos': list(pos), 'result': 'placed', 'expected': terrain.DIRT}]
                    for pos in terrain.CELLS[:2]]
        cells = ['--max-cells', '2']
        for pos in terrain.CELLS[:2]:
            cells += ['--cell', *map(str, pos)]
        with (patch.object(cli, 'read_fresh', side_effect=[self.client.status(),
                                                           self.guarded_state()]),
              patch.object(cli.paving_cli, 'verify_high_park',
                           return_value={'ground_clearance': 40}),
              patch.object(cli, 'TerrainClient', return_value=self.client),
              patch.object(cli, 'replace_batch', side_effect=receipts) as replace,
              redirect_stdout(output)):
            code = cli.main(self.argv(out) + cells)
        self.assertEqual(code, 0)
        self.assertEqual(replace.call_count, 2)
        self.assertTrue(all('pre_send_evidence' not in call.kwargs
                            for call in replace.call_args_list))
        self.assertTrue(all('post_send_evidence' not in call.kwargs
                            for call in replace.call_args_list))
        self.assertEqual(json.loads((out / 'progress.json').read_text())['done'], 2)

    def test_single_cell_receipt_requires_owned_high_guard_and_finishes_once(self):
        out = self.root / 'smoke'
        output = io.StringIO()
        self.client.heartbeat = SimpleNamespace(id='owned-lease')

        def confirmed_finish():
            (out / 'stock-safety.json').write_text(json.dumps(self.guard_receipt()))

        self.client.finish = confirmed_finish
        with (patch.object(cli, 'read_fresh', side_effect=[self.client.status(),
                                                           self.guarded_state()]),
              patch.object(cli.paving_cli, 'verify_high_park',
                           return_value={'ground_clearance': 40}),
              patch.object(cli, 'TerrainClient', return_value=self.client) as owner,
              patch.object(cli, 'replace_batch', return_value=[
                  {'pos': list(terrain.CELLS[0]), 'result': 'placed', 'expected': terrain.DIRT}]) as replace,
              redirect_stdout(output)):
            code = cli.main(self.argv(out))
        self.assertEqual(code, 0)
        self.assertEqual(owner.call_args.kwargs['remote_finish'], 'guard')
        replace.assert_called_once()
        self.assertEqual(replace.call_args.kwargs['max_cells'], 1)
        self.assertEqual(replace.call_args.kwargs['cells'], [terrain.CELLS[0]])
        saved = json.loads((out / 'progress.json').read_text())
        self.assertEqual(saved['done'], 1)
        self.assertEqual(saved['status'], 'completed')
        self.assertEqual(saved['finish']['state'], 'high_guard_confirmed')
        self.assertEqual(saved['finish']['park_position'], self.client.park_target)
        self.assertTrue(saved['finish']['high_park_verified'])
        self.assertFalse([entry for entry in self.client.actions if entry[0] == 'safe_logout'])

    def test_completed_cell_without_owned_guard_remains_finish_unconfirmed(self):
        out = self.root / 'unconfirmed-exit'
        output = io.StringIO()
        self.client.heartbeat = SimpleNamespace(id='owned-lease')

        def unrelated_finish():
            (out / 'stock-safety.json').write_text(json.dumps(
                self.guard_receipt(lease='another-lease')))

        self.client.finish = unrelated_finish
        with (patch.object(cli, 'read_fresh', return_value=self.client.status()),
              patch.object(cli.paving_cli, 'verify_high_park',
                           return_value={'ground_clearance': 40}),
              patch.object(cli, 'TerrainClient', return_value=self.client),
              patch.object(cli, 'replace_batch', return_value=[
                  {'pos': list(terrain.CELLS[0]), 'result': 'placed', 'expected': terrain.DIRT}]),
              redirect_stdout(output)):
            code = cli.main(self.argv(out))
        self.assertEqual(code, 2)
        saved = json.loads((out / 'progress.json').read_text())
        self.assertEqual(saved['done'], 1)
        self.assertEqual(saved['work_status'], 'completed')
        self.assertEqual(saved['status'], 'finish_unconfirmed')
        self.assertFalse([entry for entry in self.client.actions if entry[0] == 'safe_logout'])

    def test_owned_guard_receipt_does_not_override_fresh_disconnected_status(self):
        out = self.root / 'disconnected'
        out.mkdir()
        self.client.heartbeat = SimpleNamespace(id='owned-lease')
        (out / 'stock-safety.json').write_text(json.dumps(self.guard_receipt()))
        state = self.guarded_state()
        state['connected'] = False
        with patch.object(cli, 'read_fresh', return_value=state):
            self.assertEqual(cli._finish_receipt(self.client, self.root, out)['state'],
                             'unconfirmed')

    def test_logout_receipt_is_not_reported_as_retained_guard(self):
        out = self.root / 'logout-receipt'
        out.mkdir()
        self.client.heartbeat = SimpleNamespace(id='owned-lease')
        (out / 'stock-safety.json').write_text(json.dumps(
            self.guard_receipt(action='LOGOUT')))
        with patch.object(cli, 'read_fresh', return_value=self.guarded_state()):
            self.assertEqual(cli._finish_receipt(self.client, self.root, out)['state'],
                             'unconfirmed')

    def test_late_native_guard_receipt_is_not_promoted_past_material_client_gate(self):
        out=self.root/'late-native-receipt'
        out.mkdir()
        self.client.heartbeat=SimpleNamespace(id='owned-lease')
        native=self.root/'supervision-receipt-owned-lease.json'
        native.write_text(json.dumps(self.guard_receipt()))
        with (patch.object(cli.time,'sleep') as sleep,
              patch.object(cli,'read_fresh') as read):
            result=cli._finish_receipt(self.client,self.root,out)
        self.assertEqual('unconfirmed',result['state'])
        self.assertEqual(str(out/'stock-safety.json'),result['evidence'])
        sleep.assert_not_called()
        read.assert_not_called()
        self.assertEqual([],self.client.actions)

    def test_pending_native_receipt_is_not_turned_into_a_success(self):
        out = self.root / 'pending'
        output = io.StringIO()
        self.client.heartbeat = SimpleNamespace(id='owned-lease')
        def guarded_finish():
            (out / 'stock-safety.json').write_text(json.dumps(self.guard_receipt()))
        self.client.finish = guarded_finish
        with (patch.object(cli, 'read_fresh', side_effect=[self.client.status(),
                                                           self.guarded_state()]),
              patch.object(cli.paving_cli, 'verify_high_park',
                           return_value={'ground_clearance': 40}),
              patch.object(cli, 'TerrainClient', return_value=self.client) as owner,
              patch.object(cli, 'replace_batch', side_effect=paving.PavingPending('unknown click')),
              redirect_stdout(output)):
            code = cli.main(self.argv(out))
        self.assertEqual(code, 2)
        self.assertEqual(owner.call_args.kwargs['remote_finish'], 'guard')
        saved = json.loads((out / 'progress.json').read_text())
        self.assertEqual(saved['status'], 'pending_review')
        self.assertEqual(saved['done'], 0)
        self.assertEqual(saved['finish']['state'], 'high_guard_confirmed')
        self.assertFalse([entry for entry in self.client.actions if entry[0] == 'safe_logout'])

    def test_blocked_work_still_finishes_with_high_guard_without_claiming_success(self):
        out = self.root / 'blocked'
        output = io.StringIO()
        self.client.heartbeat = SimpleNamespace(id='owned-lease')

        def guarded_finish():
            (out / 'stock-safety.json').write_text(json.dumps(self.guard_receipt()))

        self.client.finish = guarded_finish
        with (patch.object(cli, 'read_fresh', side_effect=[self.client.status(),
                                                           self.guarded_state()]),
              patch.object(cli.paving_cli, 'verify_high_park',
                           return_value={'ground_clearance': 40}),
              patch.object(cli, 'TerrainClient', return_value=self.client),
              patch.object(cli, 'replace_batch',
                           side_effect=paving.PavingBlocked('route changed')),
              redirect_stdout(output)):
            code = cli.main(self.argv(out))
        self.assertEqual(code, 2)
        saved = json.loads((out / 'progress.json').read_text())
        self.assertEqual(saved['status'], 'blocked')
        self.assertEqual(saved['finish']['state'], 'high_guard_confirmed')
        self.assertFalse([entry for entry in self.client.actions if entry[0] == 'safe_logout'])

    def test_finish_rejects_unsafe_or_unowned_live_evidence(self):
        self.client.heartbeat = SimpleNamespace(id='owned-lease')
        baseline = self.guarded_state()
        cases = [
            ('wrong_task', self.guard_receipt(task='other-task'), baseline),
            ('wrong_world', self.guard_receipt(world='other-world'), baseline),
            ('manual', self.guard_receipt(), {**baseline, 'manual_movement': True}),
            ('menu', self.guard_receipt(), {**baseline, 'screen': 'InventoryScreen'}),
            ('underwater', self.guard_receipt(), {**baseline, 'under_water': True}),
            ('low_health', self.guard_receipt(), {**baseline, 'health': 17}),
            ('no_guard', self.guard_receipt(), {**baseline, 'guard_armed': False}),
            ('not_pve', self.guard_receipt(), {**baseline, 'guard_pve_only': False}),
            ('guard_busy', self.guard_receipt(), {**baseline, 'guard_busy': True}),
            ('no_flight', self.guard_receipt(), {**baseline, 'flight': False}),
            ('foreign_lease', self.guard_receipt(), {**baseline,
                'supervision_lease': {'id': 'foreign', 'kind': 'materials'}}),
            ('too_far', self.guard_receipt(), {**baseline,
                'pos': [self.client.park_target[0] + 9,
                        self.client.park_target[1], self.client.park_target[2]]}),
        ]
        for name, receipt, state in cases:
            with self.subTest(name=name):
                out = self.root / ('bad-' + name)
                out.mkdir()
                (out / 'stock-safety.json').write_text(json.dumps(receipt))
                with patch.object(cli, 'read_fresh', return_value=state):
                    result = cli._finish_receipt(self.client, self.root, out)
                self.assertEqual(result['state'], 'unconfirmed')
        self.assertFalse([entry for entry in self.client.actions if entry[0] == 'safe_logout'])

    def test_terrain_client_uses_material_client_guard_finish_without_override(self):
        self.assertIs(cli.TerrainClient._finish, cli.MaterialClient._finish)


if __name__ == '__main__':
    unittest.main()
