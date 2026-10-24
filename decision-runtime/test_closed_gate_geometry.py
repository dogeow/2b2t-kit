import unittest
from closed_gate_geometry import admitted
class GateGeometryTest(unittest.TestCase):
 def fixture(self):return {'scan_entities':[dict(type='minecraft:villager',uuid='v',health=20,is_baby=False,bounds={'min':[.23,64,14.48],'max':[.83,65.95,15.08]})]}
 def test_voxel_overlap_is_safe_only_when_actual_gate_shape_is_clear(self):self.assertTrue(admitted(self.fixture(),[0,64,15],'v'))
 def test_real_shape_overlap_or_lost_clearance_fails(self):
  s=self.fixture();s['scan_entities'][0]['bounds']['max'][2]=15.4;self.assertFalse(admitted(s,[0,64,15],'v'))
 def test_other_entity_in_actual_shape_fails(self):
  s=self.fixture();s['scan_entities'].append(dict(type='minecraft:item',bounds={'min':[.2,64,15.45],'max':[.4,64.25,15.7]}));self.assertFalse(admitted(s,[0,64,15],'v'))
 def test_damaged_or_baby_patient_never_admitted(self):
  for key,value in [('health',19),('is_baby',True)]:
   s=self.fixture();s['scan_entities'][0][key]=value;self.assertFalse(admitted(s,[0,64,15],'v'))

 def test_north_cell_requires_resident_south_of_actual_gate_plane(self):
  s=self.fixture();s['scan_entities'][0]['bounds']['min'][2]=15.9;s['scan_entities'][0]['bounds']['max'][2]=16.5
  self.assertTrue(admitted(s,[0,64,15],'v',inward=-1));self.assertFalse(admitted(s,[0,64,15],'v',inward=1))
