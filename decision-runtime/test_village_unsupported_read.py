import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kit_runtime.journal import write_json
from village_queue import VillageQueue
class UnsupportedReadTests(unittest.TestCase):
 def fixture(self,directory):
  q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'task'};q.prefix='observe';q.index=0;q.closing_menu=None
  (q.out/'old').mkdir();(q.out/'control').mkdir();command=dict(id='old',action='native',op='scan_snow_biomes');write_json(q.out/'command.json',command);error=dict(error='Native operation is outside this village project',type='ValueError',native_inflight=None,unconfirmed_native_request=None,last_request='done');write_json(q.out/'old/error.json',error);s=dict(world_session='w',last_request='done',phase='done',control_revision=2,pos=[1,2,3],screen='');q.status=lambda **kw:s;event=dict(request_id='done',world_session='w',phase='done',params={'task_session':'task'},revision_after=2,position_after=[1,2,3]);(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');return q,s,error
 def test_only_snapshot_dispatched_and_original_rejection_retained(self):
  with tempfile.TemporaryDirectory()as d:
   q,s,error=self.fixture(d);original=(q.out/'old/error.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':
     sent.append(value);(q.out/value['id']).mkdir();write_json(q.out/value['id']/'result.json',dict(phase='done',world_session='w'))
   with patch('village_queue.write_json',side_effect=owner):q.observe_unsupported_readonly_native()
   self.assertEqual([x['op']for x in sent],['snapshot']);self.assertEqual(original,(q.out/'old/error.json').read_bytes())
 def test_unknown_request_position_revision_or_mutating_op_rejected(self):
  for mode in ['unknown','request','position','revision','op']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as d:
    q,s,error=self.fixture(d)
    if mode=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if mode=='request':s['last_request']='other'
    if mode=='position':s['pos']=[2,2,3]
    if mode=='revision':s['control_revision']=3
    if mode=='op':write_json(q.out/'command.json',dict(id='old',action='native',op='mine_block'))
    with self.assertRaises(RuntimeError):q.observe_unsupported_readonly_native()
if __name__=='__main__':unittest.main()
