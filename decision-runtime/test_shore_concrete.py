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
