import unittest,json,hashlib,tempfile
from pathlib import Path
from lighting_cli import known_rejected_intent

class KnownRejectionTests(unittest.TestCase):
 def test_exact_pre_send_rejection_preserves_identity_and_hash(self):
  with tempfile.TemporaryDirectory()as td:
   root=Path(td);rid='materials-abc123'
   reply={'id':rid,'world_session':'w','phase':'error','detail':'Target interaction face is occluded or out of reach'}
   rr=json.dumps(reply).encode();(root/('reply-'+rid+'.json')).write_bytes(rr)
   proof={'original_request':rid,'phase':'pre_send_rejected','target':[1,65,2],'same_world':'w','same_task':'t','unchanged_stock':59,'two_current_inventory_frames':True,'target_currently_air':True,'original_replayed':False,'original_reply_sha256':hashlib.sha256(rr).hexdigest()}
   p=root/'proof.json';raw=json.dumps(proof).encode();p.write_bytes(raw)
   record={'state':'native_rejected_without_send','target':[1,65,2],'world_session':'w','task_session':'t','before_stock':59,'no_send_proof':str(p),'no_send_proof_sha256':hashlib.sha256(raw).hexdigest()}
   self.assertTrue(known_rejected_intent(record,root))
   for change in ({'world_session':'other'},{'target':[1,66,2]},{'before_stock':58},{'state':'interaction_intent'}):self.assertFalse(known_rejected_intent({**record,**change},root))
   p.write_text('{}');self.assertFalse(known_rejected_intent(record,root))
 def test_unknown_reply_never_retires_an_intent(self):
  self.assertFalse(known_rejected_intent({'state':'interaction_intent'},Path('/tmp')))
if __name__=='__main__':unittest.main()
