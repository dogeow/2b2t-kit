import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock

from material_worker_release import build
from singleplayer_trial_hot_update import (install_and_restart, load_checkpoint,
                                          restore_checkpoint, unresolved_mutations)
from singleplayer_trial import TrialSkills
from singleplayer_trial_bridge import TrialBridge


def setup(root):
    game = root / 'game'
    save = game / 'saves/Trial'
    save.mkdir(parents=True)
    trial = game / 'config/twob2tkit/singleplayer-trial'
    trial.mkdir(parents=True)
    automation = game / 'config/twob2tkit/automation'
    automation.mkdir()
    reg = {'protocol': 1, 'trial_id': 'trial-a', 'run_id': 'run-a', 'world_id': str(save),
           'world_name': 'Trial', 'enabled': True, 'allow_death_respawn': True, 'goal': 'defeat_ender_dragon'}
    (trial / 'registry.json').write_text(json.dumps(reg))
    state = {'time': int(time.time() * 1000), 'connected': True, 'server': 'singleplayer',
             'world_id': str(save), 'world_name': 'Trial', 'world_session': 'world-a',
             'singleplayer_trial_protocol': 1, 'singleplayer_trial_api_protocol': 1,
             'game_mode': 'survival', 'game_version': '26.1.2', 'health': 20, 'food': 20,
             'control_revision': 3, 'last_request': 'old', 'phase': 'done', 'screen': '',
             'manual_movement': False, 'pos': [.5, 70, .5], 'player_dead': False,
             'movement_keys': {'forward': False, 'back': False, 'jump': False, 'sneak': False},
             'trial_identity': {'registered': True, 'process_alive': True,
                                'trial_id': 'trial-a', 'run_id': 'run-a', 'world_id': str(save)}}
    source = root / 'source'
    source.mkdir()
    for file in ('material_jobs_cli.py', 'material_jobs_backend.py', 'singleplayer_trial.py',
                 'singleplayer_trial_bridge.py', 'singleplayer_experience.py', 'singleplayer_trial_cli.py',
                 'singleplayer_trial_hot_update.py'):
        (source / file).write_text('VALUE = "new verified worker"\n')
    (source / 'singleplayer_trial_capabilities.py').write_text('VALUE = "only registered macros"\n')
    bundle = root / 'worker.zip'
    build(source, bundle)
    installed = game / 'config/twob2tkit/material-worker'
    installed.mkdir()
    (installed / 'old.py').write_text('old source preserved')
    commands = []
    def native(unused, command):
        commands.append(command)
        state['time'] += 10
        if command == 'pause':
            state['phase'] = 'waiting'
        elif command == 'cancel':
            state['trial_identity'] = {**state['trial_identity'], 'process_alive': False, 'run_id': ''}
        elif command == 'start':
            state['trial_identity'] = {**state['trial_identity'], 'process_alive': True, 'run_id': 'run-new'}
            state['phase'] = 'done'
            (trial / 'registry.json').write_text(json.dumps({**reg, 'run_id': 'run-new'}))
        return {'phase': 'done', 'trial_identity': dict(state['trial_identity'])}
    return game, reg, state, bundle, commands, native


def mining_reply(reg, **changes):
    return {'id': 'trial-mine', 'op': 'mine_block', 'world_id': reg['world_id'],
            'world_session': 'world-a', 'server': 'singleplayer', 'phase': 'waiting',
            'trial_identity': {'trial_id': reg['trial_id'], 'run_id': reg['run_id']},
            'detail': 'mining target is occluded', 'mining_target': [3, 70, 1],
            'native_sequence': -1, 'server_ack_sequence': -1, 'outcome_pending': False,
            'server_update_seen': False, 'server_confirmed': False,
            'requested_confirmation_scope': 'single_target_server_block_update_and_native_sequence_ack',
            'confirmation_scope': 'none',
            'movement_keys': {'forward': False, 'back': False, 'jump': False, 'sneak': False}, **changes}


