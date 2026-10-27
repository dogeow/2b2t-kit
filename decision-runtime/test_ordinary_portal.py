import unittest
from material_jobs.ordinary_portal import frame,empty_grass_plot,outside_regions


class FullFrameTest(unittest.TestCase):
    def test_every_non_base_block_has_a_previously_placed_ordinary_anchor(self):
        positions=frame([0,64,0]);self.assertEqual(14,len(set(map(tuple,positions))));seen=set()
        for x,y,z in positions:
            if y!=64:self.assertTrue((x,y-1,z)in seen or(x-1,y,z)in seen)
            seen.add((x,y,z))
    def test_real_water_container_or_existing_structure_prevents_plot_use(self):
        rows=[{'pos':[x,63,0],'state':'Block{minecraft:grass_block}[snowy=false]','solid':True,'fluid':False,'block_entity':False}for x in range(4)]
        self.assertTrue(empty_grass_plot(rows,[0,64,0]))
        self.assertTrue(empty_grass_plot({tuple(r['pos']):r for r in rows},[0,64,0]))
        for extra in ({'pos':[1,65,0],'state':'Block{minecraft:water}[level=0]','fluid':True},
                      {'pos':[2,64,1],'state':'Block{minecraft:chest}','block_entity':True}):
            self.assertFalse(empty_grass_plot(rows+[extra],[0,64,0]))
            self.assertFalse(empty_grass_plot({tuple(r['pos']):r for r in rows+[extra]},[0,64,0]))
    def test_access_grass_is_preserved_but_frame_plants_are_not_replaced(self):
        rows=[{'pos':[x,63,0],'state':'Block{minecraft:grass_block}[snowy=false]','solid':True,'fluid':False,'block_entity':False}for x in range(4)]
        grass={'pos':[1,64,1],'state':'Block{minecraft:short_grass}','passable':True,'fluid':False,'block_entity':False}
        self.assertTrue(empty_grass_plot(rows+[grass],[0,64,0]))
        self.assertFalse(empty_grass_plot(rows+[{**grass,'pos':[1,64,0]}],[0,64,0]))
    def test_existing_protected_boundary_and_access_margin_are_never_widened(self):
        regions=[{'min':[760850,40,797600],'max':[761200,200,798020]}]
        self.assertFalse(outside_regions([761035,64,797870],regions))
        self.assertFalse(outside_regions([761203,64,797870],regions))
        self.assertTrue(outside_regions([761204,64,797870],regions))
        self.assertEqual(761200,regions[0]['max'][0])
