from copy import deepcopy
from types import SimpleNamespace
import unittest
from held_airlock_return import begin,return_through,require_restored
from library_airlock_route import closed

class Builder:
 def __init__(self,delay=False):
  self.book={'world_session':'world'};self.calls=[];self.pos=[760996.5,64.,797811.5];self.delay=delay;self.deferred=None
  self.lease={'id':'lease','job_session':'task','world_session':'world'};self.q=SimpleNamespace(world='world',lease=self.lease)
  self.rows={(x,63,797811):{'solid':True,'fluid':False}for x in range(760992,760999)}
  for x in (760993,760997):
   for y,half in [(64,'lower'),(65,'upper')]:self.rows[x,y,797811]={'state':f'Block{{minecraft:iron_door}}[facing=west,half={half},hinge=left,open=false,powered=false]'}
  self.rows[760996,64,797811]={'state':'Block{minecraft:lever}[face=floor,facing=east,powered=false]','passable':True,'fluid':False}
  self.entities=[];self.health=20;self.manual=False;self.fail_walk=False;self.fail_on=False;self.fail_off=False
 def check(self):return {'connected':True,'health':self.health,'manual_movement':self.manual,'world_session':'world','supervision_lease':dict(self.lease),'screen':'','pos':self.pos,'hand':{'item':'minecraft:netherite_sword'},'time':10000}
 def scan(self,*args):
  reply={'scan_entities':deepcopy(self.entities),'blocks':[dict(v,pos=list(k))for k,v in self.rows.items()],'time':10000,'world_session':'world'},deepcopy(self.rows)
  if self.deferred is not None:self.rows=self.deferred;self.deferred=None
  return reply
 def save(self):pass
 def n(self,op,**p):
  assert closed(self.rows,760993),'Never open the inner door during this held trip'
  self.calls.append((op,p))
  if op=='walk':
   if self.fail_walk:raise RuntimeError('Unknown walk terminal retained')
   self.pos=p['target']
  else:
   assert op=='interact'and p['pos']==[760996,64,797811]
   assert self.rows[760996,64,797811]['state']==p['expected_state']
   on='powered=false'in p['expected_state']
   if on and self.fail_on or not on and self.fail_off:raise RuntimeError('Unknown toggle terminal retained')
   later=deepcopy(self.rows)
   later[760996,64,797811]['state']=p['expected_state'].replace('powered=false','powered=true')if on else p['expected_state'].replace('powered=true','powered=false')
   for y in (64,65):
    text=later[760997,y,797811]['state'];later[760997,y,797811]['state']=text.replace('open=false','open=true').replace('powered=false','powered=true')if on else text.replace('open=true','open=false').replace('powered=true','powered=false')
   if self.delay:self.deferred=later
   else:self.rows=later
  return {'id':'request-'+str(len(self.calls))}

