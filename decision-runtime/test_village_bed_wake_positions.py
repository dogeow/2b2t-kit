import unittest
from village_bed_wake_positions import possible_wake_cells


class WakeCandidatesTests(unittest.TestCase):
    def test_wn02_old_empty_rear_remains_a_wake_candidate_beyond_foot_wall(self):
        cells = possible_wake_cells([761002, 64, 797808], [761002, 64, 797807])
        self.assertIn((761002, 64, 797806), cells)
        self.assertIn((761002, 64, 797808), cells)
        self.assertIn((761002, 64, 797809), cells)
        self.assertNotIn((761002, 64, 797810), cells)
        self.assertEqual(12, len(cells))

    def test_all_bed_directions_include_both_parts_and_far_foot_end(self):
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            head = [10, 65, 20]
            foot = [10-dx, 65, 20-dz]
            with self.subTest(dx=dx, dz=dz):
                cells = possible_wake_cells(head, foot)
                self.assertEqual(12, len(cells))
                self.assertIn(tuple(head), cells)
                self.assertIn(tuple(foot), cells)
                self.assertIn((10-2*dx, 65, 20-2*dz), cells)

    def test_non_bed_coordinates_are_rejected(self):
        for head in ([0, 64, 0], [0, 65, 1], [1, 64, 1], [0, 64, 2], [True, 64, 1]):
            with self.subTest(head=head), self.assertRaises(ValueError):
                possible_wake_cells(head, [0, 64, 0])


if __name__ == '__main__':
    unittest.main()
