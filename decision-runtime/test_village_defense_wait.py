import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kit_runtime.journal import write_json
from village_queue import VillageQueue
class DefenseWaitTests(unittest.TestCase):
 def fixture(self,d):
  q=VillageQueue.__new__(VillageQueue);q.out=Path(d);q.world='w';q.lease={'job_session':'task'};q.prefix='observe';q.index=0;q.closing_menu=None;(q.out/'old').mkdir();(q.out/'control').mkdir();write_json(q.out/'command.json',dict(id='old',action='native',op='navigate'));write_json(q.out/'old/error.json',dict(error='Defense remains busy',type='RuntimeError',native_inflight=None,unconfirmed_native_request=None,last_request='done'));s=dict(world_session='w',last_request='done',phase='done',control_revision=2,pos=[1,2,3],health=20,screen='',movement_keys={'forward':False});q.status=lambda **kw:s;event=dict(request_id='done',world_session='w',phase='done',params={'task_session':'task'},revision_after=2,position_after=[1,2,3]);(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');return q,s
 def test_read_only_no_original_navigation_replay(self):
  with tempfile.TemporaryDirectory()as d:
   q,s=self.fixture(d);original=(q.out/'old/error.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':sent.append(value);(q.out/value['id']).mkdir();write_json(q.out/value['id']/'result.json',dict(phase='done',world_session='w'))
   with patch('village_queue.write_json',side_effect=owner):q.observe_deferred_defense_navigation()
   self.assertEqual([x['op']for x in sent],['snapshot']);self.assertEqual(original,(q.out/'old/error.json').read_bytes())
 def test_unknown_or_changed_state_is_fenced(self):
  for mode in ['unknown','pos','rev','health','key']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as d:
    q,s=self.fixture(d)
    if mode=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if mode=='pos':s['pos']=[2,2,3]
    if mode=='rev':s['control_revision']=3
    if mode=='health':s['health']=19
    if mode=='key':s['movement_keys']['forward']=True
    with self.assertRaises(RuntimeError):q.observe_deferred_defense_navigation()
if __name__=='__main__':unittest.main()
