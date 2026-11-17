import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kit_runtime.journal import write_json
from test_village_storage_corridor_refusal import StorageCorridorRefusalTests

class DepotLandingRefusalTests(unittest.TestCase):
 def fixture(self,d):
  q,s,events=StorageCorridorRefusalTests().fixture(d)
  write_json(q.out/'old-001/intent.json',{'action':'native','op':'walk'})
  write_json(q.out/'old-002/error.json',{'error':'Chest landing column is obstructed','type':'OutdoorChestLandingBlocked','native_inflight':None,'unconfirmed_native_request':None,'last_request':'last'})
  return q,s,events
 def test_only_snapshot_after_known_preflight_refusal(self):
  with tempfile.TemporaryDirectory() as d:
   q,s,events=self.fixture(d);sent=[];old=(q.out/'old-002/error.json').read_bytes()
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':sent.append(value);(q.out/value['id']).mkdir();write_json(q.out/value['id']/'result.json',{'phase':'done','world_session':'w'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_depot_landing_refusal()
   self.assertEqual([v['op'] for v in sent],['snapshot']);self.assertEqual(old,(q.out/'old-002/error.json').read_bytes())
 def test_input_or_changed_inventory_fences_observation(self):
  for mode in ('input','inventory','unknown'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
    q,s,events=self.fixture(d)
    if mode=='input':events[-1]['op']='interact';(q.out/'control/events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    if mode=='inventory':s['inventory'][0]['count']=24
    if mode=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    with self.assertRaises(RuntimeError):q.observe_depot_landing_refusal()
if __name__=='__main__':unittest.main()
