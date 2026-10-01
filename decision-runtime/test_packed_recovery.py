"""A terminal recovery error must not repeat mining or guess portable-box ownership."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from packed_supplies import reconcile_recovered_box,recover_and_return


class RecoveryReconciliationTest(unittest.TestCase):
    BOX='minecraft:pink_shulker_box'
    PAD=[761020,64,797848]
    ENDER=[761021,64,797850]
    WORLD='owned-world'

    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.out=Path(temporary.name);self.journal=self.out/'packed-transfer-active.json'
        owner=self
        class Client:
            def __init__(self):
                self.out=owner.out;self.resource_cleanup={};self.actions=[];self.scans=0;self.reads=0
                self.world=owner.WORLD;self.scan_world=owner.WORLD;self.scan_blocks=[]
                self.s={'connected':True,'world_session':owner.WORLD,'screen':'',
                    'inventory':owner.empty_inventory(),'menu':{'id':0,'type':'InventoryMenu',
                    'cursor':{'item':'minecraft:air','count':0}}}
                self.s['inventory'][9]={'slot':9,'item':owner.BOX,'count':1,
                    'contains':[{'item':'minecraft:book','count':2}]}
            def status(self):self.reads+=1;return copy.deepcopy(self.s)
            def request(self,op,**params):
                owner.assertEqual('scan',op);owner.assertEqual({'min':owner.PAD,'max':owner.PAD},params)
                self.scans+=1
                return {'phase':'done','world_session':self.scan_world,'blocks':copy.deepcopy(self.scan_blocks)}
            def checked(self,op,**params):
                self.actions.append((op,params))
                if op=='close_menu':self.s['screen']='';return
                owner.assertEqual('slot_click',op);owner.assertEqual('pickup',params['kind'])
                menu=self.s['menu'];cell=menu['slots'][params['slot']]
                owner.assertEqual((cell['item'],cell['count']),(params['expected_item'],params['expected_count']))
                cursor=menu['cursor'];menu['cursor']={k:v for k,v in cell.items() if k!='slot'}
                cell.update(cursor)
        self.client=Client()
        self.record={'world_session':self.WORLD,'stage':'breaking','slot':24,'item':self.BOX,
            'temporary_position':self.PAD,'initial_counts':{'minecraft:book':3},
            'remaining_counts':{'minecraft:book':2},'taken':{'minecraft:book':1},
            'placed_state':'Block{minecraft:pink_shulker_box}[facing=up]',
            'ownership_preflight':{'world_session':self.WORLD,'cursor_clean':True,
                'inventory':self.empty_inventory()},
            'source':{'position':self.ENDER,'slot':24,'item':self.BOX,'count':1,'counts':{'minecraft:book':3}},
            'recover_request_id':'owned-recover',
            'recover_terminal':{'request_id':'owned-recover','world_session':self.WORLD,
                'op':'recover_shulker','phase':'error','detail':'Mining target changed',
                'params':{'pos':self.PAD,'expected_state':'Block{minecraft:pink_shulker_box}[facing=up]'}}}
        self.journal.write_text(json.dumps(self.record))

    def empty_inventory(self):
        return [{'slot':i,'item':'minecraft:air','count':0} for i in range(36)]

    def test_false_negative_carried_box_is_read_only_reconciled_then_returned_to_original_slot(self):
        def open_ender(client,ender,kind):
            self.assertEqual(self.ENDER,ender);self.assertEqual('ChestMenu',kind)
            self.assertEqual('recovered',json.loads(self.journal.read_text())['stage'])
            slots=[{'slot':i,'item':'minecraft:air','count':0} for i in range(27)]
            slots.extend(dict(row,slot=27+i) for i,row in enumerate(client.s['inventory']))
            client.s['menu']={'id':10,'type':'ChestMenu','cursor':{'item':'minecraft:air','count':0},'slots':slots}
            client.s['screen']='ContainerScreen';return client.status()
        with patch('packed_supplies.open_box',side_effect=open_ender):
            recover_and_return(self.client,self.record,self.ENDER,self.journal)
        self.assertEqual('returned',self.record['stage']);self.assertEqual(1,self.client.scans)
        self.assertEqual([36,24],[args['slot'] for op,args in self.client.actions if op=='slot_click'])
        self.assertEqual({'minecraft:book':2},self.record['remaining_counts'])
        self.assertFalse(any(op in ('recover_shulker','mine_block','collect_item') for op,_ in self.client.actions))

    def test_one_reconciliation_has_two_status_reads_and_one_scan_without_mutations(self):
        reconcile_recovered_box(self.client,self.record,self.ENDER,self.journal)
        self.assertEqual((2,1,[]),(self.client.reads,self.client.scans,self.client.actions))
        self.assertEqual('recovered',self.record['stage'])

    def test_wrong_world_duplicate_missing_or_changed_boxes_and_occupied_pad_stay_blocked(self):
        scenarios={
            'wrong_world':lambda:self.client.s.update(world_session='different-world'),
            'duplicate_boxes':lambda:self.client.s['inventory'].__setitem__(10,copy.deepcopy(dict(self.client.s['inventory'][9],slot=10))),
            'missing_box':lambda:self.client.s['inventory'].__setitem__(9,self.empty_inventory()[9]),
            'incomplete_inventory':lambda:self.client.s['inventory'].pop(),
            'different_contents':lambda:self.client.s['inventory'][9].update(contains=[{'item':'minecraft:book','count':1}]),
            'unknown_contents':lambda:self.client.s['inventory'][9].pop('contains'),
            'pad_occupied':lambda:self.client.scan_blocks.append({'pos':self.PAD,'state':'Block{minecraft:pink_shulker_box}'}),
            'scan_wrong_world':lambda:setattr(self.client,'scan_world','different-world'),
            'dirty_cursor':lambda:self.client.s['menu']['cursor'].update(item='minecraft:book',count=1),
            'unknown_stage':lambda:self.record.update(stage='uncertain'),
            'old_carried_box':lambda:self.record['ownership_preflight']['inventory'].__setitem__(8,dict(self.client.s['inventory'][9],slot=8)),
            'foreign_request':lambda:self.record['recover_terminal'].update(request_id='foreign-recover'),
            'nonterminal_request':lambda:self.record['recover_terminal'].update(phase='running'),
            'wrong_pad_request':lambda:self.record['recover_terminal']['params'].update(pos=[761021,64,797848]),
            'wrong_source_slot':lambda:self.record['source'].update(slot=23),
            'legacy_without_preflight':lambda:self.record.pop('ownership_preflight'),
        }
        for name,change in scenarios.items():
            with self.subTest(name=name):
                self.setUp();change();before=copy.deepcopy(self.record);self.journal.write_text(json.dumps(before))
                with self.assertRaises(RuntimeError):reconcile_recovered_box(self.client,self.record,self.ENDER,self.journal)
                self.assertEqual(before,self.record);self.assertEqual(before,json.loads(self.journal.read_text()))
                self.assertFalse(self.client.actions);self.assertLessEqual(self.client.scans,1)

    def test_cleanup_does_not_guess_recovery_for_an_unknown_or_placed_stage(self):
        for stage in ('placed','prepared','unknown'):
            with self.subTest(stage=stage):
                self.record['stage']=stage;self.journal.write_text(json.dumps(self.record))
                with self.assertRaises(RuntimeError):recover_and_return(self.client,self.record,self.ENDER,self.journal)
                self.assertEqual(stage,self.record['stage']);self.assertFalse(self.client.actions)
        self.assertEqual(0,self.client.scans)


class RecoveryRpcFailureTest(unittest.TestCase):
    def test_timeout_or_stale_receipt_does_not_reconcile_or_repeat_the_recover_request(self):
        from test_packed_supplies import EquipmentWithdrawalTest
        fixture=EquipmentWithdrawalTest()
        for stale in (False,True):
            with self.subTest(stale=stale),tempfile.TemporaryDirectory() as folder:
                client=fixture.client(folder);original=client.checked
                if stale:
                    client.last='earlier-recover'
                    client.last_terminal_evidence={'request_id':client.last,'op':'recover_shulker',
                        'phase':'error','world_session':'owned-world','params':{'pos':fixture.PAD}}
                def checked(op,**params):
                    if op!='recover_shulker':return original(op,**params)
                    client.actions.append((op,params));raise RuntimeError('Native operation timed out; do not replay it')
                client.checked=checked
                with patch('packed_supplies.reconcile_recovered_box') as reconcile:
                    with self.assertRaisesRegex(RuntimeError,'timed out'):fixture.run_withdrawal(client,4)
                reconcile.assert_not_called();self.assertFalse(client.returned)
                self.assertEqual(1,len([op for op,_ in client.actions if op=='recover_shulker']))
                record=json.loads((client.out/'packed-transfer-active.json').read_text())
                self.assertEqual('breaking',record['stage']);self.assertNotIn('recover_terminal',record)

    def test_take_box_reconciles_one_owned_terminal_error_without_replaying_recovery(self):
        # Reuse the existing real withdrawal fixture, including exact tool receipts.
        from test_packed_supplies import EquipmentWithdrawalTest
        fixture=EquipmentWithdrawalTest()
        with tempfile.TemporaryDirectory() as folder:
            client=fixture.client(folder);client.world='owned-world'
            original_status=client.status;original_checked=client.checked;scans=[]
            def status():
                state=original_status();state.update(connected=True,world_session=client.world);return state
            client.status=status
            def checked(op,**params):
                if op!='recover_shulker':return original_checked(op,**params)
                client.actions.append((op,params));client.placed=False
                index=next(i for i,row in enumerate(client.inventory) if not row['count'])
                client.inventory[index]={'slot':index,'item':fixture.BOX,'count':1,'contains':copy.deepcopy(client.box)}
                client.last='owned-recover';client.last_terminal_evidence={'request_id':client.last,
                    'world_session':client.world,'op':op,'phase':'error','params':params,'detail':'Mining target changed'}
                raise RuntimeError('Mining target changed')
            client.checked=checked
            def request(op,**params):
                self.assertEqual('scan',op);scans.append(params)
                return {'phase':'done','world_session':client.world,'blocks':[]}
            client.request=request
            record=fixture.run_withdrawal(client,4)
            self.assertTrue(client.returned);self.assertEqual('returned',record['stage'])
            self.assertEqual(1,len([op for op,_ in client.actions if op=='recover_shulker']))
            self.assertEqual([{'min':fixture.PAD,'max':fixture.PAD}],scans)
            self.assertEqual('owned-recover',record['recovery_reconciliation']['recover_request_id'])
            self.assertEqual(client.world,record['ownership_preflight']['world_session'])


class RecoveryPreflightOrderingTest(unittest.TestCase):
    def test_baseline_precedes_tool_switch_and_changed_pad_never_mines_or_collects(self):
        from test_packed_supplies import EquipmentWithdrawalTest
        fixture=EquipmentWithdrawalTest()
        with tempfile.TemporaryDirectory() as folder:
            client=fixture.client(folder);original_status=client.status;original_checked=client.checked
            selected_pick=False
            old={'uuid':'old','type':'minecraft:item','stack':{'item':'minecraft:shulker_box','count':1},
                 'pos':fixture.PAD}
            fresh={**old,'uuid':'new-after-pick'}
            def status():
                state=original_status();state['entities']=[old]+([fresh] if selected_pick else [])
                return state
            def checked(op,**params):
                nonlocal selected_pick
                if op=='select_item' and params['item']=='minecraft:diamond_pickaxe':
                    before=json.loads((client.out/'packed-transfer-active.json').read_text())
                    self.assertEqual('withdrawn',before['stage'])
                    self.assertEqual(['old'],before['before_drop_uuids'])
                    self.assertIn('remaining_counts',before)
                    selected_pick=True;client.placed=False
                return original_checked(op,**params)
            client.status=status;client.checked=checked
            with patch('packed_supplies.collect_drop') as collected:
                with self.assertRaisesRegex(RuntimeError,'pad changed before recovery'):
                    fixture.run_withdrawal(client,4)
            record=json.loads((client.out/'packed-transfer-active.json').read_text())
            self.assertEqual(['old'],record['before_drop_uuids'])
            self.assertEqual('confirmed_open_box_before_close_and_tool_selection',record['drop_baseline_scope'])
            self.assertEqual('withdrawn',record['stage'])
            self.assertIsNone(record['recovery_preflight']['observed_state'])
            self.assertFalse(client.returned);collected.assert_not_called()
            self.assertFalse(any(op in ('recover_shulker','mine_block','collect_item') for op,_ in client.actions))

    def test_unchanged_pad_gets_one_recovery_with_preserved_baseline(self):
        from test_packed_supplies import EquipmentWithdrawalTest
        fixture=EquipmentWithdrawalTest()
        with tempfile.TemporaryDirectory() as folder:
            client=fixture.client(folder)
            record=fixture.run_withdrawal(client,4)
            self.assertTrue(client.returned)
            self.assertEqual(record['placed_state'],record['recovery_preflight']['observed_state'])
            self.assertEqual([],record['before_drop_uuids'])
            self.assertEqual(1,sum(op=='recover_shulker' for op,_ in client.actions))


if __name__=='__main__':unittest.main()
