import unittest

from projection_site import evaluate, survey


class SiteTests(unittest.TestCase):
    def supports(self):
        return [{'pos': [x, 63, z], 'state': 'Block{minecraft:sand}',
                 'solid': True, 'fluid': False, 'block_entity': False}
                for x in range(10, 27) for z in range(20, 31)]

    def test_flat_support_and_clear_tower(self):
        result = evaluate([10, 64, 20], [17, 123, 11], self.supports(), [])
        self.assertTrue(result['clear'])
        self.assertEqual(result['supported'], 187)

    def test_preexisting_block_or_storage_rejects_site(self):
        result = evaluate([10, 64, 20], [17, 123, 11], self.supports(),
                          [{'pos': [16, 140, 25], 'state': 'Block{minecraft:stone}'}])
        self.assertFalse(result['clear'])
        self.assertEqual(len(result['obstructions']), 1)
        supports = self.supports()
        supports[0]['block_entity'] = True
        self.assertFalse(evaluate([10, 64, 20], [17, 123, 11], supports, [])['clear'])

    def test_live_survey_reads_support_and_full_height(self):
        class FakeClient:
            def __init__(self): self.calls = []
            def request(self, op, **params):
                self.calls.append((op, params))
                return {'blocks': supports if len(self.calls) == 1 else []}
        supports = self.supports()
        c = FakeClient()
        self.assertTrue(survey(c, [10, 64, 20], [17, 123, 11])['clear'])
        self.assertEqual(c.calls[0][1]['min'], [7, 63, 17])
        self.assertEqual(c.calls[1][1]['max'], [26, 186, 30])


if __name__ == '__main__':
    unittest.main()
