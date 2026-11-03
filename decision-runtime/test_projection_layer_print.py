import unittest
from projection_layer_print import next_window,layer_state
from material_jobs.protocol import JobBlocked
class LayerPolicyTest(unittest.TestCase):
 def setUp(self):self.e={(x,10,z)for x in range(7)for z in range(7)}
 def test_window_is_local_missing_and_has_proved_same_layer_stand(self):
  a={(0,10,0):'Block{minecraft:cobblestone}'};r=next_window(self.e,a,[.5,11.1,.5]);self.assertEqual([.5,11.1,.5],r['stand']);self.assertLessEqual(len(r['positions']),6)
  for p in r['positions']:self.assertIn(tuple(p),self.e);self.assertNotIn(tuple(p),a);self.assertLessEqual(p[0]**2+p[2]**2,2.8**2)
 def test_fixed_feet_margin_survives_native_settling_inside_two_block_gap(self):
  margin=.1
  self.assertGreater(1+margin-.05,1)
  self.assertLess(1+margin+.05+1.8,3)
 def test_complete_needs_no_action_and_unseeded_refuses(self):
  self.assertIsNone(next_window(self.e,dict.fromkeys(self.e),[0,0,0]))
  with self.assertRaises(JobBlocked):next_window(self.e,{},[0,0,0])
 def test_mixed_layer_or_outside_observation_is_rejected(self):
  for e,a in [(self.e|{(0,11,0)},{}),(self.e,{(9,10,9):''})]:
   with self.assertRaises(ValueError):next_window(e,a,[0,0,0])
 def test_partial_scan_is_not_empty_air_and_changed_block_is_protected(self):
  r=dict(phase='done',scan_cells_read=49,scan_total_cells=49,scan_start_revision=2,scan_end_revision=2,blocks=[]);self.assertEqual({},layer_state(self.e,r))
  for patch in [{'phase':'waiting'},{'scan_cells_read':48},{'scan_end_revision':3},{'blocks':[dict(pos=[0,10,0],state='Block{minecraft:chest}',fluid=False,block_entity=True)]}]:
   with self.assertRaises(JobBlocked):layer_state(self.e,{**r,**patch})
if __name__=='__main__':unittest.main()
