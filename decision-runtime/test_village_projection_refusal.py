import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kit_runtime.journal import write_json
from village_queue import VillageQueue

class ProjectionReadRefusalTests(unittest.TestCase):
 def fixture(self,d):
  q=VillageQueue.__new__(VillageQueue);q.out=Path(d);q.root=q.out/'root';q.root.mkdir();q.world='w';q.lease={'job_session':'task'};q.prefix='observe';q.index=0;q.closing_menu=None
  (q.out/'old').mkdir();(q.out/'control').mkdir();write_json(q.out/'command.json',{'id':'old','action':'native','op':'projection_model','params':{}})
  reply={'id':'r','phase':'error','detail':'请只启用本次要建造的一份投影','world_session':'w'};write_json(q.out/'old/result.json',reply)
  s={'world_session':'w','last_request':'r','control_revision':2,'pos':[1,2,3],'screen':''};q.status=lambda **kw:s
  event={'request_id':'r','world_session':'w','op':'projection_model','phase':'error','params':{'task_session':'task'},'revision_after':2,'position_after':[1,2,3],'inventory_delta':{}}
  (q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');return q,s,reply,event
 def test_only_snapshot_dispatched(self):
  with tempfile.TemporaryDirectory() as d:
   q,s,reply,event=self.fixture(d);before=(q.out/'old/result.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':sent.append(value);(q.out/value['id']).mkdir();write_json(q.out/value['id']/'result.json',{'phase':'done','world_session':'w'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_projection_model_selection_refusal()
   self.assertEqual([v['op'] for v in sent],['snapshot']);self.assertEqual(before,(q.out/'old/result.json').read_bytes())
 def test_uncertain_print_only_allows_exact_read_and_preserves_original(self):
  for bad in (None,'changed_revision','printer_busy','wrong_mask','manual','multiple_targets'):
   with self.subTest(bad=bad),tempfile.TemporaryDirectory() as d:
    q,s,reply,event=self.fixture(d);target=[4,5,6]
    write_json(q.out/'command.json',{'id':'old','action':'native','op':'professional_print','params':{}})
    reply.update(phase='error',outcome_pending=True,server_confirmed=False,bounded_targets=[target],placement_key='key',control_revision=2)
    s.update(health=20,manual_movement=False,professional_printer={'enabled':False,'waiting_for_server':False},projection_batch={'active':True,'count':1,'placement_key':'key'})
    if bad=='changed_revision':s['control_revision']=3
    if bad=='printer_busy':s['professional_printer']['enabled']=True
    if bad=='wrong_mask':s['projection_batch']['placement_key']='other'
    if bad=='manual':s['manual_movement']=True
    if bad=='multiple_targets':reply['bounded_targets']=[target,[7,8,9]]
    write_json(q.out/'old/result.json',reply);before=(q.out/'old/result.json').read_bytes();sent=[]
    q.native=lambda op,**params:sent.append((op,params)) or {'id':'scan'}
    if bad:
     with self.assertRaises(RuntimeError):q.observe_uncertain_single_printer()
     self.assertEqual(sent,[])
    else:
     self.assertEqual(q.observe_uncertain_single_printer(),{'id':'scan'})
     self.assertEqual(sent,[('scan',{'min':target,'max':target,'details':True,'include_predictions':True})])
    self.assertEqual(before,(q.out/'old/result.json').read_bytes())
 def test_unknown_or_changed_outcome_rejected(self):
  for mode in ('pending','position','revision','detail','inventory'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
    q,s,reply,event=self.fixture(d)
    if mode=='pending':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if mode=='position':s['pos']=[2,2,3]
    if mode=='revision':s['control_revision']=3
    if mode=='detail':reply['detail']='other';write_json(q.out/'old/result.json',reply)
    if mode=='inventory':event['inventory_delta']={'minecraft:stone':1};(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
    with self.assertRaises(RuntimeError):q.observe_projection_model_selection_refusal()
 def test_load_envelope_refusal_allows_only_snapshot(self):
  with tempfile.TemporaryDirectory() as d:
   q,s,reply,event=self.fixture(d)
   write_json(q.out/'command.json',{'id':'old','action':'native','op':'projection_load','params':{}})
   reply['detail']='Unsupported projection-load field: task_session';write_json(q.out/'old/result.json',reply)
   event['op']='projection_load';(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':sent.append(value);(q.out/value['id']).mkdir();write_json(q.out/value['id']/'result.json',{'phase':'done','world_session':'w'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_projection_model_selection_refusal()
   self.assertEqual([v['op'] for v in sent],['snapshot'])
 def test_load_idle_refusal_is_observed_without_replay(self):
  with tempfile.TemporaryDirectory() as d:
   q,s,reply,event=self.fixture(d)
   write_json(q.out/'command.json',{'id':'old','action':'native','op':'projection_load','params':{}})
   reply['detail']='Projection import needs an idle, healthy, current world/controller and unexpired explicit request';write_json(q.out/'old/result.json',reply)
   event['op']='projection_load';(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':sent.append(value);(q.out/value['id']).mkdir();write_json(q.out/value['id']/'result.json',{'phase':'done','world_session':'w'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_projection_model_selection_refusal()
   self.assertEqual([v['op'] for v in sent],['snapshot'])
 def test_taskless_load_requires_matching_retained_owner(self):
  for owner in ('task','other'):
   with self.subTest(owner=owner),tempfile.TemporaryDirectory() as d:
    q,s,reply,event=self.fixture(d)
    command={'id':'old','action':'native','op':'projection_load','params':{'schema':1}}
    write_json(q.out/'command.json',command);reply['detail']='Projection import needs an idle, healthy, current world/controller and unexpired explicit request';write_json(q.out/'old/result.json',reply)
    event.update(op='projection_load',params={'schema':1});(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');write_json(q.out/'transport-kernel.json',{'world_session':'w','task_session':owner})
    def dispatch(op,**kwargs):self.assertEqual(op,'snapshot');return {'id':'observed'}
    q.native=dispatch
    if owner=='task':self.assertEqual(q.observe_projection_model_selection_refusal()['id'],'observed')
    else:
     with self.assertRaises(RuntimeError):q.observe_projection_model_selection_refusal()
if __name__=='__main__':unittest.main()
