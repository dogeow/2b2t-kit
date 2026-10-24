import unittest
from library_airlock_route import require_path,require_empty_relay,closed,cross
BUTTON='Block{minecraft:cherry_button}[face=wall,facing=south,powered=false]'
class Tests(unittest.TestCase):
 def rows(self):
  return {(x,63,797811):{'solid':True,'fluid':False}for x in range(760992,760999)}
 def doors(self,rows):
  for x in (760993,760997):
   for y,half in [(64,'lower'),(65,'upper')]:rows[x,y,797811]={'state':f'Block{{minecraft:iron_door}}[facing=west,half={half},hinge=left,open=false,powered=false]'}
  return rows
 def test_missing_floor_fluid_chest_and_nonpassable_body_refused(self):
  points=[[760992.5,64,797811.5]]*2
  for change in [('floor',None),('floor',{'solid':True,'fluid':True}),('body',{'passable':False,'fluid':False}),('body',{'passable':True,'fluid':True})]:
   rows=self.rows();key=(760992,63 if change[0]=='floor'else 64,797811)
   if change[1]is None:rows.pop(key)
   else:rows[key]=change[1]
   with self.assertRaises(RuntimeError):require_path(rows,points)
 def test_safe_passable_nonfluid_button_does_not_block_walk(self):
  rows=self.rows();rows[760992,65,797811]={'state':BUTTON,'passable':True,'fluid':False};require_path(rows,[[760992.5,64,797811.5]]*2)
 def actor(self,x,z=797811.5):return {'type':'minecraft:villager','pos':[x,64,z],'bounds':{'min':[x-.3,64,z-.3],'max':[x+.3,65.95,z+.3]}}
 def test_baby_or_adult_in_relay_blocks_opening(self):
  for baby in (True,False):
   a=self.actor(760995.5);a['is_baby']=baby
   with self.assertRaises(RuntimeError):require_empty_relay({'scan_entities':[a]})
 def test_villager_approaching_door_blocks_opening(self):
  with self.assertRaises(RuntimeError):require_empty_relay({'scan_entities':[self.actor(760991.5)]},760993)
 def test_other_open_or_powered_or_missing_half_is_not_closed(self):
  for bad in ['open=true','powered=true','missing']:
   r=self.doors({});r[760997,65,797811]['state']=r[760997,65,797811]['state'].replace('open=false',bad)if bad!='powered=true'else r[760997,65,797811]['state'].replace('powered=false',bad)
   self.assertFalse(closed(r,760997))
 def test_no_interaction_when_other_door_open_or_resident_in_relay(self):
  for occupied in (False,True):
   r=self.doors(self.rows());r[760992,65,797811]={'state':BUTTON};scene={'scan_entities':[self.actor(760995.5)]if occupied else []}
   if not occupied:r[760997,65,797811]['state']=r[760997,65,797811]['state'].replace('open=false','open=true')
   class B:
    book={}
    def scan(self,*args):return scene,r
    def n(self,*a,**kw):raise AssertionError('No input allowed')
   with self.assertRaises(RuntimeError):cross(B(),760993,760992,[760994.5,64,797811.5])
 def test_only_physically_enclosed_adjacent_adult_is_exempt_from_proximity(self):
  from library_airlock_route import enclosed_neighbor
  r={};full={'state':'Block{minecraft:cobblestone}','solid':True,'fluid':False,'block_entity':False}
  for z in range(797805,797810):
   r[760998,63,z]=dict(full)
   for y in range(64,68):
    if z in (797805,797809):r[760998,y,z]=dict(full)
    for x in (760997,760999):r[x,y,z]=dict(full)
   r[760998,67,z]=dict(full)
  a=self.actor(760998.5,797808.7);a.update(health=20,is_baby=False)
  scene={'blocks':[dict(v,pos=list(k))for k,v in r.items()],'scan_entities':[a]};self.assertTrue(enclosed_neighbor(scene,a));require_empty_relay(scene,760997)
  scene['blocks']=[v for v in scene['blocks']if v['pos']not in ([760998,64,797809],[760998,65,797809])]
  self.assertFalse(enclosed_neighbor(scene,a))
  with self.assertRaises(RuntimeError):require_empty_relay(scene,760997)
 def test_held_lever_waits_for_late_updates_without_repeating_a_toggle(self):
  from copy import deepcopy
  rows=self.doors(self.rows());rows[760992,64,797811]={'state':'Block{minecraft:lever}[face=floor,facing=east,powered=false]','fluid':False,'passable':True}
  class B:
   def __init__(self):self.book={};self.pos=[760992.5,64.,797811.5];self.calls=[];self.deferred=None
   def scan(self,*args):
    reply={'scan_entities':[]},deepcopy(rows)
    if self.deferred is not None:rows.clear();rows.update(self.deferred);self.deferred=None
    return reply
   def check(self):return {'pos':self.pos,'hand':{'item':'minecraft:netherite_sword'}}
   def save(self):pass
   def n(self,op,**p):
    self.calls.append((op,p))
    if op=='walk':self.pos=p['target']
    else:
     self_test.assertTrue(closed(rows,760997));self_test.assertEqual(p['expected_state'],rows[760992,64,797811]['state']);on='powered=false'in p['expected_state'];later=deepcopy(rows);later[760992,64,797811]['state']=p['expected_state'].replace('powered=false','powered=true')if on else p['expected_state'].replace('powered=true','powered=false')
     for y in (64,65):later[760993,y,797811]['state']=later[760993,y,797811]['state'].replace('open=false','open=true')if on else later[760993,y,797811]['state'].replace('open=true','open=false')
     self.deferred=later
    return {'id':str(len(self.calls))}
  self_test=self;b=B();cross(b,760993,760992,[760994.5,64.,797811.5]);self.assertEqual(['interact','walk','interact'],[op for op,p in b.calls]);self.assertTrue(closed(rows,760993));self.assertFalse(b.book['airlock_crossings'][0]['pending']);self.assertTrue(b.book['airlock_crossings'][0]['lever_restored'])
 def test_pending_crossing_is_never_replayed(self):
  class B:
   book={'airlock_crossings':[{'pending':True}]}
   def scan(self,*a):raise AssertionError('No further request')
  with self.assertRaises(RuntimeError):cross(B(),760993,760992,[760994.5,64.,797811.5])
 def test_incidental_pickup_is_retained_without_goal_credit_but_loss_stops(self):
  from library_airlock_route import record_walk_inventory
  from collections import Counter
  class B:
   book={}
   def check(self):return {'inventory':[{'slot':0,'item':'minecraft:emerald','count':10},{'slot':1,'item':'minecraft:poisonous_potato','count':1}]}
   def save(self):pass
  b=B();gained=record_walk_inventory(b,Counter({'minecraft:emerald':10}));self.assertEqual({'minecraft:poisonous_potato':1},dict(gained));self.assertFalse(b.book['incidental_walk_pickups'][0]['counts_are_goal_credit'])
  with self.assertRaises(RuntimeError):record_walk_inventory(b,Counter({'minecraft:emerald':11}))
 def test_stale_crossing_preflight_is_rejected_before_any_input(self):
  from types import SimpleNamespace
  class B:
   book={};q=SimpleNamespace(world='world')
   def check(self):return {'time':2000}
   def n(self,*a,**kw):raise AssertionError('No input allowed')
  for scene in ({'time':0,'world_session':'world'},{'time':2000,'world_session':'foreign'}):
   with self.assertRaises(RuntimeError):cross(B(),760993,760992,[760994.5,64,797811.5],observation=(scene,{}))
if __name__=='__main__':unittest.main()
