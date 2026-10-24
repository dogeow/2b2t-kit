import unittest
from profession_xp_pose import collecting_inside


class PoseTests(unittest.TestCase):
    def test_native_ground_and_bed_top_positions_both_collect_inside_the_same_counter(self):
        slot={'work_block':[100,64,200],'bed_foot':[100,64,198]}
        for pos in ([100.5,64,199.7],[100.4701117532,64.5625,199.1850283833]):
            self.assertTrue(collecting_inside({'pos':pos,'flight':False,'on_ground':True},slot))
    def test_hovering_workstation_top_foreign_room_and_unsupported_pose_are_rejected(self):
        slot={'work_block':[100,64,200],'bed_foot':[100,64,198]}
        for pos,flight,ground in [([100.5,65.1,199.5],True,False),([100.5,65,199.5],False,True),
                                  ([102.5,64,199.5],False,True),([100.5,64,199.5],False,False)]:
            self.assertFalse(collecting_inside({'pos':pos,'flight':flight,'on_ground':ground},slot))
    def test_opposite_counter_orientation_and_ambiguous_profile(self):
        state={'pos':[100.5,64.5625,201.8],'flight':False,'on_ground':True}
        self.assertTrue(collecting_inside(state,{'work_block':[100,64,200],'bed_foot':[100,64,202]}))
        self.assertFalse(collecting_inside(state,{'work_block':[100,64,200],'bed_foot':[100,64,200]}))


if __name__=='__main__':unittest.main()
