import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from material_client import MaterialClient,recovery_action_allowed
class PriorityRecoveryTest(unittest.TestCase):
 def test_recovery_never_allows_work_or_lateral_descent(self):
  state={'pos':[1,70,2]}
  for op in ['mine_block','interact','slot_click','craft_recipe','chop','professional_print']:
   self.assertFalse(recovery_action_allowed(state,op,{}))
  self.assertTrue(recovery_action_allowed(state,'use_item',{'item':'minecraft:cooked_beef'}))
  self.assertTrue(recovery_action_allowed(state,'navigate',{'target':[1,110,2],'air_only':True}))
  self.assertFalse(recovery_action_allowed(state,'navigate',{'target':[1,60,2],'air_only':True}))
  self.assertFalse(recovery_action_allowed(state,'navigate',{'target':[5,110,2],'air_only':True}))
 def test_formal_acquisition_waits_for_idle_release_before_initializing_and_cleans_token_on_failure(self):
  token=Mock();order=[]
  with patch('live_snapshot.read_fresh',return_value={'world_session':'w'}),patch('safety_interlock.require_unlocked'),patch('idle_priority.request_foreground',side_effect=lambda *a:(order.append('idle released')or token)),patch.object(MaterialClient,'_init_material',side_effect=lambda *a:(order.append('init')or (_ for _ in ()).throw(RuntimeError('init failure')))):
   with self.assertRaisesRegex(RuntimeError,'init failure'):MaterialClient(Path('/test'),Path('/out'))
  self.assertEqual(['idle released','init'],order);token.close.assert_called_once()
 def test_idle_client_does_not_preempt_itself(self):
  class Idle(MaterialClient):
   def __init__(self):self.idle_service_id='idle';super().__init__(Path('/test'),Path('/out'))
  with patch('idle_priority.request_foreground') as demand,patch.object(MaterialClient,'_init_material'):
   Idle();demand.assert_not_called()
if __name__=='__main__':unittest.main()
