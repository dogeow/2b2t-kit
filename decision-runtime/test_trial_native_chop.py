import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import os

from singleplayer_trial import TrialSkills, TrialWorker, TrialWorld, local_failure_context, local_wait_reason
from singleplayer_trial_bridge import TrialBridge, Paused, TrialGuardBusy, TrialMovementBlocked
from singleplayer_trial_capabilities import eligible_candidates
from survival_world import World
from trial_native_chop import (complete_tree_survey, gather_native_wood,
                               known_chop_receipt, observed_chop_plan,
                               record_chop_receipt, validate_chop_arguments,
                               native_chop_protection_clear)


def context(game):
    save = Path(game) / 'saves/trial'
    save.mkdir(parents=True)
    registry = {'protocol': 1, 'enabled': True, 'trial_id': 'trial-a', 'run_id': 'run-a',
                'world_id': str(save.resolve()), 'world_name': 'Trial',
                'goal': 'defeat_ender_dragon', 'allow_death_respawn': True}
    root = Path(game) / 'config/twob2tkit/automation'
    root.mkdir(parents=True)
    stock = [{'slot': slot, 'item': 'minecraft:air', 'count': 0} for slot in range(36)]
    stock[0] = {'slot': 0, 'item': 'minecraft:oak_log', 'count': 1}
    stock[1] = {'slot': 1, 'item': 'minecraft:dirt', 'count': 2}
    state = {'time': 100, 'connected': True, 'server': 'singleplayer', 'game_mode': 'survival',
             'singleplayer_trial_protocol': 1, 'tree_survey_protocol': 1, 'kit_version': '2026.10.7.6',
             'dimension': 'minecraft:overworld', 'world_id': registry['world_id'], 'world_name': 'Trial',
             'world_session': 'session-a', 'control_revision': 4, 'last_request': 'old',
             'trial_identity': {'registered': True, 'trial_id': 'trial-a', 'run_id': 'run-a',
                                'world_id': registry['world_id']},
             'phase': 'done', 'op': 'walk', 'pos': [.5, 1, .5], 'health': 20, 'food': 20,
             'on_ground': True, 'manual_movement': False, 'screen': '', 'guard_armed': True,
             'guard_busy': False, 'inventory': stock, 'chopping': False,
             'chopper_remaining': 0, 'chopper_platforms': 0, 'chopper_verified_trees': 1,
             'movement_keys': {'forward': False, 'back': False, 'jump': False, 'sneak': False}}
    return root, registry, state


def survey(state, **updates):
    return {**state, 'tree_survey': {'loaded_columns': 289, 'unloaded_columns': 0,
            'highest_surface': 8, 'biomes': {},
            'trees': [{'pos': [3, 1, 0], 'top': 8, 'natural_leaves': 4}]}, **updates}


def request(state, **updates):
    return {'id': 'trial-test', 'op': 'chop', 'local_trial': True, 'local_survival': True,
            'world_id': state['world_id'], 'world_session': state['world_session'],
            'dimension': state['dimension'], 'trial_id': 'trial-a', 'run_id': 'run-a',
            'expected_revision': 4, 'item': 'minecraft:oak_log', 'target_count': 4,
            'tree_limit': 1, 'seconds': 240, **updates}


def terminal(state, rid='trial-test', count=7, **updates):
    stock = copy.deepcopy(state['inventory'])
    stock[0]['count'] = count
    return {**state, 'id': rid, 'last_request': rid, 'op': 'chop', 'phase': 'done',
            'control_revision': 5, 'time': 101, 'inventory': stock, **updates}


