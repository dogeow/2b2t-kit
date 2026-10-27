import copy,unittest
from unittest.mock import patch
from block_recovery import new_drop,pickup,return_to_origin

class RecoveryTests(unittest.TestCase):
 def test_partial_height_origin_uses_valid_grid_margin_and_keeps_exact_goal(self):
  from types import SimpleNamespace
  from pathlib import Path
  from material_jobs.local_air_path import plan
  for y in [64.0,64.5625,64.9375]:
   origin=[.5,y,.5];start=[.5,65.1,.5];b=SimpleNamespace(out=Path('/unused'),check=lambda:dict(pos=start))
   def route(owner,target,out,**kwargs):
    self.assertEqual(target,origin);self.assertTrue(kwargs['exact_target'])
    return plan([],start,target,[-1,62,-1],[2,69,2],foot_offset=kwargs['foot_offset'])
   with patch('queued_village_owner.QueuedVillageOwner',return_value=object()),patch('material_jobs.local_air_path.move',side_effect=route):
    self.assertTrue(return_to_origin(b,origin,'mine'))
 def drop(self,uid='new'):
  return dict(type='minecraft:item',uuid=uid,pos=[.5,64,.5],stack=dict(item='minecraft:dark_oak_fence',count=1))
 def test_ignores_old_drops_and_uses_actual_fallen_position(self):
  fresh=self.drop();old=self.drop('old');state=dict(entities=[old,fresh]);self.assertEqual(new_drop(state,'minecraft:dark_oak_fence',{'old'},[0,65,0]),fresh)
 def test_ambiguous_merged_far_and_invalid_stacks_are_never_guessed(self):
  for mode in ['ambiguous','merged','far','invalid','missing_uuid']:
   d=self.drop();entities=[d]
   if mode=='ambiguous':entities.append(self.drop('other'))
   if mode=='merged':d['stack']['count']=2
   if mode=='far':d['pos']=[10,64,0]
   if mode=='invalid':d['stack']['count']=True
   if mode=='missing_uuid':d.pop('uuid')
   with self.subTest(mode=mode):self.assertIsNone(new_drop(dict(entities=entities),'minecraft:dark_oak_fence',set(),[0,65,0]))
 def builder(self,*,gain=False,fail=False):
  drop=self.drop()
  class Builder:
   def __init__(self):self.book={};self.calls=[];self.clock=0;self.held=1 if gain else 0;self.entities=[]if gain else[drop]
   def save(self):pass
   def check(self):
    self.clock+=1;return dict(time=self.clock,inventory=[dict(slot=0,item='minecraft:dark_oak_fence',count=self.held)],entities=self.entities)
   def n(self,op,**params):
    self.calls.append((op,params))
    if fail:raise RuntimeError('Original collector uncertain')
    self.held=1;self.entities=[];return dict(id='collect',phase='done')
  return Builder()
 def test_one_native_identity_collection_and_two_later_frames(self):
  b=self.builder()
  with patch('block_recovery.time.sleep'):r=pickup(b,'minecraft:dark_oak_fence',0,set(),[0,65,0])
  self.assertFalse(r['pending']);self.assertEqual(len(r['confirmed_frames']),2);self.assertEqual(b.calls,[('collect_item',dict(expected_uuid='new',expected_item='minecraft:dark_oak_fence',expected_count=1,seconds=20))])
 def test_already_collected_makes_no_input(self):
  b=self.builder(gain=True);self.assertIsNone(pickup(b,'minecraft:dark_oak_fence',0,set(),[0,65,0]));self.assertEqual(b.calls,[])
 def test_uncertain_collector_is_retained_and_never_retried(self):
  b=self.builder(fail=True)
  with self.assertRaisesRegex(RuntimeError,'uncertain'):pickup(b,'minecraft:dark_oak_fence',0,set(),[0,65,0])
  self.assertEqual(len(b.calls),1);self.assertTrue(b.book['pending_block_pickup']['pending'])
 def test_natural_pickup_race_observes_exact_refusal_without_another_collection(self):
  from types import SimpleNamespace
  b=self.builder();observations=[];original_check=b.check
  def check():return dict(original_check(),last_request='collect')
  def raced(op,**params):
   b.calls.append((op,params));b.held=1;b.entities=[]
   raise RuntimeError('Original village action did not complete: Drop is no longer loaded; observe again')
  def observe():observations.append('snapshot');return dict(id='snapshot')
  b.check=check;b.n=raced;b.q=SimpleNamespace(observe_missing_drop=observe)
  with patch('block_recovery.time.sleep'):r=pickup(b,'minecraft:dark_oak_fence',0,set(),[0,65,0])
  self.assertEqual(len(b.calls),1);self.assertEqual(observations,['snapshot']);self.assertFalse(r['pending']);self.assertEqual(r['completion'],'natural_pickup_before_collector');self.assertIsNone(b.book['pending'])
 def test_settled_collector_waits_for_late_stock_without_repeating_collection(self):
  from types import SimpleNamespace
  b=self.builder();original_check=b.check;observations=[];reads=0
  def check():
   nonlocal reads
   if b.calls:
    reads+=1
    if reads>=3:b.held=1;b.entities=[]
   return dict(original_check(),last_request='collect')
  def settled(op,**params):
   b.calls.append((op,params))
   raise RuntimeError('Original village action did not complete: Drop pickup not confirmed at the reached position')
  def observe():observations.append('snapshot');return dict(id='snapshot')
  b.check=check;b.n=settled;b.q=SimpleNamespace(observe_unconfirmed_pickup_terminal=observe)
  with patch('block_recovery.time.sleep'):r=pickup(b,'minecraft:dark_oak_fence',0,set(),[0,65,0])
  self.assertEqual(len(b.calls),1);self.assertEqual(observations,['snapshot']);self.assertFalse(r['pending']);self.assertEqual(r['completion'],'late_natural_pickup_after_settled_collector')
 def test_settled_collector_needs_exact_stock_disappearance_and_pinned_observation(self):
  from types import SimpleNamespace
  for mode in ['no_gain','extra_gain','drop_remains','observer_refuses']:
   with self.subTest(mode=mode):
    b=self.builder();original_check=b.check;observations=[]
    def check():return dict(original_check(),last_request='collect')
    def settled(op,**params):
     b.calls.append((op,params));b.held=0 if mode=='no_gain'else 2 if mode=='extra_gain'else 1
     if mode!='drop_remains':b.entities=[]
     raise RuntimeError('Original village action did not complete: Drop pickup not confirmed at the reached position')
    def observe():observations.append('snapshot');raise RuntimeError('Pinned collector observation refused')
    b.check=check;b.n=settled;b.q=SimpleNamespace(observe_unconfirmed_pickup_terminal=observe)
    with patch('block_recovery.time.sleep'),patch('block_recovery.time.monotonic',side_effect=[0,0,10,20,30,40]):
     with self.assertRaises(RuntimeError):pickup(b,'minecraft:dark_oak_fence',0,set(),[0,65,0])
    self.assertEqual(len(b.calls),1);self.assertTrue(b.book['pending_block_pickup']['pending']);self.assertEqual(observations,['snapshot']if mode=='observer_refuses'else[])

 def test_route_refusal_can_observe_late_natural_pickup_without_replaying(self):
  from types import SimpleNamespace
  b=self.builder();original_check=b.check;reads=0;observations=[]
  def check():
   nonlocal reads
   if b.calls:
    reads+=1
    if reads>=3:b.held=1;b.entities=[]
   return dict(original_check(),last_request='collect')
  def refused(op,**params):
   b.calls.append((op,params));raise RuntimeError('Original village action did not complete: No loaded collision-free route to this depot; no ceiling is broken')
  def observe():observations.append('snapshot');return dict(id='snapshot')
  b.check=check;b.n=refused;b.q=SimpleNamespace(observe_refused_collection_path=observe)
  with patch('block_recovery.time.sleep'):r=pickup(b,'minecraft:dark_oak_fence',0,set(),[0,65,0])
  self.assertEqual(len(b.calls),1);self.assertEqual(observations,['snapshot'])
  self.assertEqual(r['completion'],'late_natural_pickup_after_route_refusal');self.assertFalse(r['pending']);self.assertEqual(len(r['confirmed_frames']),2)

 def test_route_refusal_keeps_missing_extra_and_unconfirmed_pickups_pending(self):
  from types import SimpleNamespace
  for mode in ['no_gain','extra_gain','drop_remains','observer_refuses']:
   with self.subTest(mode=mode):
    b=self.builder();original_check=b.check;observations=[]
    def check():return dict(original_check(),last_request='collect')
    def refused(op,**params):
     b.calls.append((op,params));b.held=0 if mode=='no_gain'else 2 if mode=='extra_gain'else 1
     if mode!='drop_remains':b.entities=[]
     raise RuntimeError('Original village action did not complete: No loaded collision-free route to this depot; no ceiling is broken')
    def observe():observations.append('snapshot');raise RuntimeError('Route observation refused')
    b.check=check;b.n=refused;b.q=SimpleNamespace(observe_refused_collection_path=observe)
    with patch('block_recovery.time.sleep'),patch('block_recovery.time.monotonic',side_effect=[0,0,10,20,30,40]):
     with self.assertRaises(RuntimeError):pickup(b,'minecraft:dark_oak_fence',0,set(),[0,65,0])
    self.assertEqual(len(b.calls),1);self.assertTrue(b.book['pending_block_pickup']['pending'])
    self.assertEqual(observations,['snapshot']if mode=='observer_refuses'else[])

if __name__=='__main__':unittest.main()
