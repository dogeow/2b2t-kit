import unittest
from packed_supplies import contents,choose_box
class PackedTest(unittest.TestCase):
 def test_duplicate_stacks_are_summed_not_overwritten(self):
  self.assertEqual(contents([{'item':'minecraft:paper','count':64},{'item':'minecraft:paper','count':16}]),{'minecraft:paper':80})
 def test_only_observed_useful_box_is_selected_and_existing_stock_is_subtracted(self):
  rows=[{'slot':0,'item':'minecraft:shulker_box','count':1,'contains':[{'item':'minecraft:paper','count':64}]},{'slot':3,'item':'minecraft:shulker_box','count':1,'contains':[{'item':'minecraft:diamond','count':32}]}]
  choice=choose_box(rows,{'minecraft:paper':30,'minecraft:diamond':2},{'minecraft:paper':30})
  self.assertEqual(choice,(2,3,{'minecraft:diamond':2}))
 def test_empty_or_unobserved_box_is_not_guessed(self):
  self.assertIsNone(choose_box([{'slot':1,'item':'minecraft:shulker_box','count':1}],{'minecraft:diamond':2},{}))
if __name__=='__main__':unittest.main()