class NativeChopBridgeTest(unittest.TestCase):
    def test_tree_survey_uses_matched_payload_and_keeps_inherited_phase_truthful(self):
        with tempfile.TemporaryDirectory() as game:
            root, reg, first = context(game)
            reads = [0]
            def reader(unused):
                reads[0] += 1
                mailbox = root / 'request.json'
                if not mailbox.exists(): return copy.deepcopy(first)
                sent = json.loads(mailbox.read_text())
                value = survey(first, id=sent['id'], phase='running', op='walk')
                (root / ('reply-' + sent['id'] + '.json')).write_text(json.dumps(value))
                return {**first, 'last_request': sent['id']}
            bridge = TrialBridge(root, reg, 'run-a', reader=reader)
            result = bridge.request('scan_trees', item='minecraft:oak_log', radius=8)
            self.assertEqual(result['phase'], 'running')
            self.assertEqual(result['op'], 'walk')
            self.assertEqual(bridge.last_receipt['receipt_class'], 'native_tree_survey')
            self.assertFalse(bridge.halted)
            self.assertEqual(reads[0], 3)

    def test_tree_survey_rejects_malformed_partial_or_changed_revision(self):
        with tempfile.TemporaryDirectory() as game:
            root, reg, first = context(game)
            bad = survey(first)
            for field, value in [('loaded_columns', 288), ('unloaded_columns', -1),
                                 ('highest_surface', 999), ('trees', [{'pos': [50, 1, 0], 'top': 8, 'natural_leaves': 4}])]:
                changed = copy.deepcopy(bad)
                changed['tree_survey'][field] = value
                self.assertFalse(complete_tree_survey(changed, {'item': 'minecraft:oak_log', 'radius': 8}, 4, first['pos']))
            self.assertFalse(complete_tree_survey({**bad, 'control_revision': 5}, {'item': 'minecraft:oak_log', 'radius': 8}, 4, first['pos']))
            def reader(unused):
                if not (root / 'request.json').exists(): return copy.deepcopy(first)
                sent = json.loads((root / 'request.json').read_text())
                value = survey(first, id=sent['id'], control_revision=5)
                (root / ('reply-' + sent['id'] + '.json')).write_text(json.dumps(value))
                return {**first, 'last_request': sent['id'], 'control_revision': 5}
            bridge = TrialBridge(root, reg, 'run-a', reader=reader)
            with self.assertRaises(Paused): bridge.request('scan_trees', item='minecraft:oak_log', radius=8)
            self.assertTrue(bridge.halted)

    def test_one_native_chop_writes_only_worker_receipt_and_clears_exact_intent(self):
        with tempfile.TemporaryDirectory() as game:
            root, reg, first = context(game)
            events = []
            def reader(unused):
                if not (root / 'request.json').exists(): return copy.deepcopy(first)
                sent = json.loads((root / 'request.json').read_text())
                return terminal(first, rid=sent['id'])
            bridge = TrialBridge(root, reg, 'run-a', reader=reader,
                                 events=lambda name, **data: events.append((name, data)))
            result = bridge.request('chop', item='minecraft:oak_log', target_count=4, tree_limit=1, seconds=240)
            sent = json.loads((root / 'request.json').read_text())
            self.assertEqual(sum(name == 'native_request' for name, _ in events), 1)
            self.assertFalse((root / ('reply-' + sent['id'] + '.json')).exists())
            self.assertFalse(bridge.pending_mutations)
            self.assertFalse(bridge.halted)
            proof = known_chop_receipt(game, reg, {'id': sent['id'], 'op': 'chop', 'world_session': 'session-a'}, result)
            self.assertEqual(proof['gained'], 6)
            self.assertEqual(proof['source'], 'matched_native_status_snapshot')

    def test_pending_platform_or_extra_revision_preserves_intent_and_never_replays(self):
        for changed in ({'chopper_platforms': 1}, {'chopping': True}, {'on_ground': False},
                        {'control_revision': 6}, {'chopper_remaining': 1},
                        {'movement_keys': {'forward': True, 'back': False, 'jump': False, 'sneak': False}}):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as game:
                root, reg, first = context(game)
                events = []
                def reader(unused):
                    if not (root / 'request.json').exists(): return copy.deepcopy(first)
                    sent = json.loads((root / 'request.json').read_text())
                    return terminal(first, rid=sent['id'], **changed)
                bridge = TrialBridge(root, reg, 'run-a', reader=reader,
                                     events=lambda name, **data: events.append((name, data)))
                with self.assertRaises(Paused): bridge.request('chop', item='minecraft:oak_log', target_count=4, tree_limit=1, seconds=240)
                self.assertTrue(bridge.halted)
                self.assertEqual(len(bridge.pending_mutations), 1)
                with self.assertRaises(Paused): bridge.request('chop', item='minecraft:oak_log', target_count=4, tree_limit=1, seconds=240)
                self.assertEqual(sum(name == 'native_request' for name, _ in events), 1)

    def test_guard_busy_waits_without_dispatching_and_is_not_unknown(self):
        with tempfile.TemporaryDirectory() as game:
            root, reg, first = context(game)
            first['guard_busy'] = True
            clock = [0.]
            with patch('singleplayer_trial_bridge.time.monotonic', side_effect=lambda: clock[0]):
                bridge = TrialBridge(root, reg, 'run-a', reader=lambda _: copy.deepcopy(first),
                                     sleeper=lambda _: clock.__setitem__(0, clock[0] + 500))
                with self.assertRaises(TrialGuardBusy): bridge.request('chop', item='minecraft:oak_log', target_count=4, tree_limit=1, seconds=240)
            self.assertFalse((root / 'request.json').exists())
            self.assertFalse(bridge.pending_mutations)
            self.assertFalse(bridge.halted)

    def test_guard_displacement_reobserves_before_any_native_mailbox(self):
        with tempfile.TemporaryDirectory() as game:
            root, reg, first = context(game)
            first['guard_busy'] = True
            def sleeper(unused):
                first['pos'][0] = 1.5
                first['guard_busy'] = False
            bridge = TrialBridge(root, reg, 'run-a', reader=lambda _: copy.deepcopy(first), sleeper=sleeper)
            with self.assertRaisesRegex(Paused, 'origin changed before dispatch'):
                bridge.request('chop', item='minecraft:oak_log', target_count=4, tree_limit=1,
                               seconds=240, _chop_origin=(0,1,0))
            self.assertFalse((root / 'request.json').exists())
            self.assertFalse(bridge.pending_mutations)
            self.assertFalse(bridge.halted)

    def test_old_host_fixed_tree_and_invalid_batch_are_rejected_before_mailbox(self):
        with tempfile.TemporaryDirectory() as game:
            root, reg, first = context(game)
            valid = {'item': 'minecraft:oak_log', 'target_count': 4, 'tree_limit': 1, 'seconds': 240}
            for changes in ({'tree_limit': 2}, {'seconds': 601}, {'target_count': 1}, {'item': 'minecraft:stone'}, {'tree_root': [3, 1, 0]}):
                with self.assertRaises(Paused): validate_chop_arguments(first, {**valid, **changes})
            bridge = TrialBridge(root, reg, 'run-a', reader=lambda _: {**first, 'kit_version': '2026.10.7.5'})
            with self.assertRaises(Paused): bridge.request('chop', **valid)
            self.assertFalse((root / 'request.json').exists())

    def test_hot_update_helper_rejects_cross_run_session_and_altered_native_result(self):
        with tempfile.TemporaryDirectory() as game:
            root, reg, first = context(game)
            sent, result = request(first), terminal(first)
            record_chop_receipt(root, sent, first, result)
            pending = {'id': sent['id'], 'op': 'chop', 'world_session': 'session-a'}
            self.assertIsNotNone(known_chop_receipt(game, reg, pending))
            self.assertIsNone(known_chop_receipt(game, {**reg, 'run_id': 'other'}, pending))
            self.assertIsNone(known_chop_receipt(game, reg, {**pending, 'world_session': 'other'}))
            self.assertIsNone(known_chop_receipt(game, reg, pending, {**result, 'manual_movement': True}))
            old_scope = {**pending, **{key: sent[key] for key in ('world_id', 'trial_id', 'run_id', 'dimension')}}
            resumed_reg = {**reg, 'run_id': 'run-b'}
            resumed_state = {**result, 'trial_identity': {**result['trial_identity'], 'run_id': 'run-b'},
                             'time': 102, 'control_revision': 6}
            self.assertIsNotNone(known_chop_receipt(game, resumed_reg, old_scope, resumed_state))
            self.assertIsNone(known_chop_receipt(game, resumed_reg, pending, resumed_state))
            self.assertIsNone(known_chop_receipt(game, resumed_reg, {**old_scope, 'run_id': 'different-old'}, resumed_state))
            path = root.parent / 'singleplayer-trial/worker/native-chop-receipts/trial-test.json'
            proof = json.loads(path.read_text())
            proof['native_result']['control_revision'] = 88
            path.write_text(json.dumps(proof))
            self.assertIsNone(known_chop_receipt(game, reg, pending))

    def test_pause_during_running_chop_keeps_intent_for_exact_native_cleanup(self):
        with tempfile.TemporaryDirectory() as game:
            root, reg, first = context(game)
            running = [False]
            def reader(unused):
                if not (root / 'request.json').exists(): return copy.deepcopy(first)
                sent = json.loads((root / 'request.json').read_text())
                running[0] = True
                return {**first, 'id': sent['id'], 'last_request': sent['id'], 'op': 'chop',
                        'phase': 'running', 'chopping': True, 'control_revision': 5}
            def control():
                if running[0]: raise Paused('native pause')
            bridge = TrialBridge(root, reg, 'run-a', reader=reader, check_control=control, sleeper=lambda _: None)
            with self.assertRaises(Paused): bridge.request('chop', item='minecraft:oak_log', target_count=4, tree_limit=1, seconds=240)
            self.assertEqual(len(bridge.pending_mutations), 1)
            bridge.stop_owned()
            cleanup = json.loads((root / 'request.json').read_text())
            self.assertEqual(cleanup['op'], 'trial_stop')
            self.assertEqual(cleanup['run_id'], 'run-a')
            self.assertNotEqual(cleanup['op'], 'stop')


