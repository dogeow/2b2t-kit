import copy,json,tempfile,unittest
from pathlib import Path
from certified_hover_trunk_harvest import run
from ground_work_threat_survey import ENTITY_SCOPE
class Builder:
 def __init__(self,root,plan,threat=False):self.root=root;self.plan=plan;self.threat=threat;self.rows={tuple(s['pos']):{'pos':s['pos'],'state':s['expected_state'],'fluid':False,'block_entity':False}for s in plan['steps']};self.calls=[];self.pos=[.5,90,.5];self.logs=0;self.clock=1000;self.deferred=0
 def check(self):
  return {'connected':True,'world_session':'w','health':20,'manual_movement':False,'guard_armed':True,'guard_pve_only':True,'screen':'','flight':True,'guard_busy':getattr(self,'busy',False),'pos':self.pos,'control_revision':5,'supervision_lease':{'kind':'materials','world_session':'w','job_session':'t','revision':5},'inventory':[{'slot':1,'item':'minecraft:oak_log','count':self.logs}]}
 def nav(self,p):
  self.calls.append(('navigate',p));self.pos=p
  if getattr(self,'drift',False)and p in [s['hover']for s in self.plan['steps']]:self.pos=[p[0],p[1]+6,p[2]]
  if p==self.plan['pickup_core']:self.logs+=self.deferred;self.deferred=0
 def scan(self,lo,hi):return {},{p:r for p,r in self.rows.items()if all(a<=v<=b for a,v,b in zip(lo,p,hi))}
 def n(self,op,**p):
  self.calls.append((op,p))
  if op=='select_item':return {'phase':'done'}
  if op=='scan':
   import time
   n=1
   for a,b in zip(p['min'],p['max']):n*=b-a+1
   return {'id':'s','phase':'done','world_session':'w','scan_start_revision':5,'scan_end_revision':5,'scan_cells_read':n,'scan_total_cells':n,'scan_entity_scope':ENTITY_SCOPE,'scan_ended_at':int(time.time()*1000),'scan_entities':[{'alive':True,'hostile':True,'pos':[1,63,1]}]if self.threat else []}
  if op=='mine_block':
   row=self.rows.pop(tuple(p['pos']));self.deferred+=int('oak_log'in row['state']);return {'id':'m','server_confirmed':True,'native_sequence':1,'server_ack_sequence':1}
  raise AssertionError(op)
class CertifiedHoverTrunkHarvestTest(unittest.TestCase):
 def plan(self):
  from test_certified_hover_trunk_plan import CertifiedHoverTrunkPlanTest
  f=CertifiedHoverTrunkPlanTest();return f.call(f.fixture())
 def test_executes_only_certified_core_and_no_grounded_chop(self):
  with tempfile.TemporaryDirectory()as t:
   root=Path(t);p=self.plan();b=Builder(root,p);r=run(b,p,root/'job.json');self.assertTrue(r['complete']);self.assertEqual(8,r['logs_mined']);self.assertFalse(any(op in ['walk','chop']for op,_ in b.calls));self.assertEqual([s['pos']for s in p['steps']],[a['pos']for op,a in b.calls if op=='mine_block'])
 def test_ground_threat_pauses_before_low_work_and_can_resume_without_remining(self):
  with tempfile.TemporaryDirectory()as t:
   root=Path(t);p=self.plan();b=Builder(root,p,True);path=root/'job.json';r=run(b,p,path);self.assertFalse(r['complete']);prior=[a['pos']for op,a in b.calls if op=='mine_block'];b.threat=False;self.assertTrue(run(b,p,path,resume=True)['complete']);allpos=[tuple(a['pos'])for op,a in b.calls if op=='mine_block'];self.assertEqual(len(allpos),len(set(allpos)));self.assertGreater(len(prior),0)
 def test_active_native_safety_hold_sends_no_input(self):
  with tempfile.TemporaryDirectory()as t:
   root=Path(t);(root/'safety-hold.json').write_text(json.dumps({'active':True}));p=self.plan();b=Builder(root,p)
   with self.assertRaisesRegex(RuntimeError,'Safety lock'):run(b,p,root/'job.json')
   self.assertEqual([],b.calls)
 def test_pve_input_priority_does_not_select_tools_or_move(self):
  with tempfile.TemporaryDirectory()as t:
   root=Path(t);p=self.plan();b=Builder(root,p);b.busy=True;r=run(b,p,root/'job.json');self.assertFalse(r['complete']);self.assertEqual('waiting_for_defense',r['phase']);self.assertEqual([],b.calls)
 def test_guard_pose_change_does_not_mine_from_the_wrong_height(self):
  with tempfile.TemporaryDirectory()as t:
   root=Path(t);p=self.plan();b=Builder(root,p);b.drift=True;r=run(b,p,root/'job.json');self.assertFalse(r['complete']);self.assertEqual('waiting_after_owned_pose_changed',r['phase']);self.assertFalse(any(op=='mine_block'for op,_ in b.calls))
 def test_unknown_break_reply_is_retained_and_never_resent(self):
  with tempfile.TemporaryDirectory()as t:
   root=Path(t);p=self.plan()
   class Unconfirmed(Builder):
    def n(self,op,**kw):
     result=super().n(op,**kw)
     if op=='mine_block':result['server_confirmed']=False
     return result
   b=Unconfirmed(root,p);path=root/'job.json'
   with self.assertRaisesRegex(RuntimeError,'not server-confirmed'):run(b,p,path)
   before=len(b.calls);self.assertIsNotNone(json.loads(path.read_text())['pending'])
   with self.assertRaisesRegex(RuntimeError,'same-owner'):run(b,p,path,resume=True)
   self.assertEqual(before,len(b.calls))
 def test_pending_journal_is_never_replayed(self):
  with tempfile.TemporaryDirectory()as t:
   root=Path(t);p=self.plan();b=Builder(root,p);path=root/'job.json';path.write_text(json.dumps({'pending':{'op':'mine_block'}}))
   with self.assertRaisesRegex(RuntimeError,'same-owner'):run(b,p,path,resume=True)
   self.assertEqual([],b.calls)
if __name__=='__main__':unittest.main()
