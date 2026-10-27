import unittest
from unittest.mock import patch
from villager_trading import settle_closed_trade


class Clock:
    def __init__(self):self.now=0
    def monotonic(self):return self.now
    def sleep(self,n):self.now+=n


class Bridge:
    world='world';task='task'
    def __init__(self,clock,*,refund_at=8,slow=0.5,changed=None):
        self.clock=clock;self.refund_at=refund_at;self.slow=slow;self.changed=changed;self.requests=[]
    def request(self,op):
        self.requests.append(op);self.clock.now+=self.slow
        s={'connected':True,'world_session':self.world,'supervision_lease':{'job_session':self.task},'health':20,'manual_movement':False,'screen':'',
           'menu':{'type':'InventoryMenu','id':0,'cursor':{'count':0}},'time':int(self.clock.now*1000),
           'inventory':[{'slot':0,'item':'minecraft:iron_ingot','count':61 if self.clock.now>=self.refund_at else 0}, {'slot':1,'item':'minecraft:emerald','count':1}]}
        if self.changed:self.changed(s,len(self.requests))
        return s


class ClosedTradeSettlementTests(unittest.TestCase):
    receipt={'complete':True,'pending':None,'world_session':'world','after':{'minecraft:iron_ingot':61,'minecraft:emerald':1}}
    def run_observation(self,bridge,clock,**kwargs):
        with patch('villager_trading.time',clock):return settle_closed_trade(bridge,self.receipt,**kwargs)
    def test_delayed_full_payment_return_is_only_observed_not_repurchased(self):
        clock=Clock();bridge=Bridge(clock)
        result=self.run_observation(bridge,clock)
        self.assertTrue(result['complete']);self.assertEqual(result['purchases_sent'],0)
        self.assertGreaterEqual(result['confirmations'][0],8000)
        self.assertGreater(result['confirmations'][1],result['confirmations'][0])
        self.assertEqual(set(bridge.requests),{'snapshot'})
    def test_an_explicit_short_budget_keeps_the_original_outcome_unresolved(self):
        clock=Clock();bridge=Bridge(clock)
        with self.assertRaisesRegex(RuntimeError,'remain unconfirmed'):self.run_observation(bridge,clock,seconds=6)
        self.assertEqual(set(bridge.requests),{'snapshot'})
    def test_the_second_correct_frame_is_not_discarded_for_a_slow_read(self):
        clock=Clock();bridge=Bridge(clock,refund_at=0,slow=.7)
        result=self.run_observation(bridge,clock,seconds=1)
        self.assertTrue(result['complete']);self.assertEqual(len(bridge.requests),2)
    def test_repeated_or_backward_frames_do_not_count_as_fresh_confirmation(self):
        for stamp in (700,600):
            clock=Clock();bridge=Bridge(clock,refund_at=0,slow=.7,changed=lambda s,n:s.update(time=700 if n==1 else stamp))
            with self.subTest(stamp=stamp),self.assertRaisesRegex(RuntimeError,'remain unconfirmed'):
                self.run_observation(bridge,clock,seconds=2)
    def test_scope_cursor_health_and_inventory_must_still_match(self):
        for kind in ('world','lease','cursor','health','manual','stock'):
            def changed(s,n):
                if kind=='world':s['world_session']='other'
                if kind=='lease':s['supervision_lease']['job_session']='other'
                if kind=='cursor':s['menu']['cursor']['count']=1
                if kind=='health':s['health']=18
                if kind=='manual':s['manual_movement']=True
                if kind=='stock':s['inventory'][0]['count']=60
            clock=Clock();bridge=Bridge(clock,refund_at=0,changed=changed)
            with self.subTest(kind=kind),self.assertRaises(RuntimeError):self.run_observation(bridge,clock,seconds=1)
            self.assertEqual(set(bridge.requests),{'snapshot'})


if __name__=='__main__':unittest.main()
