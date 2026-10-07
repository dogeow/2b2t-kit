import json
import math
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

from decisions import DecisionError
from singleplayer_trial import TrialSkills, TrialWorker, TrialWorld, GAPS, short_term_goal
from survival_world import center
from singleplayer_trial_bridge import (TrialBridge, TrialDeath, TrialMovementBlocked,
                                      TrialMiningRejected, Paused, validate_registry, validate_scope)


def registry(game):
    save = Path(game) / 'saves/Trial'
    save.mkdir(parents=True, exist_ok=True)
    return {'protocol': 1, 'trial_id': 'trial-a', 'run_id': 'run-a',
            'world_id': str(save.resolve()), 'world_name': 'Clef Dragon Trial A',
            'enabled': True, 'allow_death_respawn': True, 'goal': 'defeat_ender_dragon'}


def state(reg, **updates):
    return {'time': int(time.time() * 1000), 'singleplayer_trial_protocol': 1,
            'connected': True, 'server': 'singleplayer', 'game_mode': 'survival',
            'game_version': '26.1.2', 'kit_version': '2026.10.7.3', 'runtime_version': '1.7.83',
            'difficulty': 'normal', 'dimension': 'minecraft:overworld',
            'world_id': reg['world_id'], 'world_name': reg['world_name'],
            'world_session': 'session-a', 'control_revision': 4, 'last_request': 'old',
            'trial_identity': {'registered': True, 'trial_id': reg['trial_id'],
                               'run_id': reg['run_id'], 'world_id': reg['world_id']},
            'health': 20, 'food': 20, 'player_dead': False, 'trial_deaths': 0,
            'screen': '', 'game_paused': False, 'manual_movement': False,
            'movement_keys': {'forward': False, 'back': False, 'jump': False, 'sneak': False},
            'pos': [.5, 1, .5], 'phase': 'done', 'inventory': [], 'entities': [],
            'bridge_version': 4, 'hand': {'item': 'minecraft:air'},
            'menu': {'id': 0, 'cursor': {'count': 0}, 'slots': []}, **updates}


def row(point, name):
    return {'pos': list(point), 'state': 'Block{minecraft:' + name + '}',
            'solid': True, 'passable': False, 'fluid': False, 'block_entity': False}


def terrain():
    return [row((x, 0, z), 'stone') for x in range(-10, 11) for z in range(-10, 11)]


