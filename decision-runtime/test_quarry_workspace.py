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
            return {'phase':'done','source_and_destination_conserved':True}
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
        def wrong(*args,**kwargs):self.exchange(*args,**kwargs);self.held['minecraft:diamond']-=1;return {'phase':'done'}
        with patch('material_storage_index.select_destinations',return_value={'positions':[[1,64,1]]}),\
             patch('material_depots.exchange',side_effect=wrong):
            with self.assertRaises(JobBlocked):run(self.b)
        book=json.loads((self.out/'quarry-workspace.json').read_text());self.assertEqual('deposit',book['pending'])
        self.assertFalse(book['complete'])

    def test_invalid_or_unregistered_profile_never_stores(self):
        self.b.profile['quarry_inventory_staging']['authorized']=False
        self.assertFalse(run(self.b)['prepared']);self.b.prepare_travel.assert_not_called()
        self.b.profile['quarry_inventory_staging']['authorized']=True
        self.b.profile['quarry_inventory_staging']['reserves']['minecraft:diamond']=0
        with patch('material_depots.exchange')as exchange:
            with self.assertRaises(JobBlocked):run(self.b)
            exchange.assert_not_called()


if __name__=='__main__':unittest.main()
