import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from material_depots import capacity,exchange,audit
from material_client import Client as NativeClient


def state(chest,carried):
    return {'menu':{'slots':chest+[{'count':0}]*36},
            'inventory':[{'slot':i,'item':k,'count':v} for i,(k,v) in enumerate(carried.items())]}


class StorageClient:
    """Vanilla-like slot operations; exercise the real Client.transfer path."""
    transfer=NativeClient.transfer
    def __init__(self,directory):
        self.out=Path(directory);self.calls=[];self.delay=False;self.stale=None
        self.menu={'id':1,'type':'ChestMenu','cursor':{'item':'minecraft:air','count':0},
                   'slots':[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1} for i in range(63)]}
    def status(self):
        if self.stale is not None:
            old,self.stale=self.stale,None;return old
        return copy.deepcopy({'menu':self.menu,'inventory':[
            dict(v,slot=i) for i,v in enumerate(self.menu['slots'][27:])]})
    def checked(self,op,**params):
        if op=='close_menu':return self.status()
        self.assert_click(params);old=self.status();self.calls.append(params)
        source=self.menu['slots'][params['slot']];cursor=self.menu['cursor']
        if params['kind']=='quick_move':
            pool=self.menu['slots'][:27] if params['slot']>=27 else self.menu['slots'][27:]
            for dest in sorted(pool,key=lambda v:not v['count']):
                if dest['count'] and dest['item']!=source['item']:continue
                limit=dest['max_stack'] if dest['count'] else source['max_stack']
                count=min(source['count'],limit-dest['count'])
                if count:dest.update(item=source['item'],count=dest['count']+count,max_stack=limit);source['count']-=count
                if not source['count']:break
        elif not cursor['count']:
            count=(source['count']+1)//2 if params['button']==1 else source['count']
            cursor.update(item=source['item'],count=count,max_stack=source['max_stack']);source['count']-=count
        elif not source['count'] or source['item']==cursor['item']:
            limit=source['max_stack'] if source['count'] else cursor['max_stack']
            count=min(1 if params['button']==1 else cursor['count'],limit-source['count'])
            source.update(item=cursor['item'],count=source['count']+count,max_stack=limit);cursor['count']-=count
        else:
            raise AssertionError('Transfer attempted to swap an unrelated stack')
        if not source['count']:source.update(item='minecraft:air',max_stack=1)
        if not cursor['count']:cursor.update(item='minecraft:air',max_stack=1)
        fresh=self.status()
        if self.delay and len(self.calls)==1:self.stale=old;return old
        return fresh
    def assert_click(self,params):
        assert params['menu_id']==self.menu['id']
        source=self.menu['slots'][params['slot']]
        assert (source['item'],source['count'])==(params['expected_item'],params['expected_count'])
    def put(self,slot,item,count,max_stack=64):self.menu['slots'][slot].update(item=item,count=count,max_stack=max_stack)

