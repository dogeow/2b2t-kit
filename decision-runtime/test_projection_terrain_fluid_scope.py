import unittest
from projection_terrain import unsafe_nearby_fluid

class TerrainFluidScopeTest(unittest.TestCase):
    def test_water_below_and_offset_can_remain_while_surface_is_cleared(self):
        self.assertFalse(unsafe_nearby_fluid([{'pos':[9,9,10],'state':'Block{minecraft:water}[level=2]','fluid':True}],[10,10,10]))
    def test_source_water_and_lava_are_not_exempted(self):
        for state in ('Block{minecraft:water}[level=0]','Block{minecraft:lava}[level=2]'):
            self.assertTrue(unsafe_nearby_fluid([{'pos':[9,9,10],'state':state,'fluid':True}],[10,10,10]))
    def test_adjacent_below_same_height_and_above_stay_protected(self):
        for pos in ([10,9,10],[9,10,10],[9,11,10]):
            self.assertTrue(unsafe_nearby_fluid([{'pos':pos,'state':'Block{minecraft:water}[level=2]','fluid':True}],[10,10,10]))
