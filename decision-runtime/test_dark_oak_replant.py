import unittest
from unittest.mock import patch
from dark_oak_replant import stance, replant, SAPLING


def ground():
    return {(x, 62, z): {'state': 'Block{minecraft:dirt}', 'solid': True, 'fluid': False}
            for x in range(-4, 6) for z in range(-4, 6)}


class Builder:
    def __init__(self):
        self.rows = ground(); self.seeds = 8; self.inputs = []
    def scan(self, low, high):
        return {}, {p: v for p, v in self.rows.items() if all(low[i] <= p[i] <= high[i] for i in range(3))}
    def check(self):
        return {'inventory': [{'slot': 0, 'item': SAPLING, 'count': self.seeds}]}
    def place(self, pos, support, face, **kwargs):
        self.inputs.append(tuple(pos)); self.seeds -= 1
        self.rows[tuple(pos)] = {'state': kwargs['expected']}


class ReplantTests(unittest.TestCase):
    def test_stance_never_overlaps_the_future_trunk(self):
        pose = stance([0, 63, 0], ground())
        self.assertEqual(63.1, pose[1])
        self.assertTrue(pose[0]+.3 <= -1 or pose[0]-.3 >= 3
                        or pose[2]+.3 <= -1 or pose[2]-.3 >= 3)

    def test_closed_or_wet_outside_stances_refuse_without_input(self):
        b = Builder()
        for (x, _, z) in list(b.rows):
            if not (0 <= x <= 1 and 0 <= z <= 1):
                b.rows[x, 63, z] = {'state': 'Block{minecraft:dark_oak_leaves}'}
        with patch('village_air_route.move') as move:
            with self.assertRaisesRegex(RuntimeError, 'outside'):
                replant(b, [0, 63, 0])
        move.assert_not_called(); self.assertEqual([], b.inputs)

    def test_all_four_seeds_are_placed_from_one_outside_pose(self):
        b = Builder()
        with patch('village_air_route.move') as move:
            result = replant(b, [0, 63, 0])
        move.assert_called_once_with(b, result['stance'])
        self.assertEqual(4, b.seeds); self.assertEqual(4, len(b.inputs))
        self.assertEqual('horizontal_clear_ground_before_ascending', result['next_move'])
        with patch('village_air_route.move') as move:
            self.assertTrue(replant(b, [0, 63, 0])['already_renewed'])
        move.assert_not_called(); self.assertEqual(4, len(b.inputs))

    def test_partial_existing_stump_never_gets_overwritten(self):
        b = Builder(); b.rows[0, 63, 0] = {'state': 'Block{minecraft:dark_oak_log}[axis=y]'}
        with self.assertRaisesRegex(RuntimeError, 'not four empty'):
            replant(b, [0, 63, 0])
        self.assertEqual([], b.inputs)


if __name__ == '__main__':
    unittest.main()
