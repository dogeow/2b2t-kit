import copy,unittest
from paid_librarian_bed import plan,recovery_space_ready
class Tests(unittest.TestCase):
 def fixture(self):return [{'id':'WS04','occupant_uuid':'v','work_block':[6,64,13],'bed_foot':[6,64,15],'bed_head':[6,64,16]}, {'villager_uuid':'v','server_history_verified':True,'trader_xp':1},[],'w']
 def test_paid_private_bed_plan(self):
  room,foot,head,roof=plan(*self.fixture());self.assertEqual([6,67,14],roof);self.assertEqual('v',room.uid)
 def test_wrong_or_unpaid_supplier_refused(self):
  for key,value in [('villager_uuid','other'),('server_history_verified',False),('trader_xp',0)]:
   a=copy.deepcopy(self.fixture());a[1][key]=value
   with self.assertRaises(ValueError):plan(*a)
 def test_critical_quarantined_points_refused(self):
  for pos in [[6,64,15],[6,64,16],[6,67,14]]:
   a=self.fixture();a[2]=[{'world_session':'w','native_claim_not_cleared':True,'pos':pos}]
   with self.assertRaises(ValueError):plan(*a)
 def test_bed_outside_actual_room_refused(self):
  a=self.fixture();a[0]['bed_head']=[6,64,18]
  with self.assertRaises(ValueError):plan(*a)

 def test_two_slots_reserved_for_bed_and_roof(self):
  state={'inventory':[{'slot':i,'count':1}for i in range(36)]};state['inventory'][0]['count']=0;self.assertFalse(recovery_space_ready(state));state['inventory'][1]['count']=0;self.assertTrue(recovery_space_ready(state));state['inventory']=state['inventory'][:2];self.assertFalse(recovery_space_ready(state))
 def test_armor_and_duplicate_slots_are_not_recovery_space(self):
  state={'inventory':[{'slot':i,'count':1}for i in range(36)]+[{'slot':36,'count':0},{'slot':37,'count':0}]};self.assertFalse(recovery_space_ready(state));state={'inventory':[{'slot':0,'count':0}for _ in range(36)]};self.assertFalse(recovery_space_ready(state))

 def test_raised_workstation_not_treated_like_floor_level_counter(self):
  a=self.fixture();a[0]['work_block'][1]=65;a[0]['interior_floor_y']=64
  with self.assertRaisesRegex(ValueError,'Raised workpoints'):plan(*a)
