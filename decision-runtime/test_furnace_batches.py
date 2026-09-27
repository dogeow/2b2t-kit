import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from furnace_batches import collect,distribution,load,recipe_balance,wait_loading_balance
from test_inventory_session import Client as InventoryClient


class LoadingClient(InventoryClient):
 world='w'
 def __init__(self):
  super().__init__(furnace=True)
  self.state['menu']['slots'][9].update(item='minecraft:stone',count=64)
  self.state['menu']['slots'][10].update(item='minecraft:stone',count=64)
  self.state['menu']['slots'][11].update(item='minecraft:coal',count=16)
 def status(self):
  s=copy.deepcopy(self.state)
  s['inventory']=[dict(v,slot=i) for i,v in enumerate(s['menu']['slots'][3:])]
  return s
 def checked(self,op,**args):
  if op=='close_menu':return self.status()
  super().checked(op,**args)
  return self.status()


class FurnaceBankClient(LoadingClient):
 """Actual slot clicks against distinct furnace menus and a shared inventory."""
 def __init__(self,raw=(64,54),coal=(2,)*9):
  super().__init__()
  self.state['menu']['slots']=[{'slot':i,'item':'minecraft:air','count':0} for i in range(39)]
  for i,(item,count) in enumerate([('minecraft:cobblestone',n) for n in raw]+[('minecraft:coal',n) for n in coal],3):
   self.state['menu']['slots'][i].update(item=item,count=count)
  self.furnaces={};self.active=None;self.after_click=None;self.hot=False
 def open(self,pos):
  self.active=tuple(pos);self.state['menu']['id']+=1;self.burned=0
  self.state['menu']['slots'][:3]=copy.deepcopy(self.furnaces.get(self.active,
      [{'slot':i,'item':'minecraft:air','count':0} for i in range(3)]))
  return self.status()
 def checked(self,op,**args):
  if op=='close_menu':
   self.furnaces[self.active]=copy.deepcopy(self.state['menu']['slots'][:3]);return self.status()
  result=super().checked(op,**args)
  if self.hot and self.state['menu']['slots'][0]['count']:
   inp,out=self.state['menu']['slots'][0],self.state['menu']['slots'][2]
   inp['count']-=1
   if not inp['count']:inp['item']='minecraft:air'
   out.update(item='minecraft:stone',count=out['count']+1)
  if self.after_click:self.after_click(self,args)
  return self.status()


