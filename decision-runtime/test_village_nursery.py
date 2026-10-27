import unittest
from village_nursery import preflight,planting_order

class VillageNurseryTests(unittest.TestCase):
    def test_plant_far_roots_before_near_seedlings_from_east_and_north(self):
        roots=[[14,63,798],[14,63,799],[15,63,798],[15,63,799]]
        self.assertEqual(planting_order(roots,[17.5,63,798.5]),
                         [[14,63,799],[14,63,798],[15,63,799],[15,63,798]])
        self.assertEqual(planting_order(roots,[14.5,63,797.5])[-1],[14,63,798])
        self.assertEqual(roots,[[14,63,798],[14,63,799],[15,63,798],[15,63,799]])
    def test_invalid_or_duplicate_planting_scene_never_orders_inputs(self):
        for roots,position in[([[1,2,3],[1,2,3]],[0,0,0]),([[1,2,3]],[float('nan'),0,0])]:
            with self.assertRaises(ValueError):planting_order(roots,position)
    def fixture(self):
        low=[0,62,0];high=[3,82,3];root=[1,63,1]
        rows=[{'pos':[x,62,z],'state':'Block{minecraft:grass_block}[snowy=false]','solid':True,'fluid':False,'block_entity':False}for x in(1,2)for z in(1,2)]
        return {'world_session':'w','scan_cells_read':336,'scan_total_cells':336,'blocks':rows},root,low,high
    def test_existing_low_fence_is_preserved_but_canopy_construction_or_mixed_trunk_refused(self):
        s,r,l,h=self.fixture();s['blocks'].append({'pos':[0,63,0],'state':'Block{minecraft:oak_fence}','fluid':False,'block_entity':False});preflight(s,r,l,h,'w')
        for y,state in[(65,'Block{minecraft:oak_fence}'),(63,'Block{minecraft:stripped_oak_log}[axis=y]')]:
            s,r,l,h=self.fixture();s['blocks'].append({'pos':[0,y,0],'state':state,'fluid':False,'block_entity':False})
            with self.assertRaises(RuntimeError):preflight(s,r,l,h,'w')
    def test_wrong_world_incomplete_cells_and_nonempty_roots_never_plant(self):
        for change in({'world_session':'other'},{'scan_cells_read':335}):
            s,r,l,h=self.fixture();s.update(change)
            with self.assertRaises(RuntimeError):preflight(s,r,l,h,'w')
        s,r,l,h=self.fixture();s['blocks'].append({'pos':[1,63,1],'state':'Block{minecraft:short_grass}','fluid':False,'block_entity':False})
        with self.assertRaises(RuntimeError):preflight(s,r,l,h,'w')
