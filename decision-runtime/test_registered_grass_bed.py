import json,unittest
from unittest.mock import patch
import test_direct_clay_refill as fixtures
from material_jobs import registered_grass_bed as m
from material_jobs.protocol import JobBlocked


class Tests(unittest.TestCase):
    def setUp(self):
        fixtures.Tests.setUp(self)
        self.c.blocks[(100,64,100)]='Block{minecraft:grass_block}[snowy=false]'
        self.c.root=self.out
        request=self.c.request
        def confirmed(op,**kw):
            reply=request(op,**kw)
            if op=='mine_block':reply.update(id=self.c.last,world_session='world',mining_target=kw['pos'],server_confirmed=True,
                native_sequence=4,server_ack_sequence=4,confirmation_scope='single_target_server_block_update_and_native_sequence_ack')
            return reply
        self.c.request=confirmed
        p=patch.object(m,'approach_faces',return_value='up');p.start();self.addCleanup(p.stop)
        original=m.refill
        p=patch.object(m,'refill',side_effect=lambda *a,**kw:original(*a,**kw,water_result=self.water));p.start();self.addCleanup(p.stop)
    def run_bed(self):return m.run(self.c,[100,64,100],self.profile,self.out/'grass-work',lambda:None)
    def test_registered_existing_grass_is_reused_with_zero_net_carried_dirt_and_retained_tip(self):
        result=self.run_bed()
        self.assertTrue(result['complete']);self.assertEqual(0,result['dirt_net_consumed'])
        self.assertEqual(2,self.c.count('minecraft:dirt'));self.assertEqual('Block{minecraft:mud}',self.c.blocks[(100,64,100)])
        self.assertIn((100,62,100),self.c.blocks)
        self.assertEqual(1,sum(op=='mine_block'for op,_ in self.c.calls))
        self.assertEqual(['minecraft:dirt','minecraft:potion'],[q['expected_hand']for op,q in self.c.calls if op=='interact'])
    def test_existing_grass_supplies_its_own_dirt_without_carried_soil(self):
        self.c.add('minecraft:dirt',-2);self.assertTrue(self.run_bed()['complete']);self.assertEqual(0,self.c.count('minecraft:dirt'))
    def test_unknown_original_mining_is_never_replayed_or_followed_by_refill(self):
        request=self.c.request
        def unknown(op,**kw):
            reply=request(op,**kw)
            if op=='mine_block':reply['server_ack_sequence']=3
            return reply
        self.c.request=unknown
        with self.assertRaises(JobBlocked):self.run_bed()
        self.assertFalse(any(op=='interact'for op,_ in self.c.calls))
        self.assertEqual('mine_registered_grass',json.loads((self.out/'grass-work/grass-bed.json').read_text())['pending'])
        with self.assertRaisesRegex(JobBlocked,'no replay'):self.run_bed()
        self.assertEqual(1,sum(op=='mine_block'for op,_ in self.c.calls))
    def test_unregistered_grass_and_missing_real_tip_have_no_mining_authority(self):
        self.profile['clay_conversion_farm']['authorized']=False
        with self.assertRaises(JobBlocked):self.run_bed()
        self.assertFalse(self.c.calls)
        self.profile['clay_conversion_farm']['authorized']=True;self.c.blocks.pop((100,62,100))
        with self.assertRaises(JobBlocked):self.run_bed()
        self.assertFalse(any(op=='mine_block'for op,_ in self.c.calls))

if __name__=='__main__':unittest.main()
