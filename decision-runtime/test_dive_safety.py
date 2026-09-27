import unittest
import time

from dive_safety import ready_for_gravel_dive, must_surface, ascent_air_floor, work_air_floor
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

    def test_ascent_budget_grows_with_depth_and_keeps_reserve(self):
        state=self.state();state['pos']=[10.5,52,20.5]
        self.assertEqual(240,ascent_air_floor(state))
        state['pos']=[10.5,45,20.5]
        self.assertEqual(260,ascent_air_floor(state))
        state['pos']=[10.5,35,20.5]
        self.assertEqual(340,ascent_air_floor(state))

    def test_observed_route_uses_air_and_keeps_one_bubble_at_surface(self):
        state=self.state()
        state.update(pos=[10.5,52,20.5],under_water=True,air_supply=100,
                     max_air_supply=300,air_budget_source='observed',
                     air_return_floor=62,air_work_floor=88,air_pickup_floor=77,air_return_y=65,
                     air_budget_valid_until=time.time()*1000+60000)
        self.assertEqual(62,ascent_air_floor(state))
        self.assertEqual(88,work_air_floor(state))
        self.assertIsNone(ready_for_gravel_dive(state))
        self.assertTrue(underwater_action_allowed(state,'mine_block',{'pos':[10,51,20]}))
        self.assertFalse(must_surface(state))
        state['air_supply']=80
        self.assertFalse(underwater_action_allowed(state,'mine_block',{'pos':[10,51,20]}))
        self.assertTrue(underwater_action_allowed(state,'walk',
                        {'target':[10.5,50,20.5],'water_descend':True}))
        state['air_supply']=61
        self.assertTrue(must_surface(state))
        self.assertFalse(underwater_action_allowed(state,'mine_block',{'pos':[10,51,20]}))

    def test_expired_or_invalid_budget_cannot_relax_underwater_safety(self):
        state=self.state()
        state.update(pos=[10.5,52,20.5],air_supply=100,under_water=True,
                     air_budget_source='observed',air_return_floor=20,
                     air_work_floor=80,air_return_y=65,
                     air_budget_valid_until=time.time()*1000+60000)
        self.assertEqual(240,ascent_air_floor(state))
        state['air_return_floor']=60
        state['air_budget_valid_until']=time.time()*1000-1
        self.assertEqual(240,ascent_air_floor(state))
        state['air_budget_valid_until']=time.time()*1000+60000
        state['air_return_active']=True
        self.assertTrue(must_surface(state))
        self.assertFalse(underwater_action_allowed(state,'mine_block',{}))

    def test_return_cost_above_full_air_refuses_work_instead_of_falling_back(self):
        state=self.state()
        state.update(pos=[10.5,52,20.5],under_water=True,
                     air_budget_source='observed',air_return_floor=320,
                     air_work_floor=360,air_return_y=65,
                     air_budget_valid_until=time.time()*1000+60000)
        self.assertEqual(320,ascent_air_floor(state))
        self.assertIn('air',ready_for_gravel_dive(state))
        self.assertTrue(must_surface(state))
        self.assertFalse(underwater_action_allowed(state,'mine_block',{}))


if __name__ == '__main__': unittest.main()
