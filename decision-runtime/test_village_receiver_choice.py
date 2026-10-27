import unittest
from village_receiver_choice import choose
class ReceiverChoiceTests(unittest.TestCase):
 def cells(self):return [dict(id='N',min=[10,65,6],max_exclusive=[11,68,9],front_z=9),dict(id='S',min=[10,65,14],max_exclusive=[11,68,17],front_z=13)]
 def actor(self,uid,z):return dict(uuid=uid,type='minecraft:villager',health=20,alive=True,is_baby=False,bounds={'min':[10.2,65,z-.3],'max':[10.8,66.95,z+.3]})
 def test_actual_south_receiver_is_selected_and_northern_resident_remains_independent(self):
  actors=[self.actor('already_fixed',7),self.actor('new',16)];self.assertEqual(choose(actors,'new',self.cells())['id'],'S')
 def test_counter_straddle_two_residents_baby_and_injured_actor_never_allow_closure(self):
  cases=[[self.actor('new',9)],[self.actor('new',7),self.actor('extra',8)],[{**self.actor('new',7),'is_baby':True}],[{**self.actor('new',7),'health':19}]]
  for actors in cases:
   with self.subTest(actors=actors):self.assertIsNone(choose(actors,'new',self.cells()))
 def test_whole_body_must_be_inside_not_just_centre(self):
  actor=self.actor('new',7);actor['bounds']['max'][0]=11.05;self.assertIsNone(choose([actor],'new',self.cells()))
if __name__=='__main__':unittest.main()
