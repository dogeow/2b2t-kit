import json,tempfile,unittest
from pathlib import Path
from job_progress import JobProgress
class JobProgressTest(unittest.TestCase):
 def state(self):return dict(connected=True,world_session='w',control_revision=3,supervision_lease={'job_session':'j'})
 def test_explicit_verified_progress_survives_inventory_deposit(self):
  with tempfile.TemporaryDirectory() as d:
   job=JobProgress(d,'w','j',3,'混凝土制作',800,101);job.update(phase='存放成品')
   state=self.state();state['inventory']=[];job.publish(state,10)
   data=json.loads(job.path.read_text());self.assertEqual((101,800),(data['done'],data['total']));self.assertEqual('存放成品',data['phase'])
 def test_wrong_world_owner_revision_and_manual_do_not_publish(self):
  for key,value in [('world_session','other'),('control_revision',4),('manual_movement',True),('connected',False),('supervision_lease',{'job_session':'other'})]:
   with tempfile.TemporaryDirectory() as d:
    job=JobProgress(d,'w','j',3,'作业',800);state=self.state();state[key]=value;job.publish(state,10);self.assertFalse(job.path.exists())
 def test_close_does_not_remove_another_task(self):
  with tempfile.TemporaryDirectory() as d:
   job=JobProgress(d,'w','j',3,'作业',800);job.publish(self.state(),10);job.close();self.assertFalse(job.path.exists())
   job.path.write_text('{"task_session":"other","world_session":"w"}');job.close();self.assertTrue(job.path.exists())
 def test_throttle_and_advance(self):
  with tempfile.TemporaryDirectory() as d:
   job=JobProgress(d,'w','j',3,'作业',800);job.publish(self.state(),10);job.publish(self.state(),10.1);self.assertEqual(10000,json.loads(job.path.read_text())['updated_at'])
   job.update(done=8);job.publish(self.state(),10.15);self.assertEqual(8,json.loads(job.path.read_text())['done'])
if __name__=='__main__':unittest.main()

class ClientProgressRevisionTest(unittest.TestCase):
 def test_follows_only_revisions_already_accepted_by_controller(self):
  from unittest.mock import patch
  from material_client import MaterialClient,Client
  with tempfile.TemporaryDirectory() as d:
   c=object.__new__(MaterialClient);c.heartbeat=None;c.rev=3
   c.job_progress=JobProgress(d,'w','j',3,'混凝土制作',800,101)
   state=dict(connected=True,world_session='w',control_revision=3,supervision_lease={'job_session':'j'})
   with patch.object(Client,'raw',return_value=state):c.raw()
   c.rev=4;state['control_revision']=4;c.job_progress.update(done=109)
   with patch.object(Client,'raw',return_value=state):c.raw()
   self.assertEqual(4,json.loads(c.job_progress.path.read_text())['control_revision'])
   state['control_revision']=5;c.job_progress.update(done=117)
   with patch.object(Client,'raw',return_value=state):c.raw()
   self.assertEqual(109,json.loads(c.job_progress.path.read_text())['done'])
