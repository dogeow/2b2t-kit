import unittest
from container_hand import select_container_hand


class Client:
    def __init__(self, hand, inventory):
        self.state = {'hand': {'item': hand}, 'inventory': inventory}; self.calls = []
    def status(self): return self.state
    def checked(self, op, **params):
        self.calls.append((op, params)); self.state['hand']['item'] = params['item']


class ContainerHandTest(unittest.TestCase):
    def test_existing_sword_is_kept_without_selection(self):
        c = Client('minecraft:netherite_sword', [])
        self.assertEqual('minecraft:netherite_sword', select_container_hand(c)); self.assertEqual([], c.calls)
    def test_actual_netherite_sword_replaces_missing_diamond_assumption(self):
        c = Client('minecraft:bow', [{'slot': 0, 'item': 'minecraft:netherite_sword', 'count': 1}])
        self.assertEqual('minecraft:netherite_sword', select_container_hand(c))
        self.assertEqual([('select_item', {'item': 'minecraft:netherite_sword'})], c.calls)
    def test_no_sword_or_equipment_only_sword_sends_no_action(self):
        c = Client('minecraft:bow', [{'slot': 40, 'item': 'minecraft:diamond_sword', 'count': 1}])
        with self.assertRaisesRegex(RuntimeError, 'No carried sword'): select_container_hand(c)
        self.assertEqual([], c.calls)
    def test_unconfirmed_selection_is_not_retried(self):
        c = Client('minecraft:bow', [{'slot': 0, 'item': 'minecraft:netherite_sword', 'count': 1}])
        c.checked = lambda op, **p: c.calls.append((op, p))
        with self.assertRaisesRegex(RuntimeError, 'not confirmed'): select_container_hand(c)
        self.assertEqual(1, len(c.calls))


if __name__ == '__main__': unittest.main()
