import copy,unittest
from projection_stage_reconciliation import reconcile,preview,ERROR,INCOMPLETE,transient_wire
class ReconciliationTests(unittest.TestCase):
 def test_unresolved_projection_record_blocks_world_input_before_dispatch(self):
  import tempfile,json
  from pathlib import Path
  from village_queue import VillageQueue
  with tempfile.TemporaryDirectory()as directory:
   q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);(q.out/'unresolved-projection-stage.json').write_text(json.dumps(dict(pending=True)))
   with self.assertRaisesRegex(RuntimeError,'conserved prediction-free observation'):
    q._send('native',op='interact',params={})
 def fixture(self):
  stage=dict(world_session='w',complete=False,placement_key='key',passes=[dict(total=2,matched=1,loaded_server_chunks_verified=True,placement_key='key',mismatches=[dict(kind='missing',pos=[1,0,0])])],before=dict(mismatches=[dict(pos=[0,0,0]),dict(pos=[1,0,0])]),inventory_before={'minecraft:cobblestone':2})
  model=dict(placement_key='key',bounds=dict(min=[0,0,0],max=[1,0,0]),expected=[dict(pos=[x,0,0],state='stone',item='minecraft:cobblestone')for x in [0,1]])
  frame=dict(world_session='w',scan_cells_read=2,scan_total_cells=2,scan_predictions=dict(complete=True,pending_count=0,pending_positions=[]),blocks=[dict(pos=[0,0,0],state='stone')])
  state=dict(inventory=[dict(slot=0,item='minecraft:cobblestone',count=1)],last_request='audit',control_revision=4,pos=[0,2,0],health=20,screen='',manual_movement=False,build_job=dict(active=False,queue_settled=True,placement_key='key',matched=1),professional_printer=dict(enabled=False,owned=False,waiting_for_server=False))
  return stage,model,frame,state
 def test_conserves_partial_stage_without_replaying(self):
  a,b,c,s=self.fixture();r=reconcile(a,b,c,s);self.assertEqual(r['matched'],1);self.assertEqual(r['missing'],[[1,0,0]]);self.assertFalse(r['replayed'])
 def test_wire_connection_change_is_conserved_but_not_final_completion(self):
  a,b,c,s=self.fixture();wanted='Block{minecraft:redstone_wire}[east=side,north=none,power=0,south=side,west=side]';actual=wanted.replace('east=side','east=none')
  b['expected'][0].update(state=wanted,item='minecraft:redstone');c['blocks'][0]['state']=actual
  a['inventory_before']={'minecraft:redstone':1,'minecraft:cobblestone':1};a['passes'][0]['matched']=0;s['build_job']['matched']=0
  a['passes'][0]['mismatches']=[dict(kind='state_only',pos=[0,0,0],expected=wanted,actual=actual),dict(kind='missing',pos=[1,0,0])]
  r=reconcile(a,b,c,s);self.assertEqual(r['physical_placements'],1);self.assertEqual(r['matched'],0);self.assertFalse(r['final_topology_verified']);self.assertFalse(r['replayed'])
  last=dict(request_id='audit',op='projection_audit',world_session='w',params=dict(task_session='t'),revision_after=4,position_after=[0,2,0])
  error=dict(error=INCOMPLETE,type='RuntimeError',native_inflight=None,unconfirmed_native_request=None,last_request='audit')
  self.assertEqual(preview(dict(action='build_village_stage'),error,a,b,s,last,'w','t'),b['bounds'])
  c['scan_predictions']['pending_count']=1
  with self.assertRaises(ValueError):reconcile(a,b,c,s)
 def test_wire_power_type_and_property_set_changes_are_not_neighbor_connections(self):
  wanted='Block{minecraft:redstone_wire}[east=side,north=none,power=0,south=side,west=side]'
  for actual in [wanted.replace('power=0','power=15'),wanted.replace('redstone_wire','tripwire'),wanted.replace(',west=side',''),'Block{minecraft:air}']:
   with self.subTest(actual=actual):self.assertFalse(transient_wire(wanted,actual))
 def test_pending_predictions_inventory_loss_and_replacement_block_recovery(self):
  for bad in ['prediction','count','inventory','replacement','world']:
   a,b,c,s=self.fixture()
   if bad=='prediction':c['scan_predictions']['pending_count']=1
   if bad=='count':c['scan_cells_read']=1
   if bad=='inventory':s['inventory'][0]['count']=2
   if bad=='replacement':c['blocks'][0]['state']='other'
   if bad=='world':c['world_session']='old'
   with self.subTest(bad=bad),self.assertRaises(ValueError):reconcile(a,b,c,s)
 def test_read_preview_rejects_live_jobs_unknown_inputs_manual_and_foreign_events(self):
  for bad in [None,'running','unknown','manual','event','pending_scope','pending_count']:
   a,b,c,s=self.fixture();command=dict(action='build_village_stage');error=dict(error=ERROR,type='RuntimeError',native_inflight=None,unconfirmed_native_request=None,last_request='audit');last=dict(request_id='audit',op='projection_audit',world_session='w',params=dict(task_session='t'),revision_after=4,position_after=[0,2,0])
   if bad=='running':s['build_job']['active']=True
   if bad=='unknown':error['unconfirmed_native_request']='x'
   if bad=='manual':s['manual_movement']=True
   if bad=='event':last['world_session']='other'
   if bad=='pending_scope':s['professional_printer'].update(travel_pending=1,last_proposal=dict(target='99, 0, 0',interaction_matches_proposal=True))
   if bad=='pending_count':s['professional_printer']['travel_pending']=2
   if bad:
    with self.subTest(bad=bad),self.assertRaises(ValueError):preview(command,error,a,b,s,last,'w','t')
   else:self.assertEqual(preview(command,error,a,b,s,last,'w','t'),b['bounds'])
if __name__=='__main__':unittest.main()
