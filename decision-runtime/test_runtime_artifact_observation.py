import unittest,tempfile,json,hashlib
from pathlib import Path
from copy import deepcopy
from village_queue import VillageQueue
class RuntimeArtifactObservationTests(unittest.TestCase):
 def run_case(self,change=None):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);out=root/'out';out.mkdir();old=out/'prior';old.mkdir();new=out/'bad';new.mkdir();runtime=root/'runtime';runtime.mkdir();(runtime/'twob2tkit-engine.jar').write_bytes(b'old')
   s={'world_session':'w','phase':'done','id':'r','last_request':'r','pos':[1,2,3],'control_revision':2,'inventory':[{'slot':0,'item':'minecraft:stone','count':3}],'screen':''};prior=deepcopy(s)
   (old/'intent.json').write_text(json.dumps({'action':'native','op':'navigate'}));(old/'result.json').write_text(json.dumps(prior));(out/'command.json').write_text(json.dumps({'id':'bad','action':'hot_runtime_update','jar':'new.jar'}));(new/'error.json').write_text(json.dumps({'type':'KeyError','error':"'sha256'",'last_request':'r','native_inflight':None,'unconfirmed_native_request':None}))
   q=object.__new__(VillageQueue);q.root=root/'automation';q.out=out;q.world='w';q.status=lambda:s;calls=[];q.native=lambda op:(calls.append(op)or{'id':'snapshot'})
   if change:change(s,new)
   try:r=q.observe_unstarted_runtime_artifact_refusal('prior',hashlib.sha256(b'old').hexdigest());return r,calls
   except RuntimeError:return None,calls
 def test_missing_arguments_can_only_authorize_snapshot(self):self.assertEqual(({'id':'snapshot'},['snapshot']),self.run_case())
 def test_inventory_change_blocks_observation(self):self.assertEqual((None,[]),self.run_case(lambda s,p:s['inventory'][0].update(count=4)))
 def test_unknown_native_input_blocks_observation(self):
  def change(s,p):
   e=json.loads((p/'error.json').read_text());e['unconfirmed_native_request']='unknown';(p/'error.json').write_text(json.dumps(e))
  self.assertEqual((None,[]),self.run_case(change))
if __name__=='__main__':unittest.main()
