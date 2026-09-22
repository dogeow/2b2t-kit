import unittest
from natural_terrain import NaturalWorld
from test_survival import row,terrain

class NaturalTerrainTests(unittest.TestCase):
    def test_leaf_corner_ray_has_margin_for_real_waypoint_arrival(self):
        w=NaturalWorld([row((-32,110,18),'oak_leaves'),row((-32,110,17),'oak_log')],[-35,100,15],[-25,115,25])
        self.assertFalse(w.sight((-31,107,19),(-32,110,17)))
    def test_rejected_upper_log_does_not_hide_reachable_lower_log(self):
        w=NaturalWorld(terrain()+[row((2,y,0),'oak_log') for y in (1,2)],[-6,0,-6],[6,6,6])
        target,_=w.resource([.5,1,.5],{'oak_log'},{(2,2,0)})
        self.assertEqual(target,(2,1,0))
    def test_short_grass_is_a_removable_camp_obstacle_not_flat_air_requirement(self):
        grass=row((0,1,0),'short_grass',False,True);grass['replaceable']=True
        w=NaturalWorld(terrain()+[grass],[-6,0,-6],[6,6,6])
        plan=w.camp_plan([.5,1,.5]);self.assertIsNotNone(plan)
        self.assertTrue(w.build_space((0,1,0)))

if __name__=='__main__':unittest.main()
