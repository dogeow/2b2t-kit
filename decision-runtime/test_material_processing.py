"""Actual processing orchestration and inventory transfers against offline fixtures."""
from collections import Counter
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from material_jobs import JobPaused
from material_jobs import processing
from test_furnace_batches import FurnaceBankClient


class MetalClient(FurnaceBankClient):
    def __init__(self, raw=(7,13), coal=(3,), ingots=5):
        super().__init__(raw=raw, coal=coal)
        self.cook = True
        for row in self.state['menu']['slots'][3:]:
            if row['item']=='minecraft:cobblestone':
                row['item']='minecraft:raw_iron'
        if ingots:
            slot=next(r for r in self.state['menu']['slots'][3:] if not r['count'])
            slot.update(item='minecraft:iron_ingot',count=ingots)

    def open(self,pos):
        if self.cook and tuple(pos) in self.furnaces:
            inp,_,out=self.furnaces[tuple(pos)]
            if inp['count']:
                out.update(item='minecraft:iron_ingot',count=out['count']+inp['count'])
                inp.update(item='minecraft:air',count=0)
        return super().open(pos)

    def checked(self,op,**args):
        if op=='slot_click' and args.get('kind')=='quick_move':
            self.calls.append(args)
            source=self.state['menu']['slots'][args['slot']]
            assert (source['item'],source['count'])==(args['expected_item'],args['expected_count'])
            for dest in sorted(self.state['menu']['slots'][3:],key=lambda v:not v['count']):
                if dest['count'] and dest['item']!=source['item']:
                    continue
                count=min(source['count'],64-dest['count'])
                dest.update(item=source['item'],count=dest['count']+count)
                source['count']-=count
                if not source['count']:
                    source['item']='minecraft:air';break
            return self.status()
        return super().checked(op,**args)


class ConcreteClient:
    world='w'
    def __init__(self,powder=200,solid=0):
        self.items=Counter({'minecraft:white_concrete_powder':powder,'minecraft:white_concrete':solid})
        self.cell='Block{minecraft:air}';self.commands=[]
    def status(self):
        return {'inventory':[{'slot':i,'item':item,'count':n} for i,(item,n) in enumerate(self.items.items())]
                +[{'slot':8,'item':'minecraft:diamond_pickaxe','count':1,'durability':100}],
                'health':20,'world_session':self.world,'entities':[]}
    def request(self,op,**args):
        self.commands.append((op,args))
        if op=='scan':
            rows=[]
            if args['min']==[1,61,1]:rows.append({'pos':[1,61,1],'state':'Block{minecraft:dirt}','solid':True})
            if self.cell!='Block{minecraft:air}':rows.append({'pos':[1,62,1],'state':self.cell})
            return {'blocks':rows}
        if op=='mine_block':
            self.cell='Block{minecraft:air}';self.items['minecraft:white_concrete']+=1
        return {'phase':'done'}
    def checked(self,op,**args):return self.request(op,**args)


class ProcessingTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.jar=self.root/'recipes.jar'
        with zipfile.ZipFile(self.jar,'w') as archive:
            archive.writestr('data/minecraft/recipe/iron_from_raw.json',json.dumps({
                'type':'minecraft:smelting','ingredient':'minecraft:raw_iron',
                'result':{'id':'minecraft:iron_ingot'},'cookingtime':200}))
        self.recipe={'recipe_id':'smelting/iron_from_raw','source':'minecraft:raw_iron','output':'minecraft:iron_ingot'}
        self.profile={'recipe_jar':str(self.jar),'furnace_positions':[[1,64,1]],
                      'concrete_station':{'support':[1,61,1],'expected_state':'Block{minecraft:dirt}','batch_size':8}}
        self.checks=0
    def checkpoint(self):self.checks+=1
    def smelt(self,c,out=None):
        with patch('material_jobs.processing.snapshot',side_effect=lambda c,p:c.open(p)), \
             patch('furnace_batches.snapshot',side_effect=lambda c,p:c.open(p)):
            return processing.smelt(c,self.recipe,25,self.profile,out or self.root/'smelt',self.checkpoint)
    def test_raw_iron_actual_slot_transfers_honor_final_backpack_target(self):
        c=MetalClient();result=self.smelt(c)
        self.assertEqual('done',result['phase'],result);self.assertEqual(25,result['count'])
        job=json.loads((self.root/'smelt/batch-0001.json').read_text())
        self.assertEqual(20,job['amount']);self.assertEqual('collected',job['furnaces'][0]['stage'])
        self.assertEqual(0,sum(row['count'] for row in c.status()['inventory'] if row['item']=='minecraft:raw_iron'))
        self.assertGreater(self.checks,5)
    def test_missing_coal_returns_real_requirement_without_loading(self):
        c=MetalClient(coal=());result=self.smelt(c)
        self.assertEqual('waiting',result['phase']);self.assertEqual({'minecraft:coal':3},result['requirements'])
        self.assertEqual([],c.calls);self.assertFalse((self.root/'smelt/batch-0001.json').exists())
    def test_forged_recipe_is_blocked_before_any_item_action(self):
        c=MetalClient();self.recipe['source']='minecraft:diamond';result=self.smelt(c)
        self.assertEqual('blocked',result['phase']);self.assertEqual([],c.calls)
    def test_existing_furnace_contents_are_preserved(self):
        c=MetalClient();rows=copy.deepcopy(c.state['menu']['slots'][:3]);rows[2].update(item='minecraft:diamond',count=1)
        c.furnaces[(1,64,1)]=rows;result=self.smelt(c)
        self.assertEqual('blocked',result['phase']);self.assertEqual([],c.calls)
        self.assertEqual('minecraft:diamond',c.furnaces[(1,64,1)][2]['item'])
    def test_pause_during_unacknowledged_transfer_cannot_repeat_input(self):
        c=MetalClient()
        def pause(c,args):raise JobPaused('pause during the first click')
        c.after_click=pause
        with self.assertRaises(JobPaused):self.smelt(c)
        calls=len(c.calls);c.after_click=None
        result=self.smelt(c)
        self.assertEqual('blocked',result['phase']);self.assertEqual(calls,len(c.calls))
        recovered=processing.recover(c,'smelt',[self.recipe,25],self.profile,self.root/'smelt',self.checkpoint)
        self.assertEqual('blocked',recovered['phase']);self.assertFalse(recovered['safe_to_replan'])
        self.assertEqual(calls,len(c.calls))
        saved=json.loads((self.root/'smelt/batch-0001.json').read_text())
        self.assertTrue(saved['furnaces'][0]['pending'])
    def test_loaded_batch_resumes_collection_without_reloading(self):
        c=MetalClient();c.cook=False
        def paused(*args):raise JobPaused('pause after all furnaces are loaded')
        with patch('material_jobs.processing._wait_collect',side_effect=paused):
            with self.assertRaises(JobPaused):self.smelt(c)
        before=sum(1 for row in c.calls if row['slot'] in (0,1) and row.get('kind')!='quick_move');c.cook=True
        result=self.smelt(c)
        self.assertEqual('done',result['phase'],result)
        self.assertEqual(before,sum(1 for row in c.calls if row['slot'] in (0,1) and row.get('kind')!='quick_move'))
    def test_recovery_api_collects_only_fully_loaded_smelting_batch(self):
        c=MetalClient();c.cook=False
        with patch('material_jobs.processing._wait_collect',side_effect=JobPaused('loaded pause')):
            with self.assertRaises(JobPaused):self.smelt(c)
        c.cook=True
        with patch('material_jobs.processing.snapshot',side_effect=lambda c,p:c.open(p)), \
             patch('furnace_batches.snapshot',side_effect=lambda c,p:c.open(p)):
            result=processing.recover(c,'smelt',[self.recipe,25],self.profile,self.root/'smelt',self.checkpoint)
        self.assertEqual('done',result['phase'],result);self.assertTrue(result['safe_to_replan'])
    def test_completed_job_is_not_reproduced_after_outputs_are_moved(self):
        c=MetalClient();self.assertEqual('done',self.smelt(c)['phase']);calls=len(c.calls)
        for row in c.state['menu']['slots'][3:]:
            if row['item']=='minecraft:iron_ingot':row.update(item='minecraft:air',count=0)
        self.assertEqual('blocked',self.smelt(c)['phase']);self.assertEqual(calls,len(c.calls))
    def convert(self,c,support,state,powder,solid,count,**kwargs):
        for _ in range(0,count,8):
            n=min(8,count-_);c._client.items[powder]-=n;c._client.items[solid]+=n
            kwargs['on_progress'](n)
        return {'completed':count}
    def test_hardening_uses_bounded_batches_and_counts_only_new_output(self):
        c=ConcreteClient(powder=200,solid=10)
        with patch('material_jobs.processing.convert',side_effect=self.convert) as convert:
            result=processing.harden(c,'minecraft:white_concrete',150,self.profile,self.root/'harden',self.checkpoint)
        self.assertEqual('done',result['phase'],result);self.assertEqual(150,c.items['minecraft:white_concrete'])
        self.assertEqual([64,64,12],[call.args[5] for call in convert.call_args_list])
        self.assertEqual(60,c.items['minecraft:white_concrete_powder'])
    def test_missing_powder_is_a_requirement_not_fake_completed_output(self):
        c=ConcreteClient(powder=0)
        with patch('material_jobs.processing.convert') as convert:
            result=processing.harden(c,'minecraft:white_concrete',150,self.profile,self.root/'harden',self.checkpoint)
        self.assertEqual('waiting',result['phase']);self.assertEqual({'minecraft:white_concrete_powder':64},result['requirements']);convert.assert_not_called()
    def test_unconfirmed_hardening_cannot_be_replayed(self):
        c=ConcreteClient(powder=64)
        def pause(c,support,state,powder,solid,count,**kwargs):
            c._client.items[powder]-=8;c._client.items[solid]+=8
            kwargs['on_progress'](8)
            raise JobPaused('pause before next native batch')
        with patch('material_jobs.processing.convert',side_effect=pause) as convert:
            with self.assertRaises(JobPaused):processing.harden(c,'minecraft:white_concrete',64,self.profile,self.root/'harden',self.checkpoint)
            result=processing.harden(c,'minecraft:white_concrete',64,self.profile,self.root/'harden',self.checkpoint)
        self.assertEqual('blocked',result['phase']);self.assertEqual(1,convert.call_count)
        self.assertEqual(8,c.items['minecraft:white_concrete'])
    def test_recovery_accepts_exact_hardened_prefix_and_only_uses_unspent_powder(self):
        c=ConcreteClient(powder=64)
        def pause(c,support,state,powder,solid,count,**kwargs):
            c._client.items[powder]-=8;c._client.items[solid]+=8
            kwargs['on_progress'](8)
            raise JobPaused('pause after verified prefix')
        with patch('material_jobs.processing.convert',side_effect=pause):
            with self.assertRaises(JobPaused):processing.harden(c,'minecraft:white_concrete',64,self.profile,self.root/'harden',self.checkpoint)
        with patch('material_jobs.processing.convert',side_effect=self.convert) as convert:
            result=processing.recover(c,'harden',['minecraft:white_concrete',64],self.profile,self.root/'harden',self.checkpoint)
        self.assertEqual('done',result['phase'],result);self.assertTrue(result['safe_to_replan'])
        self.assertEqual(56,convert.call_args.args[5]);self.assertEqual(64,c.items['minecraft:white_concrete'])
        self.assertEqual(0,c.items['minecraft:white_concrete_powder'])
    def test_recovery_mines_owned_residual_before_any_more_powder(self):
        c=ConcreteClient(powder=64)
        def pause(c,*args,**kwargs):
            c._client.items['minecraft:white_concrete_powder']-=1;c._client.cell='Block{minecraft:white_concrete}'
            raise JobPaused('placed and hardened but not mined')
        with patch('material_jobs.processing.convert',side_effect=pause):
            with self.assertRaises(JobPaused):processing.harden(c,'minecraft:white_concrete',64,self.profile,self.root/'harden',self.checkpoint)
        with patch('material_jobs.processing.convert',side_effect=self.convert) as convert:
            result=processing.recover(c,'harden',['minecraft:white_concrete',64],self.profile,self.root/'harden',self.checkpoint)
        self.assertEqual('done',result['phase'],result);self.assertTrue(result['safe_to_replan'])
        self.assertEqual(63,convert.call_args.args[5]);self.assertEqual(1,len([op for op,args in c.commands if op=='mine_block']))
    def test_zero_consumption_unknown_hardening_does_not_repeat_placement(self):
        c=ConcreteClient(powder=64)
        with patch('material_jobs.processing.convert',side_effect=JobPaused('unknown before progress')):
            with self.assertRaises(JobPaused):processing.harden(c,'minecraft:white_concrete',64,self.profile,self.root/'harden',self.checkpoint)
        with patch('material_jobs.processing.convert') as convert:
            result=processing.recover(c,'harden',['minecraft:white_concrete',64],self.profile,self.root/'harden',self.checkpoint)
        self.assertEqual('blocked',result['phase']);self.assertFalse(result['safe_to_replan']);convert.assert_not_called()
    def test_false_concrete_receipt_fails_inventory_conservation(self):
        c=ConcreteClient(powder=64)
        with patch('material_jobs.processing.convert',return_value={'completed':64}):
            result=processing.harden(c,'minecraft:white_concrete',64,self.profile,self.root/'harden',self.checkpoint)
        self.assertEqual('blocked',result['phase']);self.assertFalse(json.loads((self.root/'harden/hardening.json').read_text())['complete'])
    def test_checkpoint_proxy_preserves_underlying_menu_ownership(self):
        c=ConcreteClient();proxy=processing.CheckpointClient(c,self.checkpoint)
        proxy.owned_material_menu=37
        self.assertEqual(37,c.owned_material_menu);proxy.status();self.assertEqual(1,self.checks)

    def shelter(self):
        path=self.root/'shelter.json'
        ledger={'layout':{'cell':[1,62,1],'stand':[0,63,1]},'path':str(path),'complete':True}
        path.write_text(json.dumps(ledger))
        self.profile['concrete_station'].update(shelter_ledger=str(path),stand_block=[0,62,1])
        return ledger
    def test_sheltered_station_enters_once_and_exits_before_normal_return(self):
        ledger=self.shelter();c=ConcreteClient(powder=128);c.items['minecraft:cobbled_deepslate']=3
        with patch('material_jobs.processing.enter_station',return_value=ledger) as enter, \
             patch('material_jobs.processing.exit_station') as exit, \
             patch('material_jobs.processing.convert',side_effect=self.convert):
            result=processing.harden(c,'minecraft:white_concrete',128,self.profile,self.root/'harden',self.checkpoint)
        self.assertEqual('done',result['phase'],result);self.assertEqual(1,enter.call_count);self.assertEqual(1,exit.call_count)
        self.assertEqual('outside',c.material_job_shelter['phase'])
    def test_paused_station_does_not_walk_in_finally_and_keeps_exit_receipt(self):
        ledger=self.shelter();c=ConcreteClient(powder=64);c.items['minecraft:dirt']=1
        with patch('material_jobs.processing.enter_station',return_value=ledger), \
             patch('material_jobs.processing.exit_station') as exit, \
             patch('material_jobs.processing.convert',side_effect=JobPaused('manual takeover')):
            with self.assertRaises(JobPaused):
                processing.harden(c,'minecraft:white_concrete',64,self.profile,self.root/'harden',self.checkpoint)
        exit.assert_not_called();self.assertEqual('inside',c.material_job_shelter['phase'])
        self.assertEqual(ledger,c.material_job_shelter_ledger)

    def test_missing_hatch_material_requests_one_cobble_before_entering(self):
        self.shelter();c=ConcreteClient(powder=8,solid=8)
        with patch('material_jobs.processing.enter_station') as enter,patch('material_jobs.processing.convert') as convert:
            result=processing.harden(c,'minecraft:white_concrete',16,self.profile,self.root/'harden',self.checkpoint)
        self.assertEqual('waiting',result['phase'],result)
        self.assertEqual({'minecraft:cobblestone':1},result['requirements'])
        enter.assert_not_called();convert.assert_not_called()
        self.assertEqual([],json.loads((self.root/'harden/hardening.json').read_text())['batches'])

    def test_existing_deepslate_hatch_material_needs_no_extra_cobble_fetch(self):
        ledger=self.shelter();c=ConcreteClient(powder=8,solid=8);c.items['minecraft:cobbled_deepslate']=3
        with patch('material_jobs.processing.enter_station',return_value=ledger) as enter, \
             patch('material_jobs.processing.exit_station'),patch('material_jobs.processing.convert',side_effect=self.convert):
            result=processing.harden(c,'minecraft:white_concrete',16,self.profile,self.root/'harden',self.checkpoint)
        self.assertEqual('done',result['phase'],result);enter.assert_called_once()
        self.assertEqual(16,c.items['minecraft:white_concrete']);self.assertNotIn('requirements',result)


if __name__=='__main__':unittest.main()
