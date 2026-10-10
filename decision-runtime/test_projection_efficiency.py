import unittest
from projection_efficiency import WindowEfficiency


class EfficiencyTest(unittest.TestCase):
    def test_three_confirmed_windows_review_does_not_change_parameters(self):
        review = WindowEfficiency()
        row = {'complete': True, 'pending': None, 'physical_positions': [[1,64,1]],
               'elapsed_seconds': 10, 'travel_seconds': 8}
        self.assertIsNone(review.add(row)); self.assertIsNone(review.add(row))
        result = review.add(row)
        self.assertEqual((result['sample_windows'], result['confirmed_cells'], result['seconds_per_cell']), (3,3,10))
        self.assertFalse(result['automatic_parameter_changes'])
        self.assertEqual(len(result['findings']),2)
        for _ in range(30):review.add(row)
        self.assertEqual(len(review.records),12)

    def test_unknown_or_inconsistent_windows_are_not_diagnostic_progress(self):
        review = WindowEfficiency()
        row = {'complete': True, 'pending': None, 'physical_positions': [[1,64,1]],
               'elapsed_seconds': 10, 'travel_seconds': 8}
        for change in ({'complete': False}, {'pending': 'professional_print'}, {'physical_positions': []},
                       {'elapsed_seconds': -1}, {'travel_seconds': 11}):
            self.assertIsNone(review.add({**row, **change}))
        self.assertEqual(review.completed,0)


if __name__ == '__main__': unittest.main()
