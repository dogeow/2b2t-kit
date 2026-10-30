import unittest
from material_jobs.local_air_path import plan
from material_jobs.protocol import JobBlocked
class OpenGateTest(unittest.TestCase):
    def gate(self,opened):return {'pos':[1,1,1],'state':'Block{minecraft:spruce_fence_gate}[facing=west,in_wall=false,open='+opened+',powered=false]','solid':False,'fluid':False,'block_entity':False}
    def route(self,row):return plan([row],[.5,2.1,1.5],[2.5,2.1,1.5],[0,1,1],[2,3,1],foot_offset=.1)
    def test_open_gate_does_not_create_a_phantom_collider_above_its_voxel(self):
        row=self.gate('true');self.assertEqual(self.route(row),[[.5,2.1,1.5],[2.5,2.1,1.5]]);self.assertIn('open=true',row['state'])
    def test_closed_gate_still_blocks_its_one_and_half_block_shape(self):
        with self.assertRaises(JobBlocked):self.route(self.gate('false'))
    def test_missing_open_state_is_conservative(self):
        row=self.gate('false');row['state']=row['state'].replace('open=false,','')
        with self.assertRaises(JobBlocked):self.route(row)
    def test_fences_and_walls_remain_tall(self):
        for block in ['minecraft:oak_fence','minecraft:cobblestone_wall']:
            row={'pos':[1,1,1],'state':'Block{'+block+'}','solid':False,'fluid':False,'block_entity':False}
            with self.assertRaises(JobBlocked):self.route(row)
if __name__=='__main__':unittest.main()
