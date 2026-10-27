import json,tempfile,unittest
from unittest.mock import patch
from kit_runtime.journal import write_json
import test_village_queue
class WorksiteRefusalTests(unittest.TestCase):
 def fixture(self,directory):
  q,d,e=test_village_queue.VillageQueueTests().air_refusal(directory)
  command=json.loads((q.out/'command.json').read_text());command['params']={'air_only':True,'target':[400,111,10]};write_json(q.out/'command.json',command)
  reply=json.loads((d/'result.json').read_text());reply.update(detail='Target outside worksite',pos=[1,2,3],control_revision=6);write_json(d/'result.json',reply);e['detail']=reply['detail'];e['revision_after']=6;e['params'].update(command['params']);(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n')
  s={'screen':'','last_request':'native-old','pos':[1,2,3],'health':20,'manual_movement':False,'control_revision':6,'phase':'error','movement_keys':{'forward':False}};q.status=lambda **kw:s
  return q,d,e,s
 def test_only_observes_preserving_failed_request(self):
  with tempfile.TemporaryDirectory()as td:
   q,d,e,s=self.fixture(td);original=(d/'result.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':
     sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done','world_session':'w'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_refused_worksite_navigation()
   self.assertEqual(['snapshot'],[r['op']for r in sent]);self.assertEqual(original,(d/'result.json').read_bytes())
 def test_refuses_unknown_movement_other_error_or_changed_scope(self):
  for mode in ['unknown','drift','manual','injured','keys','revision','error','inventory','task']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as td:
    q,d,e,s=self.fixture(td)
    if mode=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if mode=='drift':s['pos']=[2,2,3]
    if mode=='manual':s['manual_movement']=True
    if mode=='injured':s['health']=19
    if mode=='keys':s['movement_keys']['forward']=True
    if mode=='revision':s['control_revision']=5
    if mode=='error':
     r=json.loads((d/'result.json').read_text());r['detail']='navigation timed out';write_json(d/'result.json',r)
    if mode=='inventory':e['inventory_delta']={'minecraft:lead':-1}
    if mode=='task':e['params']['task_session']='other'
    (q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n')
    with self.assertRaises(RuntimeError):q.observe_refused_worksite_navigation()
    self.assertFalse((q.out/'observe-001').exists())
if __name__=='__main__':unittest.main()
