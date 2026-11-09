import tempfile,unittest
from pathlib import Path
from collections import Counter
from unittest.mock import patch
import guarded_plane_recovery as m
class Fake:
 def __init__(self):self.world='w';self.targets=[[0,196,0],[1,196,0],[2,196,0]];self.count=0;self.position=[0.5,193.8,0.5];self.mined=[]
 def status(self):return {'pos':self.position,'inventory':[{'slot':1,'item':'minecraft:diamond_pickaxe','durability':300}],'health':20,'food':20,'guard_armed':True,'guard_busy':False,'manual_movement':False,'screen':'','flight':True}
 def checked(self,op,**kw):
  if op=='navigate':self.position=kw['target'];return {'phase':'done'}
  if op=='select_item':return {'phase':'done'}
  if op=='mine_block':self.targets.remove(kw['pos']);self.mined.append(kw['pos']);return {'id':'mine-'+str(len(self.mined)),'server_confirmed':True,'native_sequence':len(self.mined),'server_ack_sequence':len(self.mined)}
  if op=='scan':
   lo,hi=kw['min'],kw['max'];rows=[x for x in self.targets if all(lo[i]<=x[i]<=hi[i] for i in range(3))];n=(hi[0]-lo[0]+1)*(hi[1]-lo[1]+1)*(hi[2]-lo[2]+1);return {'scan_cells_read':n,'scan_total_cells':n,'blocks':[{'pos':x,'state':'Block{minecraft:magma_block}'}for x in rows],'scan_entities':[]}
  raise AssertionError(op)
