import copy,unittest
from unittest.mock import patch
from kit_runtime.inventory import InventorySession

class Client:
    def __init__(self,furnace=False):
        self.calls=[];self.burned=0;self.furnace=furnace
        self.state={'menu':{'id':1,'type':'FurnaceMenu' if furnace else 'CraftingMenu','cursor':{'item':'minecraft:air','count':0},
                   'slots':[{'slot':i,'item':'minecraft:air','count':0} for i in range(12)]}}
        self.state['menu']['slots'][10].update(item='minecraft:coal',count=64)
    def status(self):return self.state
    def checked(self,op,**args):
        self.calls.append(args);menu=self.state['menu'];slot=menu['slots'][args['slot']];cursor=menu['cursor']
        assert slot['item']==args['expected_item'] and slot['count']==args['expected_count']
        if args.get('button')==1:
            if cursor['count']:
                slot['item']=cursor['item'];slot['count']+=1;cursor['count']-=1
                if not cursor['count']:cursor['item']='minecraft:air'
            else:
                n=(slot['count']+1)//2;cursor.update(item=slot['item'],count=n);slot['count']-=n
        else:
            if cursor['count'] and slot['item']==cursor['item']:
                slot['count']+=cursor['count'];cursor.update(item='minecraft:air',count=0)
            else:
                slot['item'],cursor['item']=cursor['item'],slot['item'];slot['count'],cursor['count']=cursor['count'],slot['count']
        if not slot['count']:slot['item']='minecraft:air'
        if self.furnace and args['slot']==1 and slot['count'] and not self.burned:
            self.burned=1;slot['count']-=1
            if not slot['count']:slot['item']='minecraft:air'
        return self.state

