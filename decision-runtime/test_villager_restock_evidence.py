import copy
import unittest
from villager_restock_evidence import compare


class Tests(unittest.TestCase):
    def fixture(self):
        offer = {'index': 0, 'uses': 1, 'max_uses': 16,
                 'cost_a': {'item': 'minecraft:coal', 'count': 15, 'stack_data': {'id': 'minecraft:coal', 'count': 15}},
                 'cost_b': {'item': 'minecraft:air', 'count': 0},
                 'result': {'item': 'minecraft:emerald', 'count': 1}}
        before = {'protocol': 1, 'owned': True, 'villager_uuid': 'v', 'trader_xp': 1,
                  'observation_scope': 'current_server_received_merchant_menu_not_trade_completion', 'offers': [offer]}
        after = copy.deepcopy(before); after['offers'][0]['uses'] = 0
        return before, after

    def test_real_used_offer_decrease(self):
        before, after = self.fixture()
        self.assertEqual((1, 0), tuple(compare(before, after, uuid='v')[0][k] for k in ('uses_before', 'uses_after')))

    def test_discount_and_added_trade_do_not_hide_existing_offer(self):
        before, after = self.fixture(); after['offers'][0]['cost_a'].update(count=14, stack_data={'id': 'minecraft:coal', 'count': 14})
        after['trader_xp'] = 12; extra = copy.deepcopy(after['offers'][0]); extra['result']['item'] = 'minecraft:bread'; after['offers'].append(extra)
        self.assertEqual(1, len(compare(before, after, uuid='v')))

    def test_new_zero_use_offer_is_not_restock(self):
        before, after = self.fixture(); before['offers'][0]['uses'] = 0
        self.assertEqual([], compare(before, after, uuid='v'))

    def test_replaced_or_ambiguous_offer_is_not_restock(self):
        for mode in ('result', 'limit', 'duplicate'):
            before, after = self.fixture()
            if mode == 'result': after['offers'][0]['result']['item'] = 'minecraft:bread'
            elif mode == 'limit': after['offers'][0]['max_uses'] = 12
            else: after['offers'].append(copy.deepcopy(after['offers'][0]))
            with self.subTest(mode=mode): self.assertEqual([], compare(before, after, uuid='v'))

    def test_wrong_resident_or_unlocked_quote_rejected(self):
        for mode in ('uuid', 'xp', 'scope'):
            before, after = self.fixture()
            if mode == 'uuid': after['villager_uuid'] = 'other'
            elif mode == 'xp': after['trader_xp'] = 0
            else: after['observation_scope'] = 'client_prediction'
            with self.subTest(mode=mode), self.assertRaises(ValueError): compare(before, after, uuid='v')


if __name__ == '__main__': unittest.main()
