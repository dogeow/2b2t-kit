import unittest
from projection_armor_stands import placement_pose,matches


class StandGeometryTest(unittest.TestCase):
    def test_vanilla_item_rotation_comes_from_the_opposite_facing_side(self):
        self.assertEqual([27.5,65.1,3.5],placement_pose({'yaw':270.,'pos':[25.5,65.,3.5]}))
        self.assertEqual([17.5,70.1,10.5],placement_pose({'yaw':0.,'pos':[17.5,70.,8.5]}))
    def test_same_position_without_correct_pose_and_flags_is_not_complete(self):
        e={'type':'minecraft:armor_stand','pos':[25.5,65.,3.5],'yaw':270.,'small':False,'show_arms':False,'base_plate':True,'default_pose':True,'invisible':False}
        self.assertTrue(matches(e,{**e,'yaw':-90.}))
        self.assertFalse(matches(e,{**e,'yaw':0.}))
        self.assertFalse(matches(e,{**e,'invisible':True}))
