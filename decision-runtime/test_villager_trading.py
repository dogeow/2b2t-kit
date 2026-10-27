from collections import Counter
from copy import deepcopy
from pathlib import Path
import json,tempfile,unittest
from unittest.mock import patch
from villager_trading import book_matches,candidates,buy_one,verify_reopened_lock,_settle_purchase_hand,open as open_merchant

def stack(item='minecraft:air',count=0,**extra):return {'item':item,'count':count,**extra}
BOOK=stack('minecraft:enchanted_book',1,stored_enchantments=[{'id':'minecraft:mending','level':1}])
class Clock:
    now=0
    def monotonic(self):return self.now
    def sleep(self,n):self.now+=n
class Merchant:
    world='w';task='t';server='simpcraft.com';last='before'
    def __init__(self,root,no_effect=False):
        self.root=self.out=Path(root);self.calls=[];self.no_effect=no_effect;self.tick=0
        self.offer={'index':0,'cost_a':stack('minecraft:emerald',12),'cost_b':stack('minecraft:book',1),'result':deepcopy(BOOK),'out_of_stock':False,'uses':0}
        self.menu={'type':'MerchantMenu','id':7,'material_owned':True,'cursor':stack(),
            'slots':[stack(),stack(),stack(),stack('minecraft:emerald',20),stack('minecraft:book',3),stack()],
            'merchant':{'protocol':1,'owned':True,'owner_task':'t','villager_uuid':'v','offers_fingerprint':'fp','offers':[self.offer],'trader_xp':0}}
        for i,v in enumerate(self.menu['slots']):v['slot']=i
    def status(self):
        self.tick+=1
        return {'time':self.tick,'world_session':'w','health':20,'guard_busy':False,'connected':True,'manual_movement':False,
                'guard_armed':True,'guard_pve_only':True,'supervision_lease':{'job_session':'t'},
                'menu':deepcopy(self.menu),'inventory':[{'slot':i,**deepcopy(v)}for i,v in enumerate(self.menu['slots'][3:])]}
    def checked(self,op,**params):
        self.calls.append((op,params));self.last='request-'+str(len(self.calls));m=self.menu
        if op=='merchant_select_trade':
            m['slots'][0].update(item='minecraft:emerald',count=20);m['slots'][1].update(item='minecraft:book',count=3)
            m['slots'][3].update(item='minecraft:air',count=0);m['slots'][4].update(item='minecraft:air',count=0);m['slots'][2].update(deepcopy(BOOK))
        elif params['slot']==2:
            if not self.no_effect:
                m['slots'][0]['count']-=12;m['slots'][1]['count']-=1;m['cursor']=deepcopy(BOOK);m['slots'][2].update(stack())
        else:
            m['slots'][params['slot']].update(m['cursor']);m['cursor']=stack()
        return {'phase':'done','id':self.last}

