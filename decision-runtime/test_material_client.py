import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from material_client import Client,MaterialClient,high_park_clearance,credit_guard_pause,vertical_surface_escape,pending_request_state,bounded_canopy_path,Handoff
BUSY='Construction guard is defending or eating; wait before changing items or starting work'
class Tests(unittest.TestCase):
 def test_combat_pause_extends_only_guarded_native_wait_with_a_cap(self):
  deadline,paused=credit_guard_pause(100,0,35,True)
  self.assertEqual((135,35),(deadline,paused))
  self.assertEqual((135,35),credit_guard_pause(deadline,paused,20,False))
  self.assertEqual((280,180),credit_guard_pause(deadline,paused,200,True))
 def test_underwater_guard_wait_allows_only_vertical_surface_escape(self):
  state={'pos':[10,52,20]}
  self.assertTrue(vertical_surface_escape(state,'navigate',{'target':[10.5,66,20.5]}))
  self.assertFalse(vertical_surface_escape(state,'navigate',{'target':[13,66,20]}))
  self.assertFalse(vertical_surface_escape(state,'navigate',{'target':[10,53,20]}))
  self.assertFalse(vertical_surface_escape(state,'mine_block',{'target':[10,66,20]}))
 def test_previous_owned_request_may_finish_status_update_without_replay(self):
  request={'id':'mine-1','world_session':'world-1'}
  self.assertEqual('wait_owned',pending_request_state(request,'scan-0','mine-1','world-1'))
  self.assertEqual('clear',pending_request_state(request,'mine-1','mine-1','world-1'))
  self.assertEqual('foreign',pending_request_state(request,'scan-0','other','world-1'))
  self.assertEqual('foreign',pending_request_state(request,'scan-0','mine-1','world-2'))
 def test_ground_level_park_is_rejected_before_material_control(self):
  rows=[{'pos':[10,73,20],'passable':False,'fluid':False}]
  self.assertEqual(1,high_park_clearance(rows,75))
  self.assertEqual(20,high_park_clearance(rows,94))
  with self.assertRaises(Handoff):high_park_clearance([],120)
 def test_high_parking_checks_height_and_horizontal_drift_separately(self):
  c=MaterialClient.__new__(MaterialClient);c.park_target=[100.5,95,200.5]
  self.assertTrue(c.park_near({'pos':[107.5,95,200.5]}))
  self.assertFalse(c.park_near({'pos':[109.5,95,200.5]}))
  self.assertFalse(c.park_near({'pos':[100.5,88,200.5]}))
 def test_canopy_walk_requires_confirmed_paving_support_before_any_horizontal_step(self):
  floors=[{'pos':[x,63,0],'state':'Block{minecraft:grass_block}',
           'solid':True,'passable':False,'fluid':False,'block_entity':False} for x in range(3)]
  roof=[{'pos':[x,68,0],'state':'Block{minecraft:oak_leaves}',
         'solid':True,'passable':False,'fluid':False,'block_entity':False} for x in (0,1)]
  self.assertIsNone(bounded_canopy_path(floors[1:]+roof,[.5,64.2,.5],95))
  floors[0]['state']='Block{minecraft:stone_bricks}'
  self.assertIsNone(bounded_canopy_path(floors+roof,[.18,64.2,.18],95),
                    'A body crossing neighbouring cells must not use a single-cell route proof')
  self.assertEqual([p[0] for p in bounded_canopy_path(floors+roof,[.5,64.2,.5],95)], [.5,1.5,2.5])
  floors[0]['state']='Block{minecraft:polished_andesite}'
  self.assertEqual(len(bounded_canopy_path(floors+roof,[.5,64.2,.5],95)),3)
 def test_canopy_path_rejects_a_long_maze_even_within_the_nine_by_nine_scan(self):
  floors=[{'pos':[x,63,z],'state':'Block{minecraft:grass_block}',
           'solid':True,'passable':False,'fluid':False,'block_entity':False}
          for x in range(-4,5) for z in range(-4,5)]
  roof=[{'pos':[x,68,z],'state':'Block{minecraft:oak_leaves}',
         'solid':True,'passable':False,'fluid':False,'block_entity':False}
        for x in range(-4,5) for z in range(-4,5) if (x,z)!=(4,4)]
  self.assertIsNone(bounded_canopy_path(floors+roof,[.5,64.2,.5],95))
 def test_top_world_high_park_remains_a_supported_verified_target(self):
  c=MaterialClient.__new__(MaterialClient);c.world='world-2';c.park_target=[100.5,320,200.5]
  calls=[]
  def request(op,**params):
   calls.append(params)
   return {'world_session':c.world,'blocks':[]}
  c.request=request
  self.assertEqual([],c.ascent_obstacles({'pos':[100.5,300,200.5]}))
  self.assertEqual(calls[0]['max'][1],319)
 def test_leaf_canopy_forces_safe_logout_before_high_park_navigation(self):
  with tempfile.TemporaryDirectory() as temp:
   c=MaterialClient.__new__(MaterialClient)
   c.root=c.out=Path(temp);c.world='world-2';c.park_target=[100.5,145,200.5]
   c.remote_finish='guard';c.heartbeat=Mock();c.owned_material_menu=None
   state={'pos':[100.5,64.2,200.5],'guard_armed':True,'flight':True,'air_supply':300,'health':20,
          'menu':{'type':'InventoryMenu','slots':[{'count':0}]*5,'cursor':{'count':0}}}
   c.status=lambda:state
   calls=[]
   def request(op,**params):
    calls.append((op,params))
    if op=='scan':
     return {'world_session':c.world,'blocks':[{'pos':[100,66,200],
             'state':'Block{minecraft:oak_leaves}'}]}
    if op=='safe_logout':return {'phase':'done'}
    raise AssertionError('The blocked canopy must never receive a navigation command')
   c.request=request
   with patch('material_cleanup.run'),patch('craft_recovery.clear_owned_workbench'):
    c._finish()
   self.assertEqual([op for op,_ in calls],['scan','scan','safe_logout'])
   self.assertEqual(calls[0][1]['min'],[100,65,200])
   self.assertEqual(json.loads((c.out/'park-column-obstacle.json').read_text())['count'],1)
   self.assertEqual(json.loads((c.out/'park-fallback.json').read_text())['action'],'safe_logout')
   c.heartbeat.close.assert_called_once()
 def test_unverified_high_park_column_never_sends_navigation(self):
  c=MaterialClient.__new__(MaterialClient);c.world='world-2';c.park_target=[100.5,145,200.5]
  c.request=lambda op,**kw:{'phase':'error','world_session':c.world,'blocks':[]}
  with self.assertRaisesRegex(RuntimeError,'not freshly scanned'):
   c.ascent_obstacles({'pos':[100.5,64.2,200.5]})
 def test_grounded_full_health_guard_takes_off_in_bounded_verified_segments(self):
  c=MaterialClient.__new__(MaterialClient);c.world='world-2';c.park_target=[100.5,145,200.5]
  grounded={'pos':[100.5,64.875,200.5],'guard_armed':True,'guard_busy':False,
            'flight':False,'on_ground':True,'under_water':False,'health':20}
  middle={**grounded,'pos':[100.5,112.875,200.5],'flight':True,'on_ground':False}
  reached={**middle,'pos':[100.5,145,200.5]}
  states=iter([grounded,middle,middle,reached]);c.status=lambda:next(states)
  calls=[]
  def request(op,**params):
   calls.append((op,params))
   if op=='scan':return {'phase':'done','world_session':c.world,'blocks':[]}
   if op=='navigate':return {'phase':'done'}
   raise AssertionError(op)
  c.request=request
  first=c._finish_vertical(grounded)
  self.assertIs(first,middle)
  result=c._finish_vertical(first)
  self.assertIs(result,reached)
  self.assertEqual([op for op,_ in calls],['scan','navigate','scan','navigate'])
  moves=[params for op,params in calls if op=='navigate']
  self.assertEqual(len(moves),2)
  self.assertTrue(all(m['air_only'] for m in moves))
  self.assertEqual(moves[0]['target'],[100.5,112.875,200.5])
  self.assertEqual(moves[1]['target'],[100.5,145,200.5])

 def test_grounded_takeoff_rechecks_pose_health_and_guard_after_clear_scan(self):
  original={'pos':[100.5,64.875,200.5],'guard_armed':True,'guard_busy':False,
            'flight':False,'on_ground':True,'under_water':False,'health':20}
  changed_states=[{**original,'pos':[100.9,64.875,200.5]},
                  {**original,'guard_armed':False},
                  {**original,'health':19},
                  {**original,'on_ground':False}]
  for changed in changed_states:
   with self.subTest(changed=changed):
    c=MaterialClient.__new__(MaterialClient);c.world='world-2';c.park_target=[100.5,145,200.5]
    calls=[];c.status=lambda:changed
    def request(op,**params):
     calls.append((op,params))
     if op=='scan':return {'phase':'done','world_session':c.world,'blocks':[]}
     raise AssertionError('No movement may follow a stale takeoff scan')
    c.request=request
    with self.assertRaisesRegex(RuntimeError,'position or protection changed'):
     c._finish_vertical(original)
    self.assertEqual([op for op,_ in calls],['scan'])
 def test_grounded_blocked_column_uses_logout_fallback_without_movement(self):
  with tempfile.TemporaryDirectory() as temp:
   c=MaterialClient.__new__(MaterialClient)
   c.root=c.out=Path(temp);c.world='world-2';c.park_target=[100.5,145,200.5]
   c.remote_finish='guard';c.heartbeat=Mock();c.owned_material_menu=None
   state={'pos':[100.5,64.875,200.5],'guard_armed':True,'guard_busy':False,
          'flight':False,'on_ground':True,'under_water':False,'air_supply':300,'health':20,
          'menu':{'type':'InventoryMenu','slots':[{'count':0}]*5,'cursor':{'count':0}}}
   c.status=lambda:state
   calls=[]
   def request(op,**params):
    calls.append((op,params))
    if op=='scan':return {'phase':'done','world_session':c.world,'blocks':[
     {'pos':[100,66,200],'state':'Block{minecraft:stone}'}]}
    if op=='safe_logout':return {'phase':'done'}
    raise AssertionError('Blocked takeoff must not move')
   c.request=request
   with patch('material_cleanup.run'),patch('craft_recovery.clear_owned_workbench'):
    c._finish()
   self.assertEqual([op for op,_ in calls],['scan','safe_logout'])
   self.assertEqual(json.loads((c.out/'park-fallback.json').read_text())['action'],'safe_logout')
   c.heartbeat.close.assert_called_once()
 def test_only_pre_dispatch_guard_busy_is_retried(self):
  c=MaterialClient.__new__(MaterialClient);c.task='t';c.status=lambda:{}
  with patch.object(c,'_wait_guard_admission',return_value=True),patch.object(Client,'request',side_effect=[{'phase':'error','detail':BUSY},{'phase':'done'}]) as call,patch('material_client.time.sleep'):
   self.assertEqual(c.request('slot_click')['phase'],'done');self.assertEqual(call.call_count,2)
 def test_ambiguous_inventory_errors_are_never_replayed(self):
  c=MaterialClient.__new__(MaterialClient);c.task='t';c.status=lambda:{}
  with patch.object(Client,'request',return_value={'phase':'error','detail':'Inventory transfer not confirmed'}) as call:
   self.assertEqual(c.request('slot_click')['phase'],'error');self.assertEqual(call.call_count,1)
 def test_empty_approved_depot_is_not_reported_as_a_successful_fetch(self):
  c=MaterialClient.__new__(MaterialClient);c.task='t'
  c.status=lambda:{'inventory':[{'slot':0,'item':'minecraft:gravel','count':1}]}
  with patch.object(MaterialClient,'request',return_value={'phase':'done','build_supply':{'taken':{}}}) as call:
   result=c.fetch([1,2,3],{'gravel':16})
   self.assertEqual(result['phase'],'waiting')
   self.assertEqual(result['shortfall'],{'gravel':15})
   self.assertEqual(result['native_phase'],'done')
   self.assertEqual(call.call_count,1)
if __name__=='__main__':unittest.main()
