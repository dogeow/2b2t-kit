import unittest
from material_jobs.discovery import tiles,frontier,excluded

class NearResourceFrontierTest(unittest.TestCase):
    def test_optional_near_tiles_do_not_expand_the_original_outer_radius(self):
        old=set(tiles([0,100,0],128));new=list(tiles([0,100,0],128,include_near=True))
        self.assertEqual(new[0],(0,0));self.assertTrue(old<=set(new))
        self.assertEqual(len(set(new)-old),25)
        self.assertTrue(all(abs(x)<=128 and abs(z)<=128 for x,z in new))
    def test_real_home_and_depot_protection_still_excludes_nearby_tiles(self):
        p={'include_near_search_origin':True,'depots':[[8,65,8]],'protected_regions':[]}
        self.assertEqual(frontier([0,100,0],128,p)[0],(0,0))
        self.assertTrue(excluded([0,48,0],[15,164,15],p,{}))
