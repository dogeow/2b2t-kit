import tempfile,unittest,zipfile
from pathlib import Path
from hot_update import install_and_reload
class HotUpdateTest(unittest.TestCase):
 def setup_case(self,root,protocol=1,bad_reply=False):
  jar=root/'new.jar'
  with zipfile.ZipFile(jar,'w') as z:
   z.writestr('META-INF/MANIFEST.MF','twob2tkit-Engine-Version: 1.7.56\ntwob2tkit-Host-API: 3\n')
   z.writestr('dev/twob2tkit/runtime/engine/DefaultBuildNavigation.class',b'test fixture')
  class Client:
   def __init__(self):
    self.root=root/'automation';self.root.mkdir();self.out=root;self.calls=0
    self.state={'runtime_reload_protocol':protocol,'runtime_host_api':3,'runtime_generation':2,'world_session':'world','health':20,'connected':True,'build_job':{'active':True,'session':'same-job'}}
   def status(self):return dict(self.state)
   def checked(self,op):
    self.calls+=1
    return {**self.state,'runtime_generation':3,'runtime_version':'wrong' if bad_reply else '1.7.56','navigation_runtime_version':'1.7.56'}
  return jar,Client()
 def test_updates_once_and_preserves_task_and_backup(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);jar,c=self.setup_case(root);(root/'runtime').mkdir();old=root/'runtime/twob2tkit-engine.jar';old.write_bytes(b'old')
   proof=install_and_reload(c,jar);self.assertEqual(c.calls,1);self.assertEqual(proof['build_session'],'same-job');self.assertEqual(Path(proof['backup']).read_bytes(),b'old');self.assertEqual(old.read_bytes(),jar.read_bytes())
 def test_old_host_rejected_before_disk_or_commands(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);jar,c=self.setup_case(root,protocol=0)
   with self.assertRaises(RuntimeError):install_and_reload(c,jar)
   self.assertEqual(c.calls,0);self.assertFalse((root/'runtime').exists())
 def test_uncertain_result_restores_disk_without_replaying(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);jar,c=self.setup_case(root,bad_reply=True);(root/'runtime').mkdir();old=root/'runtime/twob2tkit-engine.jar';old.write_bytes(b'old')
   with self.assertRaises(RuntimeError):install_and_reload(c,jar)
   self.assertEqual(c.calls,1);self.assertEqual(old.read_bytes(),b'old')
if __name__=='__main__':unittest.main()
