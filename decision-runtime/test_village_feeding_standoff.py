import unittest
from village_feeding import ground_food_pose

class SupportedFoodPoseTests(unittest.TestCase):
    def test_bedside_has_no_close_full_floor_but_aisle_is_reachable(self):
        cells={(3,63,5):{'solid':True,'fluid':False}}
        target={'uuid':'parent','pos':[3.36,64.5625,3.34]}
        state={'pos':[3.5,64,5.5]}
        self.assertIsNone(ground_food_pose([0,64,0],[7,67,7],cells,target,[target],state))
        self.assertEqual([3.5,64,5.5],ground_food_pose([0,64,0],[7,67,7],cells,target,[target],state,standoff=True))

    def test_fluid_body_obstruction_and_out_of_range_are_never_poses(self):
        target={'uuid':'p','pos':[3.5,64,3.5]};state={'pos':[3.5,64,5.5]}
        for extra in ({(3,63,5):{'solid':True,'fluid':True}},
                      {(3,63,5):{'solid':True,'fluid':False},(3,64,5):{'passable':False,'fluid':False,'block_entity':True}},
                      {(3,63,6):{'solid':True,'fluid':False}}):
            self.assertIsNone(ground_food_pose([0,64,0],[7,67,7],extra,target,[target],state,standoff=True))

    def test_standoff_prefers_current_supported_aisle_over_extra_walking(self):
        cells={(x,63,z):{'solid':True,'fluid':False}for x,z in [(3,5),(5,3)]}
        target={'uuid':'p','pos':[3.5,64,3.5]};state={'pos':[3.5,64,5.5]}
        self.assertEqual(state['pos'],ground_food_pose([0,64,0],[7,67,7],cells,target,[target],state,standoff=True))
