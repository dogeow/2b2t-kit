import unittest
from village_shell_audit import audit_cell
class CellShellTest(unittest.TestCase):
 def fixture(self):
  rows={(x,y,z):dict(state='Block{minecraft:dark_oak_planks}',solid=True,fluid=False,block_entity=False)for x in range(-1,2)for y in range(63,68)for z in range(0,5)}
  rows[(0,65,0)]=dict(state='Block{minecraft:dark_oak_slab}[type=bottom,waterlogged=false]',solid=False,fluid=False,block_entity=False)
  return rows,dict(id='WS01',work_block=[0,64,0])
 def test_complete_shell_is_separate_from_any_resident_position(self):r,s=self.fixture();self.assertTrue(audit_cell(r,s)['verified'])
 def test_rear_hole_detected_even_without_displaced_resident(self):
  r,s=self.fixture();r.pop((0,64,4));a=audit_cell(r,s);self.assertFalse(a['verified']);self.assertIn([0,64,4],[v['pos']for v in a['issues']])
 def test_open_trapdoor_cannot_prove_safe_reset_opening(self):
  r,s=self.fixture();r[(0,65,0)]['state']='Block{minecraft:acacia_trapdoor}[half=top,open=true,waterlogged=false]';self.assertFalse(audit_cell(r,s)['verified'])
 def test_nonfull_or_flooded_boundary_is_not_credited(self):
  for key,value in [('solid',False),('fluid',True),('block_entity',True)]:
   r,s=self.fixture();r[(-1,65,2)][key]=value;self.assertFalse(audit_cell(r,s)['verified'])
