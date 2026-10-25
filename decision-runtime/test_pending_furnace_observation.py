import json,tempfile,unittest
from pathlib import Path
from owned_furnace_origin import pending_observation
class PendingFurnaceObservationTest(unittest.TestCase):
 def fixture(self,root):
  from test_owned_furnace_origin import OwnedFurnaceOriginTest
  c,r,e,s=OwnedFurnaceOriginTest().fixture();out=root/'owner';out.mkdir();(out/'cmd').mkdir();c['id']='cmd';(out/'command.json').write_text(json.dumps(c));(out/'cmd/intent.json').write_text(json.dumps(c));request=dict(c['params'],id='r',op='interact',world_session='w',task_session='t',expected_revision=5);(root/'request.json').write_text(json.dumps(request))
  class Q:world='w';lease={'id':'l','job_session':'t'}
  q=Q();q.root=root;q.out=out;return q,r,e,s
 def test_only_our_exact_pending_opener_can_be_polled(self):
  with tempfile.TemporaryDirectory()as t:
   q,r,e,s=self.fixture(Path(t));self.assertTrue(pending_observation(q,s))
   request=json.loads((q.root/'request.json').read_text());request['id']='foreign';(q.root/'request.json').write_text(json.dumps(request));self.assertFalse(pending_observation(q,s))
 def test_known_terminal_requires_the_full_original_reply_proof(self):
  with tempfile.TemporaryDirectory()as t:
   q,r,e,s=self.fixture(Path(t));(q.out/'cmd/result.json').write_text(json.dumps(r));(q.out/'control').mkdir();(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n');self.assertTrue(pending_observation(q,s));e['inventory_delta']={'minecraft:glass':1};(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n');self.assertFalse(pending_observation(q,s))
 def test_manual_or_safety_state_never_becomes_owned_observation(self):
  for key,value in [('manual_movement',True),('health',19),('guard_armed',False),('guard_busy',True)]:
   with self.subTest(key=key),tempfile.TemporaryDirectory()as t:
    q,r,e,s=self.fixture(Path(t));s[key]=value;self.assertFalse(pending_observation(q,s))
if __name__=='__main__':unittest.main()
