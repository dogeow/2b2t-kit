import unittest

from ocean_pickup import pickup_pose, supported_drop_neighborhood, select_next_gravel


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

    def test_one_block_seabed_step_is_collectable_but_deep_cavity_is_not(self):
        target=[10,52,20]
        floor=[{'pos':[10+dx,51,20+dz],'solid':True}
               for dx in (-1,0,1) for dz in (-1,0,1)]
        self.assertTrue(supported_drop_neighborhood(
            floor[:-1]+[{'pos':[11,50,21],'solid':True}],target))
        self.assertFalse(supported_drop_neighborhood(
            floor[:-1]+[{'pos':[11,49,21],'solid':True}],target))

    def test_bad_first_neighbor_does_not_end_the_chain(self):
        state={'pos':[10.5,52.25,20.5]}
        choices=[{'pos':[11,50,21]},{'pos':[10,50,21]}]
        rows=[{'pos':[x,49,z],'solid':True} for x in range(9,13) for z in range(19,24)]
        rows += [{'pos':c['pos'],'state':'Block{minecraft:gravel}'} for c in choices]
        self.assertEqual([10,50,21],select_next_gravel(state,choices,rows,[10,50,20])['pos'])
        self.assertIsNone(select_next_gravel(state,choices,rows[-2:],[10,50,20]))

    def test_standing_on_supported_gravel_is_a_valid_next_pickup(self):
        target=[10,50,20]
        rows=[{'pos':[10+dx,49,20+dz],'solid':True}
               for dx in (-1,0,1) for dz in (-1,0,1)]
        rows.append({'pos':target,'state':'Block{minecraft:gravel}'})
        state={'pos':[10.5,51,20.5]}
        self.assertEqual(target,select_next_gravel(state,[{'pos':target}],rows,[10,50,21])['pos'])


if __name__ == '__main__':
    unittest.main()
