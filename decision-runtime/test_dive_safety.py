import unittest

from dive_safety import ready_for_gravel_dive, must_surface
from material_client import underwater_action_allowed


class DiveSafetyTest(unittest.TestCase):
    def state(self):
        return {'bridge_version': 4, 'connected': True, 'dimension': 'minecraft:overworld',
                'screen': '', 'manual_movement': False, 'health': 20, 'food': 20,
                'guard_armed': True, 'auto_log': True, 'air_supply': 300,
                'selected_slot': 2,
                'equipment': {
                    'head': {'item': 'minecraft:netherite_helmet', 'enchantments': [
                        {'id': 'minecraft:aqua_affinity', 'level': 1},
                        {'id': 'minecraft:respiration', 'level': 3}]},
                    'feet': {'item': 'minecraft:netherite_boots', 'enchantments': [
                        {'id': 'minecraft:depth_strider', 'level': 3}]}},
                'inventory': [{'slot': 2, 'item': 'minecraft:diamond_shovel',
                               'durability': 1000, 'enchantments': []}]}

    def test_current_dive_gear_can_start_only_with_safe_air_and_no_fortune(self):
        state = self.state()
        self.assertIsNone(ready_for_gravel_dive(state))
        state['inventory'][0]['enchantments'] = [{'id': 'minecraft:fortune', 'level': 3}]
        self.assertIn('Fortune', ready_for_gravel_dive(state))
        state['inventory'][0]['enchantments'] = []
        state['air_supply'] = 100
        self.assertIn('air', ready_for_gravel_dive(state))

    def test_surface_trigger_is_independent_of_enchantment_score(self):
        state = self.state()
        self.assertFalse(must_surface(state))
        state['air_supply'] = 239
        self.assertTrue(must_surface(state))
        state['water_breathing_effect'] = True
        self.assertFalse(must_surface(state))
        state['health'] = 17
        self.assertTrue(must_surface(state))

    def test_low_oxygen_blocks_new_work_but_allows_vertical_escape(self):
        state = self.state()
        state.update(under_water=True, air_supply=27, pos=[10.5, 53, 20.5])
        self.assertFalse(underwater_action_allowed(state, 'mine_block', {'pos':[10,52,20]}))
        self.assertFalse(underwater_action_allowed(state, 'walk', {'target':[11,51,20]}))
        self.assertFalse(underwater_action_allowed(state, 'navigate', {'target':[14,70,20.5]}))
        self.assertTrue(underwater_action_allowed(state, 'navigate', {'target':[10.5,70,20.5]}))
        state['water_breathing_effect'] = True
        self.assertTrue(underwater_action_allowed(state, 'walk', {'target':[11,51,20]}))


if __name__ == '__main__': unittest.main()
