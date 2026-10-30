import math,unittest
from material_jobs.navigation import _body_sweep
from material_jobs.local_air_path import plan
class ContactTest(unittest.TestCase):
    def test_floor_contact_and_actual_immersion_have_distinct_sweeps(self):
        self.assertEqual(_body_sweep([1.5,math.nextafter(63,-math.inf),1.5],[1.5,66.1,1.5])[0][1],63)
        self.assertEqual(_body_sweep([1.5,62.99999,1.5],[1.5,66.1,1.5])[0][1],62)
    def test_standing_above_waterlogged_top_slab_does_not_change_its_world_row(self):
        slab={'pos':[1,62,1],'state':'Block{minecraft:cobblestone_slab}[type=top,waterlogged=true]','solid':False,'fluid':True,'block_entity':False}
        start=[1.5,math.nextafter(63,-math.inf),1.5]
        route=plan([slab],start,[1.5,66.1,1.5],[0,60,0],[2,70,2],foot_offset=.1)
        self.assertEqual(route[0],[1.5,63.1,1.5]);self.assertTrue(slab['fluid'])
        contact=[1.5,math.nextafter(63,-math.inf),2.5];horizontal=plan([slab],start,contact,[0,60,0],[2,70,3],foot_offset=.1);self.assertEqual(horizontal[-1],[1.5,63.1,2.5])
        with self.assertRaises(Exception):plan([slab],[1.5,62.99999,1.5],[1.5,66.1,1.5],[0,60,0],[2,70,2],foot_offset=.1)
if __name__=='__main__':unittest.main()
