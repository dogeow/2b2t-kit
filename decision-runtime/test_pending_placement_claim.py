import unittest
from pending_placement_claim import guard
class PendingPlacementTests(unittest.TestCase):
 def fixture(self):return {'protected_pending_placement_targets':[{'world_session':'w','target':[1,65,2],'support':[1,64,2],'claim_not_cleared':True}]}
 def test_target_support_and_printer_cannot_replay_the_unconfirmed_use(self):
  for op,params in [('interact',{'pos':[1,64,2]}),('mine_block',{'pos':[1,65,2]}),('projection_batch_set',{'positions':[[1,65,2]]})]:
   with self.subTest(op=op),self.assertRaises(RuntimeError):guard(self.fixture(),'w','native',{'op':op,'params':params})
 def test_read_only_observation_and_other_workpoints_remain_allowed(self):
  guard(self.fixture(),'w','native',{'op':'scan','params':{'min':[1,65,2],'max':[1,65,2]}})
  guard(self.fixture(),'w','native',{'op':'mine_block','params':{'pos':[1,65,4]}})