class FurnaceBatchTest(unittest.TestCase):
 def test_parallel_distribution_preserves_total(self):
  self.assertEqual([20,20,20,20,19,19],distribution(118,6))
  self.assertEqual([28,28,28,28,27,27],distribution(166,6))
 def test_expected_input_plus_output_conservation(self):
  def row(item,count):return {'item':'minecraft:'+item,'count':count}
  rows=[row('stone',6),row('coal',2),row('smooth_stone',14)]
  self.assertTrue(recipe_balance(rows,'minecraft:stone','minecraft:smooth_stone',20))
  rows[2]['count']=13;self.assertFalse(recipe_balance(rows,'minecraft:stone','minecraft:smooth_stone',20))
  rows[2]=row('iron_ingot',14);self.assertFalse(recipe_balance(rows,'minecraft:stone','minecraft:smooth_stone',20))
 def test_second_furnace_failure_preserves_full_plan_and_cannot_complete_half_batch(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'batch.json';client=LoadingClient()
   def opening(c,pos):
    if pos==[4,5,6]:raise RuntimeError('Approach interrupted')
    return c.status()
   with patch('furnace_batches.snapshot',side_effect=opening):
    with self.assertRaisesRegex(RuntimeError,'Approach interrupted'):
     load(client,[[1,2,3],[4,5,6]],'minecraft:stone','minecraft:smooth_stone',128,path)
   job=json.loads(path.read_text())
   self.assertEqual(128,sum(e['amount'] for e in job['furnaces']))
   self.assertEqual(['loaded','planned'],[e['stage'] for e in job['furnaces']])
   self.assertFalse(job['complete'])
   with patch('furnace_batches.snapshot') as opened:
    with self.assertRaisesRegex(RuntimeError,'Partial furnace loading'):collect(client,path)
    opened.assert_not_called()
   self.assertFalse(json.loads(path.read_text())['complete'])
 def test_fragmented_source_and_coal_load_the_entire_parallel_bank(self):
  with tempfile.TemporaryDirectory() as d:
   client=FurnaceBankClient();path=Path(d)/'batch.json'
   with patch('furnace_batches.snapshot',side_effect=lambda c,p:c.open(p)):
    job=load(client,[[i,2,3] for i in range(6)],'minecraft:cobblestone','minecraft:stone',118,path)
   self.assertEqual([20,20,20,20,19,19],[e['loaded_source'] for e in job['furnaces']])
   self.assertTrue(all(e['loaded_fuel']==3 and e['stage']=='loaded' for e in job['furnaces']))
   self.assertEqual(118,sum(rows[0]['count'] for rows in client.furnaces.values()))
   self.assertEqual(12,sum(rows[1]['count'] for rows in client.furnaces.values()))
   self.assertTrue(all(v['count']==0 for v in client.state['menu']['slots'][3:]))
   self.assertEqual(0,client.state['menu']['cursor']['count'])
   self.assertEqual(job,json.loads(path.read_text()))
 def test_furnace_may_smelt_while_appending_batch_fragments(self):
  with tempfile.TemporaryDirectory() as d:
   client=FurnaceBankClient(raw=(4,15),coal=(1,2));client.hot=True
   with patch('furnace_batches.snapshot',side_effect=lambda c,p:c.open(p)):
    job=load(client,[[1,2,3]],'minecraft:cobblestone','minecraft:stone',19,Path(d)/'batch.json')
   self.assertEqual('loaded',job['furnaces'][0]['stage'])
   rows=client.furnaces[(1,2,3)]
   self.assertTrue(recipe_balance(rows,'minecraft:cobblestone','minecraft:stone',19))
   self.assertGreater(rows[2]['count'],0)
 def test_initial_matching_contents_are_not_claimed_or_overwritten(self):
  with tempfile.TemporaryDirectory() as d:
   client=FurnaceBankClient(raw=(20,),coal=(3,));rows=copy.deepcopy(client.state['menu']['slots'][:3])
   rows[0].update(item='minecraft:cobblestone',count=1);client.furnaces[(1,2,3)]=rows
   with patch('furnace_batches.snapshot',side_effect=lambda c,p:c.open(p)):
    with self.assertRaisesRegex(RuntimeError,'pre-existing'):
     load(client,[[1,2,3]],'minecraft:cobblestone','minecraft:stone',20,Path(d)/'batch.json')
   self.assertEqual([],client.calls);self.assertEqual(rows,client.furnaces[(1,2,3)])
 def test_changed_second_fragment_target_stops_before_another_deposit(self):
  with tempfile.TemporaryDirectory() as d:
   client=FurnaceBankClient(raw=(4,15),coal=(3,));path=Path(d)/'batch.json'
   def mutate(c,args):
    if len(c.calls)==3:c.state['menu']['slots'][0].update(item='minecraft:diamond',count=1)
   client.after_click=mutate
   with patch('furnace_batches.snapshot',side_effect=lambda c,p:c.open(p)):
    with self.assertRaisesRegex(RuntimeError,'Furnace cell changed'):
     load(client,[[1,2,3]],'minecraft:cobblestone','minecraft:stone',19,path)
   self.assertEqual(3,len(client.calls));self.assertEqual('minecraft:diamond',client.state['menu']['slots'][0]['item'])
   entry=json.loads(path.read_text())['furnaces'][0]
   self.assertEqual(('input_loading',15,0),(entry['stage'],entry['loaded_source'],entry['loaded_fuel']))
 def test_changed_same_item_count_fails_conservation_and_does_not_load_fuel(self):
  with tempfile.TemporaryDirectory() as d:
   client=FurnaceBankClient(raw=(4,15),coal=(3,));path=Path(d)/'batch.json'
   def mutate(c,args):
    if len(c.calls)==2:c.state['menu']['slots'][0]['count']-=1
   client.after_click=mutate
   with patch('furnace_batches.snapshot',side_effect=lambda c,p:c.open(p)),\
        patch('furnace_batches.time.monotonic',side_effect=[0,0,0,0,6]),patch('furnace_batches.time.sleep'):
    with self.assertRaisesRegex(RuntimeError,'contents changed'):
     load(client,[[1,2,3]],'minecraft:cobblestone','minecraft:stone',19,path)
   self.assertEqual(2,len(client.calls));self.assertFalse(any(a['slot']==1 for a in client.calls))
   self.assertEqual(0,json.loads(path.read_text())['furnaces'][0]['loaded_source'])
 def test_late_furnace_output_packet_is_observed_after_source_or_fuel_without_replay(self):
  for lag_after_cell in (0,1):
   class SplitPackets(FurnaceBankClient):
    pending=0;lagged=False;observations=0
    def checked(self,op,**args):
     result=super().checked(op,**args)
     if op=='slot_click' and args['slot']==lag_after_cell and not self.lagged:
      self.lagged=True;self.state['menu']['slots'][0]['count']-=1;self.pending=3
      return self.status()
     return result
    def status(self):
     if self.pending:
      self.observations+=1;self.pending-=1
      if not self.pending:self.state['menu']['slots'][2].update(item='minecraft:stone',count=1)
     return super().status()
   with self.subTest(lag_after_cell=lag_after_cell),tempfile.TemporaryDirectory() as d,patch('furnace_batches.time.sleep'):
    baseline=FurnaceBankClient(raw=(20,),coal=(3,));delayed=SplitPackets(raw=(20,),coal=(3,))
    for name,client in [('baseline',baseline),('delayed',delayed)]:
     with patch('furnace_batches.snapshot',side_effect=lambda c,p:c.open(p)):
      job=load(client,[[1,2,3]],'minecraft:cobblestone','minecraft:stone',20,Path(d)/(name+'.json'))
     self.assertEqual('loaded',job['furnaces'][0]['stage'])
    self.assertEqual(baseline.calls,delayed.calls)
    self.assertGreaterEqual(delayed.observations,3)
    self.assertEqual((19,1),(delayed.furnaces[(1,2,3)][0]['count'],delayed.furnaces[(1,2,3)][2]['count']))
 def test_delayed_fragment_pickup_is_observed_without_click_replay(self):
  class Delayed(FurnaceBankClient):
   stale=None
   def checked(self,op,**args):
    old=self.status();result=super().checked(op,**args)
    if op=='slot_click' and len(self.calls)==3:self.stale=old;return old
    return result
   def status(self):
    if self.stale is not None:
     old,self.stale=self.stale,None;return old
    return super().status()
  with tempfile.TemporaryDirectory() as d,patch('kit_runtime.inventory.time.sleep'):
   baseline=FurnaceBankClient(raw=(4,15),coal=(1,2));delayed=Delayed(raw=(4,15),coal=(1,2))
   for name,client in [('baseline',baseline),('delayed',delayed)]:
    with patch('furnace_batches.snapshot',side_effect=lambda c,p:c.open(p)):
     load(client,[[1,2,3]],'minecraft:cobblestone','minecraft:stone',19,Path(d)/(name+'.json'))
   self.assertEqual(baseline.calls,delayed.calls)
   self.assertEqual(baseline.furnaces,delayed.furnaces)
 def test_changed_container_during_second_fragment_has_no_further_click(self):
  with tempfile.TemporaryDirectory() as d:
   client=FurnaceBankClient(raw=(4,15),coal=(3,));path=Path(d)/'batch.json'
   def mutate(c,args):
    if len(c.calls)==3:c.state['menu']['id']+=1
   client.after_click=mutate
   with patch('furnace_batches.snapshot',side_effect=lambda c,p:c.open(p)):
    with self.assertRaisesRegex(RuntimeError,'Container changed'):
     load(client,[[1,2,3]],'minecraft:cobblestone','minecraft:stone',19,path)
   self.assertEqual(3,len(client.calls));self.assertEqual(15,json.loads(path.read_text())['furnaces'][0]['loaded_source'])
 def test_missing_second_fragment_ack_is_not_replayed_or_marked_loaded(self):
  class Missing(FurnaceBankClient):
   def checked(self,op,**args):
    if op=='slot_click' and len(self.calls)==2:
     self.calls.append(args);return self.status()
    return super().checked(op,**args)
  with tempfile.TemporaryDirectory() as d:
   client=Missing(raw=(4,15),coal=(3,));path=Path(d)/'batch.json'
   with patch('furnace_batches.snapshot',side_effect=lambda c,p:c.open(p)),\
        patch('kit_runtime.inventory.time.monotonic',side_effect=[0,0,0,0,7]):
    with self.assertRaisesRegex(RuntimeError,'no action replay'):
     load(client,[[1,2,3]],'minecraft:cobblestone','minecraft:stone',19,path)
   self.assertEqual(3,len(client.calls));entry=json.loads(path.read_text())['furnaces'][0]
   self.assertEqual(('input_loading',15,0),(entry['stage'],entry['loaded_source'],entry['loaded_fuel']))
   with patch('furnace_batches.snapshot') as opened:
    with self.assertRaisesRegex(RuntimeError,'Partial furnace loading'):collect(client,path)
    opened.assert_not_called()
 def test_old_incomplete_journal_is_rejected_before_any_collection(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'batch.json'
   path.write_text(json.dumps({'world_session':'w','amount':128,'complete':False,
       'furnaces':[{'pos':[1,2,3],'amount':64,'stage':'loaded'}]}))
   with patch('furnace_batches.snapshot') as opened:
    with self.assertRaisesRegex(RuntimeError,'entire requested batch'):collect(LoadingClient(),path)
    opened.assert_not_called()
   self.assertFalse(json.loads(path.read_text())['complete'])

class FurnaceCollectionTest(unittest.TestCase):
 def test_completed_output_is_collected_and_journaled_once(self):
  import tempfile,json
  from pathlib import Path
  from unittest.mock import patch
  from furnace_batches import collect
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'batch.json';p.write_text(json.dumps({'world_session':'w','amount':20,'source':'minecraft:stone','output':'minecraft:smooth_stone','furnaces':[{'pos':[1,2,3],'amount':20,'stage':'loaded'}]}))
   state={'inventory':[],'menu':{'id':1,'type':'FurnaceMenu','slots':[{'item':'minecraft:air','count':0},{'item':'minecraft:air','count':0},{'item':'minecraft:smooth_stone','count':20}]}}
   class Client:
    world='w'
    def status(self):return state
    def checked(self,*args,**kwargs):return state
   def click(s,slot,kind):
    self.assertEqual((2,'quick_move'),(slot,kind));state['inventory']=[{'slot':0,'item':'minecraft:smooth_stone','count':20}];state['menu']['slots'][2]={'item':'minecraft:air','count':0};return state
   with patch('furnace_batches.snapshot',return_value=state),patch('furnace_batches.InventorySession.click',side_effect=click) as clicked:
    self.assertTrue(collect(Client(),p));self.assertTrue(collect(Client(),p));self.assertEqual(1,clicked.call_count)
   self.assertTrue(json.loads(p.read_text())['complete'])


class FurnaceObservationTest(unittest.TestCase):
 def state(self):
  return {'world_session':'w','control_revision':7,'connected':True,'manual_movement':False,
          'menu':{'id':4,'type':'FurnaceMenu','cursor':{'item':'minecraft:air','count':0},
                  'slots':[{'item':'minecraft:cobblestone','count':19},{'item':'minecraft:coal','count':1},
                           {'item':'minecraft:air','count':0}]}}
 def client(self,states):
  class ReadOnly:
   reads=0
   def status(self):
    self.reads+=1
    if isinstance(states,Exception):raise states
    return copy.deepcopy(states[min(self.reads-1,len(states)-1)])
   def checked(self,*args,**kwargs):raise AssertionError('Observation must not dispatch clicks')
   def request(self,*args,**kwargs):raise AssertionError('Observation must only read existing status')
  return ReadOnly()
 def observe(self,c,state):return wait_loading_balance(c,state,'minecraft:cobblestone','minecraft:stone',20,3,4)
 def test_missing_packet_times_out_within_six_seconds_without_actions(self):
  s=self.state();c=self.client([s])
  with patch('furnace_batches.time.monotonic',side_effect=[0,6]),patch('furnace_batches.time.sleep') as sleep:
   with self.assertRaisesRegex(RuntimeError,'within six seconds; do not replay'):self.observe(c,s)
  self.assertEqual(1,c.reads);sleep.assert_called_once_with(.15)
 def test_unknown_items_and_excess_fuel_are_rejected_without_waiting(self):
  for cell,item,count in ((0,'minecraft:diamond',19),(1,'minecraft:lava_bucket',1),(2,'minecraft:iron_ingot',1),(1,'minecraft:coal',4)):
   with self.subTest(cell=cell,item=item,count=count):
    s=self.state();s['menu']['slots'][cell].update(item=item,count=count);c=self.client([s])
    with patch('furnace_batches.time.sleep') as sleep:
     with self.assertRaisesRegex(RuntimeError,'contents changed'):self.observe(c,s)
     sleep.assert_not_called()
    self.assertEqual(0,c.reads)
 def test_menu_world_control_or_manual_changes_stop_during_observation(self):
  for change in ('menu_id','menu_type','world_session','control_revision','manual_movement','connected'):
   with self.subTest(change=change):
    s=self.state();changed=copy.deepcopy(s)
    if change=='menu_id':changed['menu']['id']=5
    elif change=='menu_type':changed['menu']['type']='ChestMenu'
    elif change=='world_session':changed[change]='another'
    elif change=='control_revision':changed[change]=8
    elif change=='manual_movement':changed[change]=True
    else:changed[change]=False
    c=self.client([changed])
    with patch('furnace_batches.time.sleep'):
     with self.assertRaisesRegex(RuntimeError,'changed'):self.observe(c,s)
    self.assertEqual(1,c.reads)
 def test_native_handoff_from_status_is_propagated_without_retry(self):
  from material_client import Handoff
  c=self.client(Handoff('Control or world changed; no more commands'))
  with patch('furnace_batches.time.sleep'):
   with self.assertRaises(Handoff):self.observe(c,self.state())
  self.assertEqual(1,c.reads)

if __name__=='__main__':unittest.main()
