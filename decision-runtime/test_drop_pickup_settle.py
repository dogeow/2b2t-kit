import unittest
from drop_pickup_settle import poses

class Tests(unittest.TestCase):
    def terrain(self):
        return [{'pos':[x,63,z],'solid':True,'passable':False,'fluid':False,'block_entity':False}
                for x in range(24,30)for z in range(858,864)] + \
               [{'pos':[27,64,z],'solid':True,'passable':False,'fluid':False,'block_entity':False}for z in range(858,864)]
    def test_real_one_block_ledge_has_a_close_lower_supported_pose(self):
        result=poses([27.5,65,859.5],[26.875,64,861.414],self.terrain())
        self.assertTrue(result);self.assertEqual([26.5,64,861.5],result[0])
    def test_missing_ground_fluid_and_container_support_are_rejected(self):
        for rows in ([],[dict(r,fluid=True)for r in self.terrain()],
                     [dict(r,block_entity=True)for r in self.terrain()]):
            self.assertFalse(poses([27.5,65,859.5],[26.875,64,861.414],rows))
    def test_no_long_descent_or_far_adjustment_is_proposed(self):
        self.assertFalse(poses([27.5,70,859.5],[26.875,64,861.414],self.terrain()))

if __name__=='__main__':unittest.main()
