import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_client import Handoff
import projection_dry_paving as paving
import projection_dry_paving_cli as cli


class AuditClient:
    def __init__(self, root, count=6):
        self.root = Path(root)
        self.world = 'world-a'
        self.task = 'materials-a'
        self.positions = list(paving.SITE['pinned_conflicts'])[:count]
        self.key = 'pinned-eight-regions'
        self.state = {'world_session': self.world,
                      'projection_selection': {'key': self.key},
                      'pos': [self.positions[0][0] + .5, 64, self.positions[0][2] + .5],
                      'inventory': [
                          {'slot': 0, 'item': 'minecraft:stone_bricks', 'count': 64},
                          {'slot': 1, 'item': 'minecraft:polished_andesite', 'count': 64},
                      ]}
        self.model = {'content_hash': 'pinned-model', 'observed_at': 1000,
                      'expected': [{'pos': list(pos),
                                    'state': paving.SITE['pinned_conflicts'][pos][0]}
                                   for pos in self.positions]}
        self.audit = {'observed_at': 1000, 'total': 3701, 'matched': 3701 - count,
                      'mismatches': [self._mismatch(pos) for pos in self.positions]}
        self.calls = []

    def _mismatch(self, pos):
        expected, actual = paving.SITE['pinned_conflicts'][pos]
        return {'pos': list(pos), 'expected': expected, 'actual': actual,
                'kind': 'occupied', 'block_entity': False, 'fluid': False,
                'adjacent_fluid': False, 'neighbors_loaded': True}

    def context(self, *args):
        return copy.deepcopy((self.state, self.model, self.audit))

    def write_journal(self, pos, phase):
        expected, actual = paving.SITE['pinned_conflicts'][tuple(pos)]
        path = paving._journal_path(self, paving.SITE, tuple(pos))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'schema': 1, 'server': paving.SITE['server'],
                                    'dimension': paving.SITE['dimension'],
                                    'placement_key': self.key, 'model_hash': 'pinned-model',
                                    'world_session': self.world, 'pos': list(pos),
                                    'expected': expected, 'actual': actual,
                                    'phase': phase, 'updated_at_ns': 1234,
                                    'receipts': []}))

    def pave(self, client, positions, *, on_cell_complete):
        self.calls.append(copy.deepcopy(positions))
        results = []
        for pos in positions:
            self.write_journal(pos, 'complete')
            self.audit['mismatches'] = [row for row in self.audit['mismatches']
                                        if row['pos'] != pos]
            self.audit['matched'] += 1
            self.audit['observed_at'] += 1
            result = {'pos': pos, 'result': 'placed'}
            on_cell_complete(result)
            results.append(result)
        return results


class PavingCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = AuditClient(self.temp.name)
        self.context_patch = patch.object(paving, '_fresh_context', self.client.context)
        self.context_patch.start()
        self.addCleanup(self.context_patch.stop)

    def test_selects_only_current_pinned_conflicts_in_batches_of_four(self):
        result = cli.run(self.client, Path(self.temp.name) / 'out', minutes=20,
                         max_cells=6, pave=self.client.pave, monotonic=lambda: 0,
                         wall_time=lambda: 100)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([len(batch) for batch in self.client.calls], [4, 2])
        self.assertEqual(result['done'], 6)
        self.assertEqual(len(result['cells']), 6)
        self.assertTrue(all(cell['journal_phase'] == 'complete'
                            and cell['audit']['mismatch_count'] >= 0
                            for cell in result['cells']))
        self.assertTrue(all(tuple(pos) in paving.SITE['pinned_conflicts']
                            for batch in self.client.calls for pos in batch))
        saved = json.loads((Path(self.temp.name) / 'out' / 'progress.json').read_text())
        self.assertEqual(saved['status'], 'completed')
        self.assertEqual(len((Path(self.temp.name) / 'out' / 'events.jsonl').read_text().splitlines()), 11)

    def test_one_cell_short_validation_run(self):
        result = cli.run(self.client, Path(self.temp.name) / 'out', minutes=1,
                         max_cells=1, allowed_cells=[self.client.positions[0]],
                         pave=self.client.pave, monotonic=lambda: 0)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([len(batch) for batch in self.client.calls], [1])
        self.assertEqual(result['cells'][0]['audit']['matched'], 3696)

    def test_one_cell_requires_reviewed_coordinate_and_uses_only_that_cell(self):
        with self.assertRaisesRegex(ValueError, 'explicit --cell'):
            cli.validate_cells(None, 1)
        with self.assertRaises(ValueError):
            cli.validate_cells([self.client.positions[0], self.client.positions[1]], 1)
        target = self.client.positions[-1]
        result = cli.run(self.client, Path(self.temp.name) / 'chosen', minutes=1,
                         max_cells=1, allowed_cells=[target],
                         pave=self.client.pave, monotonic=lambda: 0)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(self.client.calls, [[list(target)]])
        with self.assertRaises(ValueError):
            cli.validate_cells([[0, 63, 0]], 1)

    def test_partial_batch_persists_each_completed_cell_before_later_failure(self):
        def fail_second(client, positions, *, on_cell_complete):
            self.client.calls.append(copy.deepcopy(positions))
            first = positions[0]
            self.client.write_journal(first, 'complete')
            self.client.audit['mismatches'] = [row for row in self.client.audit['mismatches']
                                               if row['pos'] != first]
            self.client.audit['matched'] += 1
            on_cell_complete({'pos': first, 'result': 'placed'})
            self.client.write_journal(positions[1], 'mine_intent')
            raise paving.PavingPending('second cell uncertain')

        out = Path(self.temp.name) / 'partial'
        result = cli.run(self.client, out, minutes=20, max_cells=4,
                         pave=fail_second, monotonic=lambda: 0)
        self.assertEqual(result['status'], 'pending_review')
        self.assertEqual(result['done'], 1)
        self.assertEqual(len(result['cells']), 1)
        saved = json.loads((out / 'progress.json').read_text())
        self.assertEqual(saved['done'], 1)
        self.assertEqual(saved['batches'][0]['journal_phases'][
            '_'.join(map(str, self.client.calls[0][1]))], 'mine_intent')

    def test_pending_intent_stops_before_another_batch(self):
        pos = self.client.positions[4]
        self.client.write_journal(pos, 'mine_intent')
        with self.assertRaises(paving.PavingPending):
            cli.select_batch(self.client, 4)
        self.assertEqual(self.client.calls, [])

    def test_pending_intent_outside_explicit_cell_still_blocks_run(self):
        named, other = self.client.positions[:2]
        self.client.write_journal(other, 'place_intent')
        self.client.state['inventory'] = []
        with self.assertRaisesRegex(paving.PavingPending, 'Uncertain prior intent'):
            cli.select_batch(self.client, 1, frozenset({named}))
        self.assertEqual(self.client.calls, [])

    def test_completed_cell_changed_by_player_is_not_replayed(self):
        self.client.write_journal(self.client.positions[0], 'complete')
        self.client.state['inventory'] = []
        with self.assertRaisesRegex(paving.PavingPending, 'Previously completed'):
            cli.select_batch(self.client, 4)

    def test_recovered_cell_can_resume_only_when_full_audit_shows_air(self):
        pos = self.client.positions[0]
        self.client.write_journal(pos, 'recovered')
        self.client.audit['mismatches'][0].update(actual='Block{minecraft:air}', kind='missing')
        selected, _ = cli.select_batch(self.client, 1)
        self.assertEqual(selected, [list(pos)])
        self.client.audit['mismatches'][0]['actual'] = 'Block{minecraft:stone}'
        with self.assertRaisesRegex(paving.PavingPending, 'Recovered cell changed'):
            cli.select_batch(self.client, 1)

    def test_unheld_replacement_is_skipped_before_a_new_cell_is_touched(self):
        client = AuditClient(self.temp.name, count=79)
        client.state['pos'] = [760987.5, 64, 797828.5]
        client.state['inventory'] = [
            {'slot': 0, 'item': 'minecraft:stone_bricks', 'count': 1}]
        with patch.object(paving, '_fresh_context', client.context):
            selected, receipt = cli.select_batch(client, 4)
        self.assertEqual(len(selected), 1)
        self.assertEqual(paving._block(paving.SITE['pinned_conflicts'][tuple(selected[0])][0]),
                         'minecraft:stone_bricks')
        self.assertGreater(receipt['selection']['missing_replacement_cells'][
            'minecraft:polished_andesite'], 0)
        self.assertEqual(client.calls, [])

    def test_only_unheld_replacements_end_without_dispatching_a_batch(self):
        self.client.state['inventory'] = []
        result = cli.run(self.client, Path(self.temp.name) / 'out', minutes=1,
                         max_cells=2, pave=self.client.pave, monotonic=lambda: 0)
        self.assertEqual(result['status'], 'materials_exhausted')
        self.assertEqual(result['done'], 0)
        self.assertEqual(result['batches'], [])
        self.assertIn('minecraft:stone_bricks=', result['reason'])
        self.assertEqual(self.client.calls, [])

    def test_recovered_cell_with_unheld_replacement_remains_pending(self):
        pos = self.client.positions[0]
        self.client.write_journal(pos, 'recovered')
        self.client.audit['mismatches'][0].update(actual='Block{minecraft:air}', kind='missing')
        self.client.state['inventory'] = []
        with self.assertRaisesRegex(paving.PavingPending, 'awaits its replacement'):
            cli.select_batch(self.client, 4)

    def test_player_changed_untouched_cell_is_skipped(self):
        pos = self.client.positions[0]
        self.client.audit['mismatches'][0]['actual'] = 'Block{minecraft:stone}'
        selected, _ = cli.select_batch(self.client, 4)
        self.assertNotIn(list(pos), selected)

    def test_protected_buffer_is_preserved_by_selector(self):
        pos = self.client.positions[0]
        site = {**paving.SITE, 'protected_xz': ((pos[0], pos[0], pos[2], pos[2]),)}
        with patch.object(paving, 'SITE', site):
            selected, _ = cli.select_batch(self.client, 4)
        self.assertNotIn(list(pos), selected)

    def test_uncertain_native_receipt_reports_pending_journal_without_retry(self):
        def uncertain(client, positions, *, on_cell_complete):
            self.client.calls.append(copy.deepcopy(positions))
            self.client.write_journal(positions[0], 'mine_intent')
            raise RuntimeError('Native operation timed out')

        result = cli.run(self.client, Path(self.temp.name) / 'out', minutes=1,
                         max_cells=1, allowed_cells=[self.client.positions[0]],
                         pave=uncertain, monotonic=lambda: 0)
        self.assertEqual(result['status'], 'pending_review')
        self.assertEqual(result['batches'][0]['journal_phases'], {
            '_'.join(map(str, self.client.calls[0][0])): 'mine_intent'})
        self.assertEqual(len(self.client.calls), 1)

    def test_manual_handoff_stops_without_dispatching_a_second_batch(self):
        def handoff(client, positions, *, on_cell_complete):
            self.client.calls.append(copy.deepcopy(positions))
            raise Handoff('manual movement')

        result = cli.run(self.client, Path(self.temp.name) / 'out', minutes=1,
                         max_cells=1, allowed_cells=[self.client.positions[0]],
                         pave=handoff, monotonic=lambda: 0)
        self.assertEqual(result['status'], 'manual_handoff')
        self.assertEqual(len(self.client.calls), 1)

    def test_protocol_and_limits_fail_before_material_session(self):
        for values in ((0, 1, 1), (61, 1, 1), (20, 80, 1), (20, 1, 5)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                cli.validate_limits(*values)
        key = 'test-site'
        site = {**paving.SITE,
                'placement_key_sha256': hashlib.sha256(key.encode()).hexdigest()}
        state = {'connected': True, 'server': 'simpcraft.com:25565',
                 'dimension': 'minecraft:overworld', 'manual_movement': False,
                 'screen': '', 'dry_paving_protocol': 0, 'health': 20, 'food': 20,
                 'guard_armed': True, 'guard_pve_only': True, 'flight': True,
                 'projection_selection': {'key': key, 'min': list(site['bounds']['min']),
                                          'max': list(site['bounds']['max'])},
                 'pos': [761020.5, 100, 797854.5]}
        with (patch.object(paving, 'SITE', site),
              patch.object(cli, 'require_unlocked'),
              patch.object(cli, 'read_fresh', return_value=state)):
            with self.assertRaisesRegex(paving.PavingBlocked, 'protocol'):
                cli.preflight(Path(self.temp.name), [761020.5, 100, 797854.5])
            state['dry_paving_protocol'] = 1
            cli.preflight(Path(self.temp.name), [761020.5, 100, 797854.5])
            state['professional_printer'] = {'enabled': True}
            with self.assertRaises(paving.PavingBlocked):
                cli.preflight(Path(self.temp.name), [761020.5, 100, 797854.5])
            state['professional_printer'] = {'enabled': False}
            for flag in ('borer_active', 'chopping', 'navigating'):
                state[flag] = True
                with self.assertRaises(paving.PavingBlocked):
                    cli.preflight(Path(self.temp.name), [761020.5, 100, 797854.5])
                state[flag] = False
            with self.assertRaisesRegex(ValueError, '32 horizontal'):
                cli.preflight(Path(self.temp.name), [760982, 100, 797819])

    def test_guarded_recovery_choice_is_local(self):
        client = cli.DeterministicPavingClient.__new__(cli.DeterministicPavingClient)
        self.assertEqual(client.advise('recover', {'eat': 'meal', 'wait': 'pause'})['choice'], 'wait')

    def test_pave_batch_callback_runs_before_next_cell_failure(self):
        positions = [list(pos) for pos in self.client.positions[:2]]
        seen = []
        with patch.object(paving, '_one', side_effect=[
            {'pos': positions[0], 'result': 'placed'}, paving.PavingPending('uncertain')]):
            with self.assertRaises(paving.PavingPending):
                paving.pave_batch(self.client, positions, on_cell_complete=seen.append)
        self.assertEqual(seen, [{'pos': positions[0], 'result': 'placed'}])

    def test_high_park_is_rechecked_after_session_and_never_trusts_other_column(self):
        park = [761020.5, 100, 797854.5]

        class ParkClient:
            world = 'world-a'

            def __init__(self):
                self.pos = list(park)
                self.requests = []

            def status(self):
                return {'pos': self.pos}

            def request(self, op, **kwargs):
                self.requests.append((op, kwargs))
                # Native successful scans provide blocks and world scope but
                # do not set a phase field.
                return {'world_session': self.world,
                        'blocks': [{'pos': [761020, 70, 797854],
                                    'passable': False, 'fluid': False}]}

        client = ParkClient()
        self.assertGreaterEqual(cli.verify_high_park(client, park)['ground_clearance'], 20)
        self.assertEqual([op for op, _ in client.requests], ['scan'])
        client.pos = [760982.5, 100, 797819.5]
        with self.assertRaisesRegex(ValueError, '32 horizontal'):
            cli.verify_high_park(client, park)
        self.assertEqual(len(client.requests), 1)
        client.pos = list(park)

        def wrong_column(op, **kwargs):
            return {'phase': 'done', 'world_session': client.world,
                    'blocks': [{'pos': [761019, 70, 797854],
                                'passable': False, 'fluid': False}]}

        client.request = wrong_column
        with self.assertRaisesRegex(paving.PavingBlocked, 'unexpected cells'):
            cli.verify_high_park(client, park)

        client.request = lambda op, **kwargs: {
            'phase': 'error', 'world_session': client.world,
            'blocks': [{'pos': [761020, 70, 797854],
                        'passable': False, 'fluid': False}]}
        with self.assertRaisesRegex(paving.PavingBlocked, 'incomplete'):
            cli.verify_high_park(client, park)

    def test_material_client_assertion_is_json_blocked_and_no_work_runs(self):
        out = Path(self.temp.name) / 'assertion-result'
        output = io.StringIO()
        with (patch.object(cli, 'preflight'),
              patch.object(cli, 'DeterministicPavingClient', side_effect=AssertionError),
              patch.object(cli, 'run') as run, redirect_stdout(output)):
            code = cli.main(['--root', str(self.temp.name), '--out', str(out),
                             '--park-high', '761020.5', '100', '797854.5',
                             '--max-cells', '1', '--cell', *map(str, self.client.positions[0])])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())['status'], 'blocked_before_run')
        self.assertIn('assertion', output.getvalue())
        run.assert_not_called()

    def test_unverified_high_park_logs_out_without_starting_work(self):
        out = Path(self.temp.name) / 'park-failure'
        actions = []

        class FinishClient:
            def __init__(self, root, evidence, **kwargs):
                Path(evidence).mkdir(parents=True)

            def request(self, op, **kwargs):
                actions.append(op)

            def finish(self):
                actions.append('finish')

        output = io.StringIO()
        with (patch.object(cli, 'preflight'),
              patch.object(cli, 'verify_high_park', side_effect=paving.PavingBlocked('unsafe park')),
              patch.object(cli, 'DeterministicPavingClient', FinishClient),
              patch.object(cli, 'run') as run, redirect_stdout(output)):
            code = cli.main(['--root', str(self.temp.name), '--out', str(out),
                             '--park-high', '761020.5', '100', '797854.5',
                             '--max-cells', '1', '--cell', *map(str, self.client.positions[0])])
        self.assertEqual(code, 2)
        self.assertEqual(actions, ['safe_logout', 'finish'])
        self.assertEqual(json.loads(output.getvalue())['status'], 'blocked_before_run')
        run.assert_not_called()

    def test_required_root_and_max_cells_are_parser_errors(self):
        from contextlib import redirect_stderr

        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as missing_root:
            cli.main(['--out', str(Path(self.temp.name) / 'missing-root'),
                      '--park-high', '761020.5', '100', '797854.5', '--max-cells', '1'])
        self.assertEqual(missing_root.exception.code, 2)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as missing_max:
            cli.main(['--root', str(self.temp.name),
                      '--out', str(Path(self.temp.name) / 'missing-max'),
                      '--park-high', '761020.5', '100', '797854.5'])
        self.assertEqual(missing_max.exception.code, 2)

    def test_single_cell_without_exact_coordinate_is_json_blocked_before_preflight(self):
        output = io.StringIO()
        with patch.object(cli, 'preflight') as preflight, redirect_stdout(output):
            code = cli.main(['--root', str(self.temp.name),
                             '--out', str(Path(self.temp.name) / 'unnamed-cell'),
                             '--park-high', '761020.5', '100', '797854.5',
                             '--max-cells', '1'])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())['status'], 'blocked_before_run')
        preflight.assert_not_called()

    def test_single_cell_with_two_coordinates_is_json_blocked_before_preflight(self):
        output = io.StringIO()
        with patch.object(cli, 'preflight') as preflight, redirect_stdout(output):
            code = cli.main(['--root', str(self.temp.name),
                             '--out', str(Path(self.temp.name) / 'two-cells'),
                             '--park-high', '761020.5', '100', '797854.5',
                             '--max-cells', '1',
                             '--cell', *map(str, self.client.positions[0]),
                             '--cell', *map(str, self.client.positions[1])])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())['status'], 'blocked_before_run')
        preflight.assert_not_called()

    def test_terminal_result_requires_this_runs_high_guard_receipt(self):
        out = Path(self.temp.name) / 'run-result'

        class FinishClient:
            def __init__(self, root, evidence, **kwargs):
                self.evidence = Path(evidence)
                self.evidence.mkdir(parents=True)
                self.options = kwargs

            def finish(self):
                (self.evidence / 'stock-safety.json').write_text(
                    json.dumps({'action': 'KEEP_PVE_GUARD'}))

        def fake_run(client, evidence, **kwargs):
            result = {'status': 'completed', 'done': 1}
            cli._write_progress(evidence, result)
            return result

        output = io.StringIO()
        with (patch.object(cli, 'preflight'),
              patch.object(cli, 'verify_high_park', return_value={'ground_clearance': 30}),
              patch.object(cli, 'DeterministicPavingClient', FinishClient),
              patch.object(cli, 'run', fake_run), redirect_stdout(output)):
            code = cli.main(['--root', str(self.temp.name), '--out', str(out),
                             '--park-high', '761020.5', '100', '797854.5',
                             '--minutes', '1', '--max-cells', '1',
                             '--cell', *map(str, self.client.positions[0])])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result['finish']['state'], 'high_guard_confirmed')
        self.assertTrue(result['terminal'])
        self.assertFalse(result.get('finish_error'))

    def test_unconfirmed_finish_has_distinct_terminal_status(self):
        out = Path(self.temp.name) / 'unfinished-result'

        class FinishClient:
            def __init__(self, root, evidence, **kwargs):
                Path(evidence).mkdir(parents=True)

            def finish(self):
                pass

        def fake_run(client, evidence, **kwargs):
            result = {'status': 'completed', 'done': 1}
            cli._write_progress(evidence, result)
            return result

        output = io.StringIO()
        with (patch.object(cli, 'preflight'),
              patch.object(cli, 'verify_high_park', return_value={'ground_clearance': 30}),
              patch.object(cli, 'DeterministicPavingClient', FinishClient),
              patch.object(cli, 'run', fake_run), redirect_stdout(output)):
            code = cli.main(['--root', str(self.temp.name), '--out', str(out),
                             '--park-high', '761020.5', '100', '797854.5',
                             '--minutes', '1', '--max-cells', '1',
                             '--cell', *map(str, self.client.positions[0])])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())['status'], 'finish_unconfirmed')

    def test_material_exhaustion_is_normal_only_after_high_guard_receipt(self):
        class FinishClient:
            def __init__(self, root, evidence, **kwargs):
                self.evidence = Path(evidence)
                self.evidence.mkdir(parents=True)

            def finish(self):
                (self.evidence / 'stock-safety.json').write_text(
                    json.dumps({'action': 'KEEP_PVE_GUARD'}))

        def fake_run(client, evidence, **kwargs):
            result = {'status': 'materials_exhausted', 'done': 0,
                      'reason': 'No held replacement blocks'}
            cli._write_progress(evidence, result)
            return result

        output = io.StringIO()
        with (patch.object(cli, 'preflight'),
              patch.object(cli, 'verify_high_park', return_value={'ground_clearance': 30}),
              patch.object(cli, 'DeterministicPavingClient', FinishClient),
              patch.object(cli, 'run', fake_run), redirect_stdout(output)):
            code = cli.main(['--root', str(self.temp.name),
                             '--out', str(Path(self.temp.name) / 'material-exhaustion'),
                             '--park-high', '761020.5', '100', '797854.5',
                             '--max-cells', '1',
                             '--cell', *map(str, self.client.positions[0])])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['status'], 'materials_exhausted')

    def test_outer_failure_preserves_already_durable_cell_count(self):
        out = Path(self.temp.name) / 'outer-failure'

        class FinishClient:
            def __init__(self, root, evidence, **kwargs):
                Path(evidence).mkdir(parents=True)

            def finish(self):
                pass

        def broken_run(client, evidence, **kwargs):
            cli._write_progress(evidence, {'schema': 1, 'status': 'interrupted',
                                           'done': 1, 'cells': [{'pos': [1, 2, 3]}]})
            raise AssertionError('unexpected bug')

        output = io.StringIO()
        with (patch.object(cli, 'preflight'),
              patch.object(cli, 'verify_high_park', return_value={'ground_clearance': 30}),
              patch.object(cli, 'DeterministicPavingClient', FinishClient),
              patch.object(cli, 'run', broken_run), redirect_stdout(output)):
            code = cli.main(['--root', str(self.temp.name), '--out', str(out),
                             '--park-high', '761020.5', '100', '797854.5',
                             '--max-cells', '1', '--cell', *map(str, self.client.positions[0])])
        self.assertEqual(code, 2)
        result = json.loads(output.getvalue())
        self.assertEqual(result['done'], 1)
        self.assertEqual(result['cells'][0]['pos'], [1, 2, 3])
        self.assertEqual(json.loads((out / 'progress.json').read_text())['done'], 1)


if __name__ == '__main__':
    unittest.main()
