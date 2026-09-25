import unittest

from approved_supply import fetch_exact, inventory_count, snapshot_sources


class FakeClient:
    def __init__(self):
        self.held = 0
        self.calls = []

    def status(self):
        return {'inventory': [{'slot': 4, 'item': 'minecraft:sand',
                               'count': self.held}]}

    def fetch(self, pos, materials):
        self.calls.append((pos, materials))
        self.held += 28 if pos[0] == 1 else 4
        return {'phase': 'waiting',
                'shortfall': {'sand': max(0, 32 - self.held)}}


class Tests(unittest.TestCase):
    def test_orders_only_approved_recorded_sources(self):
        config = {
            'projectionSupplySources': [
                {'server': 'simpcraft.com', 'dimension': 'minecraft:overworld',
                 'x': 1, 'y': 64, 'z': 2}],
            'storageSnapshots': [
                {'x': 1, 'y': 64, 'z': 2, 'lastSeenEpochMillis': 10,
                 'items': [{'id': 'minecraft:sand', 'count': 28}]},
                {'x': 1, 'y': 64, 'z': 2, 'lastSeenEpochMillis': 5,
                 'items': [{'id': 'minecraft:sand', 'count': 64}]},
                {'x': 9, 'y': 64, 'z': 2, 'lastSeenEpochMillis': 20,
                 'items': [{'id': 'minecraft:sand', 'count': 64}]}]}
        self.assertEqual([[1, 64, 2]], snapshot_sources(
            config, 'minecraft:sand', 'simpcraft.com',
            'minecraft:overworld', lambda pos: True))

    def test_partial_source_continues_without_repeating_transfer(self):
        client = FakeClient()
        receipts = fetch_exact(client, 'minecraft:sand', 32,
                               [[1, 64, 2], [3, 64, 2]])
        self.assertEqual(32, inventory_count(client.status(), 'minecraft:sand'))
        self.assertEqual(2, len(receipts))
        self.assertEqual(2, len(client.calls))


if __name__ == '__main__':
    unittest.main()
