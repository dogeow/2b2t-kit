import unittest
from game_input_idle import GameInputIdle,may_reacquire_without_ui_input
class GameIdleTest(unittest.TestCase):
 def state(self):return dict(connected=True,world_session='w',window_active=True,manual_movement=False,health=20,screen='',supervision_lease=None)
 def test_typing_in_codex_does_not_reset_inactive_minecraft(self):
  t=GameInputIdle();s=self.state();self.assertEqual(t.observe(s,0,0),0)
  s['window_active']=False
  self.assertEqual(t.observe(s,.01,15),15);self.assertEqual(t.observe(s,.01,31),31)
  self.assertTrue(may_reacquire_without_ui_input(s,{'authorized':True,'idle_seconds':30},31))
 def test_foreground_game_input_and_held_movement_reset_the_clock(self):
  t=GameInputIdle();s=self.state();t.observe(s,0,0)
  self.assertAlmostEqual(t.observe(s,.1,40),.1);s['manual_movement']=True;self.assertEqual(t.observe(s,60,50),0)
 def test_unknown_foreground_input_and_world_change_fail_closed(self):
  t=GameInputIdle();s=self.state();t.observe(s,0,0);self.assertIsNone(t.observe(s,None,40));s['window_active']=False;s['world_session']='new';self.assertEqual(t.observe(s,0,41),0)
 def test_idle_does_not_override_user_interfaces_locks_or_another_owner(self):
  for change in [{'screen':'ChatScreen'},{'health':19},{'safety_hold':{'active':True}},{'supervision_lease':{'kind':'materials'}},{'detail':'工具箱停止全部'},{'manual_movement':True}]:
   self.assertFalse(may_reacquire_without_ui_input({**self.state(),**change},{'authorized':True,'idle_seconds':30},60))
if __name__=='__main__':unittest.main()
