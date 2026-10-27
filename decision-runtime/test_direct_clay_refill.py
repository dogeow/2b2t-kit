import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_mud_pipeline import Client
from material_jobs.direct_clay_refill import refill
from material_jobs.mud_water_supply import BOTTLE_SCOPE
from material_jobs.protocol import JobBlocked


class Tests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.out=Path(t.name)
        self.c=Client({'minecraft:dirt':2,'minecraft:potion':1});self.c.out=self.out
        self.c.blocks.pop((103,64,100));self.c.blocks[(100,62,100)]='Block{minecraft:pointed_dripstone}[thickness=tip,vertical_direction=down,waterlogged=false]'
        self.profile={'clay_conversion_farm':{'authorized':True,'positions':[[100,64,100]]},'mud_bucket_source':{'pos':[104,63,100]}}
        water=next(copy.deepcopy(r)for r in self.c.rows if r['item']=='minecraft:potion')
        self.water={'phase':'done','derived_water_slot':water,'native_receipt':{'id':'bottle-original','phase':'done','bottle_water':{
            'world_session':'world','request_id':'bottle-original','operation':'bottle_fill','pos':[104,63,100],
            'confirmed':True,'unknown_outcome':False,'server_hand_confirmed':True,'server_water_slot_confirmed':True,
            'use_count':1,'potion':'minecraft:water','source_not_consumed_by_bottle_use':True,'water_slot':water['slot'],
            'confirmation_scope':BOTTLE_SCOPE}}}
        def nav(c,target,*a,**kw):c.pos=list(target)
        p=patch('material_jobs.local_air_path._air_move',side_effect=nav);p.start();self.addCleanup(p.stop)
    def run_refill(self):return refill(self.c,[100,64,100],self.profile,self.out/'work',lambda:None,water_result=self.water)
    def test_known_water_dirt_is_converted_in_place_without_mining_and_tip_is_retained(self):
        result=self.run_refill()
        self.assertTrue(result['complete']);self.assertFalse(result['mud_mining_sent'])
        self.assertEqual((1,0,1),(self.c.count('minecraft:dirt'),self.c.count('minecraft:potion'),self.c.count('minecraft:glass_bottle')))
        self.assertEqual('Block{minecraft:mud}',self.c.blocks[(100,64,100)])
        self.assertIn((100,62,100),self.c.blocks)
        self.assertFalse(any(op in('mine_block','bottle_fill')for op,_ in self.c.calls))
        self.assertGreaterEqual(self.c.pos[1],66)
    def test_dirt_selection_tracks_water_swapped_out_of_the_selected_slot(self):
        self.c.checked('select_item',item='minecraft:potion',slot=self.water['derived_water_slot']['slot'])
        self.water['derived_water_slot']=copy.deepcopy(self.c.rows[self.c.selected])
        self.water['native_receipt']['bottle_water']['water_slot']=self.c.selected
        self.assertTrue(self.run_refill()['complete'])
        self.assertEqual(1,self.c.count('minecraft:glass_bottle'))
    def test_only_known_finished_dirt_can_resume_without_second_placement(self):
        self.c.blocks[(100,64,100)]='Block{minecraft:dirt}'
        old=self.out/'old.json';old.write_text(json.dumps({'world_session':'world','pos':[100,64,100],'pending':None,'receipts':[{'kind':'place_dirt'}]}))
        result=refill(self.c,[100,64,100],self.profile,self.out/'new',lambda:None,water_result=self.water,owned_dirt_journal=old)
        self.assertTrue(result['known_owned_dirt_resumed']);self.assertEqual(2,self.c.count('minecraft:dirt'))
        self.assertEqual(['minecraft:potion'],[p['expected_hand']for op,p in self.c.calls if op=='interact'])
    def test_resume_proves_water_swap_and_the_single_already_used_dirt(self):
        first=self.water['derived_water_slot']['slot'];second=12
        self.water['native_receipt']['inventory']=copy.deepcopy(self.c.rows)
        self.c.rows[first],self.c.rows[second]=self.c.rows[second],self.c.rows[first]
        self.c.rows[first]['slot']=first;self.c.rows[second]['slot']=second;self.c.rows[first]['count']-=1
        self.water['derived_water_slot']=copy.deepcopy(self.c.rows[second])
        self.water['slot_relocation_receipt']={'phase':'done','world_session':'world','id':'current-observation','inventory':copy.deepcopy(self.c.rows)}
        self.c.blocks[(100,64,100)]='Block{minecraft:dirt}'
        old=self.out/'old.json';old.write_text(json.dumps({'world_session':'world','pos':[100,64,100],'pending':None,'receipts':[{'kind':'place_dirt'}]}))
        result=refill(self.c,[100,64,100],self.profile,self.out/'resume',lambda:None,water_result=self.water,owned_dirt_journal=old)
        self.assertTrue(result['complete']);self.assertEqual(1,self.c.count('minecraft:dirt'))
    def test_generic_old_potion_or_changed_slot_has_no_placement_authority(self):
        self.water['native_receipt']['bottle_water']['confirmed']=False
        with self.assertRaises(JobBlocked):self.run_refill()
        self.assertFalse(any(op=='interact'for op,_ in self.c.calls));self.assertEqual(2,self.c.count('minecraft:dirt'))
    def test_water_relocation_requires_the_exact_two_slot_swap(self):
        first=self.water['derived_water_slot']['slot'];second=12
        self.water['native_receipt']['inventory']=copy.deepcopy(self.c.rows)
        self.c.rows[first],self.c.rows[second]=self.c.rows[second],self.c.rows[first]
        self.c.rows[first]['slot']=first;self.c.rows[second]['slot']=second
        self.water['derived_water_slot']=copy.deepcopy(self.c.rows[second])
        self.water['slot_relocation_receipt']={'phase':'done','world_session':'world','id':'proved-swap','inventory':copy.deepcopy(self.c.rows)}
        self.assertTrue(self.run_refill()['complete'])
    def test_unknown_interaction_is_retained_and_not_replayed(self):
        request=self.c.request
        def unknown(op,**kw):
            if op=='interact':raise RuntimeError('unknown use')
            return request(op,**kw)
        self.c.request=unknown
        with self.assertRaisesRegex(RuntimeError,'unknown use'):self.run_refill()
        record=json.loads((self.out/'work/direct-clay-refill.json').read_text())
        self.assertEqual('place_dirt',record['pending']['kind'])
        with self.assertRaisesRegex(JobBlocked,'no replay'):self.run_refill()
    def test_preexisting_bed_is_preserved_without_using_water(self):
        self.c.blocks[(100,64,100)]='Block{minecraft:clay}'
        with self.assertRaises(JobBlocked):self.run_refill()
        self.assertFalse(any(op in('interact','select_item')for op,_ in self.c.calls))
    def test_unregistered_bed_has_no_placement_authority(self):
        self.profile['clay_conversion_farm']['authorized']=False
        with self.assertRaises(JobBlocked):self.run_refill()
        self.assertFalse(self.c.calls)


if __name__=='__main__':unittest.main()
