import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kit_runtime.journal import write_json
from village_queue import VillageQueue

class FullPickupRefusalTests(unittest.TestCase):
 def fixture(self,d):
  q=VillageQueue.__new__(VillageQueue);q.out=Path(d);q.root=q.out/'root';q.root.mkdir();q.world='w';q.lease={'job_session':'task'};q.prefix='observe';q.index=0;q.closing_menu=None
  (q.out/'old').mkdir();(q.out/'control').mkdir();write_json(q.out/'command.json',{'id':'old','action':'native','op':'collect_item','params':{}})
  reply={'id':'r','phase':'error','detail':'Insufficient room for the observed drop','world_session':'w'};write_json(q.out/'old/result.json',reply)
  s={'world_session':'w','last_request':'r','control_revision':2,'pos':[1,2,3],'screen':''};q.status=lambda **kw:s
  event={'request_id':'r','world_session':'w','op':'collect_item','phase':'error','params':{'task_session':'task'},'revision_before':2,'revision_after':2,'position_before':[1,2,3],'position_after':[1,2,3],'inventory_delta':{}}
  (q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');return q,s,reply,event
 def test_only_snapshot_is_sent(self):
  with tempfile.TemporaryDirectory() as d:
   q,s,reply,event=self.fixture(d);sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':sent.append(value);(q.out/value['id']).mkdir();write_json(q.out/value['id']/'result.json',{'phase':'done','world_session':'w'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_full_inventory_pickup_refusal()
   self.assertEqual([v['op']for v in sent],['snapshot'])
 def test_changed_or_unknown_outcome_cannot_be_settled(self):
  for mode in ('pending','position','revision','detail','inventory'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
    q,s,reply,event=self.fixture(d)
    if mode=='pending':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if mode=='position':s['pos']=[2,2,3]
    if mode=='revision':s['control_revision']=3
    if mode=='detail':reply['detail']='other';write_json(q.out/'old/result.json',reply)
    if mode=='inventory':event['inventory_delta']={'minecraft:oak_planks':1};(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
    with self.assertRaises(RuntimeError):q.observe_full_inventory_pickup_refusal()
if __name__=='__main__':unittest.main()
