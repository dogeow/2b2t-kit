import unittest
from placement_item_clearance import safely_below_top_trapdoor as clear
class ItemClearanceTest(unittest.TestCase):
 def fixture(self):return dict(type='minecraft:item',bounds={'min':[0,65.4,0],'max':[.25,65.67,.25]})
 def call(self,e,state='Block{minecraft:oak_trapdoor}[half=top,open=false,waterlogged=false]'):return clear(e,[0,65,0],'minecraft:oak_trapdoor',state)
 def test_item_below_actual_top_plane_is_kept(self):self.assertTrue(self.call(self.fixture()))
 def test_villager_or_item_intersecting_top_plane_is_never_ignored(self):
  e=self.fixture();e['type']='minecraft:villager';self.assertFalse(self.call(e));e=self.fixture();e['bounds']['max'][1]=65.85;self.assertFalse(self.call(e))
 def test_open_bottom_or_different_block_does_not_use_exception(self):
  for s in['Block{minecraft:oak_trapdoor}[half=bottom,open=false,waterlogged=false]','Block{minecraft:oak_trapdoor}[half=top,open=true,waterlogged=false]','Block{minecraft:cobblestone}']:self.assertFalse(self.call(self.fixture(),s))
 def test_nonfinite_bounds_fail(self):e=self.fixture();e['bounds']['max'][1]=float('nan');self.assertFalse(self.call(e))
