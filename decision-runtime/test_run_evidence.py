import tempfile,unittest,json
from pathlib import Path
from run_evidence import observed_delta,write_manifest
class Tests(unittest.TestCase):
 def test_inventory_delta_excludes_armor_and_does_not_claim_completion(self):
  a={'inventory':[{'slot':0,'item':'minecraft:iron_ingot','count':4},{'slot':38,'item':'minecraft:diamond_chestplate','count':1}]}
  b={'inventory':[{'slot':0,'item':'minecraft:iron_ingot','count':2},{'slot':1,'item':'minecraft:tripwire_hook','count':4}]}
  self.assertEqual(observed_delta(a,b)['inventory_delta'],{'minecraft:iron_ingot':-2,'minecraft:tripwire_hook':4})
 def test_manifest_whitelist_omits_unrelated_secret_fields(self):
  with tempfile.TemporaryDirectory() as tmp:
   d=write_manifest(tmp,'session',{'kit_version':'1.9.61','server':'private.example','game_mode':'survival','difficulty':'hard','api_key':'do-not-record'})
   text=json.dumps(d);self.assertNotIn('do-not-record',text);self.assertNotIn('private.example',text)
   self.assertFalse(d['complete']);self.assertTrue(d['source_sha256']);self.assertEqual(d['difficulty'],'hard')
if __name__=='__main__':unittest.main()
