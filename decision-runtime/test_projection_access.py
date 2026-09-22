import json,tempfile,unittest
from pathlib import Path
from projection_access import open_ladder_hatch
class Tests(unittest.TestCase):
 def test_previously_verified_hatch_is_rechecked_after_ladders_are_complete(self):
  with tempfile.TemporaryDirectory() as d:
   class Client:
    out=Path(d);calls=[]
    def status(self):return {'projection_selection':{'key':'house'}}
    def request(self,op,**args):
     self.calls.append((op,args))
     if op=='projection_audit':return {'projection_audit':{'placement_key':'house','mismatches':[]}}
     return {'blocks':[{'pos':[1,64,3],'state':'Block{minecraft:oak_trapdoor}[open=true]','fluid':False}]}
   c=Client();(c.out/'basement-hatch.json').write_text(json.dumps({'placement_key':'house','after':{'pos':[1,64,3]}}))
   self.assertEqual(open_ladder_hatch(c,[1,3])['pos'],[1,64,3])
   self.assertEqual(c.calls[-1],('scan',{'min':[1,64,3],'max':[1,64,3],'details':True}))
 def test_different_projection_cannot_reuse_cached_access(self):
  with tempfile.TemporaryDirectory() as d:
   class Client:
    out=Path(d)
    def status(self):return {'projection_selection':{'key':'new'}}
    def request(self,op,**args):
     assert op=='projection_audit';return {'projection_audit':{'placement_key':'new','mismatches':[]}}
   c=Client();(c.out/'basement-hatch.json').write_text(json.dumps({'placement_key':'old','after':{'pos':[1,64,3]}}))
   self.assertIsNone(open_ladder_hatch(c,[1,3]))
if __name__=='__main__':unittest.main()
