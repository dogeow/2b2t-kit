import unittest

from material_trip_policy import carried, room_for_item, trip_complete


def backpack():
    slots = [{'slot': index, 'item': 'minecraft:tool',
              'count': 1, 'max_stack': 1} for index in range(36)]
    slots[9] = {'slot': 9, 'item': 'minecraft:gravel',
                'count': 30, 'max_stack': 64}
    slots[10] = {'slot': 10, 'item': 'minecraft:air',
                 'count': 0, 'max_stack': 1}
    return {'inventory': slots}


class MaterialTripPolicyTest(unittest.TestCase):
    def test_one_stack_is_not_full_backpack(self):
        state = backpack()
        self.assertEqual(98, room_for_item(state, 'minecraft:gravel'))
        self.assertEqual(30, carried(state, 'minecraft:gravel'))
        self.assertFalse(trip_complete(state, 'minecraft:gravel', 250))

    def test_audited_goal_ends_trip_before_backpack_is_full(self):
        state = backpack()
        state['inventory'][11] = {'slot': 11, 'item': 'minecraft:gravel',
                                  'count': 64, 'max_stack': 64}
        self.assertTrue(trip_complete(state, 'minecraft:gravel', 90))
        self.assertFalse(trip_complete(state, 'minecraft:gravel'))

    def test_full_backpack_ends_trip(self):
        state = backpack()
        state['inventory'][9]['count'] = 64
        state['inventory'][10] = {'slot': 10, 'item': 'minecraft:tool',
                                  'count': 1, 'max_stack': 1}
        self.assertEqual(0, room_for_item(state, 'minecraft:gravel'))
        self.assertTrue(trip_complete(state, 'minecraft:gravel'))

    def test_incomplete_snapshot_cannot_authorize_return(self):
        state = backpack()
        state['inventory'].pop()
        with self.assertRaises(RuntimeError):
            trip_complete(state, 'minecraft:gravel')

    def test_non_stackable_item_uses_its_actual_stack_size(self):
        state = backpack()
        self.assertEqual(1, room_for_item(state, 'minecraft:potion', stack_size=1))


if __name__ == '__main__':
    unittest.main()
