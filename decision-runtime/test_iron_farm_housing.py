import unittest
from iron_farm_housing import receiving_plan,walking_chute_plan


class IronHousingTests(unittest.TestCase):
    def fixture(self):
        rows={(x,y,z):{'state':'Block{minecraft:cobblestone}','fluid':False}for x in range(0,5)for z in range(0,5)for y in(0,4,5)}
        for x in(0,4):
            for z in range(1,4):rows[x,3,z]={'state':'Block{minecraft:cobblestone}','fluid':False}
        actor={'health':20,'is_baby':False,'pos':[1.79,6,2.65]}
        return rows,actor

    def test_edge_straddling_footprint_gets_complete_two_stage_support(self):
        rows,actor=self.fixture();p=receiving_plan(rows,actor,room_min=[1,1],room_max=[3,3],floor_y=0)
        self.assertEqual(p['columns'],[[1,2],[2,2]]);self.assertEqual(p['free_worker_x'],3)
        self.assertEqual(p['first_max_drop'],2);self.assertEqual(p['second_max_drop'],3)
        self.assertTrue({(x,3,z)for x,z in p['columns']}<=set(map(tuple,p['platforms'])))

    def test_unsealed_deck_wall_edge_and_injured_actor_refused(self):
        for mode in('deck','edge','injury','water'):
            with self.subTest(mode=mode):
                rows,actor=self.fixture()
                if mode=='deck':del rows[2,5,2]
                if mode=='edge':actor['pos'][0]=.9
                if mode=='injury':actor['health']=19
                if mode=='water':rows[2,1,2]={'state':'Block{minecraft:water}','fluid':True}
                with self.assertRaises(ValueError):receiving_plan(rows,actor,room_min=[1,1],room_max=[3,3],floor_y=0)

    def test_fixed_path_requires_deep_cap_and_complete_intermediate_floor(self):
        rows,_=self.fixture()
        with self.assertRaises(ValueError):walking_chute_plan(rows,room_min=[1,1],room_max=[3,3],floor_y=0,chute_x=1)
        rows[1,6,1]={'state':'Block{minecraft:dark_oak_slab}[type=bottom,waterlogged=false]'}
        p=walking_chute_plan(rows,room_min=[1,1],room_max=[3,3],floor_y=0,chute_x=1)
        self.assertEqual(p['platforms'],[[1,3,2],[2,3,2]])
        self.assertEqual(p['deck_openings'],[[1,5,1],[1,5,2],[2,5,2]])
        self.assertTrue(p['deep_opening_is_covered']);self.assertLessEqual(p['first_max_drop'],3)


if __name__=='__main__':unittest.main()
