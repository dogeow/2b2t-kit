import unittest
from placement_player_body import require_player_clear


class PlayerPlacementBodyTests(unittest.TestCase):
    def test_actual_six_centimeter_stop_error_intersects_wall(self):
        with self.assertRaises(ValueError):
            require_player_clear({'pos':[992.290427,64.0921875,811.500666]},[991,64,811],'minecraft:cobblestone')

    def test_clear_standing_pose_and_floor_ceiling_touches(self):
        for target in ([991,64,811],[992,63,811],[992,66,811]):
            require_player_clear({'pos':[992.55,64.1,811.5]},list(target),'minecraft:cobblestone')

    def test_clear_neighbor_on_each_horizontal_side(self):
        for point in ([10.5,64,10.5],[12.5,64,10.5],[11.5,64,9.5],[11.5,64,11.5]):
            require_player_clear({'pos':list(point)},[11,64,10],'minecraft:dark_oak_planks')

    def test_missing_or_nonfinite_position_is_not_placement_authority(self):
        for point in (None,[0,float('nan'),0],[0,64]):
            with self.assertRaises(ValueError):
                require_player_clear({'pos':point},[0,64,0],'minecraft:cobblestone')


if __name__ == '__main__': unittest.main()
