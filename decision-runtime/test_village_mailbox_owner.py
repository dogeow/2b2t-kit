import json,tempfile,unittest
from pathlib import Path
from village_queue import require_mailbox_owner

class VillageMailboxOwnerTest(unittest.TestCase):
 def test_registered_old_worker_mailbox_never_receives_new_owner_commands(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);(p/'transport-kernel.json').write_text(json.dumps(dict(world_session='world',task_session='old')))
   with self.assertRaises(RuntimeError):require_mailbox_owner(p,dict(world_session='world',supervision_lease=dict(job_session='new')))
   self.assertFalse((p/'command.json').exists())
 def test_matching_owner_and_world_are_accepted(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);(p/'transport-kernel.json').write_text(json.dumps(dict(world_session='world',task_session='same')))
   require_mailbox_owner(p,dict(world_session='world',supervision_lease=dict(job_session='same')))
   with self.assertRaises(RuntimeError):require_mailbox_owner(p,dict(world_session='other',supervision_lease=dict(job_session='same')))

if __name__=='__main__':unittest.main()