class Tests(unittest.TestCase):
 def test_delayed_server_states_are_observed_without_repeating_toggles(self):
  for delay in (False,True):
   b=Builder(delay);begin(b);self.assertTrue(closed(b.rows,760993));self.assertFalse(closed(b.rows,760997));self.assertEqual('held_for_return',b.book['held_return_gate']['phase'])
   with self.assertRaises(RuntimeError):require_restored(b.book)
   b.pos=[761024.5,65.,797810.3];return_through(b);require_restored(b.book)
   self.assertTrue(closed(b.rows,760993)and closed(b.rows,760997));self.assertEqual(2,sum(op=='interact'for op,p in b.calls));self.assertEqual(1,len(b.book['held_return_gate_history']))
   self.assertEqual([760994.5,64.,797811.5],[p['target']for op,p in b.calls if op=='walk'][-1])
 def test_unknown_outbound_walk_cannot_repeat_opening_or_be_marked_complete(self):
  b=Builder();b.fail_walk=True
  with self.assertRaises(RuntimeError):begin(b)
  count=len(b.calls)
  with self.assertRaises(RuntimeError):begin(b)
  with self.assertRaises(RuntimeError):return_through(b)
  with self.assertRaises(RuntimeError):require_restored(b.book)
  self.assertEqual(count,len(b.calls));self.assertTrue(b.book['held_return_gate']['pending'])
 def test_unknown_return_walk_never_replays_walk_or_close(self):
  b=Builder();begin(b);b.pos=[761024.5,65.,797811.5];b.fail_walk=True
  with self.assertRaises(RuntimeError):return_through(b)
  count=len(b.calls)
  with self.assertRaises(RuntimeError):return_through(b)
  self.assertEqual(count,len(b.calls));self.assertEqual('returning',b.book['held_return_gate']['phase'])
 def test_foreign_owner_world_manual_or_health_change_sends_no_return_input(self):
  for mode in ('lease','world','manual','health','missing_receipt'):
   b=Builder();begin(b);b.pos=[761024.5,65.,797811.5]
   if mode=='lease':b.q.lease=dict(b.lease,id='foreign')
   elif mode=='world':b.q.world='other'
   elif mode=='manual':b.manual=True
   elif mode=='health':b.health=19
   else:b.book['held_return_gate'].pop('on_request')
   count=len(b.calls)
   with self.assertRaises(RuntimeError):return_through(b)
   self.assertEqual(count,len(b.calls))
 def test_other_open_door_or_changed_owned_control_blocks_return(self):
  for mode in ('inner_open','control_off','relay_occupied'):
   b=Builder();begin(b);b.pos=[761024.5,65.,797811.5]
   if mode=='inner_open':b.rows[760993,65,797811]['state']=b.rows[760993,65,797811]['state'].replace('open=false','open=true')
   elif mode=='control_off':b.rows[760996,64,797811]['state']=b.rows[760996,64,797811]['state'].replace('powered=true','powered=false')
   else:b.entities=[{'type':'minecraft:villager','pos':[760995.5,64.,797811.5],'bounds':{'min':[760995.2,64,797811.2],'max':[760995.8,65.95,797811.8]}}]
   count=len(b.calls)
   with self.assertRaises(RuntimeError):return_through(b)
   self.assertEqual(count,len(b.calls))
 def test_stale_or_foreign_preflight_scan_is_not_reused(self):
  for key,value in [('time',8000),('world_session','foreign')]:
   b=Builder();begin(b);b.pos=[761024.5,65.,797811.5];scene,rows=b.scan();scene[key]=value;count=len(b.calls)
   with self.assertRaises(RuntimeError):return_through(b,(scene,rows))
   self.assertEqual(count,len(b.calls))
 def test_farthest_supplier_uses_bounded_native_walk_segments(self):
  b=Builder();begin(b);b.pos=[761032.5,65.,797811.5];before=len(b.calls);return_through(b);walks=[p['target']for op,p in b.calls[before:]if op=='walk'];self.assertEqual([[761014.5,64.,797811.5],[760994.5,64.,797811.5]],walks)
 def test_unknown_on_or_off_never_gets_a_second_toggle(self):
  for stage in ('on','off'):
   b=Builder()
   if stage=='on':
    b.fail_on=True
    with self.assertRaises(RuntimeError):begin(b)
   else:
    begin(b);b.pos=[761024.5,65.,797811.5];b.fail_off=True
    with self.assertRaises(RuntimeError):return_through(b)
   count=len(b.calls)
   with self.assertRaises(RuntimeError):begin(b)
   with self.assertRaises(RuntimeError):return_through(b)
   with self.assertRaises(RuntimeError):require_restored(b.book)
   self.assertEqual(count,len(b.calls))
 def test_closed_phase_alone_cannot_supply_missing_close_receipt_or_wrong_world(self):
  b=Builder();begin(b);b.pos=[761024.5,65.,797811.5];return_through(b)
  for mode in ('off_receipt','restored','world'):
   book=deepcopy(b.book);row=book['held_return_gate']
   if mode=='off_receipt':row.pop('off_request')
   elif mode=='restored':row['lever_restored']=False
   else:row['scope']['world_session']='foreign'
   with self.assertRaises(RuntimeError):require_restored(book)
if __name__=='__main__':unittest.main()