class NativeChopSkillTest(unittest.TestCase):
    def test_old_host_stays_blocked_new_host_can_offer_only_supplied_candidate(self):
        with tempfile.TemporaryDirectory() as game:
            _, _, first = context(game)
            self.assertIn('gather_starting_wood', eligible_candidates(['gather_starting_wood'], first))
            self.assertEqual(eligible_candidates(['gather_starting_wood'], {**first, 'kit_version': '2026.10.7.5'}), {})

    def test_candidate_excludes_player_camp_and_unknown_support(self):
        with tempfile.TemporaryDirectory() as game:
            _, _, first = context(game)
            floor = {'pos': [3, 0, 0], 'state': 'Block{minecraft:dirt}', 'solid': True}
            log = {'pos': [3, 1, 0], 'state': 'Block{minecraft:oak_log}', 'solid': True}
            world = World([floor, log], [-10, -5, -10], [10, 7, 10])
            skills = type('Skills', (), {'excluded': set(), 'stations': {}, 'camp': None})()
            plan = observed_chop_plan(skills, first, world, 4)
            self.assertEqual(plan['target_count'], 4)
            self.assertEqual(plan['observed_root'], [3, 1, 0])
            skills.camp = [1, 1, 0]
            self.assertIsNone(observed_chop_plan(skills, first, world, 4))
            skills.camp = None
            self.assertIsNone(observed_chop_plan(skills, first, World([log], [-10, 1, -10], [10, 7, 10]), 4))

    def test_actual_native_nearest_rule_can_select_excluded_root_so_entire_species_is_refused(self):
        with tempfile.TemporaryDirectory() as game:
            _, _, first = context(game)
            rows = []
            for x in (1,3):
                rows += [{'pos': [x,0,0], 'state':'Block{minecraft:dirt}', 'solid':True},
                         {'pos':[x,1,0], 'state':'Block{minecraft:oak_log}', 'solid':True}]
            world = World(rows, [-10,-5,-10], [10,7,10])
            skills = type('Skills', (), {'excluded': {(1,1,0)}, 'stations': {}, 'owned': {}, 'camp': None})()
            # ChopperTrees uses player.position().distanceToSqr(atCenterOf(base)),
            # and its ordinary selector has no Python excluded argument.
            source = Path(__file__).parents[1] / 'src/client/java/dev/twob2tkit/chopper/ChopperTrees.java'
            self.assertIn('player.position().distanceToSqr(Vec3.atCenterOf(tree.base))', source.read_text())
            native_choice = min(((1,1,0),(3,1,0)), key=lambda p: sum((p[i]+.5-first['pos'][i])**2 for i in range(3)))
            self.assertEqual(native_choice, (1,1,0))
            self.assertNotIn((3,1,0), skills.excluded)  # A Python-only root filter would permit it.
            self.assertFalse(native_chop_protection_clear(skills, first, world))
            self.assertIsNone(observed_chop_plan(skills, first, world, 4))

    def test_connected_log_and_crown_extent_protects_owned_wood_beyond_search_radius(self):
        with tempfile.TemporaryDirectory() as game:
            _, _, first = context(game)
            skills = type('Skills', (), {'excluded': set(), 'stations': {}, 'owned': {}, 'camp': None})()
            world = World([], [-10,-5,-10], [10,7,10])
            for x in (32,33,119):
                skills.owned = {str(x)+',1,0': 'oak_log'}
                self.assertFalse(native_chop_protection_clear(skills, first, world))
            skills.owned = {'120,1,0': 'oak_log'}
            self.assertTrue(native_chop_protection_clear(skills, first, world))
            skills.owned = {'1,1,0': 'crafting_table', '1,0,0': 'dirt'}
            skills.excluded = {(1,0,0)}
            self.assertTrue(native_chop_protection_clear(skills, first, world))
            skills.camp = [122,1,0]
            self.assertFalse(native_chop_protection_clear(skills, first, world))
            skills.camp = [123,1,0]
            self.assertTrue(native_chop_protection_clear(skills, first, world))

    def test_one_tree_short_of_total_is_progress_from_actual_gain(self):
        with tempfile.TemporaryDirectory() as game:
            _, _, first = context(game)
            floor = {'pos': [3, 0, 0], 'state': 'Block{minecraft:dirt}', 'solid': True}
            log = {'pos': [3, 1, 0], 'state': 'Block{minecraft:oak_log}', 'solid': True}
            world = World([floor, log], [-10, -5, -10], [10, 7, 10])
            class Skills:
                excluded, stations, camp = set(), {}, None
                def __init__(self): self.b = self; self.state = first; self.requests = []; self.events = []
                def check(self): pass
                def read(self): return copy.deepcopy(self.state)
                def scan(self): return world
                def request(self, op, **args):
                    self.requests.append((op, args))
                    if op == 'scan_trees': return survey(self.state)
                    self.state = terminal(self.state, count=3)
                    return self.state
                def event(self, name, **data): self.events.append((name, data))
            skills = Skills()
            proof = gather_native_wood(skills, target_logs=8)
            self.assertEqual(proof['gained'], 2)
            self.assertFalse(proof['target_reached'])
            self.assertEqual(proof['phase'], 'progress')
            self.assertEqual([op for op, _ in skills.requests], ['scan_trees', 'chop'])
            self.assertEqual(skills.requests[-1][1]['target_count'], 8)
            self.assertEqual(skills.requests[-1][1]['tree_limit'], 1)


