import unittest,json,tempfile
from pathlib import Path
from owned_material_menu import owned_menu_result

class OwnedMenuTest(unittest.TestCase):
 def run_case(self,owned=7,kind='AnvilMenu'):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name);out=root/'command';out.mkdir()
  class Client:
   world='world';task='task';owned_material_menu=owned
   def status(self):return {'menu':{'id':7,'type':kind},'supervision_lease':{'id':'lease'},'control_revision':9}
  c=Client();c.out=out;return c,root
 def test_certificate_binds_the_exact_current_owned_window(self):
  c,root=self.run_case();result=owned_menu_result(c,{'complete':True});cert=json.loads((root/'owned-material-menu.json').read_text());self.assertEqual(cert,result['owned_menu']);self.assertEqual(cert,dict(type='AnvilMenu',id=7,world_session='world',task_session='task',lease_id='lease',control_revision=9))
 def test_different_window_removes_stale_certificate_without_adoption(self):
  c,root=self.run_case(owned=8);path=root/'owned-material-menu.json';path.write_text('{}');self.assertEqual(owned_menu_result(c,{'complete':True}),{'complete':True});self.assertFalse(path.exists())
 def test_no_owned_window_does_not_publish_certificate(self):
  c,root=self.run_case(owned=None);self.assertEqual(owned_menu_result(c,{}),{});self.assertFalse((root/'owned-material-menu.json').exists())
if __name__=='__main__':unittest.main()