class InventorySessionTest(unittest.TestCase):
    def test_independent_clients_do_not_share_a_global_connection(self):
        a,b=Client(),Client()
        for client in (a,b):InventorySession(client).place_cell(client.state,copy.deepcopy(client.state['menu']['slots'][10]),1,1)
        self.assertEqual(3,len(a.calls));self.assertEqual(3,len(b.calls));self.assertEqual(63,a.state['menu']['slots'][10]['count'])
    def test_half_stack_and_small_transfer_both_preserve_exact_balance(self):
        for amount in (1,3,16,32,41,64):
            c=Client();InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,amount)
            self.assertEqual(amount,c.state['menu']['slots'][1]['count']);self.assertEqual(64-amount,c.state['menu']['slots'][10]['count']);self.assertEqual(0,c.state['menu']['cursor']['count'])
    def test_fuel_consumption_during_placement_does_not_repeat_a_click(self):
        c=Client(furnace=True);InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,3)
        self.assertEqual(7,len(c.calls));self.assertEqual(61,c.state['menu']['slots'][10]['count']);self.assertEqual(3,c.burned+c.state['menu']['slots'][1]['count'])
        self.assertEqual([(1,0)],[(a['slot'],a['button']) for a in c.calls if a['slot']==1])
    def test_occupied_cell_is_preserved_before_any_action(self):
        c=Client();c.state['menu']['slots'][1].update(item='minecraft:diamond',count=1)
        with self.assertRaises(ValueError):InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,1)
        self.assertEqual([],c.calls)
    def test_only_same_item_furnace_input_or_fuel_may_be_appended(self):
        for furnace,cell,item in ((False,1,'minecraft:coal'),(True,2,'minecraft:coal'),(True,0,'minecraft:diamond')):
            c=Client(furnace=furnace);c.state['menu']['slots'][cell].update(item=item,count=2)
            with self.assertRaises(ValueError):
                InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),cell,1,append=True)
            self.assertEqual([],c.calls)
        for cell in (0,1):
            c=Client(furnace=True);c.state['menu']['slots'][cell].update(item='minecraft:coal',count=2)
            InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),cell,3,append=True)
            self.assertEqual(5,c.state['menu']['slots'][cell]['count']+(c.burned if cell==1 else 0))
            self.assertEqual(61,c.state['menu']['slots'][10]['count'])
    def test_furnace_append_rejects_stack_overflow_without_clicks(self):
        c=Client(furnace=True);c.state['menu']['slots'][1].update(item='minecraft:coal',count=63)
        with self.assertRaises(ValueError):
            InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,3,append=True)
        self.assertEqual([],c.calls)
    def test_live_empty_stack_limit_does_not_restrict_crafting_or_furnace_inputs(self):
        for furnace,cell,amount,append in ((False,1,20,False),(True,0,20,False),(True,0,20,True),(True,1,3,True)):
            with self.subTest(furnace=furnace,cell=cell,amount=amount,append=append):
                c=Client(furnace=furnace)
                c.state['menu']['slots'][cell]['max_stack']=1
                c.state['menu']['slots'][10]['max_stack']=64
                InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),cell,amount,append=append)
                self.assertEqual(amount,c.state['menu']['slots'][cell]['count']+(c.burned if cell==1 else 0))
                self.assertEqual(64-amount,c.state['menu']['slots'][10]['count'])
                self.assertEqual(0,c.state['menu']['cursor']['count'])
    def test_empty_cell_uses_incoming_small_stack_limit(self):
        c=Client();c.state['menu']['slots'][1]['max_stack']=1
        c.state['menu']['slots'][10].update(item='minecraft:ender_pearl',count=16,max_stack=16)
        InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,16)
        self.assertEqual(16,c.state['menu']['slots'][1]['count'])
        c=Client();c.state['menu']['slots'][1]['max_stack']=1
        c.state['menu']['slots'][10].update(item='minecraft:ender_pearl',count=17,max_stack=16)
        with self.assertRaises(ValueError):
            InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,17)
        self.assertEqual([],c.calls)
    def test_fuel_burn_between_snapshot_and_native_click_retries_only_rejected_click(self):
        for rejected_at,detail in ((1,'Slot item changed'),(2,'Slot count changed')):
            class Consuming(Client):
                def __init__(self):
                    super().__init__(furnace=True);self.burned=1;self.consumed=0;self.attempts=0
                def checked(self,op,**args):
                    self.attempts+=1;fuel=self.state['menu']['slots'][1]
                    if args['slot']==1 and fuel['count']==rejected_at and not self.consumed:
                        fuel['count']-=1;self.consumed+=1
                        if not fuel['count']:fuel['item']='minecraft:air'
                        raise RuntimeError(detail)
                    return super().checked(op,**args)
            with self.subTest(rejected_at=rejected_at):
                c=Consuming();c.state['menu']['slots'][1].update(item='minecraft:coal',count=rejected_at)
                InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,3,append=True)
                self.assertEqual(3+rejected_at,c.state['menu']['slots'][1]['count']+c.consumed)
                self.assertEqual(61,c.state['menu']['slots'][10]['count']);self.assertEqual(0,c.state['menu']['cursor']['count'])
                self.assertEqual(7,len(c.calls));self.assertEqual(8,c.attempts)
    def test_furnace_rejection_does_not_retry_if_cursor_source_or_menu_changed(self):
        for changed in ('cursor','source','menu','other_inventory'):
            class Changed(Client):
                def __init__(self):super().__init__(furnace=True);self.burned=1;self.attempts=0
                def checked(self,op,**args):
                    self.attempts+=1;menu=self.state['menu'];fuel=menu['slots'][1]
                    if args['slot']==1 and fuel['count']:
                        fuel.update(item='minecraft:air',count=0)
                        if changed=='cursor':menu['cursor']['count']-=1
                        elif changed=='source':menu['slots'][3].update(item='minecraft:coal',count=1)
                        elif changed=='menu':menu['id']+=1
                        else:menu['slots'][9].update(item='minecraft:diamond',count=1)
                        raise RuntimeError('Slot item changed')
                    return super().checked(op,**args)
            with self.subTest(changed=changed):
                c=Changed();c.state['menu']['slots'][1].update(item='minecraft:coal',count=1)
                with self.assertRaisesRegex(RuntimeError,'context changed'):
                    InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,3,append=True)
                self.assertEqual(7,c.attempts);self.assertEqual(6,len(c.calls))
    def test_furnace_unknown_failure_is_never_retried(self):
        for detail in ('Native operation timed out; do not replay it','Reply lost','Container changed'):
            class Failed(Client):
                def __init__(self):super().__init__(furnace=True);self.attempts=0
                def checked(self,op,**args):
                    self.attempts+=1
                    if args['slot']==1:raise RuntimeError(detail)
                    return super().checked(op,**args)
            with self.subTest(detail=detail):
                c=Failed()
                with self.assertRaisesRegex(RuntimeError,detail):
                    InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,3,append=True)
                self.assertEqual(7,c.attempts);self.assertEqual(6,len(c.calls))
    def test_furnace_known_rejection_retry_count_is_bounded(self):
        class Rejecting(Client):
            def __init__(self):super().__init__(furnace=True);self.attempts=0
            def checked(self,op,**args):
                self.attempts+=1;fuel=self.state['menu']['slots'][1];fuel['count']-=1
                if not fuel['count']:fuel['item']='minecraft:air'
                raise RuntimeError('Slot count changed')
        c=Rejecting();c.state['menu']['slots'][1].update(item='minecraft:coal',count=3)
        c.state['menu']['cursor'].update(item='minecraft:coal',count=1)
        with self.assertRaisesRegex(RuntimeError,'rejection limit'):
            InventorySession(c)._place_furnace_click(c.state,10,1,1)
        self.assertEqual(3,c.attempts);self.assertEqual([],c.calls);self.assertEqual(1,c.state['menu']['cursor']['count'])
    def test_input_smelting_during_append_is_retried_with_output_conservation(self):
        class Smelting(Client):
            def __init__(self):super().__init__(furnace=True);self.consumed=False
            def checked(self,op,**args):
                if args['slot']==0 and not self.consumed:
                    self.consumed=True;self.state['menu']['slots'][0]['count']-=1
                    self.state['menu']['slots'][2].update(item='minecraft:stone',count=1)
                    raise RuntimeError('Slot count changed')
                return super().checked(op,**args)
        c=Smelting();c.state['menu']['slots'][0].update(item='minecraft:cobblestone',count=3)
        c.state['menu']['slots'][10].update(item='minecraft:cobblestone',count=20)
        InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),0,3,append=True)
        self.assertEqual((5,1),(c.state['menu']['slots'][0]['count'],c.state['menu']['slots'][2]['count']))
        self.assertEqual(17,c.state['menu']['slots'][10]['count']);self.assertEqual(0,c.state['menu']['cursor']['count'])
    def test_known_rejection_without_observed_consumption_does_not_repeat_click(self):
        class Unchanged(Client):
            def checked(self,op,**args):
                if args['slot']==1:raise RuntimeError('Slot count changed')
                return super().checked(op,**args)
        c=Unchanged(furnace=True)
        with patch('kit_runtime.inventory.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'consumption was not confirmed'):
                InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,3,append=True)
        self.assertEqual(6,len(c.calls));self.assertEqual(3,c.state['menu']['cursor']['count'])
    def test_small_fuel_batch_is_split_in_player_inventory_and_sent_once(self):
        for size,amount in ((49,3),(64,3),(64,4)):
            with self.subTest(size=size,amount=amount):
                c=Client(furnace=True);c.state['menu']['slots'][10]['count']=size
                InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,amount,append=True)
                self.assertEqual(amount,c.state['menu']['slots'][1]['count']+c.burned)
                self.assertEqual(size-amount,c.state['menu']['slots'][10]['count'])
                self.assertEqual(0,c.state['menu']['slots'][3]['count']);self.assertEqual(0,c.state['menu']['cursor']['count'])
                self.assertEqual([(1,0)],[(a['slot'],a['button']) for a in c.calls if a['slot']==1])
                self.assertLessEqual(len(c.calls),amount+4)
    def test_full_inventory_still_sends_fuel_once_without_unsafe_scratch_slot(self):
        c=Client(furnace=True)
        for row in c.state['menu']['slots'][3:]:
            if row['slot']!=10:row.update(item='minecraft:diamond',count=64)
        InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,3,append=True)
        self.assertEqual(3,c.state['menu']['slots'][1]['count']+c.burned)
        self.assertEqual(61,c.state['menu']['slots'][10]['count'])
        self.assertEqual([(1,0)],[(a['slot'],a['button']) for a in c.calls if a['slot']==1])
        self.assertTrue(all(row['item']=='minecraft:diamond' and row['count']==64 for row in c.state['menu']['slots'][3:] if row['slot']!=10))
    def test_positive_fuel_correction_is_not_misclassified_as_consumption(self):
        class Corrected(Client):
            def checked(self,op,**args):
                self.state['menu']['slots'][1].update(item='minecraft:coal',count=1)
                raise RuntimeError('Slot item changed')
        c=Corrected(furnace=True);c.state['menu']['cursor'].update(item='minecraft:coal',count=3)
        with self.assertRaisesRegex(RuntimeError,'beyond consumption'):
            InventorySession(c)._place_furnace_click(c.state,10,1,0)
        self.assertEqual([],c.calls);self.assertEqual(3,c.state['menu']['cursor']['count'])
    def test_delayed_pickup_observes_the_reply_without_repeating_the_click(self):
        class Delayed(Client):
            stale = None
            def checked(self, op, **args):
                old = copy.deepcopy(self.state)
                result = super().checked(op, **args)
                if len(self.calls) == 1:
                    self.stale = old
                    return old
                return result
            def status(self):
                if self.stale is not None:
                    old, self.stale = self.stale, None
                    return old
                return self.state
        c = Delayed()
        with patch('kit_runtime.inventory.time.sleep'):
            InventorySession(c).place_cell(c.state, copy.deepcopy(c.state['menu']['slots'][10]), 1, 1)
        self.assertEqual(3, len(c.calls)); self.assertEqual(63, c.state['menu']['slots'][10]['count'])
    def test_live_pickup_growth_uses_observed_cursor_total_without_replaying_pickup(self):
        class DelayedCollection(Client):
            def __init__(self):
                super().__init__();self.stale=[]
            def checked(self,op,**args):
                old=copy.deepcopy(self.state);result=super().checked(op,**args)
                if len(self.calls)==1:
                    self.state['menu']['cursor']['count']+=2
                    self.stale=[old,old]
                    return old
                return result
            def status(self):
                return self.stale.pop(0) if self.stale else self.state
        for amount,expected_source,expected_calls in ((1,48,3),(44,5,7)):
            with self.subTest(amount=amount):
                c=DelayedCollection();c.state['menu']['slots'][10]['count']=47
                with patch('kit_runtime.inventory.time.sleep'):
                    InventorySession(c).place_cell(
                        c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,amount)
                self.assertEqual(amount,c.state['menu']['slots'][1]['count'])
                self.assertEqual(expected_source,c.state['menu']['slots'][10]['count'])
                self.assertEqual(0,c.state['menu']['cursor']['count'])
                pickups=[call for call in c.calls if call['slot']==10
                         and call['expected_count']==47 and call['expected_cursor_count']==0]
                self.assertEqual(1,len(pickups));self.assertEqual(expected_calls,len(c.calls))
    def test_final_grid_cell_waits_through_optimistic_rollback_before_returning_remainder(self):
        class FinalCellRollback(Client):
            def __init__(self):
                super().__init__();self.pending=[];self.clock=100
                self.state['time']=self.clock
                self.state['menu']['slots'][10]['count']=6
            def checked(self,op,**args):
                before=copy.deepcopy(self.state)
                result=super().checked(op,**args)
                self.clock+=1;self.state['time']=self.clock
                # Reproduce the live final-cell sequence: the checked reply is
                # the optimistic cursor=5/cell=1 state, one fresh status rolls
                # back to cursor=6/cell=air, then the authoritative result lands.
                if args['slot']==1 and args.get('button')==1:
                    optimistic=copy.deepcopy(self.state)
                    rollback=copy.deepcopy(before);rollback['time']=self.clock+1
                    authoritative=copy.deepcopy(optimistic);authoritative['time']=self.clock+2
                    confirmed=copy.deepcopy(optimistic);confirmed['time']=self.clock+3
                    self.clock+=3;self.pending=[rollback,authoritative,confirmed]
                return result
            def status(self):
                if self.pending:return self.pending.pop(0)
                self.clock+=1;self.state['time']=self.clock
                return self.state
        c=FinalCellRollback()
        with patch('kit_runtime.inventory.time.sleep'):
            InventorySession(c).place_cell(
                c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,1)
        self.assertEqual((1,5,0),(c.state['menu']['slots'][1]['count'],
                         c.state['menu']['slots'][10]['count'],
                         c.state['menu']['cursor']['count']))
        cell_clicks=[call for call in c.calls if call['slot']==1 and call.get('button')==1]
        self.assertEqual(1,len(cell_clicks))
        return_clicks=[call for call in c.calls if call['slot']==10
                       and call['expected_cursor_count']==5]
        self.assertEqual(1,len(return_clicks))
    def test_full_pickup_allows_late_same_item_source_refill_and_preserves_total(self):
        class SourceRefill(Client):
            def checked(self,op,**args):
                result=super().checked(op,**args)
                if len(self.calls)==1:self.state['menu']['slots'][10].update(item='minecraft:coal',count=2)
                return result
        c=SourceRefill();c.state['menu']['slots'][10]['count']=47
        InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,1)
        self.assertEqual((1,48,0),(c.state['menu']['slots'][1]['count'],
                         c.state['menu']['slots'][10]['count'],c.state['menu']['cursor']['count']))
        self.assertEqual(1,sum(call['slot']==10 and call['expected_count']==47 for call in c.calls))
    def test_refilled_source_overflow_stops_before_any_followup_click(self):
        class Overflow(Client):
            def checked(self,op,**args):
                result=super().checked(op,**args)
                if len(self.calls)==1:self.state['menu']['slots'][10].update(item='minecraft:coal',count=40)
                return result
        c=Overflow();c.state['menu']['slots'][10]['count']=47
        with self.assertRaisesRegex(RuntimeError,'no longer fit'):
            InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,1)
        self.assertEqual(1,len(c.calls));self.assertEqual(47,c.state['menu']['cursor']['count'])
    def test_missing_pickup_acknowledgement_is_not_replayed(self):
        class NoReply(Client):
            def checked(self, op, **args):
                self.calls.append(args)
                return self.state
        c = NoReply()
        with patch('kit_runtime.inventory.time.monotonic', side_effect=[0, 7]):
            with self.assertRaisesRegex(RuntimeError, 'no action replay'):
                InventorySession(c).place_cell(c.state, copy.deepcopy(c.state['menu']['slots'][10]), 1, 1)
        self.assertEqual(1, len(c.calls))
    def test_ambiguous_full_pickup_delta_times_out_without_replay(self):
        class Ambiguous(Client):
            def checked(self,op,**args):
                self.calls.append(args)
                self.state['menu']['cursor'].update(item='minecraft:coal',count=46)
                self.state['menu']['slots'][10].update(item='minecraft:coal',count=1)
                return self.state
        c=Ambiguous();c.state['menu']['slots'][10]['count']=47
        with patch('kit_runtime.inventory.time.monotonic',side_effect=[0,7]):
            with self.assertRaisesRegex(RuntimeError,'no action replay'):
                InventorySession(c).place_cell(c.state,copy.deepcopy(c.state['menu']['slots'][10]),1,1)
        self.assertEqual(1,len(c.calls))
    def test_destination_changed_after_pickup_is_not_swapped_or_overwritten(self):
        class Changed(Client):
            def checked(self, op, **args):
                result = super().checked(op, **args)
                if len(self.calls) == 1:
                    self.state['menu']['slots'][1].update(item='minecraft:diamond', count=1)
                return result
        c = Changed()
        with self.assertRaisesRegex(RuntimeError, 'cell changed'):
            InventorySession(c).place_cell(c.state, copy.deepcopy(c.state['menu']['slots'][10]), 1, 1)
        self.assertEqual(1, len(c.calls)); self.assertEqual('minecraft:diamond', c.state['menu']['slots'][1]['item'])
    def test_second_container_requires_a_new_transaction_session(self):
        c = Client(); tx = InventorySession(c)
        tx.place_cell(c.state, copy.deepcopy(c.state['menu']['slots'][10]), 1, 1)
        before = len(c.calls); c.state['menu']['id'] = 2
        with self.assertRaisesRegex(RuntimeError, 'Container changed'):
            tx.place_cell(c.state, copy.deepcopy(c.state['menu']['slots'][10]), 2, 1)
        self.assertEqual(before, len(c.calls))
    def test_menu_change_while_waiting_is_never_a_retry(self):
        c=Client();tx=InventorySession(c)
        with self.assertRaisesRegex(RuntimeError,'Container changed'):tx._wait(c.state,2,lambda m:False,'test')
        self.assertEqual([],c.calls)
if __name__=='__main__':unittest.main()
