import json,tempfile,unittest,zipfile
from pathlib import Path
from installed_kit_host import find
class InstalledHostTests(unittest.TestCase):
 def test_metadata_unique_and_numeric_version(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'twob2tkit-2026.11.06.1.jar'
   with zipfile.ZipFile(p,'w')as z:z.writestr('fabric.mod.json',json.dumps({'id':'twob2tkit','version':'2026.11.06.1'}))
   self.assertEqual(p,find(d,'2026.11.6.1'))
   with self.assertRaises(ValueError):find(d,'2026.11.7.1')
   with zipfile.ZipFile(Path(d)/'other.jar','w')as z:z.writestr('fabric.mod.json',json.dumps({'id':'twob2tkit','version':'2026.11.06.1'}))
   with self.assertRaises(ValueError):find(d,'2026.11.6.1')
if __name__=='__main__':unittest.main()
