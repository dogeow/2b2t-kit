import unittest

from ocean_pickup import pickup_pose, supported_drop_neighborhood


class Tests(unittest.TestCase):
    def test_drop_over_mined_cell_lands_on_lower_floor(self):
        rows = [{'pos':[816,51,124], 'solid':True},
                {'pos':[816,52,124], 'solid':False}]
        self.assertEqual([816.5,52,124.5],
                         pickup_pose([816.125,52,124.125],rows)['target'])

    def test_drift_into_adjacent_higher_cell_targets_that_cell(self):
        rows = [{'pos':[811,53,122], 'solid':True},
                {'pos':[811,54,122], 'solid':True}]
        self.assertEqual([811.5,55,122.5],
                         pickup_pose([811.318,54.88,122.399],rows)['target'])

    def test_no_support_or_excessively_high_drop_is_not_guessed(self):
        self.assertIsNone(pickup_pose([1.2,50,2.2],[]))
        rows=[{'pos':[1,45,2], 'solid':True}]
        self.assertIsNone(pickup_pose([1.2,50,2.2],rows))

    def test_neighborhood_rejects_a_neighboring_cave_drop(self):
        target=[10,52,20]
        floor=[{'pos':[10+dx,51,20+dz],'solid':True}
               for dx in (-1,0,1) for dz in (-1,0,1)]
        self.assertTrue(supported_drop_neighborhood(floor,target))
        self.assertFalse(supported_drop_neighborhood(floor[:-1],target))


if __name__ == '__main__':
    unittest.main()