class DepotsTest(unittest.TestCase):
    def test_audit_counts_all_depots_but_excludes_carried_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=StorageClient(tmp);c.world='world';c.put(27,'minecraft:furnace',23)
            def opening(client,pos):
                client.put(0,'minecraft:furnace',pos[0]);s=client.status();s['time']=pos[0];return s
            original_status=c.status
            def status():s=original_status();s['time']=100;return s
            c.status=status
            with patch('material_depots.open_grounded_chest',side_effect=opening):
                result=audit(c,[[1,2,3],[4,5,6]],['minecraft:furnace','minecraft:arrow'])
            self.assertEqual({'minecraft:furnace':5,'minecraft:arrow':0},result['counts'])
            self.assertTrue(result['complete']);self.assertEqual(100,result['observed_at'])
            self.assertEqual([],c.calls)
    def test_audit_disconnect_never_returns_partial_stock_as_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=StorageClient(tmp);c.world='world';c.put(0,'minecraft:furnace',23)
            first=c.status();first['time']=1
            with patch('material_depots.open_grounded_chest',side_effect=[first,RuntimeError('disconnected')]):
                with self.assertRaisesRegex(RuntimeError,'disconnected'):
                    audit(c,[[1,2,3],[4,5,6]],['minecraft:furnace'])
            receipt=json.loads(next(c.out.glob('depot-audit-*.json')).read_text())
            self.assertFalse(receipt['complete']);self.assertEqual(1,len(receipt['visited']))
    def test_audit_rejects_duplicate_chest_coordinates_before_opening(self):
        with patch('material_depots.open_grounded_chest') as opened:
            with self.assertRaises(ValueError):audit(None,[[1,2,3],[1,2,3]],['minecraft:furnace'])
            opened.assert_not_called()
    def test_real_transfer_preserves_requested_deposit_reserve(self):
        for keep in (1,17,32,63):
            with self.subTest(keep=keep),tempfile.TemporaryDirectory() as tmp:
                c=StorageClient(tmp);c.put(27,'minecraft:cobblestone',64)
                with patch('material_depots.open_grounded_chest',side_effect=lambda c,p:c.status()):
                    result=exchange(c,[[1,2,3]],deposit={'minecraft:cobblestone':keep})
                self.assertTrue(result['complete'])
                self.assertEqual(keep,sum(v['count'] for v in c.menu['slots'][27:]))
                self.assertEqual(64-keep,sum(v['count'] for v in c.menu['slots'][:27]))
                self.assertEqual(0,c.menu['cursor']['count'])
    def test_real_transfer_fills_partial_slot_then_empty_slot_without_crossing_reserve(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=StorageClient(tmp);c.put(27,'minecraft:cobblestone',64);c.put(0,'minecraft:cobblestone',60)
            self.assertEqual(32,c.transfer('minecraft:cobblestone',32,deposit=True))
            self.assertEqual((64,28),(c.menu['slots'][0]['count'],c.menu['slots'][1]['count']))
            self.assertEqual(32,c.menu['slots'][27]['count'])
    def test_real_transfer_keeps_partial_chest_exchange_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=StorageClient(tmp);c.put(27,'minecraft:cobblestone',64);c.put(0,'minecraft:cobblestone',48)
            for slot in range(1,27):c.put(slot,'minecraft:stone',64)
            with patch('material_depots.open_grounded_chest',side_effect=lambda c,p:c.status()):
                result=exchange(c,[[1,2,3]],deposit={'minecraft:cobblestone':32})
            self.assertFalse(result['complete']);self.assertEqual({'minecraft:cobblestone':16},result['remaining_deposit'])
            self.assertEqual(48,c.menu['slots'][27]['count'])
    def test_real_withdrawal_stops_at_exact_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=StorageClient(tmp);c.put(0,'minecraft:sand',64)
            self.assertEqual(17,c.transfer('minecraft:sand',17))
            self.assertEqual(47,c.menu['slots'][0]['count']);self.assertEqual(17,c.menu['slots'][27]['count'])
    def test_live_empty_stack_limit_does_not_split_half_stack_transfer(self):
        for deposit in (True,False):
            with self.subTest(deposit=deposit),tempfile.TemporaryDirectory() as tmp:
                c=StorageClient(tmp);source=27 if deposit else 0;destination=0 if deposit else 27
                c.put(source,'minecraft:cobblestone',64)
                self.assertEqual(1,c.menu['slots'][destination]['max_stack'])
                self.assertEqual(32,c.transfer('minecraft:cobblestone',32,deposit=deposit))
                self.assertEqual((32,32),(c.menu['slots'][source]['count'],c.menu['slots'][destination]['count']))
                self.assertEqual(2,len(c.calls));self.assertEqual(0,c.menu['cursor']['count'])
    def test_exact_storage_transfer_uses_incoming_item_limit_for_empty_slot(self):
        from kit_runtime.inventory import InventorySession
        from kit_runtime.storage import move_amount
        with tempfile.TemporaryDirectory() as tmp:
            c=StorageClient(tmp);c.put(27,'minecraft:ender_pearl',16,max_stack=16);s=c.status()
            move_amount(InventorySession(c),s,s['menu']['slots'][27],s['menu']['slots'][0],16)
            self.assertEqual(16,c.menu['slots'][0]['count']);self.assertEqual(2,len(c.calls))
            c=StorageClient(tmp);c.put(27,'minecraft:ender_pearl',16,max_stack=16);c.put(0,'minecraft:ender_pearl',15,max_stack=16);s=c.status()
            with self.assertRaises(ValueError):
                move_amount(InventorySession(c),s,s['menu']['slots'][27],s['menu']['slots'][0],2)
            self.assertEqual([],c.calls)
    def test_delayed_partial_transfer_acknowledgement_is_observed_without_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=StorageClient(tmp);c.put(27,'minecraft:cobblestone',64);c.delay=True
            with patch('kit_runtime.inventory.time.sleep'):
                self.assertEqual(63,c.transfer('minecraft:cobblestone',63,deposit=True))
            self.assertEqual(3,len(c.calls));self.assertEqual(1,c.menu['slots'][0]['count'])
    def test_exact_transfer_conserves_odd_stack_sizes_and_every_reserve(self):
        with tempfile.TemporaryDirectory() as tmp:
            for size in (1,3,7,31,64):
                for keep in range(size):
                    for initial in (0,63):
                        with self.subTest(size=size,keep=keep,initial=initial):
                            c=StorageClient(tmp);c.put(27,'minecraft:cobblestone',size)
                            if initial:c.put(0,'minecraft:cobblestone',initial)
                            self.assertEqual(keep,c.transfer('minecraft:cobblestone',keep,deposit=True))
                            self.assertEqual(initial+size-keep,sum(v['count'] for v in c.menu['slots'][:27]))
                            self.assertEqual(keep,sum(v['count'] for v in c.menu['slots'][27:]))
                            self.assertEqual(0,c.menu['cursor']['count'])
    def test_missing_partial_pickup_acknowledgement_never_replays_click(self):
        class NoReply(StorageClient):
            def checked(self,op,**params):self.calls.append(params);return self.status()
        with tempfile.TemporaryDirectory() as tmp:
            c=NoReply(tmp);c.put(27,'minecraft:cobblestone',64)
            with patch('kit_runtime.inventory.time.monotonic',side_effect=[0,7]):
                with self.assertRaisesRegex(RuntimeError,'no action replay'):
                    c.transfer('minecraft:cobblestone',63,deposit=True)
            self.assertEqual(1,len(c.calls));self.assertEqual(64,c.menu['slots'][27]['count'])
    def test_capacity_excludes_player_slots_and_other_materials(self):
        s=state([{'item':'minecraft:white_concrete','count':48,'max_stack':64},
                 {'item':'minecraft:stone','count':1},{'item':'minecraft:air','count':0}],{})
        self.assertEqual(80,capacity(s,'minecraft:white_concrete'))
    def test_partial_first_chest_does_not_abort_before_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            class Client:
                out=Path(tmp);held={'minecraft:white_concrete':64};current=[];visits=[]
                def status(self):return state(self.current,self.held)
                def transfer(self,item,target,deposit=False):
                    self.held[item]=target;return target
                def checked(self,*args,**kwargs):pass
            c=Client()
            def opening(client,pos):
                client.visits.append(pos)
                client.current=[{'item':'minecraft:white_concrete','count':48 if pos[0]==1 else 0,'max_stack':64}]
                return client.status()
            with patch('material_depots.open_grounded_chest',side_effect=opening):
                result=exchange(c,[[1,2,3],[4,5,6]],deposit={'minecraft:white_concrete':0})
            self.assertTrue(result['complete']);self.assertEqual(2,len(c.visits))
            rows=[json.loads(x) for x in (c.out/'depot-exchanges.jsonl').read_text().splitlines()]
            self.assertEqual(48,rows[0]['after']['minecraft:white_concrete'])
    def test_newly_freed_raw_slot_is_used_before_next_withdrawal(self):
        with tempfile.TemporaryDirectory() as tmp:
            class Client:
                out=Path(tmp);held={'minecraft:white_concrete':128,'minecraft:sand':0};actions=[]
                chest=[{'item':'minecraft:sand','count':64},{'item':'minecraft:sand','count':64}]
                def status(self):
                    result=state(self.chest,self.held)
                    # One empty ordinary backpack slot at the start.
                    result['inventory'].append({'slot':2,'item':'minecraft:air','count':0})
                    return result
                def transfer(self,item,target,deposit=False):
                    self.actions.append(('deposit' if deposit else 'withdraw',item))
                    if deposit:
                        empty=next(v for v in self.chest if not v['count']);empty.update(item=item,count=64)
                    else:
                        src=next(v for v in self.chest if v['item']==item and v['count']);src.update(item='minecraft:air',count=0)
                    self.held[item]=target
                def checked(self,*args,**kwargs):pass
            c=Client()
            with patch('material_depots.open_grounded_chest',side_effect=lambda c,p:c.status()):
                result=exchange(c,[[1,2,3]],deposit={'minecraft:white_concrete':0},withdraw={'minecraft:sand':128})
            self.assertTrue(result['complete'])
            self.assertEqual(['withdraw','deposit','withdraw','deposit'],[v[0] for v in c.actions])

    def test_no_open_when_targets_already_met(self):
        class Client:
            def status(self):return state([],{'minecraft:sand':128})
        with patch('material_depots.open_grounded_chest') as opened:
            result=exchange(Client(),[[1,2,3]],withdraw={'minecraft:sand':128})
            self.assertTrue(result['complete']);opened.assert_not_called()

if __name__=='__main__':unittest.main()
