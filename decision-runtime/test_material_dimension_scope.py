import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from material_client import Client,Handoff

class MaterialDimensionScopeTest(unittest.TestCase):
 def test_extra_processing_screens_require_exact_native_material_menu_ownership(self):
  for native_owned,task,allowed in ((True,'job',True),(False,'job',False),(True,'foreign',False)):
   with self.subTest(native_owned=native_owned,task=task):
    s=self.state('minecraft:overworld');s.update(screen='LoomScreen',menu={'id':5,'material_owned':native_owned},supervision_lease={'kind':'materials','job_session':task,'world_session':'native-world','revision':3})
    c=Client.__new__(Client);c.world='native-world';c.rev=3;c.dimension='minecraft:overworld';c.task='job';c.raw=lambda:s
    if allowed:self.assertEqual(s,c.status())
    else:
     with self.assertRaises(Handoff):c.status()
 def state(self,dimension):return {'server':'simpcraft.com','dimension':dimension,'screen':'','manual_movement':False,'health':20,'pos':[1,70,2],'world_session':'native-world','control_revision':3,'connected':True}
 def test_default_overworld_client_rejects_nether_without_explicit_context(self):
  with tempfile.TemporaryDirectory()as d,patch.object(Client,'raw',return_value=self.state('minecraft:the_nether')),self.assertRaises(AssertionError):Client(Path(d),Path(d)/'out','simpcraft.com')
 def test_explicit_dimension_binds_to_actual_native_world(self):
  with tempfile.TemporaryDirectory()as d,patch.object(Client,'raw',return_value=self.state('minecraft:the_nether')):
   c=Client(Path(d),Path(d)/'out','simpcraft.com',dimension='minecraft:the_nether')
   self.assertEqual('minecraft:the_nether',c.dimension);self.assertEqual('native-world',c.world)
   with patch.object(Client,'raw',return_value=self.state('minecraft:overworld')),self.assertRaises(Handoff):c.status()
 def test_explicit_dimension_cannot_fake_the_current_observed_dimension(self):
  with tempfile.TemporaryDirectory()as d,patch.object(Client,'raw',return_value=self.state('minecraft:overworld')),self.assertRaises(AssertionError):Client(Path(d),Path(d)/'out','simpcraft.com',dimension='minecraft:the_nether')
 def test_unknown_dimension_is_not_enabled_by_this_extension(self):
  with tempfile.TemporaryDirectory()as d,self.assertRaises(ValueError):Client(Path(d),Path(d)/'out','simpcraft.com',dimension='minecraft:the_end')

if __name__=='__main__':unittest.main()
