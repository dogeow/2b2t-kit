import unittest,tempfile,json
from unittest.mock import patch
from native_scan_bounds import validate,tiles
from village_queue import VillageQueue
import test_village_queue as queue_fixtures

class ScanBoundsTests(unittest.TestCase):
 def test_boundary_and_slices_cover_large_query_without_overlap(self):
  self.assertEqual(50000,validate([0,0,0],[49,19,49]))
  with self.assertRaises(ValueError):validate([760935,61,797832],[760995,80,797892])
  parts=list(tiles([0,0,0],[60,19,60]));self.assertEqual(2,len(parts))
  self.assertEqual(61*20*61,sum(validate(a,b)for a,b in parts))
  seen=set()
  for a,b in parts:
   cells={(x,y,z)for x in range(a[0],b[0]+1)for y in range(a[1],b[1]+1)for z in range(a[2],b[2]+1)}
   self.assertFalse(seen&cells);seen|=cells
  self.assertEqual(61*20*61,len(seen))
 def test_only_known_unmoved_invalid_scan_allows_a_snapshot_not_a_replay(self):
  from kit_runtime.journal import write_json
  for unsafe in (False,True):
   with self.subTest(unsafe=unsafe),tempfile.TemporaryDirectory()as d:
    q,old,event=queue_fixtures.VillageQueueTests().air_refusal(d);command={'id':'old','action':'native','op':'scan','params':{'min':[0,0,0],'max':[100,100,100]}};write_json(q.out/'command.json',command);event.update(op='scan',detail='Invalid scan volume');reply=json.loads((old/'result.json').read_text());reply['detail']='Invalid scan volume';write_json(old/'result.json',reply)
    if unsafe:event['inventory_delta']={'minecraft:dirt':-1}
    (q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');original=(old/'result.json').read_bytes();sent=[]
    def owner(path,value):
     write_json(path,value)
     if path.name=='command.json':
      sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done','world_session':'w'})
    with patch('village_queue.write_json',side_effect=owner):
     if unsafe:
      with self.assertRaises(RuntimeError):q.observe_refused_scan_volume()
     else:q.observe_refused_scan_volume()
    self.assertEqual([] if unsafe else ['snapshot'],[v['op']for v in sent]);self.assertEqual(original,(old/'result.json').read_bytes())

if __name__=='__main__':unittest.main()
