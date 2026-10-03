import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import kit_cli
from farm_preparation import journal_directory
from farm_preparation_cli import _FinalizingClient, execute, main


class PreparationCliTest(unittest.TestCase):
    def state(self):
        return {'server': 'example.com', 'world_session': 'w', 'dimension': 'minecraft:overworld',
                'connected': True, 'manual_movement': False, 'screen': '', 'health': 20,
                'food': 20, 'game_mode': 'survival', 'recent_hurt_at': 0, 'pos': [1.5, 80, 2.5]}

    def test_parser_and_kit_route_forward_explicit_source_and_budget(self):
        with patch('farm_preparation_cli.main', return_value=0) as delegated:
            self.assertEqual(0, kit_cli.main(['--game-dir', '/test', 'farm', 'prepare',
                '--center', '1', '63', '2', '--radius', '1', '--water-source', '4', '62', '5',
                '--max-torches', '2', '--out', '/proof', '--no-move']))
        self.assertEqual(['--game-dir', '/test', '--center', '1', '63', '2', '--radius', '1',
            '--max-torches', '2', '--water-source', '4', '62', '5', '--out', '/proof', '--no-move'], delegated.call_args.args[0])
        with patch('farm_preparation_cli.execute', return_value={'phase': 'done'}) as called, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, main(['--center', '1', '63', '2', '--radius', '1', '--no-move']))
        self.assertEqual(([1, 63, 2], 1, None, None, True, 4), called.call_args.args[1:])

    def test_invalid_radius_does_not_touch_game(self):
        with patch('farm_preparation_cli.execute') as called, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit): main(['--center', '1', '63', '2', '--radius', '3'])
        called.assert_not_called()

    def test_pending_or_unknown_control_acquisition_never_creates_second_controller(self):
        with tempfile.TemporaryDirectory() as d:
            game = Path(d); root = game / 'config/twob2tkit/automation'; state = self.state()
            with patch('farm_preparation_cli.read_fresh', return_value=state), patch('farm_preparation_cli.require_unlocked'), \
                    patch('farm_preparation_cli.MaterialClient', side_effect=RuntimeError('factory unknown')) as factory:
                with self.assertRaisesRegex(RuntimeError, 'factory unknown'): execute(game, [1, 63, 2])
                result = execute(game, [1, 63, 2]); self.assertEqual('WAIT_RECONCILE', result['code'])
                self.assertEqual(1, factory.call_count)
            book = json.loads(Path(result['journal']).read_text())
            self.assertEqual('acquire_control', book['pending']['op'])

    def test_changed_world_or_output_is_refused_before_controller_creation(self):
        with tempfile.TemporaryDirectory() as d:
            game = Path(d); root = game / 'config/twob2tkit/automation'; state = self.state()
            journal_directory(root, state, {'authorized': True, 'center': [1, 63, 2], 'radius': 2})
            for world, out in [('new', None), ('w', game / 'new')]:
                with self.subTest(world=world), patch('farm_preparation_cli.read_fresh', return_value={**state, 'world_session': world}), \
                        patch('farm_preparation_cli.require_unlocked'), patch('farm_preparation_cli.MaterialClient') as factory:
                    with self.assertRaises(RuntimeError): execute(game, [1, 63, 2], out=out)
                    factory.assert_not_called()


