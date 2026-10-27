from unittest import TestCase
from material_jobs.portal_removal import targets,STATE
from material_jobs.ordinary_portal import frame

class PortalRemovalScopeTests(TestCase):
 def approval(self):return {'world_session':'current','server':'simpcraft.com','dimension':'minecraft:overworld',
  'no_dimension_entry':True,'user_instruction':'Remove this portal','maximum_mines':14,'expected_state':STATE,
  'root':[1,70,3],'targets':frame([1,70,3])}
 def test_exact_original_frame_is_accepted(self):self.assertEqual(frame([1,70,3]),targets(self.approval(),'current'))
 def test_different_world_dimension_or_missing_instruction_is_refused(self):
  for key,value in [('world_session','old'),('dimension','minecraft:the_nether'),('no_dimension_entry',False),('user_instruction',''),('maximum_mines',15)]:
   with self.assertRaises(ValueError):targets({**self.approval(),key:value},'current')
 def test_extra_or_duplicate_cells_are_not_an_excavation_authorization(self):
  a=self.approval();a['targets'][-1]=[100,70,100]
  with self.assertRaises(ValueError):targets(a,'current')
  a=self.approval();a['targets'][-1]=a['targets'][0]
  with self.assertRaises(ValueError):targets(a,'current')
