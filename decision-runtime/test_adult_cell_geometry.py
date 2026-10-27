import unittest
from adult_cell_geometry import audit,bands,largest_gap
import test_village_shell_audit as fixtures
class AdultGeometryTest(unittest.TestCase):
 def fixture(self):return fixtures.CellShellTest().fixture()
 def test_full_cell_and_top_slab_ceiling_are_closed(self):
  r,s=self.fixture()
  for z in[1,2,3]:r[(0,67,z)]=dict(state='Block{minecraft:dark_oak_slab}[type=top,waterlogged=false]',solid=False,fluid=False)
  self.assertTrue(audit(r,s)['verified'])
 def test_actual_two_high_wall_opening_fails(self):
  r,s=self.fixture();r.pop((0,64,4));r.pop((0,65,4));self.assertFalse(audit(r,s)['verified'])
 def test_baby_sized_lower_gap_is_explicitly_not_baby_proof(self):
  r,s=self.fixture();r.pop((0,64,4));a=audit(r,s);self.assertTrue(a['verified']);self.assertTrue(a['baby_containment_not_claimed'])
 def test_raised_lectern_base_and_closed_top_trapdoor_have_no_adult_sized_gap(self):
  r,s=self.fixture();r.pop((0,64,0));r[(0,65,0)]=dict(state='Block{minecraft:lectern}',solid=False,fluid=False);r[(0,66,0)]=dict(state='Block{minecraft:oak_trapdoor}[half=top,open=false,waterlogged=false]',solid=False,fluid=False)
  self.assertTrue(audit(r,s)['verified']);r.pop((0,65,0));self.assertFalse(audit(r,s)['verified'])
 def test_moved_workstation_does_not_move_the_original_counter(self):
  r,s=self.fixture();s['previous_work_block']=[0,64,0];s['work_block']=[0,64,1];self.assertTrue(audit(r,s)['verified'])
 def test_unknown_shape_is_not_assumed_solid(self):self.assertEqual([],bands(dict(state='Block{minecraft:redstone_wire}',solid=False,fluid=False),1));self.assertEqual(3,largest_gap([],3))
