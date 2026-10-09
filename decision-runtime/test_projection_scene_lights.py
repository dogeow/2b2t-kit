import copy
import unittest
from projection_scene_lights import registered_map_light


class RegisteredMapLightTests(unittest.TestCase):
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
