import unittest

from food_refuel_policy import guarded_hotbar_meal


class Tests(unittest.TestCase):
    def test_selects_cooked_food_only_at_a_guarded_safe_break(self):
        state={'connected':True,'health':20,'air_supply':300,'under_water':False,
               'manual_movement':False,'screen':'','guard_armed':True,'food':17,
               'inventory':[{'slot':3,'item':'minecraft:cooked_porkchop','count':2},
                            {'slot':4,'item':'minecraft:rotten_flesh','count':8}]}
        self.assertEqual('minecraft:cooked_porkchop',guarded_hotbar_meal(state))
        self.assertIsNone(guarded_hotbar_meal({**state,'food':20}))
        self.assertIsNone(guarded_hotbar_meal({**state,'manual_movement':True}))
        self.assertIsNone(guarded_hotbar_meal({**state,'guard_armed':False}))


if __name__=='__main__':unittest.main()