class VillagerTradingTests(unittest.TestCase):
    def test_plain_emerald_sale_merges_output_without_consuming_another_slot(self):
        with tempfile.TemporaryDirectory()as tmp:
            c=Merchant(tmp)
            c.offer.update(cost_a=stack('minecraft:iron_ingot',4),cost_b=stack(),
                           result=stack('minecraft:emerald',1,max_stack=64,stack_data={'id':'minecraft:emerald','count':1}))
            c.menu['slots'][3]=dict(slot=3,**stack('minecraft:emerald',23,max_stack=64))
            c.menu['slots'][4]=dict(slot=4,**stack('minecraft:iron_ingot',64,max_stack=64))
            def click(op,**p):
                c.calls.append((op,p));c.last='r'+str(len(c.calls));m=c.menu
                if op=='merchant_select_trade':
                    m['slots'][0].update(item='minecraft:iron_ingot',count=64)
                    m['slots'][4].update(item='minecraft:air',count=0);m['slots'][2].update(item='minecraft:emerald',count=1)
                elif p['slot']==2:
                    m['slots'][0]['count']-=4;m['slots'][2].update(item='minecraft:air',count=0);m['cursor']=stack('minecraft:emerald',1)
                else:
                    self.assertEqual(p['slot'],3);self.assertEqual(p['expected_count'],23)
                    m['slots'][3]['count']+=m['cursor']['count'];m['cursor']=stack()
                return {'id':c.last,'phase':'done'}
            c.checked=click;result=buy_one(c,0,Path(tmp)/'sale')
            self.assertTrue(result['complete']);self.assertEqual(result['output_destination'],3)
            self.assertEqual(c.menu['slots'][3]['count'],24);self.assertEqual(c.menu['slots'][5]['count'],0)
    def test_second_purchase_from_same_opening_is_rejected_before_any_selection(self):
        import hashlib
        with tempfile.TemporaryDirectory()as tmp:
            c=Merchant(tmp);c.menu['merchant']['opening_request_id']='same-opening'
            previous={'complete':True,'pending':None,'world_session':'w','uuid':'v','opening_request_id':'same-opening'}
            path=Path(tmp)/'previous.json';path.write_text(json.dumps(previous));scope=hashlib.sha256(b'simpcraft.com|minecraft:overworld').hexdigest()[:20];registry=Path(tmp)/'merchant-trades'/scope;registry.mkdir(parents=True);(registry/'active.json').write_text(json.dumps({'journal':str(path)}))
            with self.assertRaisesRegex(RuntimeError,'fresh server quote'):buy_one(c,0,Path(tmp)/'second')
            self.assertEqual([],c.calls)
    def test_new_server_opening_allows_another_purchase_after_prior_completion(self):
        import hashlib
        with tempfile.TemporaryDirectory()as tmp:
            c=Merchant(tmp);c.menu['merchant']['opening_request_id']='new-opening'
            previous={'complete':True,'pending':None,'world_session':'w','uuid':'v','opening_request_id':'old-opening'}
            path=Path(tmp)/'previous.json';path.write_text(json.dumps(previous));scope=hashlib.sha256(b'simpcraft.com|minecraft:overworld').hexdigest()[:20];registry=Path(tmp)/'merchant-trades'/scope;registry.mkdir(parents=True);(registry/'active.json').write_text(json.dumps({'journal':str(path)}))
            result=buy_one(c,0,Path(tmp)/'second');self.assertTrue(result['complete']);self.assertEqual('merchant_select_trade',c.calls[0][0])
    def test_existing_payments_need_return_space_before_any_new_selection(self):
        with tempfile.TemporaryDirectory()as tmp:
            c=Merchant(tmp);c.menu['slots'][0].update(item='minecraft:emerald',count=1)
            c.menu['slots'][1].update(item='minecraft:book',count=1)
            with self.assertRaisesRegex(RuntimeError,'payment return slots'):buy_one(c,0,Path(tmp)/'purchase')
            self.assertEqual([],c.calls)
    def test_destination_is_chosen_after_returned_payments_fill_the_old_empty_slot(self):
        class BreadMerchant(Merchant):
            def __init__(self,root):
                super().__init__(root)
                self.offer.update(cost_a=stack('minecraft:emerald',1),cost_b=stack(),result=stack('minecraft:bread',6))
                self.menu['slots']=[stack('minecraft:wheat',20),stack(),stack(),stack(),stack(),stack(),stack('minecraft:emerald',8)]
                for i,v in enumerate(self.menu['slots']):v['slot']=i
            def checked(self,op,**params):
                self.calls.append((op,params));self.last='request-'+str(len(self.calls));m=self.menu
                if op=='merchant_select_trade':
                    m['slots'][3].update(stack('minecraft:wheat',20));m['slots'][0].update(stack('minecraft:emerald',8))
                    m['slots'][6].update(stack());m['slots'][2].update(stack('minecraft:bread',6))
                elif params['slot']==2:
                    m['slots'][0]['count']-=1;m['cursor']=stack('minecraft:bread',6);m['slots'][2].update(stack())
                else:m['slots'][params['slot']].update(m['cursor']);m['cursor']=stack()
                return {'phase':'done','id':self.last}
        with tempfile.TemporaryDirectory()as tmp:
            c=BreadMerchant(tmp);clock=Clock()
            with patch('villager_trading.time.monotonic',clock.monotonic),patch('villager_trading.time.sleep',clock.sleep):r=buy_one(c,0,Path(tmp)/'purchase')
            self.assertTrue(r['complete']);self.assertEqual(4,r['output_destination'])
            self.assertEqual('minecraft:wheat',c.menu['slots'][3]['item'])
            self.assertEqual({'minecraft:wheat':20,'minecraft:emerald':7,'minecraft:bread':6},r['after'])
    def test_exact_max_level_book_and_no_curses(self):
        self.assertTrue(book_matches(BOOK,'minecraft:mending',1))
        self.assertFalse(book_matches(BOOK,'minecraft:infinity',1))
        bad=deepcopy(BOOK);bad['stored_enchantments'].append({'id':'minecraft:binding_curse','level':1})
        self.assertFalse(book_matches(bad,'minecraft:mending',1))
        for value in (2,4):
            row=stack('minecraft:enchanted_book',1,stored_enchantments=[{'id':'minecraft:unbreaking','level':value}])
            self.assertFalse(book_matches(row,'minecraft:unbreaking',3))
    def test_catalog_does_not_select_exhausted_or_wrong_level_offers(self):
        offer={'result':BOOK,'out_of_stock':False};info={'protocol':1,'offers':[offer]}
        self.assertEqual('minecraft:mending',candidates(info)[0]['enchantment'])
        offer['out_of_stock']=True;self.assertEqual([],candidates(info))
    def test_one_purchase_conserves_payment_and_stores_cursor_without_bulk_buy(self):
        with tempfile.TemporaryDirectory()as tmp:
            c=Merchant(tmp);clock=Clock()
            with patch('villager_trading.time.monotonic',clock.monotonic),patch('villager_trading.time.sleep',clock.sleep):result=buy_one(c,0,Path(tmp)/'purchase')
            self.assertTrue(result['complete']);self.assertTrue(result['do_not_reroll']);self.assertFalse(result['lock_server_verified'])
            self.assertTrue(c.merchant_purchase_hand_pending)
            self.assertEqual(result['after'],c.merchant_purchase_hand_expected_counts)
            self.assertEqual({'minecraft:emerald':8,'minecraft:book':2,'minecraft:enchanted_book':1},result['after'])
            clicks=[p for op,p in c.calls if op=='slot_click'];self.assertEqual(2,len(clicks));self.assertTrue(all(p['kind']=='pickup'and p['button']==0 for p in clicks))
            self.assertIsNone(result['pending']);self.assertEqual(3,len(result['verified_stages']))
    def test_done_without_inventory_effect_remains_pending_and_blocks_new_directory(self):
        with tempfile.TemporaryDirectory()as tmp:
            c=Merchant(tmp,no_effect=True);clock=Clock()
            with patch('villager_trading.time.monotonic',clock.monotonic),patch('villager_trading.time.sleep',clock.sleep):
                with self.assertRaisesRegex(RuntimeError,'unconfirmed'):buy_one(c,0,Path(tmp)/'purchase')
            book=json.loads((Path(tmp)/'purchase/one-trade.json').read_text());self.assertFalse(book['complete']);self.assertEqual('slot_click',book['pending']['op'])
            count=len(c.calls)
            with self.assertRaisesRegex(RuntimeError,'unresolved'):buy_one(c,0,Path(tmp)/'different-directory')
            self.assertEqual(count,len(c.calls))
    def test_only_new_same_actor_server_xp_can_verify_lock(self):
        purchase={'complete':True,'uuid':'v','trader_xp_before':0,'opening_request_id':'first'}
        fresh={'villager_uuid':'v','protocol':1,'trader_xp':1,'opening_request_id':'second','offers':[{}],
               'observation_scope':'current_server_received_merchant_menu_not_trade_completion'}
        self.assertTrue(verify_reopened_lock(purchase,fresh)['locked'])
        for observed in ({**fresh,'villager_uuid':'other'},{**fresh,'trader_xp':0},{**fresh,'opening_request_id':'first'},
                         {**fresh,'offers':[]},{**fresh,'observation_scope':'predicted'}):
            with self.assertRaises(RuntimeError):verify_reopened_lock(purchase,observed)

