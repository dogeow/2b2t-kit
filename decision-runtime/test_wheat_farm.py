"""Wheat shares the potato workflow while proving its own seed and crop identities."""
import copy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import kit_cli
from potato_farm import FarmWait,POTATO,WHEAT_SEEDS,action_proved,crop_descriptor,plan,run,survey_rows
from potato_farm_cli import execute,journal_directory,main
from test_potato_farm import FarmClient,SPEC,row

WHEAT={**SPEC,'crop':'wheat'}


class WheatClient(FarmClient):
    def __init__(self,seeds=24,farmland=False):
        super().__init__(potatoes=seeds,farmland=farmland)
        self.inv[10]['item']=WHEAT_SEEDS if seeds else 'minecraft:air'
        self.wrong_crop=False;self.wrong_count=0;self.rollback=False;self.rollback_scans=0
        self.set_progress=Mock()
    def request(self,op,**params):
        if op=='scan' and self.rollback and self.after_interact=='plant':
            self.rollback_scans+=1
            if self.rollback_scans==2:
                self.rows.pop(self.last_crop,None)
                self.inv[self.selected].update(item=WHEAT_SEEDS,count=self.inv[self.selected]['count']+1)
        answer=super().request(op,**params)
        if op=='interact' and params['expected_hand']==WHEAT_SEEDS and self.no_change!='plant' and self.fail_op!='plant':
            if not self.wrong_crop:self.rows[self.last_crop]['state']='Block{minecraft:wheat}[age=0]'
            if self.wrong_count:
                self.inv[self.selected]['count']+=self.wrong_count
                self.inv[self.selected]['item']=WHEAT_SEEDS if self.inv[self.selected]['count'] else 'minecraft:air'
        return answer


