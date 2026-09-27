import unittest

from shore_concrete import reconcile_batch, shoreline_water_sides


def row(pos, state):
    return {'pos': list(pos), 'state': state}


class ShoreConcreteTest(unittest.TestCase):
    def test_only_one_or_two_water_sides_are_allowed(self):
        support = [10, 61, 20]
        base = [row(support, 'Block{minecraft:dirt}'), row([10, 62, 20], 'Block{minecraft:water}[level=0]')]
        east = row([11, 62, 20], 'Block{minecraft:water}[level=0]')
        north = row([10, 62, 19], 'Block{minecraft:water}[level=0]')
        west = row([9, 62, 20], 'Block{minecraft:water}[level=0]')
        self.assertEqual(1, shoreline_water_sides(base + [east], support, 'Block{minecraft:dirt}'))
        self.assertEqual(2, shoreline_water_sides(base + [east, north], support, 'Block{minecraft:dirt}'))
        residual = [row(support, 'Block{minecraft:dirt}'), row([10, 62, 20], 'Block{minecraft:white_concrete}')]
        self.assertEqual(2, shoreline_water_sides(residual + [east, north], support,
                                                 'Block{minecraft:dirt}', 'minecraft:white_concrete'))
        with self.assertRaisesRegex(RuntimeError, 'one or two'):
            shoreline_water_sides(base + [east, north, west], support, 'Block{minecraft:dirt}')

    def test_waterlogged_leaf_is_an_actual_water_side(self):
        rows=[row([0,61,0],'Block{minecraft:dirt}'),row([0,62,0],'Block{minecraft:water}[level=1]'),
              row([1,62,0],'Block{minecraft:oak_leaves}[distance=7,persistent=true,waterlogged=true]')]
        self.assertEqual(1,shoreline_water_sides(rows,[0,61,0],'Block{minecraft:dirt}'))
        # A full waterlogged leaf supplies hardening water without flooding the work cell.
        self.assertEqual(1,shoreline_water_sides([rows[0],rows[2]],[0,61,0],'Block{minecraft:dirt}'))

    def test_batch_requires_exact_powder_to_solid_accounting(self):
        before = {'inventory': [{'item': 'minecraft:white_concrete_powder', 'count': 8},
                                {'item': 'minecraft:white_concrete', 'count': 2}]}
        after = {'inventory': [{'item': 'minecraft:white_concrete_powder', 'count': 0},
                               {'item': 'minecraft:white_concrete', 'count': 10}]}
        self.assertEqual(8, reconcile_batch(before, after, 'minecraft:white_concrete_powder',
                                            'minecraft:white_concrete', 8)['solid_recovered'])
        after['inventory'][1]['count'] = 9
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            reconcile_batch(before, after, 'minecraft:white_concrete_powder', 'minecraft:white_concrete', 8)


if __name__ == '__main__':
    unittest.main()


class PickupCandidateTest(unittest.TestCase):
    def test_only_fresh_nearby_expected_drop_within_deficit_is_selected(self):
        from shore_concrete import batch_pickup_candidate
        def drop(key,item='minecraft:white_concrete',count=1,x=1.5):
            return {'uuid':key,'type':'minecraft:item','pos':[x,62.5,1.5],'stack':{'item':item,'count':count}}
        before={'entities':[drop('old')]}
        after={'pos':[.5,63,1.5],'entities':[drop('old'),drop('far',x=30),drop('oversize',count=3),drop('other',item='minecraft:diamond'),drop('new')]}
        self.assertEqual('new',batch_pickup_candidate(before,after,'minecraft:white_concrete',[1,62,1],1)['uuid'])
        self.assertIsNone(batch_pickup_candidate(before,after,'minecraft:white_concrete',[1,62,1],0))
