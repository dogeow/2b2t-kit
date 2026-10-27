from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json

from villager_trading import candidates,lock_payment,lock_wanted
from test_villager_trading import Merchant,stack,BOOK

TARGETS={'minecraft:mending':1}

def quote():
    return {'protocol':1,'level':1,'trader_xp':0,'villager_uuid':'v',
            'owned':True,'owner_task':'t','offers_fingerprint':'fp','opening_request_id':'first',
            'observation_scope':'current_server_received_merchant_menu_not_trade_completion',
            'offers':[
                {'index':0,'cost_a':stack('minecraft:emerald',12),'cost_b':stack('minecraft:book',1),
                 'result':deepcopy(BOOK),'uses':0,'out_of_stock':False},
                {'index':1,'cost_a':stack('minecraft:paper',24),'cost_b':stack(),
                 'result':stack('minecraft:emerald',1),'uses':0,'out_of_stock':False},
                {'index':2,'cost_a':stack('minecraft:emerald',9),'cost_b':stack(),
                 'result':stack('minecraft:bookshelf',1),'uses':0,'out_of_stock':False}]}

class PaymentTests(TestCase):
    def choose(self,stock,**kw):
        info=quote();return lock_payment(info,candidates(info,TARGETS)[0],stock,**kw)

    def test_paper_locks_without_spending_a_blank_book_or_emeralds(self):
        p=self.choose({'minecraft:paper':24,'minecraft:emerald':20,'minecraft:book':1})
        self.assertEqual('paper_sale',p['kind']);self.assertEqual(1,p['offer']['index'])

    def test_desired_book_and_bounded_bookshelf_fallbacks(self):
        self.assertEqual('wanted_book',self.choose({'minecraft:emerald':12,'minecraft:book':1})['kind'])
        self.assertEqual('bookshelf_purchase',self.choose({'minecraft:emerald':9})['kind'])
        self.assertIsNone(self.choose({'minecraft:emerald':8}))
        self.assertIsNone(self.choose({'minecraft:emerald':20,'minecraft:book':1},max_emeralds=0))

    def test_reserves_and_paper_budget_do_not_supply_imaginary_payments(self):
        self.assertIsNone(self.choose({'minecraft:paper':24},keep={'minecraft:paper':1}))
        self.assertIsNone(self.choose({'minecraft:paper':24},max_paper=23))
        for value in(True,-1,65):
            with self.assertRaises(ValueError):self.choose({},max_paper=value)

    def test_wrong_stale_unavailable_or_component_cost_quote_is_not_paid(self):
        info=quote();selected=candidates(info,TARGETS)[0];info['offers'][0]['cost_a']['count']=13
        with self.assertRaisesRegex(RuntimeError,'absent'):lock_payment(info,selected,{'minecraft:paper':24})
        info=quote();info['offers'][1]['out_of_stock']=True
        self.assertIsNone(lock_payment(info,candidates(info,TARGETS)[0],{'minecraft:paper':24}))
        info=quote();info['offers'][1]['cost_a']['stack_data']={'id':'minecraft:paper','count':24,'components':{'minecraft:custom_name':'treasure'}}
        self.assertIsNone(lock_payment(info,candidates(info,TARGETS)[0],{'minecraft:paper':24}))

class OwnedMerchant(Merchant):
    def __init__(self,root):
        super().__init__(root);self.menu['merchant']=quote()
        self.menu['slots']=[stack(),stack(),stack(),stack('minecraft:paper',24),stack('minecraft:emerald',10),stack()]
        for i,row in enumerate(self.menu['slots']):row['slot']=i
    def checked(self,op,**params):
        self.calls.append((op,params));self.last='request-'+str(len(self.calls))
        if op!='close_menu':raise AssertionError('Unexpected direct native operation')
        return {'phase':'done','id':self.last}

