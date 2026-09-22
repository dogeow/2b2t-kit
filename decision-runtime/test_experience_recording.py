import tempfile,unittest,sys
from pathlib import Path
from experience_recording import record_native_transaction,close_recorders
class RecordingTest(unittest.TestCase):
 def tearDown(self):close_recorders()
 def test_native_material_approach_is_recorded_in_explicit_isolated_store(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'skills'
   for i in range(2):
    req={'id':'native-'+str(i),'op':'approach_block','server':'test','dimension':'minecraft:overworld','site':[0,0,0],'world_session':'test-world','expected_revision':1,'expires_at':100,'task_session':'test-owner','background_ok':True,'pos':[1,64,2],'face':'up','expected_state':'Block{minecraft:stone}','seconds':30}
    before={'time':1000,'server':'test','dimension':'minecraft:overworld','world_session':'test-world','connected':True,'health':20,'kit_version':'test','runtime_version':'test'}
    after={**before,'time':2000,'id':req['id'],'last_request':req['id'],'phase':'done','build_supply':{'phase':'done','source':'approach:1, 64, 2','approach_only':True,'failure':''}}
    result=record_native_transaction(req,before,after,root)
   self.assertEqual(result['status'],'verified');self.assertTrue((root/'skills.sqlite3').exists())
 def test_mismatched_reply_does_not_open_a_store(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'skills';r=record_native_transaction({'id':'one','op':'walk'},{},{'id':'other','phase':'done'},root)
   self.assertEqual(r['status'],'unconfirmed');self.assertFalse(root.exists())
if __name__=='__main__':unittest.main()
