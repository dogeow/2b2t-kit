import unittest
from material_jobs.sapling_trip import natural_leaf,harvest_hoe

class SaplingTripTest(unittest.TestCase):
    def test_only_dry_natural_dark_oak_leaves_are_candidates(self):
        row={'state':'Block{minecraft:dark_oak_leaves}[distance=2,persistent=false,waterlogged=false]',
             'fluid':False,'block_entity':False}
        self.assertTrue(natural_leaf(row))
        for change in ({'fluid':True},{'block_entity':True},
                       {'state':row['state'].replace('persistent=false','persistent=true')},
                       {'state':row['state'].replace('dark_oak','oak')}):
            self.assertFalse(natural_leaf({**row,**change}))
    def test_silk_touch_or_exhausted_tools_cannot_be_used_for_sapling_drops(self):
        plain={'item':'minecraft:diamond_hoe','count':1,'durability':100,'slot':17}
        silk={**plain,'slot':2,'enchantments':[{'id':'minecraft:silk_touch','level':1}]}
        self.assertEqual(plain,harvest_hoe({'inventory':[silk,plain]}))
        for rows in ([silk],[{**plain,'durability':32}],[]):
            with self.assertRaises(RuntimeError):harvest_hoe({'inventory':rows})
