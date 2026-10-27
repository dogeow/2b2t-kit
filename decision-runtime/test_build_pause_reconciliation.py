import unittest,tempfile
from pathlib import Path
from build_pause_reconciliation import already_settled,pause_or_observe_completion,REJECTION
class TestPause(unittest.TestCase):
 def setUp(self):
  self.reply={'id':'original','phase':'error','detail':REJECTION}
  self.state={'connected':True,'screen':'','manual_movement':False,'build_job':{'session':'job','active':False,'queue_settled':True},'professional_printer':{'owned':False,'waiting_for_server':False,'travel_pending':0}}
 def test_exact_completed_job(self):self.assertTrue(already_settled(self.reply,self.state,'job'))
 def test_wrong_identity_live_queue_manual_and_missing_evidence_rejected(self):
  variants=[{'connected':False},{'manual_movement':True},{'screen':'ChatScreen'},{'navigating':True},{'pending_scan':{'id':'other'}},{'build_job':{'session':'other','active':False,'queue_settled':True}},{'build_job':{'session':'job','active':True,'queue_settled':True}},{'build_job':{'session':'job','active':False}},{'professional_printer':{'owned':False,'waiting_for_server':False,'travel_pending':1}},{'professional_printer':{}}]
  for change in variants:
   with self.subTest(change=change):self.assertFalse(already_settled(self.reply,{**self.state,**change},'job'))
 def test_unknown_and_other_errors_never_accepted(self):
  for r in ({'phase':'waiting','detail':REJECTION},{'phase':'error','detail':'foreign owner'},{}):self.assertFalse(already_settled(r,self.state,'job'))
 def test_reconciles_without_retry_and_preserves_original(self):
  with tempfile.TemporaryDirectory()as d:
   class C:
    out=Path(d)
    calls=[]
    def request(c,*a,**kw):c.calls.append((a,kw));return self.reply
    def status(c):return self.state
   c=C();pause_or_observe_completion(c,'job');self.assertEqual(1,len(c.calls));self.assertIn('original',(c.out/'build-pause-reconciliations.jsonl').read_text())
