import unittest

from material_stage_gate import require_gravel_complete


class Tests(unittest.TestCase):
    def test_requires_fresh_full_chest_audit_in_same_world(self):
        chests = [[1, 64, 2], [3, 64, 2]]
        audit = {'server': 'simpcraft.com:25565',
                 'dimension': 'minecraft:overworld',
                 'world_session': 'session-a', 'at_ms': 1000,
                 'carried_gravel': 4,
                 'chests': [
                     {'pos': chests[0], 'items': {'minecraft:gravel': 700}},
                     {'pos': chests[1], 'items': {'minecraft:gravel': 132}}]}
        state = {'server': audit['server'], 'dimension': audit['dimension'],
                 'world_session': audit['world_session'], 'time': 1500}
        self.assertEqual(836, require_gravel_complete(audit, state, 836, chests)['total_at_audit'])
        with self.assertRaisesRegex(RuntimeError, 'another world'):
            require_gravel_complete(audit, {**state, 'world_session': 'session-b'}, 836, chests)
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            require_gravel_complete(audit, {**state, 'time': 1000 + 16 * 60 * 1000}, 836, chests)
        with self.assertRaisesRegex(RuntimeError, 'Not every'):
            require_gravel_complete({**audit, 'chests': audit['chests'][:1]}, state, 836, chests)
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            require_gravel_complete({**audit, 'carried_gravel': 0}, state, 836, chests)


if __name__ == '__main__':
    unittest.main()
