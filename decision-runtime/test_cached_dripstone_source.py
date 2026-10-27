import unittest
from material_jobs.cached_dripstone_source import section_hint, locate


class CachedDripstoneTest(unittest.TestCase):
    def test_padded_signed_longs_decode_real_geometry_without_inventory_credit(self):
        # x=15 is the high nibble of a packed long, so its signed NBT value is negative.
        data=[0]*256; data[0]=-(1<<60)
        section={'Y':2,'block_states':{'palette':[{'Name':'minecraft:air'},
            {'Name':'minecraft:dripstone_block'}]+[{'Name':'minecraft:stone'}]*14,'data':data}}
        hint=section_hint(section,10,20)
        # 0xf is stone, not dripstone. A low-bit dripstone is exposed to surrounding air.
        self.assertEqual(0,hint['cached_dripstone'])
        data[0]+=1; hint=section_hint(section,10,20)
        self.assertEqual(1,hint['cached_dripstone']); self.assertEqual(1,hint['cached_exposed'])
        self.assertEqual([168,40,328],hint['target_hint'])
        self.assertFalse(hint['live_source_verified']); self.assertEqual(0,hint['inventory_credit'])

    def test_solid_palette_is_not_an_exposed_cave(self):
        hint=section_hint({'Y':1,'block_states':{'palette':[{'Name':'minecraft:dripstone_block'}]}},0,0)
        self.assertEqual(4096,hint['cached_dripstone']); self.assertEqual(0,hint['cached_exposed'])

    def test_truncated_or_out_of_palette_data_is_rejected(self):
        palette=[{'Name':'minecraft:air'},{'Name':'minecraft:dripstone_block'}]
        for data in ([0], [15]+[0]*255):
            self.assertIsNone(section_hint({'Y':2,'block_states':{'palette':palette,'data':data}},0,0))

    def test_cache_search_is_bounded_before_any_files_are_read(self):
        for centers,radius in (([[0,0]]*5,4),([[0,0]],5),([[0.5,0]],1)):
            with self.assertRaises(ValueError): locate('/unused','simpcraft.com','minecraft:overworld',centers,radius=radius)


if __name__=='__main__': unittest.main()
