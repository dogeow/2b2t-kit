from collections import Counter
from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from material_jobs.quarry_workspace import run
from material_jobs.protocol import JobBlocked


class QuarryWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)
        self.held=Counter({'minecraft:wheat_seeds':88,'minecraft:glass_bottle':3,
                           'minecraft:diamond':22,'minecraft:diorite':2,'minecraft:mud_bricks':2})
        def status():
            rows=[]
            for item,total in self.held.items():
                while total:
                    amount=min(total,64);rows.append({'slot':len(rows),'item':item,'count':amount,'max_stack':64});total-=amount
            while len(rows)<36:rows.append({'slot':len(rows),'item':'minecraft:air','count':0,'max_stack':64})
            return {'inventory':rows}
        self.c=SimpleNamespace(status=status)
        @contextmanager
        def action(name):yield self.c,self.out
        self.b=SimpleNamespace(profile={'depots':[[1,64,1]],'quarry_inventory_staging':{
                  'authorized':True,'minimum_empty_slots':8,'reserves':{'minecraft:wheat_seeds':32,
                  'minecraft:glass_bottle':0,'minecraft:mud_bricks':0}}},request={'targets':{'minecraft:mud_bricks':33}},
                  ensure_client=lambda:self.c,action=action,prepare_travel=Mock(),stage_near_base=Mock())
        # Fill unrelated single stacks to require a real deposit; they must all remain.
        for n in range(28):self.held['minecraft:fixture_'+str(n)]=1
        def exchange(c,positions,deposit):
            for item,amount in deposit.items():self.held[item]=amount
            return {'complete':True,'remaining_deposit':{},'remaining_withdraw':{}}
        self.exchange=exchange

    def test_registered_deposit_preserves_target_gear_and_records_real_space(self):
        self.b.profile['quarry_inventory_staging']['minimum_empty_slots']=4
        with patch('material_storage_index.select_destinations',return_value={'positions':[[1,64,1]]}),\
             patch('material_depots.exchange',side_effect=self.exchange)as exchange:
            result=run(self.b)
        self.assertEqual(('done',32,0,22,2),(result['phase'],self.held['minecraft:wheat_seeds'],
                         self.held['minecraft:glass_bottle'],self.held['minecraft:diamond'],self.held['minecraft:diorite']))
        self.assertNotIn('minecraft:mud_bricks',exchange.call_args.kwargs['deposit'])
        self.assertEqual(2,self.held['minecraft:mud_bricks'])
        book=json.loads((self.out/'quarry-workspace.json').read_text())
        self.assertTrue(book['complete']);self.assertIsNone(book['pending']);self.assertEqual(0,book['discarded_items'])

    def test_source_receipt_cannot_hide_unrelated_inventory_loss(self):
        def wrong(*args,**kwargs):self.exchange(*args,**kwargs);self.held['minecraft:diamond']-=1;return {'complete':True}
        with patch('material_storage_index.select_destinations',return_value={'positions':[[1,64,1]]}),\
             patch('material_depots.exchange',side_effect=wrong):
            with self.assertRaises(JobBlocked):run(self.b)
        book=json.loads((self.out/'quarry-workspace.json').read_text());self.assertEqual('deposit',book['pending'])
        self.assertFalse(book['complete'])

    def test_four_free_slots_do_not_trigger_an_eight_slot_depot_trip(self):
        for n in range(2):del self.held['minecraft:fixture_'+str(n)]
        with patch('material_storage_index.select_destinations')as select,\
             patch('material_depots.exchange')as exchange:
            result=run(self.b)
        self.assertEqual('done',result['phase']);self.assertEqual(4,result['free_slots'])
        self.assertTrue(result['staging_not_required']);select.assert_not_called();exchange.assert_not_called()
        self.b.prepare_travel.assert_not_called()

    def test_mining_byproducts_can_be_stored_but_needed_projection_stock_is_retained(self):
        del self.held['minecraft:fixture_0'];del self.held['minecraft:fixture_1']
        self.held['minecraft:granite']=28;self.held['minecraft:diorite']=28
        cfg=self.b.profile['quarry_inventory_staging'];cfg['minimum_empty_slots']=4
        cfg['reserves'].update({'minecraft:granite':0,'minecraft:diorite':2})
        self.b.audit={'replacement_items':{'minecraft:granite':16}}
        with patch('material_storage_index.select_destinations',return_value={'positions':[[1,64,1]]}),\
             patch('material_depots.exchange',side_effect=self.exchange)as exchange:
            run(self.b)
        self.assertEqual(2,self.held['minecraft:diorite']);self.assertEqual(28,self.held['minecraft:granite'])
        self.assertNotIn('minecraft:granite',exchange.call_args.kwargs['deposit'])

    def test_invalid_or_unregistered_profile_never_stores(self):
        self.b.profile['quarry_inventory_staging']['authorized']=False
        self.assertFalse(run(self.b)['prepared']);self.b.prepare_travel.assert_not_called()
        self.b.profile['quarry_inventory_staging']['authorized']=True
        self.b.profile['quarry_inventory_staging']['reserves']['minecraft:diamond']=0
        with patch('material_depots.exchange')as exchange:
            with self.assertRaises(JobBlocked):run(self.b)
            exchange.assert_not_called()

    def test_registered_deep_quarry_drops_free_space_without_discarding_valuables(self):
        for n in range(6):del self.held['minecraft:fixture_'+str(n)]
        self.held.update({'minecraft:cobbled_deepslate':91,'minecraft:lapis_lazuli':8,
                          'minecraft:redstone':5,'minecraft:raw_iron':3,'minecraft:tuff':2})
        self.b.request={'targets':{'minecraft:tuff':66}}
        self.b.profile['quarry_inventory_staging']['reserves']={
            'minecraft:wheat_seeds':32,'minecraft:cobbled_deepslate':0,
            'minecraft:lapis_lazuli':0,'minecraft:redstone':0,'minecraft:raw_iron':0}
        with patch('material_storage_index.select_destinations',return_value={'positions':[[1,64,1]]}),\
             patch('material_depots.exchange',side_effect=self.exchange):
            result=run(self.b)
        self.assertEqual('done',result['phase'])
        self.assertGreaterEqual(result['free_slots'],4)
        self.assertEqual({'minecraft:wheat_seeds':56,'minecraft:cobbled_deepslate':91,
                          'minecraft:lapis_lazuli':8,'minecraft:redstone':5,
                          'minecraft:raw_iron':3},result['stored'])
        self.assertEqual((22,2,0),(self.held['minecraft:diamond'],self.held['minecraft:tuff'],
                                result['discarded_items']))

    def test_registered_mineral_requested_by_current_job_is_not_deposited(self):
        del self.held['minecraft:fixture_0'];del self.held['minecraft:fixture_1']
        self.held.update({'minecraft:cobbled_deepslate':91,'minecraft:raw_iron':3})
        self.b.request={'targets':{'minecraft:cobbled_deepslate':100}}
        self.b.profile['quarry_inventory_staging']['reserves'].update(
            {'minecraft:cobbled_deepslate':0,'minecraft:raw_iron':0})
        with patch('material_storage_index.select_destinations',return_value={'positions':[[1,64,1]]}),\
             patch('material_depots.exchange',side_effect=self.exchange)as exchange:
            run(self.b)
        self.assertEqual(91,self.held['minecraft:cobbled_deepslate'])
        self.assertNotIn('minecraft:cobbled_deepslate',exchange.call_args.kwargs['deposit'])


if __name__=='__main__':unittest.main()
