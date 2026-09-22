import tempfile,threading,time,unittest
from background_decision import DecisionMailbox
from build_supervisor import Supervisor,DEFAULTS
from test_build_supervisor import snapshot,Log,Model

class MailboxTests(unittest.TestCase):
 def test_single_flight_and_close_discard_late_reply(self):
  gate=threading.Event();started=threading.Event();m=DecisionMailbox()
  def work():started.set();gate.wait(1);return {'ok':True}
  try:
   self.assertTrue(m.submit({'job':'a'},work));self.assertTrue(started.wait(1))
   self.assertFalse(m.submit({'job':'b'},lambda:{}));self.assertIsNone(m.take())
   m.close();gate.set();self.assertIsNone(m.take());self.assertFalse(m.submit({},lambda:{}))
  finally:gate.set()
 def test_deadline_and_invalidated_context_are_reported(self):
  clock=[0];m=DecisionMailbox(clock=lambda:clock[0]);gate=threading.Event()
  self.assertTrue(m.submit({'job':'a'},lambda:gate.wait(1)))
  m.invalidate('manual handoff');clock[0]=6;gate.set()
  until=time.monotonic()+1;delivery=None
  while delivery is None and time.monotonic()<until:delivery=m.take();time.sleep(.001)
  self.assertFalse(delivery['valid']);self.assertEqual(delivery['age'],6)

class AsyncSupervisorTests(unittest.TestCase):
 def run_case(self,change):
  with tempfile.TemporaryDirectory() as tmp:
   gate=threading.Event();started=threading.Event();base=Model();log=Log()
   class Slow:
    calls=0
    def predict(self,s,q):self.calls+=1;started.set();gate.wait(2);return base.predict(s,q)
   model=Slow();c=Supervisor(tmp,'test.example',log,model,DEFAULTS);c.ensure_safety=lambda s:True
   c.safety_receipt=lambda:None
   class Beat:
    count=0
    def touch(self):self.count+=1
   c.safety=Beat();s=snapshot()
   try:
    c.poll(s,0);self.assertEqual(c.poll(s,36),'decision_pending');self.assertTrue(started.wait(1))
    for now in (37,38,39):self.assertEqual(c.poll(s,now),'decision_pending')
    self.assertEqual(c.safety.count,5);self.assertEqual(model.calls,1)
    change(s);gate.set();result=None;until=time.monotonic()+1
    while time.monotonic()<until:
     result=c.poll(s,40)
     if result!='decision_pending':break
     time.sleep(.001)
    return c,log,result
   finally:gate.set();c.decision_worker.close()
 def test_model_latency_does_not_block_fresh_safety_polls(self):
  c,log,result=self.run_case(lambda s:None)
  self.assertEqual(result,'decision');self.assertTrue(any(k=='jev_decision' and v['background'] for k,v in log.events))
 def test_inventory_change_discards_previously_valid_choice(self):
  c,log,result=self.run_case(lambda s:s['inventory'][0].update(item='minecraft:stone',count=64))
  self.assertEqual(result,'stale_decision');self.assertFalse(c.attempts)
 def test_manual_stop_cannot_be_restarted_by_late_reply(self):
  c,log,result=self.run_case(lambda s:s['build_job'].update(active=False,outcome='manual_stop'))
  self.assertEqual(result,'stopped');self.assertFalse(c.attempts)
if __name__=='__main__':unittest.main()
