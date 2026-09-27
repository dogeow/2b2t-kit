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
        for row in config['storageSnapshots']:
            row.update(server='simpcraft.com:25565',dimension='minecraft:overworld',worldId='',status='active')
        self.assertEqual([[1, 64, 2]], snapshot_sources(
            config, 'minecraft:sand', 'simpcraft.com',
            'minecraft:overworld', lambda pos: True))

    def test_stale_legacy_and_foreign_records_never_supply_current_world(self):
        source={'server':'simpcraft.com','dimension':'minecraft:overworld','x':1,'y':64,'z':2}
        row={**source,'worldId':'','status':'active','items':[{'id':'minecraft:iron_ingot','count':64}]}
        for changes in ({'status':'missing'},{'status':'recheck'},{'status':'unknown_scope'},
                        {'server':''},{'server':'other.example'},{'dimension':'minecraft:the_nether'},{'worldId':'other'}):
            with self.subTest(changes=changes):
                config={'projectionSupplySources':[source],'storageSnapshots':[{**row,**changes}]}
                self.assertEqual([],snapshot_sources(config,'minecraft:iron_ingot','simpcraft.com','minecraft:overworld',lambda p:True))

    def test_singleplayer_save_identity_is_required_for_both_approval_and_record(self):
        source={'server':'singleplayer','worldId':'/save/a','dimension':'minecraft:overworld','x':1,'y':64,'z':2}
        config={'projectionSupplySources':[source],'storageSnapshots':[{**source,'status':'active','items':[{'id':'minecraft:sand','count':16}]}]}
        self.assertEqual([],snapshot_sources(config,'minecraft:sand','singleplayer','minecraft:overworld',lambda p:True))
        self.assertEqual([],snapshot_sources(config,'minecraft:sand','singleplayer','minecraft:overworld',lambda p:True,world_id='/save/b'))
        self.assertEqual([[1,64,2]],snapshot_sources(config,'minecraft:sand','singleplayer','minecraft:overworld',lambda p:True,world_id='/save/a'))

    def test_partial_source_continues_without_repeating_transfer(self):
        client = FakeClient()
        receipts = fetch_exact(client, 'minecraft:sand', 32,
                               [[1, 64, 2], [3, 64, 2]])
        self.assertEqual(32, inventory_count(client.status(), 'minecraft:sand'))
        self.assertEqual(2, len(receipts))
        self.assertEqual(2, len(client.calls))


if __name__ == '__main__':
    unittest.main()
