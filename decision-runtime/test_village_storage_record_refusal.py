import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kit_runtime.journal import write_json
from village_queue import VillageQueue
class StorageRecordRefusalTests(unittest.TestCase):
 def case(self,directory):
  q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'t'};q.prefix='observe';q.index=0;q.closing_menu=None
  previous=q.out/'old-001';previous.mkdir();d=q.out/'old-002';d.mkdir();(q.out/'control').mkdir();write_json(q.out/'command.json',{'id':'old-002','action':'exchange'});write_json(previous/'intent.json',{'action':'native','op':'navigate'});state={'id':'native','phase':'done','world_session':'w','last_request':'native','control_revision':3,'pos':[1,2,3],'screen':'','inventory':[{'slot':1,'item':'minecraft:cobblestone','count':29}]};write_json(previous/'result.json',state);write_json(d/'error.json',{'error':'Storage position has no current scoped Kit record','last_request':'native','native_inflight':None,'unconfirmed_native_request':None});q.status=lambda **kw:state;return q,d,state
 def test_reads_only_and_retains_original_failure(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,s=self.case(directory);original=(d/'error.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':
     sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done','world_session':'w'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_missing_storage_record()
   self.assertEqual(['snapshot'],[v['op']for v in sent]);self.assertEqual(original,(d/'error.json').read_bytes())
 def test_unknown_native_input_or_changed_stock_stays_fenced(self):
  for mode in ['unknown','inventory','request','position']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as directory:
    q,d,s=self.case(directory)
    if mode=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if mode=='inventory':s['inventory'][0]['count']=30
    if mode=='request':s['last_request']='other'
    if mode=='position':s['pos']=[2,2,3]
    with self.assertRaises(RuntimeError):q.observe_missing_storage_record()
if __name__=='__main__':unittest.main()
