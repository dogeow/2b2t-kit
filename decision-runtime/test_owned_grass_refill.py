import copy
import json
import unittest
from pathlib import Path
import test_direct_clay_refill as fixtures
from material_jobs.owned_grass_refill import finish
from material_jobs.protocol import JobBlocked


class Tests(unittest.TestCase):
    def setUp(self):
        fixtures.Tests.setUp(self)
        self.c.add('minecraft:dirt',-1);self.c.blocks[(100,64,100)]='Block{minecraft:grass_block}[snowy=false]'
        self.old=self.out/'original-grass.json'
        self.old.write_text(json.dumps({'world_session':'world','pos':[100,64,100],'water_request':'bottle-original',
            'pending':{'kind':'place_dirt','before':{'minecraft:dirt':2},'request_id':'old-use'},'receipts':[],
            'water_slot_after_dirt_selection':self.water['derived_water_slot']['slot'],'retained_water':self.water}))
        request=self.c.request
        def confirmed(op,**kw):
            result=request(op,**kw)
            if op=='mine_block':result.update(id=self.c.last,world_session='world',mining_target=kw['pos'],server_confirmed=True,
                native_sequence=3,server_ack_sequence=3,confirmation_scope='single_target_server_block_update_and_native_sequence_ack')
            return result
        self.c.request=confirmed
    def run_recovery(self):return finish(self.c,[100,64,100],self.profile,self.old,self.out/'recovery',lambda:None)
    def test_only_placed_grass_is_recovered_and_real_dirt_is_used_once_net(self):
        original=self.old.read_bytes();result=self.run_recovery()
        self.assertTrue(result['complete']);self.assertEqual(1,self.c.count('minecraft:dirt'))
        self.assertEqual(0,self.c.count('minecraft:potion'));self.assertEqual(1,self.c.count('minecraft:glass_bottle'))
        self.assertEqual('Block{minecraft:mud}',self.c.blocks[(100,64,100)]);self.assertEqual(original,self.old.read_bytes())
        self.assertEqual(1,sum(op=='mine_block'for op,_ in self.c.calls))
    def test_unproved_old_dirt_consumption_preserves_current_grass(self):
        self.c.add('minecraft:dirt',1)
        with self.assertRaises(JobBlocked):self.run_recovery()
        self.assertFalse(any(op in('mine_block','interact')for op,_ in self.c.calls))
    def test_unknown_mining_keeps_intent_and_never_places_again(self):
        request=self.c.request
        def unknown(op,**kw):
            result=request(op,**kw)
            if op=='mine_block':result['server_ack_sequence']=2
            return result
        self.c.request=unknown
        with self.assertRaises(JobBlocked):self.run_recovery()
        self.assertFalse(any(op=='interact'for op,_ in self.c.calls))
        d=json.loads((self.out/'recovery/direct-clay-refill.json').read_text());self.assertEqual('recover_owned_grass',d['pending']['kind'])
    def test_direct_refill_recovers_natural_grass_without_a_new_controller(self):
        from material_jobs.direct_clay_refill import refill
        self.c.add('minecraft:dirt',1);self.c.blocks.pop((100,64,100));request=self.c.request;first=[True]
        def growing(op,**kw):
            result=request(op,**kw)
            if op=='interact'and kw.get('expected_hand')=='minecraft:dirt'and first[0]:
                first[0]=False;self.c.blocks[(100,64,100)]='Block{minecraft:grass_block}[snowy=false]'
            return result
        self.c.request=growing
        result=refill(self.c,[100,64,100],self.profile,self.out/'normal-direct',lambda:None,water_result=self.water)
        self.assertTrue(result['complete']);self.assertTrue(result['grass_recovered'])
        self.assertEqual(1,self.c.count('minecraft:dirt'));self.assertEqual('Block{minecraft:mud}',self.c.blocks[(100,64,100)])
