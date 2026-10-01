from pathlib import Path
import copy
import itertools
import json
import math
import tempfile
import unittest
from unittest.mock import patch

from material_jobs import processing
from furnace_batches import collect,load,recipe_balance,wait_loading_balance
from test_furnace_batches import FurnaceBankClient
from material_jobs.protocol import JobPaused

JAR=Path('/Applications/.minecraft/versions/26.1.2/26.1.2.jar')


class CookingClient(FurnaceBankClient):
    def __init__(self,source='minecraft:oak_log',raw=(12,),fuel='minecraft:oak_planks',fuels=(10,),output='minecraft:charcoal',residual=0):
        super().__init__(raw=raw,coal=fuels);self.source=source;self.fuel=fuel;self.output=output
        self.cook=True;self.residual=residual
        for row in self.state['menu']['slots'][3:]:
            if row['item']=='minecraft:cobblestone':row['item']=source
            elif row['item']=='minecraft:coal':row['item']=fuel
    def open(self,pos):
        if self.cook and tuple(pos) in self.furnaces:
            inp,fuel,out=self.furnaces[tuple(pos)];n=inp['count']
            if n:
                duration=1600 if self.fuel in ('minecraft:coal','minecraft:charcoal') else 300
                # The inherited slot fixture already consumes one item when
                # fuel is inserted; count that same burn, never burn it twice.
                burned=max(0,math.ceil(max(0,n*200-self.residual)/duration)-self.burned)
                assert fuel['count']>=burned
                fuel['count']-=burned
                if not fuel['count']:fuel['item']='minecraft:air'
                inp.update(item='minecraft:air',count=0);out.update(item=self.output,count=out['count']+n)
        return super().open(pos)
    def checked(self,op,**args):
        if op=='slot_click' and args.get('kind')=='quick_move':
            self.calls.append(args);source=self.state['menu']['slots'][args['slot']]
            assert (source['item'],source['count'])==(args['expected_item'],args['expected_count'])
            for dest in sorted(self.state['menu']['slots'][3:],key=lambda v:not v['count']):
                if dest['count'] and dest['item']!=source['item']:continue
                n=min(source['count'],64-dest['count']);dest.update(item=source['item'],count=dest['count']+n);source['count']-=n
                if not source['count']:source['item']='minecraft:air';break
            if self.after_click:self.after_click(self,args)
            return self.status()
        return super().checked(op,**args)


