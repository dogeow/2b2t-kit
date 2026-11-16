import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from kit_runtime.journal import write_json
from village_queue import VillageQueue

class PackedPadRefusalTests(unittest.TestCase):
 def fixture(self,d):
  q=VillageQueue.__new__(VillageQueue);q.out=Path(d);q.world='w';q.lease={'job_session':'task'};q.prefix='observe';q.index=0;q.closing_menu=None
  for n in ('old','control'): (q.out/n).mkdir()
  profile=q.out/'profile.json';write_json(profile,{'ender_chest':[1,2,3]});command={'id':'old','action':'take_packed_materials','profile':str(profile),'targets':{'minecraft:ghast_tear':1}};write_json(q.out/'command.json',command);write_json(q.out/'old/intent.json',command)
  error={'error':'Temporary shulker pad is not empty or its verified dry support changed','type':'RuntimeError','last_request':'last','native_inflight':None,'unconfirmed_native_request':None};write_json(q.out/'old/error.json',error)
  s={'world_session':'w','last_request':'last','control_revision':2,'pos':[1,2,3],'health':20,'screen':''};q.status=lambda **kw:s
  event={'time':time.time()+1,'op':'scan','phase':'done','world_session':'w','inventory_delta':{},'params':{'task_session':'task'},'request_id':'last','revision_after':2,'position_after':[1,2,3]};(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');return q,s,event
 def test_proven_refusal_allows_only_snapshot(self):
  with tempfile.TemporaryDirectory() as d:
   q,s,e=self.fixture(d);sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':sent.append(value);(q.out/value['id']).mkdir();write_json(q.out/value['id']/'result.json',{'phase':'done','world_session':'w'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_packed_pad_refusal()
   self.assertEqual([v['op']for v in sent],['snapshot'])
 def test_any_box_move_or_unknown_is_fenced(self):
  for mode in ('slot_click','unknown','journal','inventory','other_interact'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
    q,s,e=self.fixture(d)
    if mode=='slot_click':e['op']='slot_click'
    if mode=='inventory':e['inventory_delta']={'minecraft:ghast_tear':1}
    if mode=='other_interact':e.update(op='interact',params={'task_session':'task','pos':[9,9,9]})
    if mode in ('slot_click','inventory','other_interact'):(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n')
    if mode=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if mode=='journal':(q.out/'control/packed-transfer-active.json').write_text('{}')
    with self.assertRaises(RuntimeError):q.observe_packed_pad_refusal()
if __name__=='__main__':unittest.main()
