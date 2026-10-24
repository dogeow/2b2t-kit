import unittest
from storage_transfer_source import choose


class SourceTests(unittest.TestCase):
    def test_hopper_trickle_does_not_preempt_a_full_stack(self):
        rows=[{'slot':i,'item':'minecraft:iron_ingot','count':n}for i,n in enumerate([2,64,64,32])]
        self.assertEqual(choose(rows,'minecraft:iron_ingot')['slot'],1)
        self.assertEqual(choose(rows,'minecraft:iron_ingot',deposit=True)['slot'],0)
        self.assertIsNone(choose(rows,'minecraft:diamond'))
    def test_equal_unstackable_items_keep_the_original_order(self):
        rows=[{'slot':i,'item':'minecraft:enchanted_book','count':1}for i in [3,5]]
        self.assertEqual(choose(rows,'minecraft:enchanted_book')['slot'],3)


if __name__=='__main__':unittest.main()
