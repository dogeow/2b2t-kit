import tempfile,unittest
from pathlib import Path
from work_access import approach_faces,ApproachUnavailable
class Tests(unittest.TestCase):
 def client(self,root,replies,changed=False):
  class C:
   out=Path(root);faces=[];scans=0
   def status(self):return {}
   def request(self,op,**args):
    if op=='scan':
     self.scans+=1
     return {'blocks':[{'state':'Block{minecraft:chest}' if changed and self.scans>1 else 'Block{minecraft:dirt}'}]}
    assert op=='approach_block';self.faces.append(args['face']);return replies.pop(0)
  return C()
 def test_late_occlusion_uses_another_verified_face_without_restarting_job(self):
  with tempfile.TemporaryDirectory() as tmp:
   c=self.client(tmp,[{'phase':'waiting','detail':'Depot approach occluded or out of reach'},{'phase':'done'}])
   self.assertEqual(approach_faces(c,[1,2,3],'Block{minecraft:dirt}',['up','west']),'west')
   self.assertEqual(c.faces,['up','west']);self.assertEqual(c.scans,2)
 def test_ambiguous_timeout_and_changed_target_never_retry(self):
  with tempfile.TemporaryDirectory() as tmp:
   c=self.client(tmp,[{'phase':'waiting','detail':'time limit reached'}])
   with self.assertRaises(RuntimeError):approach_faces(c,[1,2,3],'Block{minecraft:dirt}',['up','west'])
   self.assertEqual(c.faces,['up'])
   c=self.client(tmp,[{'phase':'error','detail':'No visible collision-free depot approach'}],changed=True)
   with self.assertRaises(RuntimeError):approach_faces(c,[1,2,3],'Block{minecraft:dirt}',['up','west'])
   self.assertEqual(c.faces,['up'])
 def test_known_failures_are_bounded_and_do_not_repeat_one_face(self):
  with tempfile.TemporaryDirectory() as tmp:
   c=self.client(tmp,[{'phase':'error','detail':'No visible collision-free depot approach'}])
   with self.assertRaises(ApproachUnavailable):approach_faces(c,[1,2,3],'Block{minecraft:dirt}',['up','up'])
   self.assertEqual(c.faces,['up'])
if __name__=='__main__':unittest.main()
