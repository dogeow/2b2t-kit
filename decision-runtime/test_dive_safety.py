import unittest

from dive_safety import ready_for_gravel_dive, must_surface


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
        state['air_supply'] = 149
        self.assertTrue(must_surface(state))
        state['water_breathing_effect'] = True
        self.assertFalse(must_surface(state))
        state['health'] = 17
        self.assertTrue(must_surface(state))


if __name__ == '__main__': unittest.main()