class Tests(unittest.TestCase):
 def profile(self):return dict(schema=1,authorized=True,server='s',dimension='minecraft:the_nether',item='minecraft:magma_block',block_state='Block{minecraft:magma_block}',tool='minecraft:diamond_pickaxe',min=[0,196,0],max=[2,196,0],chest=[9,1,9],chest_pose=[9.5,2,8.5],chest_face='north',park_target=[0.5,230,0.5],foot_y=193.8,minimum_y=129.5,batch_size=2,protected_columns=[[1,0]],lock_path='/tmp/x')
 def test_scope_validation_and_nearest(self):
  p=m.validate_profile(self.profile());self.assertIn(([1.5,196.05,1.5],'south'),m.side_stances([1,196,0],[{'pos':[1,196,0]}]));self.assertEqual([1,196,0],m.choose_target([[2,196,0],[1,196,0]],[.5,193,0]))
  q={'scan_cells_read':3,'scan_total_cells':3,'blocks':[{'pos':[3,196,0],'state':'Block{minecraft:magma_block}'}]}
  with self.assertRaises(RuntimeError):m.actual_targets(q,p)
 def test_side_stance_never_enters_blocks_or_living_entities(self):
  target=[10,196,10];blocks=[{'pos':target},{'pos':[11,196,10]},{'pos':[9,194,10]}]
  entity={'type':'minecraft:villager','alive':True,'bounds':{'min':[10.2,196,11.2],'max':[10.8,197.8,11.8]}}
  self.assertEqual([([10.5,196.05,9.5],'north')],m.side_stances(target,blocks,[entity]))
  self.assertEqual([],m.exposed_targets([target],{(11,196,10),(9,196,10),(10,196,11),(10,196,9)}))
 def test_floor_observation_is_not_hidden_by_later_pickup(self):
  self.assertTrue(m.pickup_near_floor({'last_observed':[1,128.4,2]},None,129.5))
  self.assertTrue(m.pickup_near_floor({}, {'source':{'pos':[1,128.4,2]}},129.5))
  self.assertFalse(m.pickup_near_floor({'last_observed':[1,180,2]},None,129.5))
 def test_no_guess_if_drop_is_ambiguous(self):
  from falling_drop_tracking import observe
  item=lambda uid:{'type':'minecraft:item','uuid':uid,'pos':[0,196,0],'stack':{'item':'minecraft:magma_block','count':1}}
  self.assertEqual('stop',observe(item='minecraft:magma_block',expected_count=1,before=0,current=0,entities=[item('a'),item('b')],known_ids=set(),origin=[0,196,0]).state)
 def test_nearby_clear_side_does_not_descend(self):
  from unittest.mock import Mock
  c=Mock();c.checked.side_effect=lambda op,**kw: {'blocks':[]} if op=='scan' else {'phase':'done'}
  state={'pos':[0.5,196.05,0.5],'on_ground':False,'flight':True}
  self.assertEqual('clear_same_height',m.goto_side(c,state,[1.5,196.05,.5],193.3))
  moves=[x.kwargs['target'] for x in c.checked.call_args_list if x.args[0]=='navigate'];self.assertEqual([[1.5,196.05,.5]],moves)
 def test_blocked_orthogonal_storage_paths_use_existing_air_planner(self):
  from unittest.mock import Mock
  c=Mock();c.out=Path('/tmp/route-test');state={'pos':[.5,193.3,2.5]};target=[2.5,193.3,.5]
  with patch.object(m,'healthy',return_value=state),patch.object(m,'clear_air_leg',return_value=False),patch('material_jobs.local_air_path.move') as route:
   m.goto_storage(c,target)
  self.assertEqual(1,route.call_count);self.assertEqual(target,route.call_args.args[1]);c.checked.assert_not_called()
 def test_side_approach_uses_checked_detour_below_plane(self):
  from unittest.mock import Mock
  c=Mock();state={'pos':[.5,193.3,2.5]};stance=[2.5,196.05,.5]
  with patch.object(m,'goto_storage') as route:
   self.assertEqual('below_then_side',m.goto_side(c,state,stance,193.3))
  route.assert_called_once_with(c,[2.5,193.3,.5]);self.assertEqual(stance,c.checked.call_args.kwargs['target'])
 def test_eat_when_hungry_and_recover_before_next_action(self):
  from unittest.mock import Mock
  base={'health':18.5,'food':17,'guard_armed':True,'guard_busy':False,'manual_movement':False,'screen':'','flight':True,'recent_hurt_at':123}
  restored=dict(base,health=19.5,food=20);c=Mock();c.status.side_effect=[base,restored]
  with patch.object(m,'inventory_counts',return_value=Counter({'minecraft:cooked_beef':5})),patch('time.sleep'):
   self.assertEqual(19.5,m.healthy(c)['health']);c.checked.assert_called_once_with('use_item',item='minecraft:cooked_beef')
  c=Mock();c.status.return_value=dict(base,guard_busy=True)
  with self.assertRaises(RuntimeError):m.healthy(c)
  c.checked.assert_not_called()
 def test_pickup_that_arrives_during_blocked_route_scan_is_confirmed(self):
  from unittest.mock import Mock
  drop={'type':'minecraft:item','uuid':'drop','pos':[.5,195,.5],'stack':{'item':'minecraft:magma_block','count':1}}
  seen={'pos':[.5,194,.5],'time':1,'entities':[drop],'stock':0};settled={'pos':[.5,194,.5],'time':2,'entities':[],'stock':1};q3=dict(settled,time=3);q4=dict(settled,time=4);c=Mock();c.checked.return_value={'blocks':[{'pos':[0,194,0]}]};ticks=[0]
  def mono():ticks[0]+=.6;return ticks[0]
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'pickup_state',side_effect=[seen,settled,q3,q4]),patch.object(m,'inventory_counts',side_effect=lambda q:Counter({'minecraft:magma_block':q['stock']})),patch('material_jobs.acquisition.blocks_route',return_value=True),patch('time.monotonic',side_effect=mono),patch('time.sleep'):
   proof=m.await_pickup(c,{'item':'minecraft:magma_block','minimum_y':129.5},{'pending':{}},Path(tmp)/'p.json',0,set(),[0,196,0])
  self.assertEqual('drop',proof['drop_uuid']);self.assertEqual(0,proof['follow_attempts']);self.assertFalse(any(x.args[0]=='navigate' for x in c.checked.call_args_list))
 def test_storage_route_avoids_blocked_diagonal_without_digging(self):
  from unittest.mock import Mock
  c=Mock();state={'pos':[0.5,193.3,2.5]};target=[2.5,193.3,.5]
  with patch.object(m,'healthy',return_value=state),patch.object(m,'clear_air_leg',side_effect=[False,True,True]):
   m.goto_storage(c,target)
  moves=[x.kwargs['target'] for x in c.checked.call_args_list if x.args[0]=='navigate']
  self.assertEqual([[.5,193.3,.5],target],moves)
  self.assertTrue(all(x.args[0]=='navigate' for x in c.checked.call_args_list))
 def test_one_script_resumes_and_finishes_all_targets(self):
  c=Fake();p=self.profile()
  def count(_):return Counter({'minecraft:magma_block':c.count})
  def deposit(c,p,book,path):
   if c.count:book['deposits'].append({'amount':c.count});c.count=0;m.write_json(path,book)
  def pickup(c,p,book,path,before,known,target,**kwargs):c.count+=1;return {'frames':[1,2]}
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'healthy',side_effect=lambda c:c.status()),patch.object(m,'inventory_counts',side_effect=count),patch.object(m,'deposit',side_effect=deposit),patch.object(m,'await_pickup',side_effect=pickup):
   out=Path(tmp)/'run';first=m.run(c,p,out,max_blocks=2);self.assertFalse(first['complete']);self.assertEqual(2,len(first['mined']));final=m.run(c,p,out,resume=True);self.assertTrue(final['complete']);self.assertEqual(3,len(final['mined']));self.assertEqual(3,len({tuple(x)for x in c.mined}));self.assertEqual(3,sum(x['amount']for x in final['deposits']))
 def test_blocked_sweep_uses_verified_air_path_for_same_drop(self):
  from unittest.mock import Mock
  drop={'type':'minecraft:item','uuid':'drop','pos':[.5,195,.5],'stack':{'item':'minecraft:magma_block','count':1}}
  seen={'pos':[.5,194,.5],'time':1,'entities':[drop],'stock':0};again=dict(seen,time=2);q3={'pos':[.5,193,.5],'time':3,'entities':[],'stock':1};q4=dict(q3,time=4);c=Mock();c.checked.return_value={'blocks':[{'pos':[0,194,0]}]};ticks=[0]
  def mono():ticks[0]+=.6;return ticks[0]
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'pickup_state',side_effect=[seen,again,q3,q4]),patch.object(m,'inventory_counts',side_effect=lambda q:Counter({'minecraft:magma_block':q['stock']})),patch('material_jobs.acquisition.blocks_route',return_value=True),patch('material_jobs.local_air_path.move') as move,patch('time.monotonic',side_effect=mono),patch('time.sleep'):
   proof=m.await_pickup(c,{'item':'minecraft:magma_block','minimum_y':129.5},{'pending':{}},Path(tmp)/'p.json',0,set(),[0,196,0])
  self.assertEqual(1,proof['follow_attempts']);self.assertEqual(1,move.call_count)
 def test_exact_server_pickup_packet_handles_other_simultaneous_items(self):
  from unittest.mock import Mock
  drop={'id':77,'type':'minecraft:item','uuid':'drop','pos':[.5,195,.5],'stack':{'item':'minecraft:magma_block','count':1}}
  initial={'world_session':'w','runtime_generation':1,'time':10,'inventory':[{'slot':0,'item':'minecraft:magma_block','count':0}],'entities':[drop]}
  q={'world_session':'w','runtime_generation':1,'time':11,'player_uuid':'player','entities':[],'stock':3};q2=dict(q,time=12);c=Mock();c.root=Path('/tmp/fake-root')
  receipt={'kind':'item_pickup','amount':1,'collector':{'uuid':'player'}}
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'pickup_state',side_effect=[q,q2]),patch.object(m,'inventory_counts',side_effect=lambda x:Counter({'minecraft:magma_block':x.get('stock',0)})),patch('villager_events.read',return_value={'frame':'fresh'}),patch('villager_events.joined_pickups',return_value=[receipt]) as joined,patch('time.sleep'):
   proof=m.await_pickup(c,{'item':'minecraft:magma_block','minimum_y':129.5},{'pending':{}},Path(tmp)/'p.json',0,set(),[0,196,0],initial=initial)
  self.assertEqual(3,proof['actual_after']);self.assertEqual(2,proof['surplus']);self.assertEqual(receipt,proof['server_pickup_receipt']);self.assertEqual('drop',joined.call_args.args[3]['entity']['uuid'])
 def test_guard_busy_keeps_observing_without_movement(self):
  from unittest.mock import Mock
  drop={'type':'minecraft:item','uuid':'drop','pos':[.5,195,.5],'stack':{'item':'minecraft:magma_block','count':1}}
  seen={'pos':[.5,194,.5],'time':1,'entities':[drop],'stock':0,'guard_busy':True};q2={'pos':[.5,194,.5],'time':2,'entities':[],'stock':1,'guard_busy':False};q3=dict(q2,time=3);c=Mock();ticks=[0]
  def mono():ticks[0]+=.6;return ticks[0]
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'pickup_state',side_effect=[seen,q2,q3]),patch.object(m,'inventory_counts',side_effect=lambda q:Counter({'minecraft:magma_block':q['stock']})),patch('time.monotonic',side_effect=mono),patch('time.sleep'):
   proof=m.await_pickup(c,{'item':'minecraft:magma_block','minimum_y':129.5},{'pending':{}},Path(tmp)/'p.json',0,set(),[0,196,0])
  self.assertEqual('drop',proof['drop_uuid']);c.checked.assert_not_called()
 def test_reconcile_exact_server_mine_and_stable_inventory_without_mutation(self):
  import json
  from unittest.mock import Mock
  p=self.profile();target=[0,196,0];pending={'op':'mine','target':target,'before':2,'request_id':'mine-1','drop_uuid':'drop-1'}
  state={'connected':True,'world_session':'w','server':'s','dimension':'minecraft:the_nether','health':20,'guard_armed':True,'guard_busy':False,'manual_movement':False,'screen':'','supervision_lease':None}
  receipt={'id':'mine-1','world_session':'w','phase':'done','server_confirmed':True,'native_sequence':5,'server_ack_sequence':5,'mining_target':target}
  frame=lambda t:{'world_session':'w','time':t,'inventory':[{'slot':4,'item':'minecraft:magma_block','count':3}],'blocks':[],'scan_entities':[]}
  client=Mock();client.checked.side_effect=[frame(1),frame(2)]
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'root';root.mkdir();out=Path(tmp)/'run';out.mkdir();(root/'reply-mine-1.json').write_text(json.dumps(receipt));(out/'progress.json').write_text(json.dumps({'profile':p,'world_session':'w','pending':pending,'mined':[]}))
   with patch.object(m,'read_fresh',return_value=state),patch('material_client.Client',return_value=client),patch('time.sleep'):
    proof=m.reconcile_pending(root,p,out)
   book=json.loads((out/'progress.json').read_text());self.assertIsNone(book['pending']);self.assertEqual(1,len(book['mined']));self.assertFalse(proof['original_replayed']);self.assertTrue(all(x.args[0]=='scan' for x in client.checked.call_args_list))
 def test_surplus_is_preserved_as_unattributed_not_success(self):
  import json
  from unittest.mock import Mock
  p=self.profile();target=[0,196,0];pending={'op':'mine','target':target,'before':2,'request_id':'mine-2','drop_uuid':'drop-2'}
  state={'connected':True,'world_session':'w','server':'s','dimension':'minecraft:the_nether','health':20,'guard_armed':True,'guard_busy':False,'manual_movement':False,'screen':'','supervision_lease':None}
  receipt={'id':'mine-2','world_session':'w','phase':'done','server_confirmed':True,'native_sequence':5,'server_ack_sequence':5,'mining_target':target}
  frame=lambda t:{'world_session':'w','time':t,'inventory':[{'slot':4,'item':'minecraft:magma_block','count':5}],'blocks':[],'scan_entities':[]};client=Mock();client.checked.side_effect=[frame(1),frame(2)]
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'root';root.mkdir();out=Path(tmp)/'run';out.mkdir();(root/'reply-mine-2.json').write_text(json.dumps(receipt));(out/'progress.json').write_text(json.dumps({'profile':p,'world_session':'w','pending':pending,'mined':[]}))
   with patch.object(m,'read_fresh',return_value=state),patch('material_client.Client',return_value=client),patch('time.sleep'):proof=m.reconcile_pending(root,p,out)
   book=json.loads((out/'progress.json').read_text());self.assertIsNone(book['pending']);self.assertEqual([],book['mined']);self.assertEqual(1,len(book['unresolved']));self.assertFalse(proof['pickup_attributed']);self.assertEqual(5,proof['after'])
 def test_unconfirmed_mine_stops_and_cannot_resume(self):
  c=Fake();p=self.profile()
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'healthy',side_effect=lambda c:c.status()),patch.object(m,'inventory_counts',return_value=Counter()),patch.object(m,'deposit'),patch.object(m,'await_pickup',side_effect=RuntimeError('unknown')):
   out=Path(tmp)/'run'
   with self.assertRaises(RuntimeError):m.run(c,p,out)
   with self.assertRaises(RuntimeError):m.run(c,p,out,resume=True)
   self.assertEqual(1,len(c.mined))
if __name__=='__main__':unittest.main()