def floor_world(table=None):
    rows = [{'pos': [x, 0, z], 'state': 'Block{minecraft:stone}', 'solid': True,
             'fluid': False, 'block_entity': False}
            for x in range(-10, 11) for z in range(-10, 11)]
    rows = [row for row in rows if row['pos'] != [3, 0, 0]]
    rows += [{'pos': [3, 0, 0], 'state': 'Block{minecraft:dirt}', 'solid': True},
             {'pos': [3, 1, 0], 'state': 'Block{minecraft:oak_log}', 'solid': True}]
    if table:
        rows.append({'pos': list(table), 'state': 'Block{minecraft:crafting_table}', 'solid': True})
    return TrialWorld(rows, [-10, -5, -10], [10, 7, 10])


class NativeChopPlanningTest(unittest.TestCase):
    def skills(self, game, logs=2, dirt=23):
        root, reg, current = context(game)
        current['inventory'][0]['count'] = logs
        current['inventory'][1]['count'] = dirt
        current['inventory'][2] = {'slot': 2, 'item': 'minecraft:stone_pickaxe', 'count': 1}
        current['inventory'][3] = {'slot': 3, 'item': 'minecraft:wooden_sword', 'count': 1}
        bridge = TrialBridge(root, reg, 'run-a', reader=lambda _: copy.deepcopy(current))
        skills = TrialSkills(bridge, Path(game) / 'skills')
        return skills, current, reg

    def test_known_reachable_or_carried_worktable_needs_six_door_boards_not_ten(self):
        for carried in (False, True):
            with self.subTest(carried=carried), tempfile.TemporaryDirectory() as game:
                skills, current, reg = self.skills(game)
                skills.stations['crafting_table'] = [6, 1, 0]
                if carried:
                    current['inventory'][4] = {'slot': 4, 'item': 'minecraft:crafting_table', 'count': 1}
                candidates = skills.candidates(current, floor_world(None if carried else [6, 1, 0]))
                self.assertIn('prepare_small_shelter', candidates)
                self.assertNotIn('gather_starting_wood', candidates)
                self.assertTrue(skills.safety_readiness['table_ready'])
                self.assertEqual(skills.safety_readiness['door_planks_required'], 6)

    def test_unknown_old_worktable_does_not_reduce_materials_and_missing_wood_uses_native_tree(self):
        with tempfile.TemporaryDirectory() as game:
            skills, current, reg = self.skills(game)
            skills.stations['crafting_table'] = [99, 1, 99]
            candidates = skills.candidates(current, floor_world())
            self.assertIn('gather_starting_wood', candidates)
            self.assertNotIn('prepare_small_shelter', candidates)
            self.assertNotIn('explore_nearby', candidates)
            self.assertEqual(skills.wood_target_logs, 3)
            self.assertFalse(skills.safety_readiness['table_ready'])
            self.assertEqual(skills.safety_readiness['wood_deficit'], 2)

    def test_house_macro_can_gather_reachable_dirt_without_twenty_three_in_advance(self):
        with tempfile.TemporaryDirectory() as game:
            skills, current, reg = self.skills(game, dirt=2)
            skills.stations['crafting_table'] = [6, 1, 0]
            world = floor_world([6, 1, 0])
            # Exposed supported earth bank, not the current player floor.
            world.blocks[(5, 1, 3)] = {'pos': [5, 1, 3], 'state': 'Block{minecraft:dirt}', 'solid': True}
            candidates = skills.candidates(current, world)
            self.assertIn('prepare_small_shelter', candidates)
            self.assertIn('prepare_small_shelter', eligible_candidates(candidates, current))
            self.assertEqual(skills.safety_readiness['dirt_deficit'], 21)

    def test_mixed_species_do_not_fake_a_six_plank_door(self):
        with tempfile.TemporaryDirectory() as game:
            skills, current, reg = self.skills(game, logs=1)
            current['inventory'][4] = {'slot': 4, 'item': 'minecraft:birch_log', 'count': 1}
            current['inventory'][5] = {'slot': 5, 'item': 'minecraft:crafting_table', 'count': 1}
            candidates = skills.candidates(current, floor_world())
            self.assertNotIn('prepare_small_shelter', candidates)
            self.assertIn('gather_starting_wood', candidates)
            self.assertEqual(skills.wood_target_logs, 3)

    def test_planks_select_sufficient_species_and_preserve_other_logs(self):
        with tempfile.TemporaryDirectory() as game:
            skills, current, reg = self.skills(game, logs=1)
            current['inventory'][4] = {'slot': 4, 'item': 'minecraft:birch_log', 'count': 2}
            calls = []
            def craft(output, cells, width, produces):
                calls.append((output, cells, width, produces))
                self.assertEqual(cells, {(0, 0): 'birch_log'})
                current['inventory'][4]['count'] -= 1
                row = current['inventory'][5]
                row['item'] = 'minecraft:birch_planks'
                row['count'] += 4
            skills.craft = craft
            self.assertEqual(skills.planks(6), 'birch_planks')
            self.assertEqual(len(calls), 2)
            self.assertEqual(current['inventory'][0]['count'], 1)
            self.assertEqual(current['inventory'][5]['count'], 8)

    def test_waiting_reason_describes_current_house_deficit_not_later_dragon_gap(self):
        with tempfile.TemporaryDirectory() as game:
            skills, current, reg = self.skills(game, dirt=2)
            skills.safety_readiness = {'sheltered': False, 'wood_deficit': 2, 'dirt_deficit': 21}
            reason = local_wait_reason(skills, current)
            self.assertIn('2', reason)
            self.assertIn('木板', reason)
            self.assertNotIn('下界', reason)
            self.assertNotIn('打龙', reason)


