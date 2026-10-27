import json,tempfile,unittest,copy
from pathlib import Path
from village_queue import VillageQueue
class RetainedGuardTests(unittest.TestCase):
 def fixture(self,directory):
  q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'t'};d=q.out/'p-002';d.mkdir();p=q.out/'p-001';p.mkdir();(q.out/'control').mkdir()
  state=dict(id='r',last_request='r',phase='done',world_session='w',pos=[0,64,0],control_revision=3,inventory=[dict(slot=0,item='minecraft:oak_boat',count=1)]);q.status=lambda:state
  files={'command.json':dict(id='p-002',action='boat_place'),'p-001/intent.json':dict(action='native',op='snapshot'),'p-001/result.json':copy.deepcopy(state),'p-002/error.json':dict(error='Original boat intent is unresolved; no repeated input',type='RuntimeError',native_inflight=None,unconfirmed_native_request=None,last_request='r')}
  for name,value in files.items():(q.out/name).write_text(json.dumps(value))
  (q.out/'control/events.jsonl').write_text(json.dumps(dict(request_id='r',phase='done',op='snapshot',world_session='w',revision_after=3,params=dict(task_session='t')))+'\n');sent=[];q.native=lambda op:sent.append(op);return q,d,state,sent
 def test_only_observes_a_known_pre_dispatch_guard(self):
  with tempfile.TemporaryDirectory()as d:
   q,p,s,sent=self.fixture(d);q.observe_retained_boat_guard();self.assertEqual(sent,['snapshot']);self.assertFalse((p/'result.json').exists())
 def test_native_immediate_snapshot_without_phase_is_still_read_only(self):
  with tempfile.TemporaryDirectory()as d:
   q,p,s,sent=self.fixture(d);path=q.out/'p-001/result.json';data=json.loads(path.read_text());data.pop('phase');path.write_text(json.dumps(data));path=q.out/'control/events.jsonl';event=json.loads(path.read_text());event['phase']=None;path.write_text(json.dumps(event)+'\n');q.observe_retained_boat_guard();self.assertEqual(sent,['snapshot'])
 def test_existing_native_unknown_new_boat_journal_or_changed_stock_refuses(self):
  for bad in ['unknown','journal','stock','moved']:
   with self.subTest(bad=bad),tempfile.TemporaryDirectory()as d:
    q,p,s,sent=self.fixture(d)
    if bad=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if bad=='journal':(p/'actual-one-boat').mkdir()
    if bad=='stock':s['inventory'][0]['count']=0
    if bad=='moved':s['pos']=[1,64,0]
    with self.assertRaises(RuntimeError):q.observe_retained_boat_guard()
    self.assertEqual(sent,[])
if __name__=='__main__':unittest.main()
