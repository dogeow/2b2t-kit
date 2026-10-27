import unittest
from village_feeding import fresh_food_pose

class FreshFoodPoseTest(unittest.TestCase):
 def test_recipient_moving_during_settle_is_reapproached_before_Q(self):
  state=dict(pos=[0,64,0],hand=dict(item='minecraft:bread',count=17))
  self.assertTrue(fresh_food_pose(state,dict(pos=[1,64,0],visible=True)))
  self.assertFalse(fresh_food_pose(state,dict(pos=[4,64,0],visible=True)))
 def test_visibility_and_actual_held_food_remain_required(self):
  target=dict(pos=[1,64,0],visible=True)
  for hand in [dict(item='minecraft:diamond_axe',count=1),dict(item='minecraft:bread',count=0)]:
   self.assertFalse(fresh_food_pose(dict(pos=[0,64,0],hand=hand),target))
  self.assertFalse(fresh_food_pose(dict(pos=[0,64,0],hand=dict(item='minecraft:bread',count=17)),dict(target,visible=False)))

if __name__=='__main__':unittest.main()
