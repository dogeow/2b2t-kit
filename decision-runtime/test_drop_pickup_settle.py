import unittest
from unittest.mock import patch
from drop_pickup_settle import settle
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

    def fake(self,counts,entities):
        drop={'uuid':'drop','pos':[0,64,0],'stack':{'item':'minecraft:furnace','count':1}}
        class Client:
            def __init__(self):self.index=0;self.requests=[]
            def status(self):
                i=min(self.index,len(counts)-1);self.index+=1
                return {'inventory':[{'slot':0,'item':'minecraft:furnace','count':counts[i]}],'entities':[drop]if entities[i]else[]}
            def request(self,op,**args):self.requests.append(op);raise AssertionError('Completed/uncertain pickup must not send another action')
        return Client(),drop
    def test_already_collected_exact_drop_needs_no_movement_or_second_collect(self):
        c,drop=self.fake([1],[False]);self.assertTrue(settle(c,drop,0));self.assertEqual([],c.requests)
    def test_removed_entity_waits_for_later_inventory_packet_without_moving(self):
        c,drop=self.fake([0,0,1],[False,False,False])
        with patch('drop_pickup_settle.time.sleep'):self.assertTrue(settle(c,drop,0))
        self.assertEqual(3,c.index);self.assertEqual([],c.requests)
    def test_inventory_packet_waits_for_entity_removal_without_second_input(self):
        c,drop=self.fake([1,1],[True,False])
        with patch('drop_pickup_settle.time.sleep'):self.assertTrue(settle(c,drop,0))
        self.assertEqual([],c.requests)
    def test_absence_without_quantity_proof_and_extra_quantity_are_not_success(self):
        c,drop=self.fake([0],[False])
        with patch('drop_pickup_settle.time.monotonic',side_effect=range(10)),patch('drop_pickup_settle.time.sleep'):self.assertFalse(settle(c,drop,0))
        self.assertEqual([],c.requests)
        c,drop=self.fake([2],[False]);self.assertFalse(settle(c,drop,0));self.assertEqual([],c.requests)

if __name__=='__main__':unittest.main()
