import unittest
from construction_materials import supply_targets


def state(occupied=0):
    return {'inventory':[{'slot':i,'item':'minecraft:diamond_sword' if i < occupied else 'minecraft:air',
                          'count':1 if i < occupied else 0, 'max_stack':1} for i in range(36)]}


class SupplyTargetsTest(unittest.TestCase):
    def test_empty_stack_capacity_does_not_inherit_air_max_stack_one(self):
        s=state(32)
        self.assertEqual({'minecraft:white_concrete':192},supply_targets(s,{'minecraft:white_concrete':1717},{'minecraft:white_concrete':1717}))

    def test_multiple_materials_share_empty_slots_without_overbooking(self):
        s=state(32)
        self.assertEqual({'minecraft:white_concrete':65,'minecraft:smooth_stone':64},supply_targets(s,
                         {'minecraft:white_concrete':65,'minecraft:smooth_stone':165,'minecraft:hopper':6},
                         {'minecraft:white_concrete':100,'minecraft:smooth_stone':216,'minecraft:hopper':6}))

    def test_existing_partial_stack_is_filled_without_consuming_another_empty_slot(self):
        s=state(35);s['inventory'][0]={'slot':0,'item':'minecraft:white_concrete','count':16,'max_stack':64}
        self.assertEqual({'minecraft:white_concrete':64},supply_targets(s,{'minecraft:white_concrete':100},{'minecraft:white_concrete':100}))

    def test_never_takes_more_than_missing_or_verified_stored_stock(self):
        s=state();self.assertEqual({'minecraft:smooth_stone':165,'minecraft:deepslate_tiles':68},supply_targets(s,
            {'minecraft:smooth_stone':165,'minecraft:deepslate_tiles':625},{'minecraft:smooth_stone':216,'minecraft:deepslate_tiles':68}))

    def test_incomplete_inventory_cannot_authorize_taking_materials(self):
        s=state();s['inventory'].pop()
        with self.assertRaises(RuntimeError):supply_targets(s,{}, {})

    def test_other_finished_items_use_observed_stack_sizes_and_preserve_work_slot(self):
        s=state(32)
        self.assertEqual({'minecraft:oak_stairs':128,'minecraft:water_bucket':1},supply_targets(s,
            {'minecraft:oak_stairs':128,'minecraft:water_bucket':4},{'minecraft:oak_stairs':128,'minecraft:water_bucket':4},
            stack_sizes={'minecraft:oak_stairs':64,'minecraft:water_bucket':1}))

    def test_unknown_item_capacity_is_not_guessed(self):
        self.assertEqual({},supply_targets(state(),{'minecraft:water_bucket':20},{'minecraft:water_bucket':20}))


if __name__=='__main__':unittest.main()
