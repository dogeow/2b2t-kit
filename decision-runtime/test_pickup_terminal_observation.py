import json,tempfile,unittest
from unittest.mock import patch
from kit_runtime.journal import write_json
from test_village_queue import VillageQueueTests
class PickupTerminalTests(unittest.TestCase):
 def fixture(self,directory):
  q,d,e,s=VillageQueueTests().stopped_walk(directory);cmd=json.loads((q.out/'command.json').read_text());cmd.update(op='collect_item',params={'expected_uuid':'drop','expected_item':'minecraft:cobblestone','expected_count':1});write_json(q.out/'command.json',cmd);r=json.loads((d/'result.json').read_text());r.update(detail='Drop pickup not confirmed at the reached position',control_revision=8);write_json(d/'result.json',r);e.update(op='collect_item',detail=r['detail'],params={'task_session':'t',**cmd['params']});s.update(health=20);(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n');return q,d,e,s
 def test_known_moved_collector_only_observes_and_preserves_original_receipt(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,e,s=self.fixture(directory);old=(d/'result.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done','world_session':'w'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_unconfirmed_pickup_terminal()
   self.assertEqual([v['op']for v in sent],['snapshot']);self.assertEqual((d/'result.json').read_bytes(),old)
 def test_unknown_moving_unhealthy_or_different_terminal_is_retained(self):
  for mode in ['unknown','moving','health','world','position','revision','inventory','task']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as directory:
    q,d,e,s=self.fixture(directory)
    if mode=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if mode=='moving':s['movement_keys']['forward']=True
    if mode=='health':s['health']=19
    if mode=='world':e['world_session']='other'
    if mode=='position':s['pos']=[9,2,3]
    if mode=='revision':s['control_revision']=9
    if mode=='inventory':e['inventory_delta']={'minecraft:cobblestone':1}
    if mode=='task':e['params']['task_session']='other'
    (q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n')
    with self.assertRaises(RuntimeError):q.observe_unconfirmed_pickup_terminal()
if __name__=='__main__':unittest.main()
