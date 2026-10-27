import copy,unittest,json,tempfile
from pathlib import Path
from unittest.mock import Mock
from stopped_lectern_mining import preview,reconcile,read_allowed,DETAIL

class Tests(unittest.TestCase):
 def fixture(self):
  p=dict(pos=[1,65,2],expected_state='Block{minecraft:lectern}[facing=north,has_book=false,powered=false]',reset_empty_lectern=True,expected_villager_uuid='v',expected_quote_opening='q',expected_offers_fingerprint='f')
  c=dict(id='command',action='native',op='mine_block',params=p)
  inv=[dict(slot=0,item='minecraft:lectern',count=0)]
  s=dict(world_session='w',last_request='request',control_revision=8,pos=[1.5,65.1,3.4],health=20,manual_movement=False,screen='',inventory=inv,time=100)
  r=dict(world_session='w',id='request',phase='waiting',detail=DETAIL,native_sequence=4,server_ack_sequence=4,server_confirmed=False,mining_target=p['pos'],pos=s['pos'],inventory=inv)
  e=dict(request_id='request',op='mine_block',phase='waiting',detail=DETAIL,world_session='w',params=dict(p,task_session='t'),inventory_delta={},revision_before=7,revision_after=8,position_before=s['pos'],position_after=s['pos'],health_before=20,health_after=20)
  return c,r,e,s
 def test_conserved_abort_reads_only_exact_cell_and_gives_zero_credit(self):
  c,r,e,s=self.fixture();m=preview(c,r,e,s,'w','t');f=dict(world_session='w',scan_cells_read=1,scan_total_cells=1,scan_predictions=dict(complete=True,pending_count=0,pending_positions=[]),blocks=[dict(pos=m['target'],state=m['expected_state'])])
  self.assertTrue(read_allowed(m,'native',dict(op='scan',params=dict(min=m['target'],max=m['target'],details=True,include_predictions=True))))
  done=reconcile(m,[f,f],[s,dict(s,time=101)]);self.assertFalse(done['pending']);self.assertFalse(done['replayed']);self.assertEqual(0,done['mining_credit'])
 def test_missing_ack_foreign_control_inventory_and_live_actions_refuse_preview(self):
  for change in ('ack','sequence','used','delta','world','revision','position','inventory','manual','live'):
   c,r,e,s=self.fixture()
   if change=='ack':r['server_ack_sequence']=3
   if change=='sequence':r['native_sequence']=0
   if change=='used':r['server_confirmed']=True
   if change=='delta':e['inventory_delta']={'minecraft:lectern':1}
   if change=='world':s['world_session']='other'
   if change=='revision':s['control_revision']=9
   if change=='position':s['pos']=[9,65,2]
   if change=='inventory':s['inventory']=[dict(slot=1,item='minecraft:lectern',count=1)]
   if change=='manual':s['manual_movement']=True
   if change=='live':s['native_material_busy']=True
   with self.subTest(change=change),self.assertRaises(ValueError):preview(c,r,e,s,'w','t')
 def test_writes_wrong_cells_and_ordinary_scans_stay_fenced(self):
  c,r,e,s=self.fixture();m=preview(c,r,e,s,'w','t')
  for op in ('mine_block','interact','snapshot','navigate'):
   self.assertFalse(read_allowed(m,'native',dict(op=op)))
  self.assertFalse(read_allowed(m,'native',dict(op='scan',params=dict(min=m['target'],max=m['target'],details=True))))
 def test_pending_predictions_changed_block_stock_duplicate_times_preserve_fence(self):
  c,r,e,s=self.fixture();m=preview(c,r,e,s,'w','t');f=dict(world_session='w',scan_cells_read=1,scan_total_cells=1,scan_predictions=dict(complete=True,pending_count=0,pending_positions=[]),blocks=[dict(pos=m['target'],state=m['expected_state'])])
  for change in ('prediction','block','stock','time','world'):
   a=copy.deepcopy(f);t=copy.deepcopy(s);t['time']=101
   if change=='prediction':a['scan_predictions']['pending_count']=1
   if change=='block':a['blocks']=[]
   if change=='stock':t['inventory']=[dict(slot=0,item='minecraft:lectern',count=1)]
   if change=='time':t['time']=100
   if change=='world':a['world_session']='other'
   with self.subTest(change=change),self.assertRaises(ValueError):reconcile(m,[f,a],[s,t])

 def test_queue_retains_persistent_fence_even_after_one_read_command(self):
  from village_queue import VillageQueue
  c,r,e,s=self.fixture();m=preview(c,r,e,s,'w','t')
  with tempfile.TemporaryDirectory()as d:
   q=VillageQueue.__new__(VillageQueue);q.out=Path(d);q.world='w'
   (q.out/'lectern-mining-readback.json').write_text(json.dumps(m))
   q.status=Mock(side_effect=AssertionError('reached ordinary status gate'))
   for op in ('interact','mine_block','navigate','snapshot'):
    with self.subTest(op=op),self.assertRaisesRegex(RuntimeError,'mutations remain fenced'):
     q._send('native',op=op,params={})
   scan=dict(min=m['target'],max=m['target'],details=True,include_predictions=True)
   with self.assertRaisesRegex(RuntimeError,'mutations remain fenced'):
    q._send('native',op='scan',params=scan)
   q.status.assert_not_called()
   q._stopped_lectern_read='command'
   with self.assertRaisesRegex(AssertionError,'ordinary status gate'):
    q._send('native',op='scan',params=scan)
   (q.out/'lectern-mining-readback.json').write_text(json.dumps(dict(m,pending=False)))
   q.status.reset_mock()
   with self.assertRaisesRegex(RuntimeError,'readback grants no retry'):
    q._send('native',op='mine_block',params=dict(pos=m['target']))
   q.status.assert_not_called()

 def test_new_owner_cannot_bypass_a_project_retained_target(self):
  from village_queue import VillageQueue
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);q=VillageQueue.__new__(VillageQueue);q.out=root/'new-owner';q.out.mkdir();q.world='w'
   (root/'project-state.json').write_text(json.dumps({'protected_pending_excavation_targets':[{'world_session':'w','pos':[1,65,2],'native_claim_not_cleared':True}]}))
   q.status=Mock(side_effect=AssertionError('unrelated target reached normal checks'))
   with self.assertRaisesRegex(RuntimeError,'new owners cannot retry'):
    q._send('native',op='mine_block',params={'pos':[1,65,2]})
   q.status.assert_not_called()
   with self.assertRaisesRegex(AssertionError,'normal checks'):
    q._send('native',op='mine_block',params={'pos':[2,65,2]})

 def test_pending_ack_readback_keeps_raw_receipt_and_unresolved_fence(self):
  c,r,e,s=self.fixture();r['server_ack_sequence']=-1;r['outcome_pending']=True
  with self.assertRaises(ValueError):preview(c,r,e,s,'w','t')
  m=preview(c,r,e,s,'w','t',allow_unacknowledged_readback=True)
  self.assertEqual(-1,m['original_reply']['server_ack_sequence'])
  f=dict(world_session='w',scan_cells_read=1,scan_total_cells=1,scan_predictions=dict(complete=True,pending_count=0,pending_positions=[]),blocks=[dict(pos=m['target'],state=m['expected_state'])])
  result=reconcile(m,[f,f],[s,dict(s,time=101)])
  self.assertTrue(result['original_outcome_unresolved']);self.assertTrue(result['native_claim_not_cleared'])
  self.assertEqual(0,result['mining_credit']);self.assertFalse(result['replayed'])
  for op in ('mine_block','interact','navigate','snapshot'):
   self.assertFalse(read_allowed(m,'native',dict(op=op)))

 def test_pending_ack_opt_in_never_admits_other_sequence_or_nonpending_outcome(self):
  for ack,pending in [(3,True),(-1,False),(-1,None)]:
   c,r,e,s=self.fixture();r['server_ack_sequence']=ack;r['outcome_pending']=pending
   with self.subTest(ack=ack,pending=pending),self.assertRaises(ValueError):preview(c,r,e,s,'w','t',allow_unacknowledged_readback=True)

if __name__=='__main__':unittest.main()
