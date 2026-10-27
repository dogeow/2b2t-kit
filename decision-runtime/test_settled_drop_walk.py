import unittest
from settled_drop_walk import conserved_coast


class SettledDropWalkTests(unittest.TestCase):
    def fixture(self):
        r={'id':'r','world_session':'w','phase':'waiting','detail':'unsafe drop ahead; choose another walking waypoint',
           'pos':[2.65,90,3.5],'inventory':[{'slot':0,'item':'minecraft:stick','count':3}]}
        s={**r,'pos':[2.41,90,3.5],'last_request':'r','health':20,'on_ground':True,
           'manual_movement':False,'screen':'','movement_keys':{'forward':False}}
        return r,s
    def test_short_conserved_ground_coast_is_only_an_observation_candidate(self):
        self.assertTrue(conserved_coast(*self.fixture()))
    def test_damage_fall_inventory_change_or_active_input_stays_protected(self):
        for update in ({'health':19},{'on_ground':False},{'pos':[2,90,3.5]},
                       {'movement_keys':{'forward':True}},{'world_session':'other'},
                       {'inventory':[]},{'manual_movement':True}):
            with self.subTest(update=update):
                r,s=self.fixture();s.update(update);self.assertFalse(conserved_coast(r,s))


if __name__=='__main__':unittest.main()