class HotUpdateTests(unittest.TestCase):
    def test_missing_dynamic_checkpoint_dependency_is_rejected_before_pause(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);game,reg,state,bundle,commands,native=setup(root)
            (root/'source/singleplayer_trial_hot_update.py').unlink()
            build(root/'source',bundle)
            with self.assertRaisesRegex(RuntimeError,'lifecycle modules'):
                install_and_restart(game,bundle,reader=lambda _:dict(state),native=native,
                                    import_checker=lambda *args:None,worker_checker=lambda:False)
            self.assertEqual([],commands)
    def test_verified_worker_swap_restarts_only_worker_and_preserves_trial_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game, reg, state, bundle, commands, native = setup(root)
            trial = game / 'config/twob2tkit/singleplayer-trial'
            (trial / 'experience').mkdir()
            experience = trial / 'experience/private.sqlite3'
            experience.write_bytes(b'unchanged experience')
            (trial / 'worker/bootstrap').mkdir(parents=True)
            journal = trial / 'worker/journal.jsonl'
            journal.write_text('native history\n')
            (trial / 'worker/bootstrap/status.json').write_text(json.dumps({
                'world_id': reg['world_id'], 'world_name': reg['world_name'],
                'camp': [0, 70, 0], 'stations': {'crafting_table': [4, 70, 0]},
                'inventory': {'diamond': 99}, 'camp_completed': True}))
            proof = install_and_restart(game, bundle, python=Path('/usr/bin/python3'),
                reader=lambda _: dict(state), native=native, import_checker=Mock(), worker_checker=lambda: False)
            self.assertEqual(['pause', 'cancel', 'start'], commands)
            self.assertFalse(proof['minecraft_restarted'])
            self.assertFalse(proof['native_actions_replayed'])
            self.assertFalse(proof['native_completion_claimed'])
            self.assertTrue(proof['checkpoint_preserved'])
            self.assertEqual('run-new', proof['after_run_id'])
            self.assertEqual(b'unchanged experience', experience.read_bytes())
            self.assertEqual('native history\n', journal.read_text())
            self.assertEqual('old source preserved', (Path(proof['installation']['backup']) / 'old.py').read_text())
            checkpoint = json.loads((trial / 'worker/checkpoint.json').read_text())
            self.assertNotIn('inventory', checkpoint)
            self.assertNotIn('camp_completed', checkpoint)
            self.assertEqual({'crafting_table': [4, 70, 0]}, checkpoint['stations'])

    def test_server_health_hold_other_run_or_pressed_keys_never_resume(self):
        cases = ({'server': 'server.example'}, {'health': 8}, {'safety_hold': {'active': True}},
                 {'trial_identity': {'registered': True, 'process_alive': True, 'trial_id': 'trial-a', 'run_id': 'other', 'world_id': 'ignored'}})
        for changes in cases:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as temp:
                game, reg, state, bundle, commands, native = setup(Path(temp))
                state.update(changes)
                with self.assertRaises(RuntimeError):
                    install_and_restart(game, bundle, reader=lambda _: dict(state), native=native,
                                        import_checker=Mock(), worker_checker=lambda: False)
                self.assertEqual([], commands)
                self.assertEqual('old source preserved', (game / 'config/twob2tkit/material-worker/old.py').read_text())

    def test_unknown_dispatched_mine_is_preserved_without_pause_or_install(self):
        with tempfile.TemporaryDirectory() as temp:
            game, reg, state, bundle, commands, native = setup(Path(temp))
            automation = game / 'config/twob2tkit/automation'
            request = {'id': 'trial-mine', 'op': 'mine_block', 'local_trial': True,
                       'trial_id': reg['trial_id'], 'world_id': reg['world_id'],
                       'world_session': 'world-a', 'pos': [3, 70, 1]}
            (automation / 'request.json').write_text(json.dumps(request))
            reply = automation / 'reply-trial-mine.json'
            reply.write_text(json.dumps(mining_reply(reg, native_sequence=8, outcome_pending=True)))
            original = reply.read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'Unconfirmed'):
                install_and_restart(game, bundle, reader=lambda _: dict(state), native=native,
                                    import_checker=Mock(), worker_checker=lambda: False)
            self.assertEqual([], commands)
            self.assertEqual(original, reply.read_bytes())
            self.assertTrue((game / 'config/twob2tkit/material-worker/old.py').is_file())

    def test_confirmed_zero_sequence_mine_preflight_refusal_is_not_pending_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            game, reg, state, bundle, commands, native = setup(Path(temp))
            automation = game / 'config/twob2tkit/automation'
            (automation / 'request.json').write_text(json.dumps({'id': 'trial-mine', 'op': 'mine_block',
                'local_trial': True, 'trial_id': reg['trial_id'], 'world_id': reg['world_id'],
                'world_session': 'world-a', 'pos': [3, 70, 1]}))
            (automation / 'reply-trial-mine.json').write_text(json.dumps(mining_reply(reg)))
            self.assertEqual([], unresolved_mutations(game, reg, state))
            proof = install_and_restart(game, bundle, python='/usr/bin/python3', reader=lambda _: dict(state),
                native=native, import_checker=Mock(), worker_checker=lambda: False)
            self.assertTrue(proof['new_worker_native_confirmed'])

    def test_world_change_during_pause_stops_before_cancel_or_replace(self):
        with tempfile.TemporaryDirectory() as temp:
            game, reg, state, bundle, commands, native = setup(Path(temp))
            def changed(unused, command):
                result = native(unused, command)
                state['world_session'] = 'foreign-world'
                return result
            with self.assertRaises(RuntimeError):
                install_and_restart(game, bundle, reader=lambda _: dict(state), native=changed,
                                    import_checker=Mock(), worker_checker=lambda: False)
            self.assertEqual(['pause'], commands)
            self.assertTrue((game / 'config/twob2tkit/material-worker/old.py').is_file())

    def test_install_failure_never_replays_start_or_native_action(self):
        with tempfile.TemporaryDirectory() as temp:
            game, reg, state, bundle, commands, native = setup(Path(temp))
            with self.assertRaises(OSError):
                install_and_restart(game, bundle, reader=lambda _: dict(state), native=native,
                    import_checker=Mock(), worker_checker=lambda: False,
                    installer=Mock(side_effect=OSError('disk failure')))
            self.assertEqual(['pause', 'cancel'], commands)
            proof = json.loads((game / 'config/twob2tkit/singleplayer-trial/hot-update-interrupted.json').read_text())
            self.assertFalse(proof['automatic_retry_allowed'])
            self.assertFalse(proof['resume_confirmed'])


