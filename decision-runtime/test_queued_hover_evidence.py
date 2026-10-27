import json,tempfile,unittest
from pathlib import Path
from queued_village_owner import QueuedVillageOwner
from material_jobs.navigation import _owned_hover_gravity_pulse
class QueuedHoverEvidenceTests(unittest.TestCase):
 def fixture(self,root):
  s=dict(world_session='w',server='s',control_revision=7,last_request='r',flight=True,guard_armed=True,manual_movement=False,under_water=False,on_fire=False,navigating=False,movement_keys={'forward':False},velocity=[0,-.0784000015258789,0],supervision_lease=dict(id='lease',kind='materials',job_session='t',world_session='w',revision=7,search_origin=[0,100,0]))
  class Builder:
   out=root
   def __init__(self):self.root=root;self.q=self
   def check(self):return s
   def status(self):return s
  (root/'control').mkdir();e=dict(request_id='r',op='navigate',phase='done',world_session='w',revision_after=7,params={'task_session':'t'});(root/'control/events.jsonl').write_text(json.dumps(e)+'\n');return QueuedVillageOwner(Builder()),s,e
 def test_real_retained_owner_receipt_allows_stationary_gravity_pulse(self):
  with tempfile.TemporaryDirectory()as td:
   c,s,e=self.fixture(Path(td));self.assertTrue(_owned_hover_gravity_pulse(c,s));self.assertEqual(c.heartbeat.id,'lease');self.assertFalse(hasattr(c.heartbeat,'close'))
 def test_foreign_stale_unknown_or_moving_evidence_stays_blocked(self):
  for mode in ['lease','request','revision','task','unknown','moving']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as td:
    c,s,e=self.fixture(Path(td))
    if mode=='lease':s['supervision_lease']['id']='other'
    if mode=='request':e['request_id']='other'
    if mode=='revision':e['revision_after']=6
    if mode=='task':e['params']['task_session']='other'
    if mode=='unknown':e['phase']='waiting'
    if mode=='moving':s['movement_keys']['forward']=True
    (Path(td)/'control/events.jsonl').write_text(json.dumps(e)+'\n');self.assertFalse(_owned_hover_gravity_pulse(c,s))
if __name__=='__main__':unittest.main()
