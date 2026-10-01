import copy,json,tempfile,unittest
from pathlib import Path
from animal_pen import PRE_DISPATCH_ERROR,SEEDS,entity_clear,place,reconcile_no_dispatch,verified_placement_counts
from potato_farm import FarmWait
from test_potato_harvest import HarvestClient
from test_potato_farm import row

class PenClient(HarvestClient):
 def __init__(self):
  super().__init__();self.rows={(0,62,0):row((0,62,0),'Block{minecraft:grass_block}[snowy=false]')};self.entities=[]
  self.inv[13].update(item='minecraft:oak_fence',count=3,max_stack=64);self.no_place=False
  self.grass_phase='done';self.no_clear=False;self.seed_gain=0;self.damage_soil=False;self.grass_drop=False
 def request(self,op,**params):
  if op=='mine_block':
   self.calls.append((op,copy.deepcopy(params)))
   assert params['pos']==[0,63,0] and params['expected_state']=='Block{minecraft:short_grass}'
   if self.grass_phase=='done' and not self.no_clear:
    self.rows.pop((0,63,0));self.rev+=1;self.extra['control_revision']=self.rev;self.extra['supervision_lease']['revision']=self.rev
    if self.seed_gain:self.inv[14].update(item=SEEDS,count=self.seed_gain,max_stack=64)
    if self.damage_soil:self.rows[(0,62,0)]['state']='Block{minecraft:dirt}'
    if self.grass_drop:self.entities.append({'uuid':'new-seed','id':70,'type':'minecraft:item','pos':[.5,63,.5],'stack':{'item':SEEDS,'count':1}})
   return {**self.status(),'phase':self.grass_phase,'id':'native-grass'}
  if op=='interact':
   self.calls.append((op,copy.deepcopy(params)))
   if not self.no_place:
    self.rows[(0,63,0)]=row((0,63,0),'Block{minecraft:oak_fence}[east=false,north=false,south=false,waterlogged=false,west=false]',False)
    self.inv[self.selected]['count']-=1
   return {**self.status(),'phase':'done','id':'native-place'}
  return super().request(op,**params)