class TrialFailureScopeTest(unittest.TestCase):
    def worker(self, game):
        root, reg, first = context(game)
        worker = TrialWorker(game, os.getpid(), reader=lambda _: copy.deepcopy(first))
        worker.registry = reg
        worker.run_id = 'run-a'
        worker.bridge = TrialBridge(root, reg, 'run-a', reader=lambda _: copy.deepcopy(first))
        worker.skills = TrialSkills(worker.bridge, Path(game) / 'skills')
        self.addCleanup(worker.pool.shutdown, wait=True)
        if worker.experience: self.addCleanup(worker.experience.close)
        return worker, first

    def test_same_cell_stock_and_station_hold_three_failures_across_clock_revision_changes(self):
        with tempfile.TemporaryDirectory() as game:
            worker, first = self.worker(game)
            world = floor_world()
            worker.failures['craft_stone_tools'] = 3
            worker.failure_contexts['craft_stone_tools'] = local_failure_context(worker.skills, first, world)
            second = {**first, 'pos': [.7, 1, .6], 'day_time': 23000, 'control_revision': 100, 'time': 999}
            candidates = worker.actionable_candidates({'wait': 'Wait', 'craft_stone_tools': 'Craft'}, second, world)
            self.assertEqual(set(candidates), {'wait'})
            self.assertEqual(worker.failures['craft_stone_tools'], 3)

    def test_changed_position_stock_or_fresh_station_reopens_known_plan(self):
        for change in ('cell', 'stock', 'station'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as game:
                worker, first = self.worker(game)
                worker.skills.stations['crafting_table'] = [6, 1, 0]
                world = floor_world()
                worker.failures['craft_stone_tools'] = 3
                worker.failure_contexts['craft_stone_tools'] = local_failure_context(worker.skills, first, world)
                second = copy.deepcopy(first)
                if change == 'cell': second['pos'][0] = 1.5
                elif change == 'stock': second['inventory'][0]['count'] += 1
                else: world = floor_world([6, 1, 0])
                candidates = worker.actionable_candidates({'wait': 'Wait', 'craft_stone_tools': 'Craft'}, second, world)
                self.assertIn('craft_stone_tools', candidates)
                self.assertEqual(worker.failures['craft_stone_tools'], 0)

    def test_exhausted_priority_plan_gets_only_verified_normal_exploration_fallback(self):
        with tempfile.TemporaryDirectory() as game:
            worker, first = self.worker(game)
            world = floor_world()
            worker.failures['prepare_small_shelter'] = 3
            worker.failure_contexts['prepare_small_shelter'] = local_failure_context(worker.skills, first, world)
            result = worker.actionable_candidates({'wait': 'Wait', 'prepare_small_shelter': 'House'}, first, world)
            self.assertEqual(set(result), {'wait', 'explore_nearby'})
            self.assertIsNotNone(worker.skills.explore_target)
            self.assertLessEqual(len(worker.skills.explore_target[1]), 32)
            self.assertEqual(worker.failures['prepare_small_shelter'], 3)

    def test_unknown_mutation_or_halted_bridge_never_reopens_on_changed_context(self):
        for unresolved in (True, False):
            with self.subTest(unresolved=unresolved), tempfile.TemporaryDirectory() as game:
                worker, first = self.worker(game)
                world = floor_world()
                worker.failures['prepare_small_shelter'] = 3
                worker.failure_contexts['prepare_small_shelter'] = local_failure_context(worker.skills, first, world)
                if unresolved: worker.bridge.pending_mutations = {'unknown': {'op': 'chop'}}
                else: worker.bridge.halted = True
                second = {**first, 'pos': [1.5, 1, .5]}
                result = worker.actionable_candidates({'wait': 'Wait', 'prepare_small_shelter': 'House'}, second, world)
                self.assertEqual(set(result), {'wait'})
                self.assertEqual(worker.failures['prepare_small_shelter'], 3)
                self.assertIsNone(worker.skills.explore_target)

    def test_repeated_released_movement_refusals_eventually_leave_priority_plan_for_safe_exploration(self):
        with tempfile.TemporaryDirectory() as game:
            worker, first = self.worker(game)
            first['guard_pve_only'] = True
            worker.guard_origin = list(first['pos'])
            worker.command = 'start'
            worker.control = lambda: None
            world = floor_world()
            worker.skills.world = world
            worker.skills.observe = Mock(return_value=world)
            worker.skills.candidates = Mock(return_value={'wait':'Wait', 'prepare_small_shelter':'House'})
            receipt = {**first, 'op':'walk_path', 'phase':'waiting', 'outcome_pending':False}
            worker.skills.execute = Mock(side_effect=TrialMovementBlocked('walk_path', {}, receipt))
            worker.decide = Mock(return_value={'choice':'prepare_small_shelter'})
            worker.attempt_record = Mock()
            for unused in range(3): worker.cycle()
            self.assertEqual(worker.failures['prepare_small_shelter'], 3)
            worker.decide = Mock(return_value={'choice':'wait'})
            worker.cycle()
            offered = worker.decide.call_args.args[0]
            self.assertNotIn('prepare_small_shelter', offered)
            self.assertIn('explore_nearby', offered)
            self.assertFalse(worker.bridge.halted)
            self.assertFalse(worker.bridge.pending_mutations)


if __name__ == '__main__':
    unittest.main()
