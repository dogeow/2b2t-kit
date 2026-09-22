import copy
import unittest
from unittest.mock import patch
import craft_grid

class PickupTests(unittest.TestCase):
 def state(self,cursor=0,left=16):
  return {'menu':{'id':5,'cursor':{'item':'minecraft:iron_nugget' if cursor else 'minecraft:air','count':cursor},'slots':[{'slot':0,'item':'minecraft:iron_nugget' if left else 'minecraft:air','count':left}]}}
 def test_delayed_pickup_is_observed_not_replayed(self):
  initial=self.state();actual=self.state(16,0);calls=[]
  def action(op,**args):
   calls.append(args)
   if len(calls)==1:return copy.deepcopy(initial)
   actual['menu']['cursor']['count']-=1;actual['menu']['slots'][0]['count']+=1;actual['menu']['slots'][0]['item']='minecraft:iron_nugget';return copy.deepcopy(actual)
  class Client:
   def status(self):return copy.deepcopy(actual)
  with patch.object(craft_grid,'k',Client()),patch.object(craft_grid,'checked',side_effect=action),patch('craft_grid.time.sleep'):
   result=craft_grid.take_portion(initial,initial['menu']['slots'][0],10)
  self.assertEqual(result['menu']['cursor']['count'],10)
  self.assertEqual([v['button'] for v in calls],[0,1,1,1,1,1,1])
 def test_half_pickup_waits_for_exact_source_balance(self):
  initial=self.state(left=15);actual=self.state(8,7)
  class Client:
   def status(self):return actual
  with patch.object(craft_grid,'k',Client()),patch.object(craft_grid,'checked',return_value=initial) as click,patch('craft_grid.time.sleep'):
   result=craft_grid.take_portion(initial,initial['menu']['slots'][0],8)
  self.assertEqual(result['menu']['cursor']['count'],8);self.assertEqual(click.call_count,1)
 def test_occupied_cursor_and_insufficient_stock_do_not_click(self):
  for s,n in [(self.state(1),5),(self.state(),17)]:
   with patch.object(craft_grid,'checked') as click:
    with self.assertRaises(RuntimeError):craft_grid.take_portion(s,s['menu']['slots'][0],n)
    click.assert_not_called()
if __name__=='__main__':unittest.main()