class PenTest(unittest.TestCase):
 def grass(self,c):
  c.rows[(0,63,0)]=row((0,63,0),'Block{minecraft:short_grass}',False);c.rows[(0,63,0)]['replaceable']=True
 def rejected(self,c,out,detail=PRE_DISPATCH_ERROR,phase='error'):
  self.grass(c)
  from potato_harvest import _counts
  s=c.status();book={'world_session':c.world,'item':'minecraft:oak_fence','cell':[0,63,0],
   'pending':{'operation':'place','support':[0,62,0],'support_state':c.rows[(0,62,0)]['state'],
    'target_before':copy.deepcopy(c.rows[(0,63,0)]),'before_counts':dict(_counts(s)),
    'hand_before':s['hand'],'time_before':s['time'],'receipt':{'id':'known-native-error','phase':phase,'detail':detail}}}
  p=Path(out)/'place-0,63,0.json';p.write_text(json.dumps(book));return book
 def test_actual_fence_uses_one_item_and_two_distinct_frames(self):
  c=PenClient()
  with tempfile.TemporaryDirectory() as out:
   receipt=place(c,'minecraft:oak_fence',[0,63,0],out)
   self.assertTrue(receipt['complete']);self.assertEqual(2,len(receipt['proof']['observed_times']))
   self.assertEqual(2,receipt['proof']['after_counts']['minecraft:oak_fence'])
 def test_animal_aabb_blocks_cell_without_a_world_interaction(self):
  self.assertFalse(entity_clear([{'type':'minecraft:cow','pos':[.9,63,.5],'is_baby':False}],[0,63,0]))
  self.assertTrue(entity_clear([{'type':'minecraft:cow','pos':[1.6,63,.5],'is_baby':False}],[0,63,0]))
  c=PenClient();c.entities=[{'uuid':'cow','id':1,'type':'minecraft:cow','pos':[.5,63,.5]}]
  with tempfile.TemporaryDirectory() as out:
   with self.assertRaises(FarmWait):place(c,'minecraft:oak_fence',[0,63,0],out)
  self.assertFalse(any(op=='interact' for op,_ in c.calls))
 def test_fake_receipt_no_placement_is_pending_and_never_repeated(self):
  c=PenClient();c.no_place=True
  with tempfile.TemporaryDirectory() as out:
   with self.assertRaises(FarmWait):place(c,'minecraft:oak_fence',[0,63,0],out)
   calls=len(c.calls)
   with self.assertRaises(FarmWait):place(c,'minecraft:oak_fence',[0,63,0],out)
   self.assertEqual(calls,len(c.calls))
 def test_single_short_grass_clear_air_soil_and_stock_proof_precedes_place(self):
  for gain in (0,1):
   c=PenClient();self.grass(c);c.seed_gain=gain
   with tempfile.TemporaryDirectory() as out:
    receipt=place(c,'minecraft:oak_fence',[0,63,0],out)
    self.assertTrue(receipt['complete']);self.assertEqual(gain,receipt['grass_clear']['observed_seed_gain'])
    self.assertEqual(2,len(receipt['grass_clear']['observed_times']))
   actions=[op for op,_ in c.calls if op in ('mine_block','interact')]
   self.assertEqual(['mine_block','interact'],actions)
 def test_unknown_clear_unchanged_grass_soil_change_or_excess_seed_never_places_or_remines(self):
  for change in (lambda c:setattr(c,'grass_phase','waiting'),lambda c:setattr(c,'no_clear',True),
                 lambda c:setattr(c,'damage_soil',True),lambda c:setattr(c,'seed_gain',2)):
   c=PenClient();self.grass(c);change(c)
   with tempfile.TemporaryDirectory() as out:
    with self.assertRaises(FarmWait):place(c,'minecraft:oak_fence',[0,63,0],out)
    count=len(c.calls)
    with self.assertRaises(FarmWait):place(c,'minecraft:oak_fence',[0,63,0],out)
    self.assertEqual(count,len(c.calls))
   self.assertEqual(1,sum(op=='mine_block' for op,_ in c.calls));self.assertFalse(any(op=='interact' for op,_ in c.calls))
 def test_observed_seed_drop_conservation_is_recorded_without_claiming_inventory_pickup(self):
  c=PenClient();self.grass(c);c.grass_drop=True
  with tempfile.TemporaryDirectory() as out:
   with self.assertRaisesRegex(FarmWait,'seed/entity'):place(c,'minecraft:oak_fence',[0,63,0],out)
   book=json.loads((Path(out)/'place-0,63,0.json').read_text())
   self.assertEqual(1,book['grass_clear']['normal_loot_total']);self.assertEqual(0,book['grass_clear']['observed_seed_gain'])
   self.assertEqual('new-seed',book['grass_clear']['observed_seed_drops'][0]['uuid']);self.assertIsNone(book['pending'])
  self.assertFalse(any(op=='interact' for op,_ in c.calls))
 def test_exact_synchronous_rejection_reconciles_by_only_two_read_frames_and_retains_history(self):
  c=PenClient()
  with tempfile.TemporaryDirectory() as out:
   old=self.rejected(c,out);r=reconcile_no_dispatch(c,'minecraft:oak_fence',[0,63,0],out)
   self.assertIsNone(r['pending']);self.assertEqual(old['pending'],r['rejected_intents'][0]['original_pending'])
   self.assertFalse(r['rejected_intents'][0]['placement_ack']);self.assertEqual(2,len(r['rejected_intents'][0]['observed_times']))
   self.assertEqual(['scan','scan'],[op for op,_ in c.calls])
 def test_reconciliation_ignores_light_layers_but_preserves_structural_identity_and_stock(self):
  c=PenClient()
  with tempfile.TemporaryDirectory() as out:
   self.rejected(c,out);c.rows[(0,63,0)].update(sky_light=0,spawn_sky_light=0,block_light=7,spawn_block_light=7)
   result=reconcile_no_dispatch(c,'minecraft:oak_fence',[0,63,0],out)
   self.assertIsNone(result['pending'])
  for field,value in (('replaceable',False),('fluid',True),('block_entity',True),('passable',False)):
   c=PenClient()
   with tempfile.TemporaryDirectory() as out:
    self.rejected(c,out);c.rows[(0,63,0)][field]=value
    with self.assertRaises(FarmWait):reconcile_no_dispatch(c,'minecraft:oak_fence',[0,63,0],out)
 def test_timeout_async_rotation_error_or_changed_counts_target_world_refuses_reconcile(self):
  for detail,phase in (('Interaction became occluded while rotating','error'),(PRE_DISPATCH_ERROR,'waiting'),('timeout','error')):
   c=PenClient()
   with tempfile.TemporaryDirectory() as out:
    self.rejected(c,out,detail,phase)
    with self.assertRaises(FarmWait):reconcile_no_dispatch(c,'minecraft:oak_fence',[0,63,0],out)
    self.assertEqual([],c.calls)
  for change in (lambda c:c.inv[13].update(count=2),lambda c:c.rows.pop((0,63,0)),lambda c:setattr(c,'world','foreign')):
   c=PenClient()
   with tempfile.TemporaryDirectory() as out:
    self.rejected(c,out);change(c)
    with self.assertRaises(FarmWait):reconcile_no_dispatch(c,'minecraft:oak_fence',[0,63,0],out)
    self.assertIsNotNone(json.loads((Path(out)/'place-0,63,0.json').read_text())['pending'])
 def test_verified_following_receipt_chain_advances_stock_without_acknowledging_rejected_place(self):
  c=PenClient()
  with tempfile.TemporaryDirectory() as out:
   old=self.rejected(c,out);counts=old['pending']['before_counts'];t=old['pending']['time_before']
   after=counts.copy();after['minecraft:oak_fence']-=1
   following={'world_session':c.world,'item':'minecraft:oak_fence','cell':[1,63,0],'complete':True,'pending':None,
    'proof':{'before_counts':counts,'after_counts':after,'time_before':t+1,'observed_times':[t+2,t+3]}}
   self.assertEqual(after,verified_placement_counts(old,[following]))
   c.inv[13]['count']=2;c.time+=100
   r=reconcile_no_dispatch(c,'minecraft:oak_fence',[0,63,0],out,completed_receipts=[following])
   self.assertEqual(after,r['rejected_intents'][0]['expected_current_counts']);self.assertIsNone(r['pending'])
   for change in (lambda r:r.update(pending={'operation':'unknown'}),lambda r:r.update(world_session='other'),
                  lambda r:r['proof'].update(after_counts=counts),lambda r:r['proof'].update(observed_times=[t+2,t+2]),
                  lambda r:r.update(cell=[0,63,0])):
    broken=copy.deepcopy(following);change(broken)
    with self.assertRaises(FarmWait):verified_placement_counts(old,[broken])
if __name__=='__main__':unittest.main()
