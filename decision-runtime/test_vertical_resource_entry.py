import unittest
from material_jobs.vertical_resource_entry import plan

def row(p,name,**kw):
    return {'pos':p,'state':'Block{minecraft:'+name+'}','fluid':False,'block_entity':False,'solid':True,**kw}

class VerticalResourceEntryTest(unittest.TestCase):
    def test_bottom_air_and_top_down_natural_order_required(self):
        rows=[row([0,8,0],'stone'),row([0,7,0],'dirt')]
        self.assertEqual([8,7],[r['pos'][1]for r in plan(rows,0,0,4,8)])
        with self.assertRaises(RuntimeError):plan(rows+[row([0,4,0],'stone')],0,0,4,8)
    def test_fluids_spikes_falling_blocks_structures_and_torch_supports_preserved(self):
        for name,kw in [('water',{'fluid':True}),('pointed_dripstone',{}),('gravel',{}),('chest',{'block_entity':True})]:
            with self.assertRaises(RuntimeError):plan([row([1,7,0],name,**kw)],0,0,4,8)
        with self.assertRaises(RuntimeError):plan([row([0,7,0],'stone_bricks')],0,0,4,8)
        torch=row([0,8,0],'torch',solid=False,passable=True)
        with self.assertRaises(RuntimeError):plan([row([0,7,0],'stone'),torch],0,0,4,8)
    def test_column_height_is_bounded(self):
        with self.assertRaises(ValueError):plan([],0,0,4,69)
    def test_stale_surface_height_refused_before_any_descent(self):
        for y in (9,10):
            with self.assertRaises(RuntimeError):plan([row([0,8,0],'stone'),row([0,y,0],'stone')],0,0,4,8)
        with self.assertRaises(RuntimeError):plan([row([0,8,0],'dirt_path')],0,0,4,8)

if __name__=='__main__':unittest.main()
