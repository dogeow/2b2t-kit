import copy
import json
from pathlib import Path
import tempfile
import unittest

from singleplayer_trial import TrialWorld
from singleplayer_trial_bridge import (Paused, TrialBridge, TrialInteractionRejected,
                                      confirmed_interaction_not_sent)
from trial_station_access import visible_station_faces, station_access_plan
import test_singleplayer_trial as fixtures
from test_singleplayer_trial import registry, state, row, native_scan_fields


ARGS = {'pos': [21, 63, -64], 'face': 'up',
        'expected_state': 'Block{minecraft:crafting_table}', 'expected_hand': 'minecraft:wooden_sword'}


def rejected(reg, **changes):
    return state(reg, phase='error', detail='Target interaction face is occluded or out of reach',
                 kit_version='2026.10.7.7', hand={'item': ARGS['expected_hand']},
                 menu={'id': 0, 'type': 'InventoryMenu', 'cursor': {'count': 0}, 'slots': []}, **changes)


class InteractionContractTests(unittest.TestCase):
    def test_reviewed_host_refuses_visibility_before_rotation_and_normal_use(self):
        source = (Path(__file__).parent.parent / 'src/client/java/dev/twob2tkit/automation/AutomationBridge.java').read_text()
        branch = source.split('}else if(command.equals("interact")){', 1)[1].split('}else if(command.equals("mine_block")', 1)[0]
        message = 'Target interaction face is occluded or out of reach'
        self.assertEqual(1, branch.count(message))
        refusal = branch.index('if(visible==null)throw new IllegalStateException("' + message + '")')
        for action in ('active=r.deepCopy()', 'PlacementRotation.after(', 'c.gameMode.useItemOn('):
            self.assertLess(refusal, branch.index(action))
        self.assertNotIn('useItemOn', branch[:refusal])
        self.assertIn('error.addProperty("detail",e.getMessage())', source)

    def test_exact_refusal_only_without_possible_action_outcome(self):
        with tempfile.TemporaryDirectory() as game:
            reg = registry(game)
            receipt = rejected(reg)
            self.assertTrue(confirmed_interaction_not_sent('interact', receipt, ARGS, 4))
            mutations = [
                {'detail': 'Interaction became occluded while rotating'},
                {'detail': 'Target moved out of reach'}, {'detail': 'Placement context changed while rotating'},
                {'phase': 'waiting'}, {'op': 'rotation'}, {'op': 'settle'}, {'kit_version': '2026.10.7.9'},
                {'bridge_version': 3}, {'game_version': '1.21'}, {'control_revision': 5},
                {'native_sequence': 0}, {'server_ack_sequence': 0}, {'outcome_pending': True},
                {'server_confirmed': True}, {'server_update_seen': True}, {'confirmation_scope': 'ack'},
                {'requested_confirmation_scope': 'exact_terrain'}, {'server': 'remote'},
                {'manual_movement': True}, {'screen': 'CraftingScreen'}, {'game_paused': True},
                {'movement_keys': {'forward': True, 'back': False, 'jump': False, 'sneak': False}},
                {'menu': {'id': 1, 'type': 'CraftingMenu', 'cursor': {'count': 0}}},
                {'menu': {'id': 0, 'type': 'InventoryMenu', 'cursor': {'count': 1}}},
                {'hand': {'item': 'minecraft:stone_pickaxe'}},
                {'menu': None}, {'hand': None},
                {'menu': {'id': False, 'type': 'InventoryMenu', 'cursor': {'count': 0}}},
                {'menu': {'id': 0, 'type': 'InventoryMenu', 'cursor': {'count': False}}},
                {'menu': {'id': 0, 'type': 'InventoryMenu', 'cursor': {'count': 0}, 'slots': [None]}},
            ]
            for change in mutations:
                with self.subTest(change=change):
                    self.assertFalse(confirmed_interaction_not_sent('interact', {**receipt, **change}, ARGS, 4))
            for change in ({'dry_paving_guard': False}, {'terrain_replace': False}, {'face': 'any'},
                           {'face': []}, {'pos': [1., 2, 3]}):
                with self.subTest(arguments=change):
                    self.assertFalse(confirmed_interaction_not_sent('interact', receipt, {**ARGS, **change}, 4))

    def test_bridge_clears_only_exact_not_sent_and_permits_fresh_scan(self):
        for change, typed in (({}, True), ({'native_sequence': 12}, False),
                              ({'detail': 'Interaction became occluded while rotating'}, False)):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as game:
                reg = registry(game)
                root = Path(game) / 'automation'
                root.mkdir()
                def read(unused):
                    request = root / 'request.json'
                    if not request.exists(): return rejected(reg)
                    envelope = json.loads(request.read_text())
                    result = rejected(reg, id=envelope['id'], last_request=envelope['id'])
                    if envelope['op'] == 'scan':
                        result.update(native_scan_fields(envelope, 4))
                    else:
                        result.update(change)
                    return result
                bridge = TrialBridge(root, reg, 'run-a', reader=read)
                with self.assertRaises(Paused) as error:
                    bridge.request('interact', **ARGS)
                self.assertEqual(typed, isinstance(error.exception, TrialInteractionRejected))
                self.assertEqual(not typed, bridge.halted)
                self.assertEqual(not typed, bool(bridge.pending_mutations))
                if typed:
                    old = json.loads((root / 'request.json').read_text())
                    self.assertEqual('interaction_pre_dispatch_refusal', bridge.last_receipt['receipt_class'])
                    self.assertIn('blocks', bridge.request('scan', min=[0, 0, 0], max=[2, 2, 2]))
                    self.assertNotEqual(old['id'], json.loads((root / 'request.json').read_text())['id'])