class ScopeTests(unittest.TestCase):
    def test_only_explicit_direct_save_is_registered(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            self.assertEqual(reg, validate_registry(reg, game))
            for change in ({'enabled': False}, {'allow_death_respawn': False},
                           {'goal': 'mine'}, {'world_id': '/tmp/some-real-world'},
                           {'trial_id': '../../bad'}):
                with self.subTest(change=change), self.assertRaises(Paused):
                    validate_registry({**reg, **change}, game)

    def test_linked_save_is_not_granted_trial_control(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            link = Path(game) / 'saves/linked'
            link.symlink_to(reg['world_id'], target_is_directory=True)
            with self.assertRaises(Paused):
                validate_registry({**reg, 'world_id': str(link)}, game)

    def test_server_other_save_creative_and_foreign_run_cannot_receive_actions(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            original = state(reg)
            for change in ({'server': 'simpcraft.com'}, {'game_mode': 'creative'},
                           {'world_id': str(Path(game) / 'saves/My Real World')},
                           {'world_name': 'My Real World'},
                           {'trial_identity': {**original['trial_identity'], 'run_id': 'other-run'}},
                           {'singleplayer_trial_protocol': 0}):
                with self.subTest(change=change), self.assertRaises(Paused):
                    validate_scope({**original, **change}, reg, run_id='run-a')

    def test_low_health_is_allowed_only_registered_trial_and_death_is_separate(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            validate_scope(state(reg, health=2, food=0), reg, run_id='run-a')
            with self.assertRaises(TrialDeath):
                validate_scope(state(reg, health=0, player_dead=True, screen='DeathScreen'), reg)
            validate_scope(state(reg, health=0, player_dead=True, screen='DeathScreen'), reg, allow_dead=True)

    def test_manual_and_menu_always_yield_even_when_background(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            for change in ({'manual_movement': True}, {'screen': 'ChatScreen'}, {'game_paused': True}):
                with self.subTest(change=change), self.assertRaises(Paused):
                    validate_scope(state(reg, **change), reg, run_id='run-a')


class BridgeTests(unittest.TestCase):
    def test_only_proven_not_sent_mining_refusal_can_skip_target_and_rescan(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            for changes, recover in (({}, True), ({'native_sequence': 0}, False),
                                     ({'outcome_pending': True}, False), ({'server_update_seen': True}, False),
                                     ({'mining_target': [4, 1, 0]}, False)):
                with self.subTest(changes=changes):
                    root = Path(game) / ('case-' + str(len(list(Path(game).iterdir()))))
                    root.mkdir()
                    def read(unused):
                        path = root / 'request.json'
                        if not path.exists(): return state(reg)
                        req = json.loads(path.read_text())
                        result = {'id': req['id'], 'op': req['op'], 'last_request': req['id'], 'phase': 'waiting',
                            'detail': 'mining target is occluded', 'control_revision': 5,
                            'native_sequence': -1, 'server_ack_sequence': -1, 'outcome_pending': False,
                            'server_update_seen': False, 'server_confirmed': False,
                            'confirmation_scope': 'none',
                            'requested_confirmation_scope': 'single_target_server_block_update_and_native_sequence_ack',
                            'mining_target': [3, 1, 0], **changes}
                        if req['op'] == 'scan': result.update(phase='done', blocks=terrain())
                        return state(reg, **result)
                    bridge = TrialBridge(root, reg, 'run-a', reader=read)
                    with self.assertRaises(Paused) as error:
                        bridge.request('mine_block', pos=[3, 1, 0], expected_state='Block{minecraft:oak_log}')
                    self.assertEqual(recover, isinstance(error.exception, TrialMiningRejected))
                    self.assertEqual(not recover, bridge.halted)
                    if recover:
                        self.assertEqual('mining target is occluded', str(error.exception))
                        self.assertFalse(bridge.pending_mutations)
                        self.assertIn('blocks', bridge.request('scan', min=[-10, -5, -10], max=[10, 7, 10]))
                    else:
                        self.assertTrue(bridge.pending_mutations)

    def test_request_uses_verified_save_run_scope_and_real_reply(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            root = Path(game) / 'automation'
            root.mkdir()
            def read(unused):
                path = root / 'request.json'
                if not path.exists():
                    return state(reg)
                req = json.loads(path.read_text())
                return state(reg, id=req['id'], last_request=req['id'], phase='done',
                             control_revision=5, inventory=[{'item': 'minecraft:oak_log', 'count': 1}])
            bridge = TrialBridge(root, reg, 'run-a', reader=read)
            result = bridge.request('mine_block', pos=[2, 1, 0], expected_state='Block{minecraft:oak_log}', seconds=1)
            request = json.loads((root / 'request.json').read_text())
            self.assertTrue(request['local_trial'])
            self.assertTrue(request['local_survival'])
            self.assertEqual(reg['world_id'], request['world_id'])
            self.assertEqual('run-a', request['run_id'])
            self.assertEqual(5, bridge.revision)
            self.assertEqual(1, result['inventory'][0]['count'])
            self.assertTrue(bridge.last_receipt['native'])

    def test_model_generated_or_broad_commands_never_reach_mailbox(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            root = Path(game)
            bridge = TrialBridge(root, reg, 'run-a', reader=lambda _: state(reg))
            for op in ('stop', 'safe_logout', 'navigate', 'execute_code', 'give', 'teleport'):
                with self.subTest(op=op), self.assertRaises(Paused):
                    bridge.request(op)
            self.assertFalse((root / 'request.json').exists())

    def test_foreign_pending_and_scope_override_are_preserved(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            root = Path(game)
            bridge = TrialBridge(root, reg, 'run-a', reader=lambda _: state(reg))
            with self.assertRaises(Paused):
                bridge.request('snapshot', world_id='/tmp/other')
            pending = root / 'request.json'
            pending.write_text('{"id":"foreign"}')
            with self.assertRaises(Paused):
                bridge.request('snapshot')
            self.assertEqual({'id': 'foreign'}, json.loads(pending.read_text()))

    def test_waiting_native_result_latches_and_never_replays(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            root = Path(game)
            def read(unused):
                pending = root / 'request.json'
                if not pending.exists():
                    return state(reg)
                req = json.loads(pending.read_text())
                return state(reg, id=req['id'], last_request=req['id'],
                             control_revision=6, phase='waiting', detail='stuck')
            bridge = TrialBridge(root, reg, 'run-a', reader=read)
            with self.assertRaises(Paused):
                bridge.request('walk', target=[1.5, 1, .5])
            original = (root / 'request.json').read_text()
            with self.assertRaises(Paused):
                bridge.request('walk', target=[1.5, 1, .5])
            self.assertEqual(original, (root / 'request.json').read_text())
            self.assertTrue(bridge.halted)

    def test_scope_revision_change_is_not_an_automatic_resume(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            current = state(reg)
            bridge = TrialBridge(game, reg, 'run-a', reader=lambda _: current)
            current['control_revision'] += 1
            with self.assertRaises(Paused):
                bridge.read()
            self.assertTrue(bridge.halted)

    def test_death_prevents_any_mutation_except_exact_respawn(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            root = Path(game)
            def read(unused):
                path = root / 'request.json'
                if not path.exists():
                    return state(reg, health=0, player_dead=True, screen='DeathScreen', trial_deaths=1)
                req = json.loads(path.read_text())
                return state(reg, id=req['id'], last_request=req['id'], phase='done',
                             world_session='new-respawn-session', control_revision=8, trial_deaths=1)
            bridge = TrialBridge(root, reg, 'run-a', reader=read)
            with self.assertRaises(TrialDeath):
                bridge.request('mine_block', pos=[1, 1, 1])
            after = bridge.request('trial_respawn', death_epoch=1)
            self.assertFalse(after['player_dead'])
            self.assertEqual('new-respawn-session', bridge.session)
            self.assertEqual(8, bridge.revision)

    def test_confirmed_terrain_movement_refusal_adopts_revision_but_never_replays_route(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            root = Path(game)
            sent = []
            def read(unused):
                path = root / 'request.json'
                if not path.exists(): return state(reg)
                req = json.loads(path.read_text())
                if not sent or sent[-1] != req['id']: sent.append(req['id'])
                if req['op'] == 'scan':
                    return state(reg, id=req['id'], op='scan', last_request=req['id'],
                                 control_revision=6, phase='done', blocks=terrain())
                return state(reg, id=req['id'], op='walk_path', last_request=req['id'],
                             control_revision=6, phase='waiting', pos=[1.2, 1, .5],
                             detail='unsafe drop ahead; choose another walking waypoint')
            bridge = TrialBridge(root, reg, 'run-a', reader=read)
            path = [[1.5, 1, .5], [2.5, 1, .5]]
            with self.assertRaises(TrialMovementBlocked) as result:
                bridge.request('walk_path', path=path)
            self.assertFalse(bridge.halted)
            self.assertEqual(6, bridge.revision)
            self.assertEqual('path_blocked', result.exception.receipt['code'])
            old_mailbox = (root / 'request.json').read_text()
            with self.assertRaises(TrialMovementBlocked):
                bridge.request('walk_path', path=path)
            self.assertEqual(old_mailbox, (root / 'request.json').read_text())
            observed = bridge.request('scan', min=[-10, -5, -10], max=[10, 7, 10], details=True)
            self.assertIn('blocks', observed)
            self.assertEqual(2, len(sent))
            self.assertFalse(bridge.halted)

    def test_movement_recovery_requires_exact_refusal_and_released_native_keys(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            for op, change in (
                ('walk_path', {'detail': 'unknown waiting'}),
                ('walk_path', {'movement_keys': {'forward': True, 'back': False, 'jump': False, 'sneak': False}}),
                ('walk_path', {'movement_keys': {}}),
                ('walk_path', {'phase': 'error'}),
                ('walk_path', {'outcome_pending': True}),
                ('mine_block', {}), ('interact', {}), ('craft_recipe', {})):
                with self.subTest(op=op, change=change):
                    root = Path(game) / ('case-' + str(len(list(Path(game).iterdir()))))
                    root.mkdir()
                    def read(unused):
                        path = root / 'request.json'
                        if not path.exists(): return state(reg)
                        req = json.loads(path.read_text())
                        return state(reg, **{'id': req['id'], 'op': op, 'last_request': req['id'],
                                            'control_revision': 6, 'phase': 'waiting',
                                            'detail': 'unsafe drop ahead; choose another walking waypoint', **change})
                    bridge = TrialBridge(root, reg, 'run-a', reader=read)
                    with self.assertRaises(Paused) as error: bridge.request(op)
                    self.assertNotIsInstance(error.exception, TrialMovementBlocked)
                    self.assertTrue(bridge.halted)


class SkillsTests(unittest.TestCase):
    def test_confirmed_log_drops_take_priority_and_unknown_pickup_never_counts_as_wood(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            entity = {'uuid': 'log-drop-a', 'id': 4, 'type': 'minecraft:item', 'visible': True,
                      'pos': [2.6, 1, .5], 'stack': {'item': 'minecraft:dark_oak_log', 'count': 3}}
            current = state(reg, entities=[entity], on_ground=True)
            bridge = TrialBridge(game, reg, 'run-a', reader=lambda _: current)
            skills = TrialSkills(bridge, game)
            world = TrialWorld(terrain() + [row((5, 1, 0), 'oak_log')], [-10, -5, -10], [10, 7, 10])
            choices = skills.candidates(current, world)
            self.assertIn('collect_log_drops', choices)
            self.assertNotIn('gather_starting_wood', choices)
            self.assertIn('dropped logs', short_term_goal(current, choices))
            skills.scan = lambda: world
            skills.walk_pickup_route = Mock()
            bridge.wait = lambda _: None
            with self.assertRaisesRegex(Paused, 'no inventory gain'):
                skills.collect_log_drops()
            self.assertEqual(0, sum(row['count'] for row in current['inventory']))
            self.assertEqual(3, sum(row['count'] for row in skills.log_drops.values()))
            self.assertFalse((Path(game) / 'request.json').exists())

    def test_normal_collision_pickup_only_succeeds_on_actual_inventory_gain(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            current = state(reg, on_ground=True, entities=[{'uuid': 'item-a', 'type': 'minecraft:item',
                'visible': True, 'pos': [2.6, 1, .5], 'stack': {'item': 'minecraft:dark_oak_log', 'count': 3}}])
            bridge = TrialBridge(game, reg, 'run-a', reader=lambda _: current)
            skills = TrialSkills(bridge, game)
            world = TrialWorld(terrain(), [-10, -5, -10], [10, 7, 10])
            skills.scan = lambda: world
            skills.walk_pickup_route = Mock()
            def collision_wait(unused):
                current['inventory'] = [{'item': 'minecraft:dark_oak_log', 'count': 3}]
                current['entities'] = []
                current['time'] += 100
            bridge.wait = collision_wait
            after = skills.collect_log_drops()
            self.assertEqual(3, after['inventory'][0]['count'])
            self.assertEqual({}, skills.log_drops)
            self.assertLessEqual(len(skills.walk_pickup_route.call_args.args[0]), 32)
            self.assertFalse((Path(game) / 'request.json').exists())

    def test_disconnected_canopy_drops_are_preserved_without_more_mining_or_far_exploration(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            entity = {'uuid': 'ground-log', 'type': 'minecraft:item', 'visible': True,
                      'pos': [1.5, 1, .5], 'stack': {'item': 'minecraft:oak_log', 'count': 9}}
            current = state(reg, pos=[.5, 4, .5], on_ground=True, entities=[entity])
            bridge = TrialBridge(game, reg, 'run-a', reader=lambda _: current)
            skills = TrialSkills(bridge, game)
            world = TrialWorld([row((0, 3, 0), 'oak_leaves'), row((1, 0, 0), 'stone'),
                                row((2, 4, 0), 'oak_log')], [-3, 0, -3], [3, 7, 3])
            choices = skills.candidates(current, world)
            self.assertNotIn('collect_log_drops', choices)
            self.assertNotIn('gather_starting_wood', choices)
            self.assertNotIn('explore_nearby', choices)
            self.assertEqual(9, sum(row['count'] for row in skills.log_drops.values()))
            self.assertEqual(0, len(current['inventory']))

    def test_pickup_graph_allows_only_verified_adjacent_dry_two_block_descent(self):
        rows = [row((0, 2, 0), 'oak_leaves'), row((1, 0, 0), 'stone')]
        world = TrialWorld(rows, [-2, 0, -2], [2, 5, 2])
        source, target = (0, 3, 0), (1, 1, 0)
        self.assertTrue(world.safe_two_block_descent(source, target, [.5, 3, .5]))
        self.assertNotIn(target, world.paths([.5, 3, .5]))
        self.assertIn(target, world.pickup_paths([.5, 3, .5]))
        self.assertFalse(world.safe_two_block_descent(source, (1, 0, 0)))
        self.assertFalse(world.safe_two_block_descent(source, target, [.85, 3, .5]))
        blocked = TrialWorld(rows + [row((1, 4, 0), 'stone')], [-2, 0, -2], [2, 5, 2])
        self.assertFalse(blocked.safe_two_block_descent(source, target))
        wet = row((1, 0, 0), 'water'); wet.update(fluid=True, solid=False, passable=True)
        self.assertFalse(TrialWorld([rows[0], wet], [-2, 0, -2], [2, 5, 2]).safe_two_block_descent(source, target))

    def test_two_block_descent_uses_only_normal_walk_and_checks_real_arrival_health(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            current = state(reg, pos=[.5, 3, .5], on_ground=True)
            class Bridge:
                world = reg['world_name']
                calls = []
                def __init__(self): self.state = current
                def read(self): return self.state
                def request(self, op, **args):
                    self.calls.append((op, args))
                    self.state = {**self.state, 'pos': args['target']}
                    return self.state
            bridge = Bridge()
            skills = TrialSkills(bridge, game)
            skills.scan = lambda: TrialWorld([row((0, 2, 0), 'oak_leaves'), row((1, 0, 0), 'stone')],
                                             [-2, 0, -2], [2, 5, 2])
            skills.walk_pickup_route([(1, 1, 0)])
            self.assertEqual(['walk'], [op for op, args in bridge.calls])
            self.assertEqual([1.5, 1, .5], bridge.calls[0][1]['target'])
            self.assertFalse(bridge.calls[0][1]['restore_flight'])
            self.assertTrue(all(op not in {'mine_block', 'interact', 'navigate', 'collect_item'} for op, args in bridge.calls))

    def test_walkable_soft_plant_is_outline_obstacle_for_log_mining_stance(self):
        from survival_world import World
        grass = row((2, 1, 0), 'short_grass')
        grass.update(solid=False, passable=True)
        rows = terrain() + [grass, row((3, 1, 0), 'oak_log')]
        old = World(rows, [-10, -5, -10], [10, 7, 10])
        trial = TrialWorld(rows, [-10, -5, -10], [10, 7, 10])
        self.assertTrue(old.sight((0, 1, 0), (3, 1, 0)))
        self.assertFalse(trial.sight((0, 1, 0), (3, 1, 0)))
        self.assertTrue(trial.sight((3, 1, 2), (3, 1, 0)))
        self.assertTrue(trial.open((2, 1, 0)))

    def test_high_tree_has_bare_hand_side_candidate_without_mining_footing(self):
        world = TrialWorld(terrain() + [row((2, y, 0), 'oak_log') for y in range(1, 8)],
                           [-10, -5, -10], [10, 7, 10])
        candidate = world.resource([.5, 1, .5], {'oak_log'})
        self.assertIsNotNone(candidate)
        self.assertLessEqual(candidate[0][1], 4)
        self.assertEqual('oak_log', world.name(candidate[0]))
        self.assertIsNone(world.resource([2.5, 2, .5], {'oak_log'},
                                        {(2, y, 0) for y in range(2, 8)}))

    def test_lava_tree_and_unknown_route_are_not_feasible_actions(self):
        rows = terrain() + [row((2, 1, 0), 'oak_log'), row((2, 1, 1), 'lava')]
        world = TrialWorld(rows, [-10, -5, -10], [10, 7, 10])
        self.assertIsNone(world.resource([.5, 1, .5], {'oak_log'}))
        self.assertFalse(world.stand((11, 1, 0)))

    def test_candidates_need_real_stock_and_never_offer_missing_dragon_skills(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            bridge = TrialBridge(game, reg, 'run-a', reader=lambda _: state(reg))
            skills = TrialSkills(bridge, Path(game) / 'out')
            skills.camp = [0, 1, 0]
            world = TrialWorld(terrain(), [-10, -5, -10], [10, 7, 10])
            options = skills.candidates(state(reg), world)
            self.assertNotIn('craft_wooden_tools', options)
            options = skills.candidates(state(reg, inventory=[{'item': 'minecraft:oak_log', 'count': 12}]), world)
            self.assertIn('craft_wooden_tools', options)
            self.assertTrue(set(options).isdisjoint(GAPS))
            self.assertIn('wait', options)

    def test_scan_is_small_local_volume_instead_of_all_vertical_levels(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            class Bridge:
                world = reg['world_name']
                state = {**globals()['state'](reg), 'pos': [.5, 70, .5]}
                def read(self): return self.state
                def request(self, op, **args):
                    self.args = args
                    return {'blocks': terrain()}
            bridge = Bridge()
            skills = TrialSkills(bridge, game)
            skills.scan()
            self.assertEqual(13, bridge.args['max'][1] - bridge.args['min'][1] + 1)
            self.assertEqual(21, bridge.args['max'][0] - bridge.args['min'][0] + 1)

    def test_station_anchor_allows_bootstrap_without_claiming_full_shelter(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            current = state(reg, inventory=[{'item': 'minecraft:oak_log', 'count': 12}])
            bridge = TrialBridge(game, reg, 'run-a', reader=lambda _: current)
            skills = TrialSkills(bridge, Path(game) / 'out')
            # Every 5x5 camp is obstructed at roof height, while ordinary
            # two-block player/head clearance and normal stations still fit.
            rows = terrain() + [row((x, 3, z), 'oak_leaves') for x in range(-10, 11) for z in range(-10, 11)]
            world = TrialWorld(rows, [-10, -5, -10], [10, 7, 10])
            skills.scan = lambda: world
            skills.observe()
            self.assertIsNone(skills.camp)
            self.assertIsNotNone(skills.station_anchor)
            self.assertIn('craft_wooden_tools', skills.candidates(current, world))
            self.assertFalse(skills.camp_completed)
            self.assertNotIn('build_shelter', skills.candidates(current, world))

    def test_station_temporarily_uses_work_anchor_and_restores_camp_identity(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            bridge = TrialBridge(game, reg, 'run-a', reader=lambda _: state(reg))
            skills = TrialSkills(bridge, game)
            skills.station_anchor = [1, 1, 1]
            observed = []
            def station(self, name):
                observed.append((name, self.camp))
                self.stations[name] = [4, 1, 1]
            with patch('survival.Runner.station', station):
                skills.station('crafting_table')
            self.assertEqual([('crafting_table', [1, 1, 1])], observed)
            self.assertIsNone(skills.camp)
            self.assertFalse(skills.camp_completed)
            self.assertEqual([4, 1, 1], skills.stations['crafting_table'])

    def test_rejected_exploration_is_not_visited_and_chooses_a_different_grid(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            bridge = TrialBridge(game, reg, 'run-a', reader=lambda _: state(reg))
            skills = TrialSkills(bridge, game)
            world = TrialWorld(terrain(), [-10, -5, -10], [10, 7, 10])
            point, route = skills.exploration(world)
            skills.explore_target = point, route
            old_grid = math.floor(point[0] / 8), math.floor(point[2] / 8)
            error = TrialMovementBlocked('walk_path', {'path': [center(p) for p in route]},
                                         state(reg, native=True, phase='waiting'))
            with patch.object(skills, 'walk', side_effect=error):
                with self.assertRaises(TrialMovementBlocked): skills.execute('explore_nearby')
            self.assertFalse(skills.explored)
            self.assertIn(old_grid, skills.tried_grids)
            point2, route2 = skills.exploration(world)
            self.assertNotEqual(old_grid, (math.floor(point2[0] / 8), math.floor(point2[2] / 8)))
            self.assertNotEqual(route, route2)


class GoalTests(unittest.TestCase):
    def test_drop_recovery_goal_precedes_new_tree_or_generic_exploration(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            goal = short_term_goal(state(reg), {'collect_log_drops': 'Pickup', 'gather_starting_wood': 'Wood', 'wait': 'Wait'}, 9)
            self.assertIn('Pick up the already observed', goal)
            goal = short_term_goal(state(reg), {'explore_nearby': 'Approach items', 'wait': 'Wait'}, 9)
            self.assertIn('toward the already observed dropped logs', goal)
            self.assertIn('Do not cut another tree', goal)
    def test_reachable_starting_tree_makes_the_current_goal_wood_not_dragon_or_exploration(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            goal = short_term_goal(state(reg), {'gather_starting_wood': 'Gather', 'explore_nearby': 'Explore', 'wait': 'Wait'})
            self.assertIn('starting logs', goal)
            self.assertIn('already observed reachable', goal)
            self.assertIn('Prioritize gathering this wood', goal)
            self.assertNotIn('Dragon', goal)
            self.assertNotIn('nether', goal)

    def test_carried_wood_prioritizes_crafting_before_gathering_or_exploration(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            carried = state(reg, inventory=[{'item': 'minecraft:oak_log', 'count': 6}])
            goal = short_term_goal(carried, {'craft_wooden_tools': 'Craft', 'gather_starting_wood': 'Gather', 'explore_nearby': 'Explore', 'wait': 'Wait'})
            self.assertIn('Craft a crafting table and wooden pickaxe now', goal)
            self.assertIn('already carried wood', goal)

    def test_wood_stone_food_and_iron_goals_follow_real_prechecked_prerequisites(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            wood_tool = state(reg, inventory=[{'item': 'minecraft:wooden_pickaxe', 'count': 1}])
            stone_tools = state(reg, inventory=[{'item': 'minecraft:stone_pickaxe', 'count': 1}, {'item': 'minecraft:stone_axe', 'count': 1}])
            for current, action, expected in (
                (wood_tool, 'gather_stone', 'Collect the needed cobblestone'),
                (wood_tool, 'craft_stone_tools', 'Craft the missing stone pickaxe'),
                (stone_tools, 'gather_food', 'Obtain and cook a reserve of food'),
                (stone_tools, 'prepare_iron_equipment', 'missing iron equipment')):
                with self.subTest(action=action):
                    goal = short_term_goal(current, {action: 'Available', 'explore_nearby': 'Explore', 'wait': 'Wait'})
                    self.assertIn(expected, goal)

    def test_explore_only_when_no_current_resource_macro_can_meet_the_next_goal(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            options = {'explore_nearby': 'Explore', 'wait': 'Wait'}
            self.assertIn('Find reachable starting wood', short_term_goal(state(reg), options))
            with_pick = state(reg, inventory=[{'item': 'minecraft:wooden_pickaxe', 'count': 1}])
            self.assertIn('Find reachable stone', short_term_goal(with_pick, options))
            with_stone = state(reg, inventory=[{'item': 'minecraft:stone_pickaxe', 'count': 1}])
            self.assertIn('Find an accessible food source', short_term_goal(with_stone, options))

    def test_eating_carried_food_precedes_construction_when_hunger_is_low(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            hungry = state(reg, food=8, inventory=[{'item': 'minecraft:cooked_beef', 'count': 4}])
            goal = short_term_goal(hungry, {'eat_carried_food': 'Eat', 'craft_wooden_tools': 'Craft', 'wait': 'Wait'})
            self.assertIn('Eat carried food now', goal)


class WorkerTests(unittest.TestCase):
    def worker(self, game):
        reg = registry(game)
        root = Path(game) / 'config/twob2tkit/singleplayer-trial'
        root.mkdir(parents=True)
        (root / 'registry.json').write_text(json.dumps(reg))
        worker = TrialWorker(game, os.getpid(), reader=lambda _: state(reg))
        return worker, reg, root

    def test_native_start_run_and_control_not_foreign_command(self):
        with tempfile.TemporaryDirectory() as game:
            worker, reg, root = self.worker(game)
            try:
                (root / 'control.json').write_text(json.dumps({'id': 'foreign', 'trial_id': 'other', 'run_id': 'run-a', 'command': 'start'}))
                with self.assertRaises(Paused): worker.control()
                self.assertIsNone(worker.run_id)
                (root / 'control.json').write_text(json.dumps({'id': 'start-1', 'trial_id': reg['trial_id'], 'run_id': 'run-a', 'command': 'start'}))
                worker.control()
                self.assertEqual('run-a', worker.run_id)
                (root / 'control.json').write_text(json.dumps({'id': 'pause-1', 'trial_id': reg['trial_id'], 'run_id': 'run-a', 'command': 'pause'}))
                with self.assertRaises(Paused): worker.control()
                self.assertEqual('pause', worker.command)
            finally:
                worker.pool.shutdown(wait=False)
                if worker.experience: worker.experience.close()

    def test_resume_discards_old_envelope_binding_but_keeps_observed_camp(self):
        with tempfile.TemporaryDirectory() as game:
            worker, reg, root = self.worker(game)
            try:
                worker.registry = reg
                worker.run_id = reg['run_id']
                worker.bridge = object()
                worker.skills = object()
                old = worker.skills
                (root / 'control.json').write_text(json.dumps({'id': 'resume-1', 'trial_id': reg['trial_id'], 'run_id': reg['run_id'], 'command': 'resume'}))
                worker.control()
                self.assertIsNone(worker.bridge)
                self.assertIs(old, worker.skills)
            finally:
                worker.pool.shutdown(wait=False)
                if worker.experience: worker.experience.close()

    def test_death_respawn_is_rate_limited_and_no_dead_model_action_executes(self):
        with tempfile.TemporaryDirectory() as game:
            worker, reg, root = self.worker(game)
            try:
                worker.registry = reg
                worker.run_id = reg['run_id']
                worker.last_respawn = time.monotonic()
                worker.death_recovery(state(reg, health=0, player_dead=True, trial_deaths=1))
                self.assertEqual('death_cooldown', worker.phase)
                self.assertFalse((Path(game) / 'request.json').exists())
                worker.last_respawn = 0
                worker.last_death_epoch = 1
                worker.death_recovery(state(reg, health=0, player_dead=True, trial_deaths=1))
                self.assertEqual('death_wait', worker.phase)
            finally:
                worker.pool.shutdown(wait=False)
                if worker.experience: worker.experience.close()

    def test_completion_is_only_native_dragon_fact_and_gaps_are_visible(self):
        with tempfile.TemporaryDirectory() as game:
            worker, reg, root = self.worker(game)
            try:
                worker.registry = reg
                worker.publish('waiting_capability', 'missing', state(reg))
                current = json.loads((root / 'worker/status.json').read_text())
                self.assertFalse(current['dragon_defeated'])
                self.assertEqual(GAPS, current['missing_capabilities'])
                worker.publish('complete', 'native', state(reg, dragon_defeated=True))
                self.assertTrue(json.loads((root / 'worker/status.json').read_text())['dragon_defeated'])
            finally:
                worker.pool.shutdown(wait=False)
                if worker.experience: worker.experience.close()

    def test_typed_model_choice_and_fixed_lesson_never_dispatch_a_command(self):
        with tempfile.TemporaryDirectory() as game:
            worker, reg, root = self.worker(game)
            calls = []
            class Model:
                def __init__(self, settings, config, image=None):
                    self.image = image
                def predict(self, scene, questions):
                    calls.append((scene, questions))
                    key = next(iter(questions))
                    candidates = questions[key]['criteria']
                    choice = 'gather_starting_wood' if key == 'action' else 'verify_inventory_after_gathering'
                    return {'model': 'kit-clef-flash', 'answers': {key: {
                        'type': 'choice', 'choice': choice, 'confidence': .9,
                        'probabilities': {name: 1.0 if name == choice else 0.0 for name in candidates}}}}
                def close(self): pass
            try:
                settings = Path(game) / 'config/twob2tkit/decision-advisor'
                settings.mkdir(parents=True)
                (settings / 'settings.json').write_text(json.dumps({
                    'provider': 'ollama', 'enabled': True, 'local_model': 'clef-flash',
                    'keep_loaded': True, 'vision_mode': 'off', 'context_length': 4096, 'timeout_seconds': 2}))
                worker.registry = reg
                worker.run_id = reg['run_id']
                worker.command = 'start'
                worker.control = lambda: None
                worker.model_factory = Model
                worker.bind()
                before = state(reg)
                answer = worker.decide({'gather_starting_wood': 'Gather verified logs', 'wait': 'Wait'}, before)
                self.assertEqual('gather_starting_wood', answer['choice'])
                self.assertFalse((worker.automation / 'request.json').exists())
                after = state(reg, time=before['time'] + 10,
                              inventory=[{'item': 'minecraft:oak_log', 'count': 1}])
                proposal = worker.reflect('gather_starting_wood', before, after)
                self.assertEqual({'lesson': 'verify_inventory_after_gathering',
                                  'category': 'gathering', 'confidence': 'high'}, proposal)
                self.assertEqual({'action'}, set(calls[0][1]))
                self.assertEqual({'lesson'}, set(calls[1][1]))
                self.assertFalse((worker.automation / 'request.json').exists())
            finally:
                worker.pool.shutdown(wait=True)
                if worker.experience: worker.experience.close()

    def test_wrong_model_or_unloading_mode_cannot_run_the_trial(self):
        with tempfile.TemporaryDirectory() as game:
            worker, reg, root = self.worker(game)
            try:
                settings = Path(game) / 'config/twob2tkit/decision-advisor'
                settings.mkdir(parents=True)
                for change in ({'local_model': 'nimble'}, {'provider': 'jev'}, {'keep_loaded': False}):
                    value = {'provider': 'ollama', 'enabled': True, 'local_model': 'clef-flash', 'keep_loaded': True, **change}
                    (settings / 'settings.json').write_text(json.dumps(value))
                    with self.subTest(change=change), self.assertRaises(Paused):
                        worker.model_config()
            finally:
                worker.pool.shutdown(wait=False)
                if worker.experience: worker.experience.close()

    def test_native_dragon_completion_ends_service_without_overwriting_evidence(self):
        with tempfile.TemporaryDirectory() as game:
            worker, reg, root = self.worker(game)
            (root / 'control.json').write_text(json.dumps({'id': 'start-1', 'trial_id': reg['trial_id'],
                                                          'run_id': reg['run_id'], 'command': 'start'}))
            worker.reader = lambda _: state(reg, dragon_defeated=True)
            worker.bridge_factory = lambda *a, **k: TrialBridge(*a, **k)
            worker.run(.1)
            final = json.loads((root / 'worker/status.json').read_text())
            self.assertEqual('complete', final['phase'])
            self.assertTrue(final['dragon_defeated'])
            self.assertFalse((worker.automation / 'request.json').exists())

    def test_reflection_contains_coarse_movement_and_native_refusal_without_coordinates(self):
        with tempfile.TemporaryDirectory() as game:
            worker, reg, root = self.worker(game)
            scenes = []
            class Model:
                def __init__(self, *args, **kwargs): pass
                def close(self): pass
                def predict(self, scene, questions):
                    scenes.append(scene)
                    choices = questions['lesson']['criteria']
                    return {'answers': {'lesson': {'type': 'choice', 'choice': 'rescan_after_stall',
                        'confidence': .9, 'probabilities': {key: float(key == 'rescan_after_stall') for key in choices}}}}
            try:
                settings = Path(game) / 'config/twob2tkit/decision-advisor'
                settings.mkdir(parents=True)
                (settings / 'settings.json').write_text(json.dumps({'provider': 'ollama', 'enabled': True,
                    'local_model': 'clef-flash', 'keep_loaded': True, 'context_length': 4096, 'timeout_seconds': 2}))
                worker.registry = reg
                worker.run_id = reg['run_id']
                worker.command = 'start'
                worker.control = lambda: None
                worker.model_factory = Model
                worker.bind()
                before = state(reg)
                after = state(reg, time=before['time'] + 1000, pos=[3.5, 1, .5])
                receipt = state(reg, id='walk-a', request_id='walk-a', native=True, phase='waiting',
                                code='path_blocked', receipt_class='terrain_movement_refusal')
                proposal = worker.reflect('explore_nearby', before, after, receipt)
                observed = scenes[0]['scene']['observed_effect']
                self.assertTrue(observed['position_changed'])
                self.assertEqual(3.0, observed['observed_displacement_blocks'])
                self.assertEqual('waiting', observed['native_receipt_phase'])
                self.assertEqual('terrain_movement_refusal', observed['native_receipt_class'])
                self.assertNotIn('pos', scenes[0]['scene']['before'])
                self.assertNotIn('world_id', json.dumps(scenes[0]))
                self.assertEqual('rescan_after_stall', proposal['lesson'])
            finally:
                worker.pool.shutdown(wait=True)
                if worker.experience: worker.experience.close()

    def test_experience_database_failure_does_not_turn_native_success_into_failure(self):
        with tempfile.TemporaryDirectory() as game:
            worker, reg, root = self.worker(game)
            real_store = worker.experience
            try:
                worker.registry = reg
                worker.experience = Mock()
                worker.experience.record_attempt.side_effect = OSError('locked experience database')
                worker.reflect = Mock(return_value={'lesson': 'no_lesson'})
                before = state(reg)
                after = state(reg, time=before['time'] + 50, pos=[3.5, 1, .5])
                worker.attempt_record('explore_nearby', before, after,
                    state(reg, id='move-a', request_id='move-a', native=True))
                records = [json.loads(line) for line in (root / 'worker/journal.jsonl').read_text().splitlines()]
                self.assertEqual(['attempt', 'experience_store_error'], [row['event'] for row in records])
                self.assertFalse((worker.automation / 'request.json').exists())
            finally:
                worker.pool.shutdown(wait=True)
                if real_store: real_store.close()

    def test_worker_replans_confirmed_movement_refusal_without_incrementing_success(self):
        with tempfile.TemporaryDirectory() as game:
            worker, reg, root = self.worker(game)
            try:
                worker.registry = reg
                worker.run_id = reg['run_id']
                worker.command = 'start'
                worker.control = lambda: None
                worker.bind()
                receipt = state(reg, id='walk-a', request_id='walk-a', native=True, phase='waiting',
                                code='path_blocked', receipt_class='terrain_movement_refusal')
                worker.skills.observe = Mock(return_value=None)
                worker.skills.candidates = Mock(return_value={'explore_nearby': 'Explore', 'wait': 'Wait'})
                worker.skills.execute = Mock(side_effect=TrialMovementBlocked('walk_path', {}, receipt))
                worker.decide = Mock(return_value={'choice': 'explore_nearby', 'confidence': .9})
                worker.attempt_record = Mock()
                worker.cycle()
                self.assertEqual('replanning', worker.phase)
                self.assertEqual('start', worker.command)
                self.assertEqual(0, worker.steps)
                self.assertFalse(worker.bridge.halted)
                self.assertEqual(receipt, worker.attempt_record.call_args.args[-1])
            finally:
                worker.pool.shutdown(wait=True)
                if worker.experience: worker.experience.close()

    def test_live_low_confidence_distributions_execute_typed_macro_without_entropy_gate(self):
        with tempfile.TemporaryDirectory() as game:
            worker, reg, root = self.worker(game)
            scenes = []
            distributions = [(.29, .55, .43), (.31, .59, .39), (.32, .61, .37)]
            class Model:
                def __init__(self, *args, **kwargs): pass
                def close(self): pass
                def predict(self, scene, questions):
                    scenes.append((scene, questions))
                    confidence, explore, wood = distributions.pop(0)
                    return {'model': 'kit-clef-flash', 'answers': {'action': {
                        'type': 'choice', 'choice': 'explore_nearby', 'confidence': confidence,
                        'probabilities': {'explore_nearby': explore, 'gather_starting_wood': wood, 'wait': .02}}}}
            try:
                settings = Path(game) / 'config/twob2tkit/decision-advisor'
                settings.mkdir(parents=True)
                (settings / 'settings.json').write_text(json.dumps({'provider': 'ollama', 'enabled': True,
                    'local_model': 'clef-flash', 'keep_loaded': True, 'vision_mode': 'off',
                    'context_length': 4096, 'timeout_seconds': 2}))
                worker.registry = reg
                worker.run_id = reg['run_id']
                worker.command = 'start'
                worker.control = lambda: None
                worker.model_factory = Model
                worker.bind()
                worker.skills.observe = Mock(return_value=None)
                worker.skills.candidates = Mock(return_value={'gather_starting_wood': 'Gather', 'explore_nearby': 'Explore', 'wait': 'Wait'})
                worker.skills.execute = Mock(return_value=state(reg))
                worker.attempt_record = Mock()
                for unused in range(3):
                    worker.cycle()
                self.assertEqual(3, worker.skills.execute.call_count)
                self.assertEqual([('explore_nearby',)] * 3, [call.args for call in worker.skills.execute.call_args_list])
                self.assertEqual(3, worker.steps)
                self.assertEqual('running', worker.phase)
                for scene, questions in scenes:
                    self.assertIn('Collect starting logs', scene['goal'])
                    self.assertEqual('defeat_ender_dragon', scene['scene']['long_term_goal'])
                    self.assertEqual(set(GAPS), set(scene['scene']['capabilities']['blocked']))
                    self.assertNotIn('missing_capabilities', scene['scene'])
                    self.assertIn('trees already observed as reachable nearby', questions['action']['criteria']['gather_starting_wood'])
                    self.assertIn('when no carried-material or reachable-resource macro', questions['action']['criteria']['explore_nearby'])
                journal = [json.loads(line) for line in (root / 'worker/journal.jsonl').read_text().splitlines()]
                decisions = [event for event in journal if event['event'] == 'decision']
                self.assertTrue(all(event['uncertainty']['low_confidence'] for event in decisions))
                self.assertTrue(all(event['uncertainty']['confidence_is_observation_only'] for event in decisions))
            finally:
                worker.pool.shutdown(wait=True)
                if worker.experience: worker.experience.close()

    def test_wait_remains_no_input_even_when_confidence_is_not_an_execution_gate(self):
        with tempfile.TemporaryDirectory() as game:
            worker, reg, root = self.worker(game)
            try:
                worker.registry = reg
                worker.run_id = reg['run_id']
                worker.command = 'start'
                worker.control = lambda: None
                worker.bind()
                worker.skills.observe = Mock(return_value=None)
                worker.skills.candidates = Mock(return_value={'gather_starting_wood': 'Gather', 'wait': 'Wait'})
                worker.skills.execute = Mock()
                worker.decide = Mock(return_value={'choice': 'wait', 'confidence': .29,
                                                  'probabilities': {'gather_starting_wood': .98, 'wait': .02}})
                worker.cycle()
                worker.skills.execute.assert_not_called()
                self.assertEqual(0, worker.steps)
                self.assertEqual('waiting_model', worker.phase)
            finally:
                worker.pool.shutdown(wait=True)
                if worker.experience: worker.experience.close()

    def test_auto_vision_budget_falls_back_to_complete_text_capabilities(self):
        with tempfile.TemporaryDirectory() as game:
            worker, reg, root = self.worker(game)
            scenes = []
            images = []
            class Model:
                def __init__(self, settings, config, image=None): images.append(image)
                def close(self): pass
                def predict(self, scene, questions):
                    scenes.append(scene)
                    choices = questions['action']['criteria']
                    return {'model': 'kit-clef-flash', 'answers': {'action': {'type': 'choice',
                        'choice': 'gather_starting_wood', 'confidence': .7,
                        'probabilities': {key: float(key == 'gather_starting_wood') for key in choices}}}}
            try:
                settings = Path(game) / 'config/twob2tkit/decision-advisor'
                settings.mkdir(parents=True)
                (settings / 'settings.json').write_text(json.dumps({'provider': 'ollama', 'enabled': True,
                    'local_model': 'clef-flash', 'keep_loaded': True, 'vision_mode': 'auto',
                    'context_length': 4096, 'timeout_seconds': 2}))
                worker.registry = reg
                worker.run_id = reg['run_id']
                worker.command = 'start'
                worker.control = lambda: None
                worker.model_factory = Model
                worker.bind()
                worker.bridge.request = Mock(side_effect=AssertionError('Budget fallback must not capture a frame'))
                result = worker.decide({'gather_starting_wood': 'Gather', 'explore_nearby': 'Explore', 'wait': 'Wait'}, state(reg))
                self.assertEqual('gather_starting_wood', result['choice'])
                self.assertEqual([None], images)
                caps = scenes[0]['scene']['capabilities']
                self.assertEqual({'gather_starting_wood', 'explore_nearby', 'wait'}, {row['id'] for row in caps['available']})
                wood = next(row for row in caps['available'] if row['id'] == 'gather_starting_wood')
                self.assertIn('mine_block', wood['via'])
                self.assertNotIn('navigate', wood['via'])
                self.assertIn('log inventory', wood['verify'])
                self.assertEqual(0, caps['omitted'])
                journal = [json.loads(line) for line in (root / 'worker/journal.jsonl').read_text().splitlines()]
                skipped = next(row for row in journal if row['event'] == 'vision_skipped_budget')
                self.assertGreater(skipped['text_bytes'], skipped['image_text_budget'])
                self.assertEqual('complete_structured_facts_and_capabilities', skipped['retained'])
                worker.bridge.request.assert_not_called()
            finally:
                worker.pool.shutdown(wait=True)
                if worker.experience: worker.experience.close()

    def test_always_vision_over_budget_waits_without_dropping_capabilities(self):
        with tempfile.TemporaryDirectory() as game:
            worker, reg, root = self.worker(game)
            try:
                settings = Path(game) / 'config/twob2tkit/decision-advisor'
                settings.mkdir(parents=True)
                (settings / 'settings.json').write_text(json.dumps({'provider': 'ollama', 'enabled': True,
                    'local_model': 'clef-flash', 'keep_loaded': True, 'vision_mode': 'always',
                    'context_length': 4096, 'timeout_seconds': 2}))
                worker.registry = reg
                worker.run_id = reg['run_id']
                worker.command = 'start'
                worker.control = lambda: None
                worker.model_factory = Mock()
                worker.bind()
                worker.bridge.request = Mock()
                with self.assertRaisesRegex(Paused, '未裁剪事实'):
                    worker.decide({'gather_starting_wood': 'Gather', 'explore_nearby': 'Explore', 'wait': 'Wait'}, state(reg))
                worker.model_factory.assert_not_called()
                worker.bridge.request.assert_not_called()
            finally:
                worker.pool.shutdown(wait=True)
                if worker.experience: worker.experience.close()


if __name__ == '__main__':
    unittest.main()