class LockWorkflowTests(TestCase):
    def purchase(self,c,index,out):
        self.assertEqual(1,index)
        return {'complete':True,'uuid':'v','trader_xp_before':0,'opening_request_id':'first',
                'after':{'minecraft:emerald':11},'offer':deepcopy(c.menu['merchant']['offers'][index])}
    def reopen(self,c,actor,out):
        self.assertEqual('v',actor['uuid']);info=c.menu['merchant'];info['opening_request_id']='second';info['trader_xp']=2
        return c.status()
    def ready(self,c):
        original=c.status
        def status():
            state=original();state['loaded_villagers']={'villagers':[{'id':1,'uuid':'v','health':20,'is_baby':False}]};return state
        c.status=status

    def test_exactly_one_sale_and_fresh_reopen_prove_lock_not_book_purchase(self):
        with TemporaryDirectory()as tmp:
            c=OwnedMerchant(tmp);self.ready(c)
            with patch('villager_trading.buy_one',side_effect=self.purchase)as buy,patch('villager_trading.open',side_effect=self.reopen)as reopen:
                result=lock_wanted(c,TARGETS,Path(tmp)/'lock')
            self.assertEqual(1,buy.call_count);self.assertEqual(1,reopen.call_count)
            self.assertTrue(result['complete']);self.assertTrue(result['locked']);self.assertFalse(result['book_purchased'])
            self.assertEqual(['close_menu','close_menu'],[op for op,_ in c.calls])

    def test_unknown_sale_is_preserved_without_close_reopen_or_second_sale(self):
        with TemporaryDirectory()as tmp:
            c=OwnedMerchant(tmp);self.ready(c);out=Path(tmp)/'lock'
            with patch('villager_trading.buy_one',side_effect=RuntimeError('unknown original purchase'))as buy,patch('villager_trading.open')as reopen:
                with self.assertRaisesRegex(RuntimeError,'unknown original'):lock_wanted(c,TARGETS,out)
            self.assertEqual(1,buy.call_count);reopen.assert_not_called();self.assertEqual([],c.calls)
            journal=json.loads((out/'lock-wanted.json').read_text());self.assertEqual('one_purchase',journal['pending']);self.assertFalse(journal['complete'])
            with self.assertRaises(FileExistsError):lock_wanted(c,TARGETS,out)

    def test_unchanged_opening_does_not_turn_a_predicted_purchase_into_a_lock(self):
        with TemporaryDirectory()as tmp:
            c=OwnedMerchant(tmp);self.ready(c)
            def same_opening(c,actor,out):c.menu['merchant']['trader_xp']=2;return c.status()
            with patch('villager_trading.buy_one',side_effect=self.purchase)as buy,patch('villager_trading.open',side_effect=same_opening):
                with self.assertRaisesRegex(RuntimeError,'Fresh server'):lock_wanted(c,TARGETS,Path(tmp)/'lock')
            self.assertEqual(1,buy.call_count)

    def test_incomplete_purchase_receipt_never_triggers_cleanup_or_reopen(self):
        with TemporaryDirectory()as tmp:
            c=OwnedMerchant(tmp);self.ready(c)
            with patch('villager_trading.buy_one',return_value={'complete':False,'pending':'original_click'})as buy,patch('villager_trading.open')as reopen:
                with self.assertRaisesRegex(RuntimeError,'incomplete'):lock_wanted(c,TARGETS,Path(tmp)/'lock')
            self.assertEqual(1,buy.call_count);self.assertEqual([],c.calls);reopen.assert_not_called()

    def test_full_inventory_preserves_wanted_quote_without_trying_a_purchase(self):
        with TemporaryDirectory()as tmp:
            c=OwnedMerchant(tmp);self.ready(c);c.menu['slots'][-1].update(item='minecraft:cobblestone',count=64)
            with patch('villager_trading.buy_one')as buy:
                result=lock_wanted(c,TARGETS,Path(tmp)/'lock')
            buy.assert_not_called();self.assertTrue(result['waiting_for_output_space']);self.assertFalse(result['locked'])
            self.assertNotIn('waiting_for_payment',result)

    def test_no_highest_book_no_payment_and_used_or_named_property_never_buys(self):
        for change in('no_wanted','no_stock','used','named'):
            with self.subTest(change=change),TemporaryDirectory()as tmp:
                c=OwnedMerchant(tmp);self.ready(c)
                if change=='no_wanted':c.menu['merchant']['offers'][0]['result']['stored_enchantments']=[{'id':'minecraft:unbreaking','level':2}]
                if change=='no_stock':
                    for row in c.menu['slots'][3:]:row.update(item='minecraft:air',count=0)
                if change=='used':c.menu['merchant']['trader_xp']=2
                if change=='named':c.menu['slots'][3]['custom_name']='keep me'
                with patch('villager_trading.buy_one')as buy:
                    if change=='named':
                        with self.assertRaisesRegex(RuntimeError,'Non-plain'):lock_wanted(c,TARGETS,Path(tmp)/'lock')
                    else:self.assertFalse(lock_wanted(c,TARGETS,Path(tmp)/'lock')['locked'])
                buy.assert_not_called()
