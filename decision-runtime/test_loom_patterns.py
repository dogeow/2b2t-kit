import unittest
from loom_patterns import exact_banner


class BannerIdentityTest(unittest.TestCase):
    def test_equal_item_counts_cannot_hide_wrong_pattern_order_or_color(self):
        wanted=[{'pattern':'minecraft:gradient','color':'light_blue'},{'pattern':'minecraft:border','color':'black'}]
        row={'item':'minecraft:light_gray_banner','count':1,'banner_patterns':wanted}
        self.assertTrue(exact_banner(row,'minecraft:light_gray_banner',wanted))
        self.assertFalse(exact_banner({**row,'banner_patterns':list(reversed(wanted))},'minecraft:light_gray_banner',wanted))
        self.assertFalse(exact_banner({**row,'banner_patterns':[wanted[0],{**wanted[1],'color':'light_gray'}]},'minecraft:light_gray_banner',wanted))
        self.assertFalse(exact_banner({**row,'count':2},'minecraft:light_gray_banner',wanted))
