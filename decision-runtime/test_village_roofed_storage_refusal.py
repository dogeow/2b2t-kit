import tempfile,json,unittest
from pathlib import Path
from unittest.mock import patch
from kit_runtime.journal import write_json
from village_queue import VillageQueue
class RoofedStorageRefusalTests(unittest.TestCase):
 def case(self,directory):
  q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'t'};q.prefix='observe';q.index=0;q.closing_menu=None;(q.out/'control').mkdir();old=q.out/'old-001';old.mkdir();d=q.out/'old-002';d.mkdir();write_json(q.out/'command.json',{'id':'old-002','action':'exchange','positions':[[1,2,3]]});inv=[{'slot':1,'item':'minecraft:cobblestone','count':288}];write_json(old/'result.json',{'id':'prior','phase':'done','world_session':'w','inventory':inv});write_json(d/'error.json',{'error':'Roofed storage needs a local registered house entry route; preserve the structure','type':'StockBlocked','last_request':'scan','native_inflight':None,'unconfirmed_native_request':None});events=[{'request_id':'prior'},{'request_id':'scan','op':'scan','phase':'done','world_session':'w','params':{'task_session':'t','min':[1,2,3],'max':[1,8,3]},'revision_after':3,'position_after':[1,20,3]}];(q.out/'control/events.jsonl').write_text(''.join(json.dumps(e)+'\n'for e in events));s={'last_request':'scan','control_revision':3,'pos':[1,20,3],'inventory':inv,'screen':''};q.status=lambda **kw:s;return q,d,events,s
 def test_only_reads_and_retains_original_roof_and_failure(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,e,s=self.case(directory);raw=(d/'error.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':
     sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done','world_session':'w'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_unchanged_roofed_storage()
   self.assertEqual(['snapshot'],[v['op']for v in sent]);self.assertEqual(raw,(d/'error.json').read_bytes())
 def test_container_input_inventory_change_or_unknown_stays_fenced(self):
  for mode in ['interact','inventory','unknown','bounds']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as directory:
    q,d,e,s=self.case(directory)
    if mode=='interact':e.insert(1,{'op':'interact','phase':'done','world_session':'w','params':{'task_session':'t'}})
    if mode=='inventory':s['inventory'][0]['count']=287
    if mode=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if mode=='bounds':e[-1]['params']['max']=[1,9,3]
    (q.out/'control/events.jsonl').write_text(''.join(json.dumps(v)+'\n'for v in e))
    with self.assertRaises(RuntimeError):q.observe_unchanged_roofed_storage()
 def test_first_exchange_after_another_planners_raw_startup_snapshot_is_read_only(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,e,s=self.case(directory);previous=q.out/'old-001';previous.rename(q.out/'startup-other-prefix')
   prior=json.loads((q.out/'startup-other-prefix/result.json').read_text());prior.update(phase=None,connected=True)
   write_json(q.out/'startup-other-prefix/result.json',prior);e[0].update(op='snapshot',world_session='w',params={'task_session':'t'})
   (q.out/'control/events.jsonl').write_text(''.join(json.dumps(v)+'\n'for v in e));sent=[];q.native=lambda op:sent.append(op)
   q.observe_unchanged_roofed_storage();self.assertEqual(sent,['snapshot'])
if __name__=='__main__':unittest.main()
