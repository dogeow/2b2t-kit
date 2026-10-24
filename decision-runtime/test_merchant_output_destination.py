from copy import deepcopy
import unittest
from merchant_output_destination import choose


class DestinationTests(unittest.TestCase):
    def fixture(self):
        rows=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1}for i in range(6)]
        rows[3]={'slot':3,'item':'minecraft:emerald','count':23,'max_stack':64}
        offer={'cost_a':{'item':'minecraft:iron_ingot','count':4},'cost_b':{'item':'minecraft:air','count':0},
               'result':{'item':'minecraft:emerald','count':1,'max_stack':64,'stack_data':{'id':'minecraft:emerald','count':1}}}
        return {'slots':rows},offer
    def test_plain_received_emerald_quote_uses_existing_capacity(self):
        menu,offer=self.fixture();self.assertEqual(choose(menu,offer)['slot'],3)
    def test_unknown_or_custom_components_and_full_stack_use_empty_slot(self):
        for change in ('no_data','custom','extra','full','same_cost'):
            menu,offer=deepcopy(self.fixture())
            if change=='no_data':del offer['result']['stack_data']
            elif change=='custom':offer['result']['stack_data']['components']={'minecraft:custom_name':'custom'}
            elif change=='extra':menu['slots'][3]['custom_name']='custom'
            elif change=='full':menu['slots'][3]['count']=64
            elif change=='same_cost':offer['cost_a']['item']='minecraft:emerald'
            with self.subTest(change=change):self.assertEqual(choose(menu,offer)['slot'],4)


if __name__=='__main__':unittest.main()
