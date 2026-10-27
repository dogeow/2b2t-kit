import unittest
from unittest.mock import patch
from village_supply_preflight import prepare_chop_inventory


def state(empty):
    return {'inventory': [{'slot': i, 'count': 0 if i < empty else 1} for i in range(36)]}


class SupplyPreflightTests(unittest.TestCase):
    def test_enough_room_never_clicks(self):
        with patch('material_stack_consolidation.prepare_fetch') as merge:
            self.assertIsNone(prepare_chop_inventory(object(), lambda: state(3)))
            merge.assert_not_called()

    def test_fragmentation_uses_existing_merge_then_rechecks(self):
        frames = iter([state(2), state(4)])
        with patch('material_stack_consolidation.prepare_fetch', return_value={'free_slots': 4}) as merge:
            self.assertEqual(prepare_chop_inventory(object(), lambda: next(frames)), {'free_slots': 4})
            merge.assert_called_once()

    def test_insufficient_space_still_blocks(self):
        with patch('material_stack_consolidation.prepare_fetch', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'three empty'):
                prepare_chop_inventory(object(), lambda: state(2))

    def test_partial_inventory_cannot_authorize_harvest(self):
        with patch('material_stack_consolidation.prepare_fetch') as merge:
            with self.assertRaisesRegex(RuntimeError, 'Complete main'):
                prepare_chop_inventory(object(), lambda: {'inventory': []})
            merge.assert_not_called()


if __name__ == '__main__':
    unittest.main()
