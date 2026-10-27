from pathlib import Path
import copy,json,tempfile,unittest
from unittest.mock import patch
from harness_strategy import DEFAULT,digest
import harness_runtime as runtime
from iron_water_sources import enclosed,STONE,RELEASE
class HarnessRuntimeTests(unittest.TestCase):
 def test_live_bait_observation_needs_no_sky_inference_or_block_scan(self):
  from types import SimpleNamespace
  mob=dict(uuid='v',type='minecraft:zombie',alive=True,health=20,is_baby=False,has_custom_name=False,on_fire=False,main_hand='minecraft:air')
  trident={**mob,'uuid':'d','type':'minecraft:drowned','main_hand':'minecraft:trident'}
  frame=dict(id='fresh',scope='current_client_loaded_server_hostile_entities',hostiles=[mob,trident],truncated=False)
  c=SimpleNamespace(root=Path('/unused'),checked=lambda *a,**k:(_ for _ in()).throw(AssertionError('No native action')))
  with tempfile.TemporaryDirectory()as td,patch.object(runtime,'require_player',return_value={'runtime_version':'1.8.20'}),patch.object(runtime,'selected',return_value=self.policy()),patch('loaded_hostiles.read',return_value=frame),patch('village_world_time.read',side_effect=AssertionError('Live entity does not depend on client sky')):
   result=runtime.find_zombie(c,Path(td)/'new'/'surface');self.assertTrue((Path(td)/'new'/'surface'/'loaded-hostiles.json').exists());self.assertEqual([mob],result['candidates']);self.assertEqual(0,result['scan_count']);self.assertEqual(0,result['capture_credit']);self.assertEqual(3,result['finder_protocol'])
 def test_new_runtime_waits_for_current_observer_instead_of_blind_scan(self):
  from types import SimpleNamespace
  c=SimpleNamespace(root=Path('/unused'))
  with patch.object(runtime,'require_player',return_value={'runtime_version':'1.8.20'}),patch.object(runtime,'selected',return_value=self.policy()),patch('loaded_hostiles.read',return_value=None):
   result=runtime.find_zombie(c,Path('/unused'));self.assertFalse(result['complete']);self.assertEqual('waiting',result['phase']);self.assertEqual(0,result['scan_count'])
 def test_feedback_keeps_policy_selected_at_command_start(self):
  with tempfile.TemporaryDirectory()as td,patch.object(runtime,'LIVE',Path(td)),patch.object(runtime,'selected',return_value=self.policy()):
   command=dict(id='fixture-command',action='native',op='scan')
   binding=runtime.begin('owner',command,{})
   with patch.object(runtime,'selected',side_effect=AssertionError('Do not relabel an in-flight command with a later policy')):
    record=runtime.feedback('owner',command,{},dict(phase='done'),None,12,strategy_snapshot=binding)
   self.assertEqual(record['strategy']['run_id'],'verified-fixture')
 def test_successful_source_stage_queues_one_receipt_review_without_game_retry(self):
  with tempfile.TemporaryDirectory()as td,patch.object(runtime,'LIVE',Path(td)):
   binding=runtime.attribution(self.policy())
   command=dict(id='verified-stage',action='harness_iron_stage',plan='local-plan.json')
   result=dict(complete=True,applied=True,selected_action='prepare_contained_sources',
               strategy=binding,source_proof='same-native-source-proof.json')
   for _ in range(2):runtime.feedback('owner',command,{},result,None,98,strategy_snapshot=binding)
   jobs=list((Path(td)/'review-requests').glob('*'));self.assertEqual(len(jobs),1)
   job=json.loads(jobs[0].read_text());self.assertEqual(job['kind'],'live_reflection')
   self.assertFalse(job['game_retry_authorized'])
   self.assertEqual(job['model_payload'],'verified_minimized_receipts_only')
 def test_observation_only_stage_cannot_create_success_learning_credit(self):
  with tempfile.TemporaryDirectory()as td,patch.object(runtime,'LIVE',Path(td)):
   binding=runtime.attribution(self.policy())
   runtime.feedback('owner',dict(id='daytime',action='harness_iron_stage'),{},
                    dict(complete=True,applied=True,selected_action='find_zombie'),None,1,strategy_snapshot=binding)
   self.assertFalse((Path(td)/'review-requests').exists())
 def policy(self):return dict(active=True,source='harness2_verified_replay_strategy',policy=DEFAULT,run_id='verified-fixture',policy_sha256=digest(DEFAULT))
 def test_enough_slots_does_not_open_or_transfer_anything(self):
  s=dict(health=20,connected=True,manual_movement=False,world_session='w',inventory=[dict(slot=i,item='minecraft:air',count=0)for i in range(4)],menu={'type':'InventoryMenu','id':0})
  class C:
   world='w'
   def status(self):return s
   def transfer(self,*a,**kw):raise AssertionError('No unnecessary transfer')
  with tempfile.TemporaryDirectory()as td,patch('harness_runtime.selected',return_value=self.policy()):
   r=runtime.prepare_space(C(),3,td);self.assertTrue(r['complete']);self.assertTrue(r['applied']);self.assertEqual(r['deposit_beds'],0);self.assertEqual(r['strategy']['run_id'],'verified-fixture')
 def test_selected_policy_deposits_only_missing_slots_and_measures_result(self):
  air=lambda i:dict(slot=i,item='minecraft:air',count=0)
  s=dict(health=20,connected=True,manual_movement=False,world_session='w',inventory=[air(0)]+[dict(slot=i,item='minecraft:white_bed',count=1)for i in range(1,7)],menu=dict(type='ChestMenu',id=1,cursor={'count':0},slots=[dict(slot=i,item='minecraft:air',count=0)for i in range(3)]+[dict(slot=i,item='minecraft:stone',count=64)for i in range(3,27)]+[air(i)for i in range(36)]))
  class C:
   world='w';owned_material_menu=1;calls=[]
   def status(self):return s
   def transfer(self,item,target,deposit):
    self.calls.append((item,target,deposit));s['inventory'][1]=air(1);s['inventory'][2]=air(2);return 4
  c=C()
  with tempfile.TemporaryDirectory()as td,patch('harness_runtime.selected',return_value=self.policy()):r=runtime.prepare_space(c,3,td)
  self.assertEqual(c.calls,[('minecraft:white_bed',4,True)]);self.assertTrue(r['complete']);self.assertEqual(r['deposit_beds'],2)
 def test_full_box_starts_no_transfer(self):
  s=dict(health=20,connected=True,manual_movement=False,world_session='w',inventory=[dict(slot=0,item='minecraft:white_bed',count=1)],menu=dict(type='ChestMenu',id=1,cursor={'count':0},slots=[dict(slot=i,item='minecraft:stone',count=64)for i in range(63)]))
  class C:
   world='w';owned_material_menu=1
   def status(self):return s
   def transfer(self,*a,**kw):raise AssertionError('Full box must be preflighted')
  with tempfile.TemporaryDirectory()as td,patch('harness_runtime.selected',return_value=self.policy()):r=runtime.prepare_space(C(),3,td)
  self.assertFalse(r['complete']);self.assertEqual(r['decision']['action'],'use_other_storage')
 def test_contained_source_preview_refuses_any_open_boundary(self):
  rows={};x,y,z=761077,95,797805
  for xx in range(x-2,x+3):
   for zz in range(z-1,z+2):rows[xx,y-1,zz]={'state':STONE}
  for xx in range(x-2,x+3):
   for zz in (z-1,z+1):rows[xx,y,zz]={'state':STONE}
  for xx in (x-2,x+2):rows[xx,y,z]={'state':STONE}
  bounds={'min':[x-2,y-1,z-1],'max':[x+2,y+2,z+1]}
  self.assertTrue(enclosed(rows,[x,y,z],bounds));del rows[x,y,z-1];self.assertFalse(enclosed(rows,[x,y,z],bounds))
if __name__=='__main__':unittest.main()
