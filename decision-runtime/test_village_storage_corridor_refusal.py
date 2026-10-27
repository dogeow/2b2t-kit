import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kit_runtime.journal import write_json
from village_queue import VillageQueue
class StorageCorridorRefusalTests(unittest.TestCase):
 def fixture(self,d):
  q=VillageQueue.__new__(VillageQueue);q.out=Path(d);q.world='w';q.lease={'job_session':'task'};q.prefix='observe';q.index=0;q.closing_menu=None
  for name in ['old-001','old-002','control']:(q.out/name).mkdir()
  write_json(q.out/'command.json',dict(id='old-002',action='exchange'));write_json(q.out/'old-001/intent.json',dict(action='native',op='scan'));s=dict(id='last',world_session='w',last_request='last',phase='done',control_revision=3,pos=[2,2,3],health=20,screen='',inventory=[{'slot':0,'item':'minecraft:cobblestone','count':23}]);q.status=lambda **kw:s;write_json(q.out/'old-001/result.json',{**s,'id':'baseline'});write_json(q.out/'old-002/error.json',dict(error='Original storage return body corridor changed; no movement sent',type='StockBlocked',native_inflight=None,unconfirmed_native_request=None,last_request='last'));events=[dict(request_id='baseline'),dict(request_id='last',world_session='w',op='scan',phase='done',inventory_delta={},params={'task_session':'task'},revision_after=3,position_after=[2,2,3])];(q.out/'control/events.jsonl').write_text(''.join(json.dumps(e)+'\n'for e in events));return q,s,events
 def test_reads_only_without_retrying_the_failed_exchange(self):
  with tempfile.TemporaryDirectory()as d:
   q,s,events=self.fixture(d);old=(q.out/'old-002/error.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':sent.append(value);(q.out/value['id']).mkdir();write_json(q.out/value['id']/'result.json',dict(phase='done',world_session='w'))
   with patch('village_queue.write_json',side_effect=owner):q.observe_storage_corridor_refusal()
   self.assertEqual([x['op']for x in sent],['snapshot']);self.assertEqual(old,(q.out/'old-002/error.json').read_bytes())
 def test_opening_transfer_unknown_or_changed_stock_cannot_be_adopted(self):
  for mode in ['interact','slot_click','unknown','stock']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as d:
    q,s,events=self.fixture(d)
    if mode in ['interact','slot_click']:events[-1]['op']=mode;(q.out/'control/events.jsonl').write_text(''.join(json.dumps(e)+'\n'for e in events))
    if mode=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if mode=='stock':s['inventory'][0]['count']=24
    with self.assertRaises(RuntimeError):q.observe_storage_corridor_refusal()
if __name__=='__main__':unittest.main()
