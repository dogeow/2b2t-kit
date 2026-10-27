import unittest
from stonecutter_batches import exact_yield


class CuttingBalanceTest(unittest.TestCase):
    def test_slab_yield_requires_two_outputs_for_each_real_consumed_block(self):
        before={'minecraft:quartz_block':33,'minecraft:quartz_slab':0}
        after={'minecraft:quartz_block':11,'minecraft:quartz_slab':44}
        self.assertTrue(exact_yield(before,after,'minecraft:quartz_block',22,'minecraft:quartz_slab',2))
        self.assertFalse(exact_yield(before,{**after,'minecraft:quartz_slab':43},'minecraft:quartz_block',22,'minecraft:quartz_slab',2))
        self.assertFalse(exact_yield(before,{**after,'minecraft:quartz_block':12},'minecraft:quartz_block',22,'minecraft:quartz_slab',2))