class PurchaseReopenHandTests(unittest.TestCase):
    def test_current_sleeping_adult_is_refused_before_sending_an_entity_use(self):
        c=self.Client();c.merchant_purchase_hand_pending=False
        with tempfile.TemporaryDirectory()as folder:
            c.root=Path(folder)
            with patch('villager_events.read',return_value={'villagers':[{'uuid':'villager','sleeping':True}]}):
                with self.assertRaisesRegex(ValueError,'asleep'):open_merchant(c,{'uuid':'villager','id':1},Path(folder)/'opening')
            proof=json.loads((Path(folder)/'opening/open.json').read_text());self.assertFalse(proof['interaction_sent']);self.assertFalse(proof['pending'])
        self.assertEqual(c.calls,[])

    def test_sleep_that_begins_during_hand_preparation_still_sends_no_entity_use(self):
        c=self.Client()
        with tempfile.TemporaryDirectory()as folder:
            c.root=Path(folder)
            frames=[{'villagers':[{'uuid':'villager','sleeping':False}]},{'villagers':[{'uuid':'villager','sleeping':True}]}]
            with patch('villager_events.read',side_effect=frames):
                with self.assertRaisesRegex(ValueError,'asleep'):open_merchant(c,{'uuid':'villager','id':1},Path(folder)/'opening')
            proof=json.loads((Path(folder)/'opening/open.json').read_text());self.assertFalse(proof['interaction_sent'])
        self.assertEqual([op for op,_ in c.calls],['select_item'])
    class Client:
        world='world';task='task';last='close-menu';merchant_purchase_hand_pending=True
        def __init__(self):
            self.calls=[];self.tick=0
            self.merchant_purchase_hand_expected_counts={'minecraft:netherite_sword':1,'minecraft:emerald':4}
            self.merchant_purchase_hand_trade_items=('minecraft:emerald',)
            self.state={'world_session':'world','connected':True,'health':20,'manual_movement':False,
                'guard_busy':False,'guard_armed':True,'guard_pve_only':True,'screen':'',
                'supervision_lease':{'job_session':'task'},'menu':{'type':'InventoryMenu','cursor':stack()},
                'hand':stack('minecraft:emerald',4),
                'inventory':[{'slot':0,**stack('minecraft:netherite_sword',1)},
                             {'slot':1,**stack('minecraft:emerald',4)}]}
        def status(self):
            self.tick+=1
            return {'time':self.tick,**deepcopy(self.state)}
        def checked(self,op,**params):
            self.calls.append((op,params));self.last='selection'
            self.state['hand']=stack(params['item'],1)
            return {'phase':'done','id':self.last}

    def test_post_payment_hand_preparation_preserves_inventory_and_sends_no_trade(self):
        c=self.Client();before=c.status()['inventory'];_settle_purchase_hand(c)
        self.assertEqual([('select_item',{'item':'minecraft:netherite_sword'})],c.calls)
        self.assertEqual(before,c.status()['inventory'])

    def test_damaged_mending_tool_stays_selected_by_exact_hotbar_slot(self):
        c=self.Client();tool=stack('minecraft:diamond_pickaxe',1,durability=411,max_durability=1561,
                                  enchantments=[{'id':'minecraft:mending','level':1}])
        c.state['inventory'].append(dict(tool,slot=5));c.state.update(hand=deepcopy(tool),selected_slot=5)
        c.merchant_purchase_hand_expected_counts['minecraft:diamond_pickaxe']=1
        def selected(op,**params):
            c.calls.append((op,params));c.last='selection';c.state['hand']=deepcopy(tool)
            c.state['hand']['durability']=500
            return {'phase':'done','id':c.last}
        c.checked=selected
        proof=_settle_purchase_hand(c)
        self.assertEqual(c.calls,[('select_item',{'item':'minecraft:diamond_pickaxe','slot':5})])
        self.assertTrue(proof['selected_repair_tool_preserved'])

    def test_unknown_selection_does_not_open_a_merchant_or_repeat_the_purchase(self):
        c=self.Client()
        def unknown(op,**params):
            c.calls.append((op,params));raise RuntimeError('selection outcome unknown')
        c.checked=unknown
        with tempfile.TemporaryDirectory()as tmp:
            with self.assertRaisesRegex(RuntimeError,'outcome unknown'):
                open_merchant(c,{'uuid':'villager','id':1},Path(tmp)/'open')
        self.assertEqual(['select_item'],[op for op,_ in c.calls])
        self.assertTrue(c.merchant_purchase_hand_pending)

    def test_takeover_or_changed_inventory_after_selection_stops_before_entity_input(self):
        for change in ('guard','inventory','lease'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as tmp:
                c=self.Client();original=c.checked
                def changed(op,**params):
                    reply=original(op,**params)
                    if change=='guard':c.state['guard_busy']=True
                    elif change=='inventory':c.state['inventory'][1]['count']+=1
                    else:c.state['supervision_lease']['job_session']='other'
                    return reply
                c.checked=changed
                clock=Clock()
                with patch('villager_trading.time.monotonic',clock.monotonic),patch('villager_trading.time.sleep',clock.sleep):
                    with self.assertRaisesRegex(RuntimeError,'no merchant interaction'):
                        open_merchant(c,{'uuid':'villager','id':1},Path(tmp)/'open')
                self.assertEqual(['select_item'],[op for op,_ in c.calls])

    def test_payment_return_must_match_completed_purchase_before_selection_and_reconverge_after_it(self):
        c=self.Client();c.state['inventory'][1]=dict(slot=1,**stack('minecraft:stick',98))
        c.state['inventory'].append(dict(slot=2,**stack('minecraft:emerald',7)))
        c.merchant_purchase_hand_expected_counts={'minecraft:netherite_sword':1,'minecraft:stick':98,'minecraft:emerald':7}
        c.merchant_purchase_hand_trade_items=('minecraft:stick','minecraft:emerald')
        original_status=c.status;original_checked=c.checked
        def delayed():
            q=original_status()
            # 32 leftover sticks arrive after menu closure. A later inventory
            # frame can briefly lag again while the selected slot settles.
            if c.tick<=2 or c.tick==5:q['inventory'][1]['count']=66
            return q
        def select(op,**params):
            self.assertGreaterEqual(c.tick,4)
            return original_checked(op,**params)
        c.status=delayed;c.checked=select;clock=Clock()
        with patch('villager_trading.time.monotonic',clock.monotonic),patch('villager_trading.time.sleep',clock.sleep):
            _settle_purchase_hand(c)
        self.assertGreaterEqual(c.tick,7)
        self.assertEqual(['select_item'],[op for op,_ in c.calls])

    def test_unreturned_payment_is_not_accepted_as_a_stable_inventory(self):
        c=self.Client();c.state['inventory'][1]['count']=3;clock=Clock()
        with patch('villager_trading.time.monotonic',clock.monotonic),patch('villager_trading.time.sleep',clock.sleep):
            with self.assertRaisesRegex(RuntimeError,'no merchant interaction'):_settle_purchase_hand(c)
        self.assertEqual([],c.calls)

    def test_independent_food_pickup_is_preserved_but_never_trade_credit(self):
        c=self.Client();c.state['inventory'].append(dict(slot=2,**stack('minecraft:potato',1)))
        clock=Clock()
        with patch('villager_trading.time.monotonic',clock.monotonic),patch('villager_trading.time.sleep',clock.sleep):
            proof=_settle_purchase_hand(c)
        self.assertEqual({'minecraft:potato':1},proof['incidental_positive_counts'])
        self.assertFalse(proof['incidental_counts_are_trade_credit'])
        self.assertEqual(1,c.state['inventory'][2]['count'])

    def test_other_carried_property_cannot_disappear_during_selection(self):
        c=self.Client();c.state['inventory'].append(dict(slot=2,**stack('minecraft:book',3)))
        c.merchant_purchase_hand_expected_counts['minecraft:book']=3
        original=c.checked
        def lost(op,**params):
            result=original(op,**params);c.state['inventory'][2]['count']=2;return result
        c.checked=lost;clock=Clock()
        with patch('villager_trading.time.monotonic',clock.monotonic),patch('villager_trading.time.sleep',clock.sleep):
            with self.assertRaisesRegex(RuntimeError,'no merchant interaction'):_settle_purchase_hand(c)
        self.assertEqual(['select_item'],[op for op,_ in c.calls])

    def test_ordinary_quote_does_not_prepare_a_post_purchase_hand(self):
        c=self.Client();c.merchant_purchase_hand_pending=False
        def interact(op,**params):
            c.calls.append((op,params));c.last='opening';return {'phase':'done'}
        c.checked=interact
        info={'villager_uuid':'villager','offers':[{}]}
        with tempfile.TemporaryDirectory()as tmp,patch('villager_trading.owned_info',return_value=({'id':2},info)):
            open_merchant(c,{'uuid':'villager','id':1},Path(tmp)/'open')
        self.assertEqual(['interact_entity'],[op for op,_ in c.calls])
        self.assertFalse(c.merchant_purchase_hand_pending)

if __name__=='__main__':unittest.main()
