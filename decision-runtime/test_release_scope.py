import json,zipfile,unittest,tempfile
from pathlib import Path
from release_scope import classify
class ScopeTest(unittest.TestCase):
 def jar(self,p,**changes):
  files={'dev/twob2tkit/KitClient.class':b'host','dev/twob2tkit/runtime/api/BorerEngine.class':b'api','runtime/twob2tkit-engine.jar':b'engine','fabric.mod.json':json.dumps({'id':'twob2tkit','version':'1'}).encode()};files.update(changes)
  with zipfile.ZipFile(p,'w') as z:
   for n,data in files.items():z.writestr(n,data)
 def test_engine_only_and_version_label_do_not_force_restart(self):
  with tempfile.TemporaryDirectory() as d:
   a,b=Path(d)/'a.jar',Path(d)/'b.jar';self.jar(a);self.jar(b,**{'runtime/twob2tkit-engine.jar':b'new','fabric.mod.json':b'{"id":"twob2tkit","version":"2"}'})
   self.assertEqual(classify(a,b)['mode'],'hot_reload')
 def test_host_api_or_dependencies_require_restart(self):
  with tempfile.TemporaryDirectory() as d:
   a,b=Path(d)/'a.jar',Path(d)/'b.jar';self.jar(a)
   for name,value in [('dev/twob2tkit/runtime/api/BorerEngine.class',b'new api'),('fabric.mod.json',b'{"id":"twob2tkit","version":"2","depends":{"extra":"*"}}')]:
    self.jar(b,**{name:value});r=classify(a,b);self.assertEqual(r['mode'],'restart_required');self.assertIn(name,r['host_changes'])
 def test_identical_artifact_needs_no_restart_or_reload(self):
  with tempfile.TemporaryDirectory() as d:
   a=Path(d)/'a.jar';self.jar(a);self.assertEqual(classify(a,a)['mode'],'unchanged')
if __name__=='__main__':unittest.main()