class FinishIntentTest(unittest.TestCase):
    def fixture(self, root):
        journal = root / 'journal.json'; journal.write_text('{"pending":null,"actions":[]}')
        c = Mock(); c.out = root; c.world = 'w'; c.task = 't'; c.rev = 2; c.heartbeat.id = 'l'; c.last = 'r'; c.park_target = [1, 100, 2]
        c.raw.return_value = {'time': 1010, 'connected': True, 'world_session': 'w', 'control_revision': 2,
            'health': 20, 'food': 20, 'pos':[1,100,2], 'manual_movement': False, 'screen': '', 'under_water': False,
            'safety_hold': {'active': False}, 'flight': True, 'guard_armed': True,
            'guard_pve_only': True, 'guard_busy': False, 'navigating': False,
            'supervision_lease': {'id': 'l', 'kind': 'parking', 'world_session': 'w', 'revision': 2,
                                  'job_session': 't', 'park_target': [1, 100, 2]}}
        c.park_near.return_value = True
        return c, journal, _FinalizingClient(c, journal)

    def test_unknown_guarded_finish_retains_intent_and_cannot_repeat(self):
        with tempfile.TemporaryDirectory() as d:
            c, journal, finalizer = self.fixture(Path(d)); c.finish.side_effect = RuntimeError('finish unknown')
            with self.assertRaises(RuntimeError): finalizer.finish()
            with self.assertRaises(RuntimeError): finalizer.finish()
            self.assertEqual(1, c.finish.call_count)
            self.assertEqual('guarded_finish', json.loads(journal.read_text())['pending']['op'])

    def test_native_owned_parking_receipt_completes_finish(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); c, journal, finalizer = self.fixture(root)
            proof = {'action': 'KEEP_PVE_GUARD', 'lease': 'l', 'job_session': 't', 'time': 1000,
                     'snapshot': {'world_session': 'w', 'flight': True, 'guard_armed': True,
                                  'supervision_lease': {'id': 'l', 'kind': 'parking'}}}
            (root / 'stock-safety.json').write_text(json.dumps(proof))
            finalizer.finish(); self.assertIsNone(json.loads(journal.read_text())['pending'])

    def test_actual_native_receipt_without_snapshot_uses_fresh_parking_observation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); c, journal, finalizer = self.fixture(root)
            proof = {'lease': 'l', 'job_session': 't', 'cause': 'controller_finished',
                     'action': 'KEEP_PVE_GUARD', 'time': 1000, 'confirmed': False}
            (root / 'stock-safety.json').write_text(json.dumps(proof))
            finalizer.finish(); book = json.loads(journal.read_text())
            self.assertIsNone(book['pending']); self.assertFalse(book['actions'][-1]['receipt']['confirmed'])
            self.assertEqual(c.raw.return_value, book['actions'][-1]['receipt']['fresh_observation'])
            self.assertEqual(proof, json.loads((root / 'stock-safety.json').read_text()))

    def test_current_parking_state_must_match_receipt_owner_world_revision_and_target(self):
        for key, value in [('world_session', 'other'), ('control_revision', 9), ('health', 19),
                           ('guard_busy', True), ('flight', False)]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as d:
                root = Path(d); c, journal, finalizer = self.fixture(root)
                c.raw.return_value[key] = value
                (root / 'stock-safety.json').write_text(json.dumps({'action': 'KEEP_PVE_GUARD', 'lease': 'l',
                    'job_session': 't', 'time': 1000, 'confirmed': False}))
                with self.assertRaises(RuntimeError): finalizer.finish()
                self.assertIsNotNone(json.loads(journal.read_text())['pending'])

    def test_native_settled_anchor_may_differ_from_requested_height(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c,journal,finalizer=self.fixture(root)
            c.raw.return_value['pos']=[1,99.7594867,2]
            c.raw.return_value['supervision_lease']['park_target']=[1,99.7594867,2]
            proof={'lease':'l','job_session':'t','action':'KEEP_PVE_GUARD','time':1000,'confirmed':False}
            (root/'stock-safety.json').write_text(json.dumps(proof))
            finalizer.finish();self.assertIsNone(json.loads(journal.read_text())['pending'])
    def test_native_anchor_must_equal_current_pose_and_remain_near_requested_target(self):
        from farm_preparation_cli import parking_anchor_matches
        self.assertTrue(parking_anchor_matches([1,100,2],{'pos':[1,99.76,2],'supervision_lease':{'park_target':[1,99.76,2]}}))
        self.assertFalse(parking_anchor_matches([1,100,2],{'pos':[1,95,2],'supervision_lease':{'park_target':[1,95,2]}}))
        self.assertFalse(parking_anchor_matches([1,100,2],{'pos':[1,100,2],'supervision_lease':{'park_target':[1,98,2]}}))

    def test_read_only_reconciliation_uses_original_park_receipt_without_a_controller(self):
        from farm_preparation_cli import reconcile_guarded_finish
        from farm_preparation import _scope
        with tempfile.TemporaryDirectory() as d:
            game=Path(d);root=game/'config/twob2tkit/automation'
            c,unused,finalizer=self.fixture(game)
            state={**c.raw.return_value,'server':'example.com','dimension':'minecraft:overworld'}
            request={'authorized':True,'center':[1,63,2],'radius':2}
            directory,journal=journal_directory(root,state,request)
            lease={'id':'l','job_session':'t','world_session':'w','kind':'materials'}
            park={'op':'material_job_park','params':{'park_target':[1,100,2]},
                  'receipt':{'phase':'done','id':'park','world_session':'w','time':990,'supervision_lease':lease}}
            book={'schema':1,'scope':_scope(state,request),'world_session':'w','complete':True,
                  'pending':{'op':'guarded_finish','params':{'park_target':[1,100,2]}},'actions':[park]}
            journal.write_text(json.dumps(book));proof_dir=directory/'control-original';proof_dir.mkdir()
            proof={'lease':'l','job_session':'t','action':'KEEP_PVE_GUARD','time':1000,'confirmed':False}
            (proof_dir/'stock-safety.json').write_text(json.dumps(proof))
            with patch('farm_preparation_cli.read_fresh',return_value=state),patch('farm_preparation_cli.require_unlocked'),patch('farm_preparation_cli.MaterialClient') as factory:
                result=reconcile_guarded_finish(game,[1,63,2]);factory.assert_not_called()
            self.assertEqual(0,result['game_actions']);self.assertTrue(result['field_complete'])
            book=json.loads(journal.read_text());self.assertIsNone(book['pending']);self.assertFalse(book['actions'][-1]['receipt']['confirmed'])

    def test_unknown_pause_retains_both_original_and_cleanup_intents(self):
        with tempfile.TemporaryDirectory() as d:
            c, journal, finalizer = self.fixture(Path(d))
            journal.write_text('{"pending":{"op":"bucket_fill"},"actions":[]}')
            c.request.return_value = {'id': 'r', 'world_session': 'w', 'phase': 'waiting'}
            with self.assertRaises(RuntimeError): finalizer.request('material_job_pause', release=False)
            book = json.loads(journal.read_text())
            self.assertEqual('bucket_fill', book['pending']['op'])
            self.assertEqual('material_job_pause', book['cleanup_pending']['op'])

    def test_foreign_or_stale_finish_receipt_never_erases_intent(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); c, journal, finalizer = self.fixture(root)
            (root / 'stock-safety.json').write_text('{"action":"KEEP_PVE_GUARD","lease":"foreign"}')
            with self.assertRaises(RuntimeError): finalizer.finish()
            self.assertIsNotNone(json.loads(journal.read_text())['pending'])


if __name__ == '__main__': unittest.main()
