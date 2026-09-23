import json,tempfile,unittest
from pathlib import Path
from material_client import Client
class RevisionTest(unittest.TestCase):
 def test_owned_printer_start_can_advance_revision_while_still_running(self):
  with tempfile.TemporaryDirectory() as d:
   class Fake(Client):
    def __init__(self):self.root=self.out=Path(d);self.world='world';self.rev=40;self.anchor=[1,2,3];self.owned=False;self.last=None;self.polls=0
    def raw(self):
     state={'world_session':'world','control_revision':40,'connected':True,'screen':'','manual_movement':False,'health':20,'server':'simpcraft.com','dimension':'minecraft:overworld','pos':[1,2,3],'time':1,'inventory':[]}
     p=self.root/'request.json'
     if p.exists():
      req=json.loads(p.read_text());self.polls+=1
      state.update(control_revision=41,id=req['id'],last_request=req['id'],phase='running' if self.polls==1 else 'done')
     return state
   c=Fake();r=c.request('professional_print',seconds=1);self.assertEqual(r['phase'],'done');self.assertEqual(c.rev,41);self.assertEqual(c.polls,2)
 def test_owned_logout_revision_jump_waits_for_disconnect_without_replay(self):
  with tempfile.TemporaryDirectory() as d:
   class Fake(Client):
    def __init__(self):self.root=self.out=Path(d);self.world='world';self.rev=40;self.anchor=[1,2,3];self.owned=False;self.last=None;self.polls=0
    def raw(self):
     state={'world_session':'world','control_revision':40,'connected':True,'screen':'','manual_movement':False,'health':20,'server':'simpcraft.com','dimension':'minecraft:overworld','pos':[1,2,3],'time':1,'inventory':[]}
     p=self.root/'request.json'
     if p.exists():
      req=json.loads(p.read_text());self.polls+=1
      state.update(control_revision=45,last_request=req['id'],connected=self.polls<2)
     return state
   c=Fake();r=c.request('safe_logout');self.assertFalse(r['connected']);self.assertEqual(c.polls,2)
if __name__=='__main__':unittest.main()