class WheatFarmTests(unittest.TestCase):
    def run_field(self,client,**options):
        with tempfile.TemporaryDirectory() as folder:
            result=run(client,WHEAT,folder,**options)
            book=json.loads(Path(result['journal']).read_text())
            return result,book
    def test_default_and_explicit_potato_keep_original_layout_and_hash(self):
        layout=plan(SPEC);self.assertEqual(layout,plan({**SPEC,'crop':'potato'}))
        self.assertNotIn('crop',layout);self.assertEqual(24,layout['potatoes']);self.assertNotIn('seeds',layout)
        client=FarmClient()
        with tempfile.TemporaryDirectory() as folder:
            result=run(client,SPEC,folder)
            scope={'server':'server','dimension':'minecraft:overworld','layout':layout}
            digest=hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()[:16]
            self.assertEqual('potato-farm-'+digest+'.json',Path(result['journal']).name)
    def test_wheat_descriptor_keeps_same_irrigated24cells_but_distinct_identity(self):
        layout=plan(WHEAT);self.assertEqual(plan(SPEC)['cells'],layout['cells'])
        self.assertEqual(('wheat',24),(layout['crop'],layout['seeds']));self.assertNotIn('potatoes',layout)
        crop=crop_descriptor(WHEAT);self.assertEqual((WHEAT_SEEDS,'wheat',7,'小麦田'),(crop.item,crop.block,crop.age_max,crop.title))
        for crop in ('carrot','minecraft:wheat',None,True,[],{}):
            with self.subTest(crop=crop),self.assertRaises(ValueError):plan({**SPEC,'crop':crop})
    def test_24_wheat_cells_till_once_and_consume_exactly24_seeds(self):
        client=WheatClient(seeds=30);result,book=self.run_field(client)
        self.assertEqual(('done',24),(result['phase'],result['planted_cells']))
        self.assertEqual(48,len(client.interact_calls()));self.assertEqual(226,client.inv[0]['durability'])
        self.assertEqual(6,sum(r['count'] for r in client.inv if r['item']==WHEAT_SEEDS))
        self.assertEqual(30,book['seeds_before']);self.assertNotIn('potatoes_before',book)
        self.assertTrue(all(v['plant']['crop_after_state']=='Block{minecraft:wheat}[age=0]' for v in book['cells'].values()))
        self.assertTrue(all(p['expected_hand']==WHEAT_SEEDS for p in client.interact_calls()[24:]))
        self.assertTrue(all(len(v['plant']['observed_times'])==2 for v in book['cells'].values()))
        self.assertLessEqual({op for op,_ in client.calls},{'scan','select_item','interact'})
    def test_missing_seeds_cannot_be_satisfied_with_potatoes_and_sends_no_till(self):
        client=WheatClient(seeds=23);client.inv[11].update(item=POTATO,count=64)
        result,book=self.run_field(client);self.assertEqual('WAIT_SEEDS',result['code']);self.assertFalse(client.interact_calls())
        self.assertEqual(23,book['seeds_before'])
    def test_wheat_crop_and_exact_minus_one_seed_both_required(self):
        for fault in ('wrong_crop','no_delta','minus_two'):
            with self.subTest(fault=fault):
                client=WheatClient(farmland=True)
                client.wrong_crop=fault=='wrong_crop';client.wrong_count=1 if fault=='no_delta' else -1 if fault=='minus_two' else 0
                result,book=self.run_field(client,max_cells=1)
                self.assertEqual('waiting',result['phase']);self.assertEqual(0,result['planted_cells'])
                self.assertTrue(book['pending']);self.assertEqual(1,len(client.interact_calls()))
    def test_till_still_requires_real_hoe_durability_decrement(self):
        client=WheatClient();original=client.request
        def no_durability(op,**params):
            answer=original(op,**params)
            if op=='interact' and params['expected_hand'].endswith('_hoe'):client.inv[0]['durability']+=1
            return answer
        client.request=no_durability;result,book=self.run_field(client,max_cells=1)
        self.assertEqual('WAIT_RECONCILE',result['code']);self.assertEqual('till',book['pending']['operation'])
        self.assertEqual(1,len(client.interact_calls()))
    def test_unknown_wheat_interact_and_prediction_rollback_are_never_replayed(self):
        for fault in ('unknown','rollback'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as folder:
                client=WheatClient(farmland=True)
                if fault=='unknown':client.fail_op='plant'
                else:client.rollback=True
                first=run(client,WHEAT,folder,max_cells=1);self.assertEqual('WAIT_RECONCILE',first['code'])
                sent=len(client.interact_calls());second=run(client,WHEAT,folder,max_cells=1)
                self.assertEqual('WAIT_RECONCILE',second['code']);self.assertEqual(sent,len(client.interact_calls()))
    def test_completed_potato_receipt_is_not_a_wheat_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            client=FarmClient();original=run(client,SPEC,folder);raw=Path(original['journal']).read_bytes()
            wheat=WheatClient(farmland=True);result=run(wheat,WHEAT,folder,max_cells=1)
            self.assertEqual('FARM_BATCH',result['code']);self.assertEqual(1,result['planted_cells'])
            self.assertTrue(Path(result['journal']).name.startswith('wheat-farm-'))
            Path(result['journal']).write_bytes(raw);count=len(wheat.interact_calls())
            copied=run(wheat,WHEAT,folder,max_cells=1);self.assertEqual('WAIT_CONTROL',copied['code'])
            self.assertEqual(count,len(wheat.interact_calls()));self.assertEqual(raw,Path(original['journal']).read_bytes())
    def test_unknown_potato_action_blocks_switching_crop_in_same_output_or_registry(self):
        with tempfile.TemporaryDirectory() as folder:
            client=FarmClient(farmland=True);client.fail_op='plant';first=run(client,SPEC,folder,max_cells=1)
            raw=Path(first['journal']).read_bytes();wheat=WheatClient(farmland=True)
            self.assertEqual('WAIT_RECONCILE',run(wheat,WHEAT,folder,max_cells=1)['code'])
            self.assertFalse(wheat.calls);self.assertEqual(raw,Path(first['journal']).read_bytes())
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state={'server':'server','dimension':'minecraft:overworld','world_session':'world-1'}
            directory,path=journal_directory(root,state,SPEC);directory.mkdir(parents=True,exist_ok=True)
            path.write_text('{"pending":{"operation":"plant"}}')
            with self.assertRaisesRegex(RuntimeError,'changing crop'):journal_directory(root,state,WHEAT)
    def test_wheat_proof_rejects_potato_or_invalid_wheat_age(self):
        pos=[-2,63,-2];client=WheatClient(farmland=True);client.request('select_item',item=WHEAT_SEEDS,slot=10)
        before=client.status();client.request('interact',pos=pos,expected_state=client.rows[tuple(pos)]['state'],expected_hand=WHEAT_SEEDS)
        after=client.status();self.assertTrue(action_proved('plant',pos,before,after,client.rows,crop='wheat'))
        for state in ('Block{minecraft:potatoes}[age=0]','Block{minecraft:wheat}[age=8]'):
            client.rows[(-2,64,-2)]['state']=state
            self.assertFalse(action_proved('plant',pos,before,after,client.rows,crop='wheat'))
    def test_cli_wheat_option_and_progress_title_use_same_workflow(self):
        with patch('potato_farm_cli.execute',return_value={'phase':'done'}) as command,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0,main(['--center','0','63','0','--crop','wheat','--no-move']))
        self.assertEqual({'crop':'wheat'},command.call_args.kwargs)
        with patch('potato_farm_cli.main',return_value=0) as delegated:
            self.assertEqual(0,kit_cli.main(['farm','plant','--center','0','63','0','--crop','wheat']))
        self.assertIn('--crop',delegated.call_args.args[0]);self.assertIn('wheat',delegated.call_args.args[0])
        client=WheatClient();current=client.status();current['server']=client.server
        with tempfile.TemporaryDirectory() as folder,patch('potato_farm_cli.read_fresh',return_value=current),patch('potato_farm_cli.require_unlocked'),patch('potato_farm_cli.MaterialClient',return_value=client),patch('potato_farm_cli.JobProgress') as progress,patch('potato_farm_cli.finish_or_yield'):
            self.assertEqual('done',execute(folder,[0,63,0],2,24,no_move=True,crop='wheat')['phase'])
            self.assertEqual('小麦田',progress.call_args.args[4])
    def test_unsupported_crop_rejects_before_game_read_and_wheat_harvest_plan_stays_bounded(self):
        with patch('potato_farm_cli.read_fresh') as observe:
            with self.assertRaises(ValueError):execute('/unused',[0,63,0],2,24,crop='carrot')
        observe.assert_not_called()
        from potato_harvest import plan as harvest_plan
        self.assertEqual('wheat',harvest_plan(WHEAT)['crop'])
        self.assertEqual(4,len(harvest_plan(WHEAT)['harvest_cells']))
        with self.assertRaises(ValueError):harvest_plan({**WHEAT,'authorized':False})


if __name__=='__main__':unittest.main()
