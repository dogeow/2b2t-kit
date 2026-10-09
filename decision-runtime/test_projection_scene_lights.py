import copy
import unittest
from projection_scene_lights import registered_map_light, completed_map_light_positions
from lighting_cli import EVIDENCE


class RegisteredMapLightTests(unittest.TestCase):
    def test_completed_reports_require_current_world_and_exact_placement_evidence(self):
        row = {'target':[4,65,8], 'world_session':'current', 'state':'verified',
               'later_verified_frames':2, 'observed_block_state':'Block{minecraft:torch}',
               'evidence_scope':EVIDENCE, 'interaction_request':'one', 'task_session':'task',
               'before_stock':7, 'after_stock':6}
        report = {'world_session':'current', 'state':'bounded_run_finished',
                  'park_native_confirmed':True, 'placed':[row]}
        self.assertEqual(frozenset({(4,65,8)}), completed_map_light_positions([report], 'current', 64))
        for change in ({'world_session':'old'}, {'park_native_confirmed':False}, {'state':'running'}):
            with self.assertRaises(ValueError):
                completed_map_light_positions([{**report, **change}], 'current', 64)
        for change in ({'world_session':'old'}, {'target':[4,64,8]}, {'after_stock':5},
                       {'later_verified_frames':1}, {'evidence_scope':'prediction'},
                       {'observed_block_state':'Block{minecraft:wall_torch}'}, {'interaction_request':''}):
            with self.assertRaises(ValueError):
                completed_map_light_positions([{**report, 'placed':[{**row, **change}]}], 'current', 64)
        with self.assertRaises(ValueError):
            completed_map_light_positions([report, report], 'current', 64)

    def setUp(self):
        self.light = {'pos': [4, 65, 8], 'state': 'Block{minecraft:torch}',
                      'passable': True, 'solid': False, 'fluid': False,
                      'block_entity': False}
        self.expected = {(4, 64, 8): {'state': 'Block{minecraft:stone}'}}
        self.observed = {(4, 64, 8): {'state': 'Block{minecraft:stone}',
                                    'solid': True, 'fluid': False,
                                    'block_entity': False}}
        self.registered = frozenset({(4, 65, 8)})

    def allowed(self, row=None, observed=None):
        return registered_map_light(row or self.light, self.expected,
                                    self.observed if observed is None else observed,
                                    self.registered, 64)

    def test_registered_torch_on_matching_real_floor_is_only_ignored_overlay(self):
        self.assertTrue(self.allowed())
        self.assertEqual(self.observed[(4, 64, 8)]['state'], 'Block{minecraft:stone}')

    def test_unknown_location_height_or_other_block_still_rejected(self):
        for key, value in [('pos', [5, 65, 8]), ('pos', [4, 66, 8]),
                           ('state', 'Block{minecraft:dirt}'),
                           ('state', 'Block{minecraft:wall_torch}[facing=north]')]:
            row = copy.deepcopy(self.light); row[key] = value
            self.assertFalse(self.allowed(row))

    def test_missing_wrong_wet_or_container_floor_cannot_be_hidden(self):
        self.assertFalse(self.allowed(observed={}))
        for key, value in [('state', 'Block{minecraft:oak_planks}'),
                           ('solid', False), ('fluid', True), ('block_entity', True)]:
            observed = copy.deepcopy(self.observed); observed[(4, 64, 8)][key] = value
            self.assertFalse(self.allowed(observed=observed))

    def test_incomplete_or_unsafe_light_record_is_rejected(self):
        for key in ['solid', 'fluid', 'block_entity', 'passable']:
            row = copy.deepcopy(self.light); del row[key]
            self.assertFalse(self.allowed(row))


if __name__ == '__main__':
    unittest.main()