class CheckpointTests(unittest.TestCase):
    def test_second_world_never_loads_first_world_coordinates_or_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            game, reg, state, bundle, commands, native = setup(Path(temp))
            checkpoint = game / 'config/twob2tkit/singleplayer-trial/worker/checkpoint.json'
            checkpoint.parent.mkdir()
            checkpoint.write_text(json.dumps({'schema': 1, 'world_id': '/some/other/save',
                'trial_id': reg['trial_id'], 'game_version': '26.1.2', 'camp': [999, 70, 999]}))
            self.assertIsNone(load_checkpoint(game, reg, state))

    def test_stations_and_camp_completion_require_actual_native_block_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            game, reg, state, bundle, commands, native = setup(Path(temp))
            class Bridge:
                world = reg['world_name']
                root = game / 'config/twob2tkit/automation'
                calls = []
                def __init__(self): self.state = state
                def read(self): return self.state
                def request(self, op, **args):
                    self.calls.append((op, args))
                    rows = []
                    if args['min'] == args['max'] == [4, 70, 0]:
                        rows = [{'pos': [4, 70, 0], 'state': 'Block{minecraft:crafting_table}', 'solid': True}]
                    return {'blocks': rows}
            bridge = Bridge()
            skills = TrialSkills(bridge, game)
            checkpoint = {'schema': 1, 'world_id': reg['world_id'], 'trial_id': reg['trial_id'],
                'game_version': '26.1.2', 'stations': {'crafting_table': [4, 70, 0], 'furnace': [5, 70, 0]},
                'camp': [0, 70, 0], 'camp_completed': True, 'inventory': {'diamond': 99}}
            restored = restore_checkpoint(skills, checkpoint, reg, state)
            self.assertEqual({'crafting_table': [4, 70, 0]}, skills.stations)
            self.assertIsNone(skills.camp)
            self.assertFalse(skills.camp_completed)
            self.assertFalse(restored['inventory_restored'])
            self.assertFalse(restored['native_request_replayed'])
            self.assertTrue(all(op == 'scan' for op, args in bridge.calls))


if __name__ == '__main__':
    unittest.main()