@unittest.skipUnless(JAR.exists(),'Actual Minecraft jar unavailable')
class ProcessingFuelsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.recipe={'recipe_id':'smelting/charcoal','source':'minecraft:oak_log','output':'minecraft:charcoal','fuel_allow_items':['minecraft:oak_planks'],'fuel_keep':{'minecraft:oak_planks':2}}
        self.profile={'recipe_jar':str(JAR),'furnace_positions':[[1,64,1]]}
    def run_smelt(self,c,target=12):
        with patch('material_jobs.processing.snapshot',side_effect=lambda c,p:c.open(p)),patch('furnace_batches.snapshot',side_effect=lambda c,p:c.open(p)):
            return processing.smelt(c,self.recipe,target,self.profile,self.root/'job',lambda:None)
    def test_wood_fuel_real_slot_transfers_make_charcoal_without_coal(self):
        c=CookingClient();r=self.run_smelt(c);self.assertEqual('done',r['phase'],r)
        job=json.loads((self.root/'job/batch-0001.json').read_text());entry=job['furnaces'][0]
        self.assertEqual(('minecraft:oak_planks',8,300),(entry['fuel_item'],entry['fuel'],entry['burn_ticks_per_fuel']))
        self.assertEqual((8,0),(entry['fuel_consumed'],entry['fuel_returned']))
        held={}
        for row in c.status()['inventory']:held[row['item']]=held.get(row['item'],0)+row['count']
        self.assertEqual(2,held['minecraft:oak_planks']);self.assertEqual(12,held['minecraft:charcoal'])
    def test_missing_planks_requirement_includes_exact_kept_amount(self):
        c=CookingClient(fuels=(1,));r=self.run_smelt(c)
        self.assertEqual('waiting',r['phase']);self.assertEqual({'minecraft:oak_planks':10},r['requirements'])
        self.assertEqual([],c.calls);self.assertFalse((self.root/'job/batch-0001.json').exists())
    def test_same_source_and_fuel_log_conservation(self):
        self.recipe.update(fuel_allow_items=['minecraft:oak_log'],fuel_keep={})
        c=CookingClient(raw=(20,),fuels=());r=self.run_smelt(c)
        self.assertEqual('done',r['phase'],r)
        entry=json.loads((self.root/'job/batch-0001.json').read_text())['furnaces'][0]
        self.assertEqual(('minecraft:oak_log',8),(entry['fuel_item'],entry['fuel_consumed']))
    def test_charcoal_as_fuel_is_carried_charcoal_not_faked_coal(self):
        self.recipe={'recipe_id':'smelting/iron_ingot_from_smelting_raw_iron','source':'minecraft:raw_iron','output':'minecraft:iron_ingot'}
        # Resolve actual game recipe name rather than relying on a remembered ID.
        from projection_material_plan import ProcessingCatalog
        cat=ProcessingCatalog(JAR)
        spec=next(r for r in cat.recipes['minecraft:iron_ingot'] if r.id in cat.smelting and r.cells[0][1]==('minecraft:raw_iron',))
        self.recipe['recipe_id']=spec.id
        c=CookingClient(source='minecraft:raw_iron',fuel='minecraft:charcoal',fuels=(2,),output='minecraft:iron_ingot')
        r=self.run_smelt(c);self.assertEqual('done',r['phase'],r)
        entry=json.loads((self.root/'job/batch-0001.json').read_text())['furnaces'][0]
        self.assertEqual(('minecraft:charcoal',2),(entry['fuel_item'],entry['fuel_consumed']))
    def test_unused_real_fuel_is_returned_and_counted_after_output(self):
        c=CookingClient(residual=2000);r=self.run_smelt(c)
        self.assertEqual('done',r['phase'],r)
        entry=json.loads((self.root/'job/batch-0001.json').read_text())['furnaces'][0]
        self.assertEqual((2,6),(entry['fuel_consumed'],entry['fuel_returned']))
    def test_pause_or_unknown_wood_loading_keeps_original_ledger_no_replay(self):
        c=CookingClient()
        def pause(c,args):
            if args.get('slot')==1:raise JobPaused('fuel click unknown')
        c.after_click=pause
        with self.assertRaises(JobPaused):self.run_smelt(c)
        before=len(c.calls);c.after_click=None;r=self.run_smelt(c)
        self.assertEqual('blocked',r['phase']);self.assertEqual(before,len(c.calls))
    def test_unknown_return_cannot_repeat_output_or_fuel_collection(self):
        c=CookingClient(residual=2000)
        def pause(c,args):
            if args.get('slot')==1 and args.get('kind')=='quick_move':raise JobPaused('return click unknown')
        c.after_click=pause
        with self.assertRaises(JobPaused):self.run_smelt(c)
        before=len(c.calls);c.after_click=None;r=self.run_smelt(c)
        self.assertEqual('blocked',r['phase']);self.assertEqual(before,len(c.calls))
        entry=json.loads((self.root/'job/batch-0001.json').read_text())['furnaces'][0]
        self.assertEqual('fuel_returning',entry['stage']);self.assertTrue(entry['pending'])
    def test_known_output_collected_resume_only_returns_owned_fuel(self):
        c=CookingClient(residual=2000);pos=[1,64,1];path=self.root/'collected.json'
        c.furnaces[tuple(pos)]=[{'slot':0,'item':'minecraft:air','count':0},
            {'slot':1,'item':'minecraft:oak_planks','count':6},{'slot':2,'item':'minecraft:air','count':0}]
        job={'world_session':'w','amount':12,'source':'minecraft:oak_log','output':'minecraft:charcoal',
             'furnaces':[{'pos':pos,'amount':12,'stage':'output_collected','pending':None,
                          'fuel_item':'minecraft:oak_planks','fuel':8,'loaded_fuel':8,'output_inventory_after':12}]}
        path.write_text(json.dumps(job))
        from smelting_workflow import inspect_batch
        self.assertEqual('output_collected',inspect_batch(path,'w',[pos],'minecraft:oak_log','minecraft:charcoal',12)['furnaces'][0]['stage'])
        with patch('furnace_batches.snapshot',side_effect=lambda c,p:c.open(p)):
            self.assertTrue(collect(c,path))
        moved=[r['slot'] for r in c.calls if r.get('kind')=='quick_move']
        self.assertEqual([1],moved)
        row=json.loads(path.read_text())['furnaces'][0]
        self.assertEqual((2,6),(row['fuel_consumed'],row['fuel_returned']))
    def test_old_complete_receipt_does_not_invent_zero_fuel_consumption(self):
        c=CookingClient();slot=next(r for r in c.state['menu']['slots'][3:] if not r['count'])
        slot.update(item='minecraft:charcoal',count=12)
        folder=self.root/'job';folder.mkdir()
        old={'kind':'smelt','world_session':'w','target':12,'recipe_id':'smelting/charcoal',
             'source':'minecraft:oak_log','output':'minecraft:charcoal','cooking_ticks':200,
             'positions':self.profile['furnace_positions'],'complete':False,
             'batches':[{'complete':True,'receipt':{'furnaces':[{'stage':'collected','fuel_item':'minecraft:oak_planks','loaded_fuel':8}]}}]}
        (folder/'smelting.json').write_text(json.dumps(old))
        result=self.run_smelt(c)
        self.assertEqual('done',result['phase'])
        row=result['fuel_consumption']['minecraft:oak_planks']
        self.assertFalse(row['known']);self.assertIsNone(row['consumed'])
        self.assertEqual([],c.calls)
    def test_nonflammable_or_unverified_allow_item_never_dispatches(self):
        self.recipe['fuel_allow_items']=['minecraft:warped_planks'];c=CookingClient()
        self.assertEqual('blocked',self.run_smelt(c)['phase']);self.assertEqual([],c.calls)
    def test_legacy_stone_loader_also_uses_actual_charcoal_and_keeps_one(self):
        c=CookingClient(source='minecraft:cobblestone',raw=(20,),fuel='minecraft:charcoal',fuels=(4,),output='minecraft:stone')
        path=self.root/'legacy.json'
        with patch('furnace_batches.snapshot',side_effect=lambda c,p:c.open(p)):
            job=load(c,[[1,64,1]],'minecraft:cobblestone','minecraft:stone',20,path,
                     recipe_jar=JAR,keep={'minecraft:charcoal':1})
            self.assertEqual(('minecraft:charcoal',3),(job['furnaces'][0]['fuel_item'],job['furnaces'][0]['fuel']))
            self.assertTrue(collect(c,path))
        self.assertEqual(1,sum(r['count'] for r in c.status()['inventory'] if r['item']=='minecraft:charcoal'))


class AlternativeBalanceTest(unittest.TestCase):
    def test_only_selected_fuel_item_can_occupy_the_owned_slot(self):
        rows=[{'item':'minecraft:oak_log','count':12},{'item':'minecraft:oak_planks','count':7},{'item':'minecraft:air','count':0}]
        self.assertTrue(recipe_balance(rows,'minecraft:oak_log','minecraft:charcoal',12,'minecraft:oak_planks',8))
        self.assertFalse(recipe_balance(rows,'minecraft:oak_log','minecraft:charcoal',12))
        rows[1]['count']=9;self.assertFalse(recipe_balance(rows,'minecraft:oak_log','minecraft:charcoal',12,'minecraft:oak_planks',8))


if __name__=='__main__':unittest.main()