class StationFaceTests(unittest.TestCase):
    def test_real_pit_pose_sees_west_side_but_not_top(self):
        target = (21, 63, -64)
        world = TrialWorld([row(target, 'crafting_table')], [16, 59, -67], [25, 68, -60])
        feet = [18.4905705773133, 62, -63.50078056258576]
        self.assertEqual(['west'], visible_station_faces(world, feet, target))
        plan = station_access_plan(world, {'pos': feet}, target)
        self.assertEqual('west', plan['face'])
        self.assertEqual([], plan['route'])

    def test_visible_top_from_above_and_blocked_or_unknown_rays_refuse(self):
        target = (3, 1, 0)
        table = row(target, 'crafting_table')
        world = TrialWorld([table], [-2, -1, -2], [7, 7, 2])
        self.assertEqual(['up'], visible_station_faces(world, [3.5, 3, .5], target))
        self.assertNotIn('up', visible_station_faces(world, [.5, 0, .5], target))
        wall = TrialWorld([table, row((1, 1, 0), 'stone')], world.low, world.high)
        self.assertEqual([], visible_station_faces(wall, [.5, 0, .5], target))
        incomplete_bounds = TrialWorld([table], [2, -1, -2], [7, 7, 2])
        self.assertEqual([], visible_station_faces(incomplete_bounds, [.5, 0, .5], target))
        furnace = TrialWorld([row(target, 'furnace')], world.low, world.high)
        self.assertEqual(['west'], visible_station_faces(furnace, [.5, 0, .5], target))

    def test_recorded_table_opens_side_from_lower_walkable_ground(self):
        with tempfile.TemporaryDirectory() as game:
            target = (3, 2, 0)
            rows = [row((x, 0, 0), 'stone') for x in range(4)] + [row(target, 'crafting_table')]
            skills, bridge = fixtures.StationNavigationTests().skills(game, rows, table=target)
            skills.station('crafting_table')
            interactions = [args for op, args in bridge.calls if op == 'interact']
            self.assertEqual(1, len(interactions))
            self.assertEqual('west', interactions[0]['face'])
            self.assertEqual('CraftingMenu', bridge.state['menu']['type'])

    def test_exact_face_refusal_reobserves_and_uses_new_face_or_stance(self):
        with tempfile.TemporaryDirectory() as game:
            target = (3, 1, 0)
            rows = [row((x, 0, z), 'stone') for x in range(5) for z in range(-1, 2)] + [row(target, 'crafting_table')]
            skills, bridge = fixtures.StationNavigationTests().skills(game, rows, table=target)
            original = bridge.request
            attempts = []
            def request(op, **args):
                if op == 'interact':
                    attempts.append((copy.deepcopy(args), list(bridge.state['pos'])))
                    if len(attempts) == 1:
                        bridge.calls.append((op, args))
                        raise TrialInteractionRejected(args, {'detail': 'Target interaction face is occluded or out of reach', 'request_id': 'old-no-send'})
                return original(op, **args)
            bridge.request = request
            skills.station('crafting_table')
            self.assertEqual(2, len(attempts))
            self.assertNotEqual((attempts[0][0]['face'], attempts[0][1]), (attempts[1][0]['face'], attempts[1][1]))
            calls = [op for op, args in bridge.calls]
            first, second = [i for i, op in enumerate(calls) if op == 'interact']
            self.assertIn('scan', calls[first + 1:second])

    def test_explicit_placement_face_never_changes_to_station_side(self):
        with tempfile.TemporaryDirectory() as game:
            target = (3, 1, 0)
            skills, bridge = fixtures.StationNavigationTests().skills(game, [row(target, 'crafting_table')], table=target)
            skills.interact(target, face='up')
            self.assertEqual('up', next(args['face'] for op, args in bridge.calls if op == 'interact'))


if __name__ == '__main__':
    unittest.main()
