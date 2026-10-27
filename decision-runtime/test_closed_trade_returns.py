import unittest,copy
from unittest.mock import patch
from villager_trading import settle_closed_trade
class ClosedTradeTests(unittest.TestCase):
 def client(self,states):
  class Client:
   world='w';task='t'
   def __init__(self):self.calls=[];self.i=0
   def request(self,op):self.calls.append(op);s=copy.deepcopy(states[min(self.i,len(states)-1)]);self.i+=1;return s
  return Client()
 def state(self,n,t):return dict(connected=True,world_session='w',supervision_lease=dict(job_session='t'),health=20,manual_movement=False,screen='',time=t,menu=dict(type='InventoryMenu',id=0,cursor=dict(count=0)),inventory=[dict(slot=0,item='minecraft:stick',count=n)])
 def receipt(self):return dict(complete=True,pending=None,world_session='w',after={'minecraft:stick':32})
 def test_delayed_server_payment_return_requires_two_fresh_matching_frames(self):
  c=self.client([self.state(0,1),self.state(32,2),self.state(32,3)])
  with patch('villager_trading.time.sleep'):r=settle_closed_trade(c,self.receipt())
  self.assertEqual(r['confirmations'],[2,3]);self.assertEqual(r['purchases_sent'],0);self.assertEqual(c.calls,['snapshot']*3)
 def test_unknown_receipt_never_reads_or_repeats_a_trade(self):
  c=self.client([self.state(32,1)]);r=self.receipt();r['pending']='original_output_click'
  with self.assertRaises(RuntimeError):settle_closed_trade(c,r)
  self.assertEqual(c.calls,[])
 def test_intermediate_mismatch_resets_the_consecutive_observation_window(self):
  c=self.client([self.state(32,1),self.state(0,2),self.state(32,3),self.state(32,4)])
  with patch('villager_trading.time.sleep'):r=settle_closed_trade(c,self.receipt())
  self.assertEqual(r['confirmations'],[3,4])
 def test_manual_or_foreign_ui_cannot_be_adopted(self):
  for change in [{'manual_movement':True},{'screen':'MerchantScreen'},{'world_session':'other'}]:
   s=self.state(32,1);s.update(change);c=self.client([s])
   with self.subTest(change=change),self.assertRaises(RuntimeError):settle_closed_trade(c,self.receipt())
 def test_repeated_timestamp_does_not_supply_two_confirmations(self):
  c=self.client([self.state(32,1)])
  with patch('villager_trading.time.sleep'),patch('villager_trading.time.monotonic',side_effect=[0,0,21]),self.assertRaisesRegex(RuntimeError,'unconfirmed'):settle_closed_trade(c,self.receipt())
if __name__=='__main__':unittest.main()
