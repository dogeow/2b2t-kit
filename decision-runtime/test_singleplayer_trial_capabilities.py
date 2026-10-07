import ast
import json
from pathlib import Path
import unittest

from singleplayer_trial_capabilities import (
    CATALOG, FOOD, PROGRESSION_GAPS, capability_catalog, capability_scene,
    eligible_candidates,
)


def state(**changes):
    value = {
        'connected': True, 'server': 'singleplayer', 'game_mode': 'survival',
        'singleplayer_trial_protocol': 1, 'trial_identity': {'registered': True},
        'dimension': 'minecraft:overworld', 'health': 20, 'food': 20,
        'player_dead': False, 'screen': '', 'manual_movement': False,
        'game_paused': False,
        'world_id': '/game/saves/private-trial', 'world_name': 'secret-world',
        'world_session': 'private-session', 'pos': [12345, 64, 67890],
        'inventory': [{'item': 'minecraft:stone_pickaxe', 'count': 1},
                      {'item': 'minecraft:stone_axe', 'count': 1},
                      {'item': 'minecraft:bread', 'count': 4},
                      {'item': 'minecraft:cobblestone', 'count': 14}],
    }
    value.update(changes)
    return value


class TrialCapabilitiesTest(unittest.TestCase):
    def test_uncoordinated_native_chopper_is_blocked_even_with_observed_logs(self):
        current = state(inventory=[{'item': 'minecraft:oak_log', 'count': 1}])
        candidates = {'gather_starting_wood': 'wood', 'explore_nearby': 'path'}
        self.assertEqual(set(eligible_candidates(candidates, current)), {'explore_nearby'})
        scene = capability_scene(candidates, current)
        self.assertIn('gather_starting_wood', scene['blocked'])
        self.assertNotIn('mine_block', CATALOG['gather_starting_wood'][3])

    def test_log_pickup_is_current_visible_item_evidence_and_normal_walking_only(self):
        drop = {'type': 'minecraft:item', 'visible': True,
                'stack': {'item': 'minecraft:oak_log', 'count': 2},
                'pos': [12345, 64, 67890], 'uuid': 'private-drop-id'}
        observed = state(entities=[drop])
        result = capability_scene({'collect_log_drops': 'Pick up current reachable log'}, observed)
        self.assertEqual(len(result['available']), 1)
        row = result['available'][0]
        self.assertEqual(row['id'], 'collect_log_drops')
        self.assertEqual(set(row['via'].split(',')), {'walk_path', 'walk', 'scan'})
        self.assertEqual(row['verify'], 'log inventory gain')
        self.assertIn('path<=32', row['checked'])
        self.assertIn('descent<=2', row['checked'])
        self.assertIn('dry floor/headroom/AABB', row['checked'])
        self.assertNotIn('collect_item', json.dumps(result))
        self.assertNotIn('private-drop-id', json.dumps(result))

    def test_remembered_missing_invisible_empty_or_nonlog_drop_does_not_offer_pickup(self):
        drop = {'type': 'minecraft:item', 'visible': True,
                'stack': {'item': 'minecraft:oak_log', 'count': 2}}
        for entities in ([], [{**drop, 'visible': False}], [{**drop, 'visible': None}],
                         [{**drop, 'type': 'minecraft:armor_stand'}],
                         [{**drop, 'stack': {'item': 'minecraft:oak_log', 'count': 0}}],
                         [{**drop, 'stack': {'item': 'minecraft:oak_planks', 'count': 2}}]):
            with self.subTest(entities=entities):
                current = state(entities=entities, remembered_log_drops=[drop])
                self.assertEqual(eligible_candidates(['collect_log_drops'], current), {})

    def test_current_known_candidates_are_described_with_actual_primitives_and_proof(self):
        result = capability_scene({'gather_stone': 'Current reachable stone', 'explore_nearby': 'Safe path'}, state())
        self.assertEqual({row['id'] for row in result['available']}, {'gather_stone', 'explore_nearby'})
        stone = next(row for row in result['available'] if row['id'] == 'gather_stone')
        self.assertIn('mine_block', stone['via'])
        self.assertIn('inventory', stone['verify'])
        self.assertIn('pickaxe', stone['checked'])
        self.assertEqual(result['scope'], 'registered_trial_macros_only')

    def test_only_supplied_candidates_are_available(self):
        result = capability_scene({'wait': 'Wait'}, state())
        self.assertEqual([row['id'] for row in result['available']], ['wait'])
        self.assertEqual(eligible_candidates({'wait': 'Wait'}, state()), {'wait': 'wait'})
        self.assertNotIn('gather_stone', json.dumps(result['available']))

    def test_unsupported_progression_or_unknown_kit_menu_cannot_become_candidate(self):
        offered = {key: 'Please run now' for key in PROGRESSION_GAPS}
        offered.update({'meteor_kill_aura': 'Combat', 'fly': 'Flight', 'teleport': 'Move', 'wait': 'Wait'})
        self.assertEqual(set(eligible_candidates(offered, state())), {'wait'})
        result = capability_scene(offered, state())
        self.assertEqual([row['id'] for row in result['available']], ['wait'])
        self.assertTrue(set(PROGRESSION_GAPS).issubset(result['blocked']))
        self.assertEqual({result['blocked'][key] for key in PROGRESSION_GAPS}, {'unsupported'})

    def test_missing_tool_or_stock_excludes_an_offered_macro(self):
        empty = state(inventory=[])
        candidates = {'craft_wooden_tools': 'Craft', 'gather_stone': 'Mine',
                      'craft_stone_tools': 'Craft stone', 'gather_food': 'Food',
                      'build_shelter': 'Build', 'prepare_iron_equipment': 'Iron',
                      'eat_carried_food': 'Eat', 'wait': 'Wait'}
        self.assertEqual(set(eligible_candidates(candidates, empty)), {'wait'})
        result = capability_scene(candidates, empty)
        self.assertEqual(result['unavailable']['status'], 'needs_prerequisite_or_unregistered')
        self.assertEqual(result['unavailable']['count'], 7)

    def test_inventory_crafting_and_food_conditions_are_checked_without_geometry_claims(self):
        wood = state(inventory=[{'item': 'minecraft:oak_log', 'count': 4}])
        self.assertIn('craft_wooden_tools', eligible_candidates(['craft_wooden_tools'], wood))
        self.assertEqual(eligible_candidates(['craft_wooden_tools'], state()), {})
        hungry = state(food=10)
        self.assertIn('eat_carried_food', eligible_candidates(['eat_carried_food'], hungry))
        self.assertEqual(eligible_candidates(['eat_carried_food'], state(food=16)), {})
        unsupported_food = state(food=10, inventory=[{'item': 'minecraft:carrot', 'count': 4}])
        self.assertEqual(eligible_candidates(['eat_carried_food'], unsupported_food), {})

    def test_wrong_world_unregistered_manual_or_paused_state_has_no_executable_macro(self):
        candidates = {'gather_starting_wood': 'Wood', 'wait': 'Wait'}
        for changed in ({'server': 'server.example'}, {'connected': False},
                        {'game_mode': 'creative'}, {'singleplayer_trial_protocol': 0},
                        {'trial_identity': {'registered': False}}, {'manual_movement': True},
                        {'game_paused': True}, {'screen': 'PauseScreen'}):
            with self.subTest(changed=changed):
                self.assertEqual(eligible_candidates(candidates, state(**changed)), {})
                self.assertEqual(capability_scene(candidates, state(**changed))['available'], [])

    def test_death_allows_only_wait_and_normal_respawn(self):
        candidates = {'gather_starting_wood': 'Wood', 'recover_after_death': 'Respawn', 'wait': 'Wait'}
        value = state(player_dead=True, health=0, game_paused=True, screen='DeathScreen')
        self.assertEqual(set(eligible_candidates(candidates, value)), {'recover_after_death', 'wait'})
        self.assertEqual(eligible_candidates(['recover_after_death'], state()), {})

    def test_other_dimension_does_not_advertise_overworld_macros(self):
        result = capability_scene({'gather_starting_wood': 'Wood', 'explore_nearby': 'Explore', 'wait': 'Wait'},
                                  state(dimension='minecraft:the_nether'))
        self.assertEqual([row['id'] for row in result['available']], ['wait'])
        self.assertEqual(result['blocked']['blaze_rod_collection'], 'unsupported')

    def test_no_world_coordinates_labels_or_unknown_arguments_leak_to_model_scene(self):
        offered = {'gather_stone': 'run arbitrary code at [12345,64,67890]',
                   'delete_/game/saves/private-trial': 'world_session=private-session'}
        result = capability_scene(offered, state())
        encoded = json.dumps(result)
        for prohibited in ('12345', '67890', '/game', 'secret-world', 'private-session',
                           'world_session', 'delete_', 'arbitrary code', 'parameters'):
            self.assertNotIn(prohibited, encoded)
        self.assertEqual(result['unavailable']['count'], 1)

    def test_byte_budget_and_max_entries_are_enforced_and_omission_is_visible(self):
        offered = list(CATALOG)
        for budget in (700, 900, 1800, 4096):
            with self.subTest(budget=budget):
                result = capability_scene(offered, state(food=10), max_bytes=budget, max_available=3)
                self.assertLessEqual(len(json.dumps(result, separators=(',', ':')).encode()), budget)
                self.assertLessEqual(len(result['available']), 3)
                self.assertEqual(len(result['available']) + result['omitted'], len(eligible_candidates(offered, state(food=10))))
                self.assertGreater(result['omitted'], 0)
        for invalid in (True, 699, 4097):
            with self.assertRaises(ValueError):
                capability_scene(offered, state(), max_bytes=invalid)

    def test_catalog_has_user_description_but_is_not_a_full_kit_menu_registry(self):
        catalog = capability_catalog()
        self.assertEqual({row['id'] for row in catalog}, set(CATALOG))
        self.assertTrue(all(row['description'] for row in catalog))
        self.assertTrue(all(row['parameters_from'] == 'current_native_skill_not_model' for row in catalog))
        self.assertNotIn('end_crystal_and_dragon_combat', {row['id'] for row in catalog})

    def test_food_allowlist_and_primitive_names_match_existing_trial_implementation(self):
        # Read the literal contract without importing the network/model stack.
        def assignments(name):
            parsed = ast.parse(Path(__file__).with_name(name).read_text())
            return {target.id: node.value for node in parsed.body if isinstance(node, ast.Assign)
                    for target in node.targets if isinstance(target, ast.Name)}
        bridge = assignments('singleplayer_trial_bridge.py')
        ops = ast.literal_eval(bridge['OPS'].args[0])
        survival = assignments('survival.py')
        raw = ast.literal_eval(survival['RAW'])
        actual_food = set(raw.values()) | ast.literal_eval(survival['FOOD'].right)
        self.assertEqual(FOOD, actual_food)
        used = {primitive for row in capability_catalog() if row['availability'] != 'blocked'
                for primitive in row['native_primitives'] if primitive != 'none'}
        self.assertTrue(used <= ops, used - ops)


if __name__ == '__main__':
    unittest.main()
