"""Regression coverage for healthy owned defense at material cleanup."""
import json
import tempfile
import unittest
from unittest.mock import patch
from material_client import Handoff
from test_material_health_exit import FakeClient

class HealthyGuardFinishTest(unittest.TestCase):
 def finish(self,c):
  with patch('material_cleanup.run',return_value=[]),patch('craft_recovery.clear_owned_workbench'),patch('material_client.time.sleep'),patch('material_client.time.monotonic',side_effect=range(0,200000,5)):
   c.finish()
 def configured(self,c,change_at,change):
  original=c.status;calls=[0]
  def status(*args,**kwargs):
   calls[0]+=1
   if calls[0]>change_at:change(c,calls[0])
   return original(*args,**kwargs)
  c.status=status
  return calls
 def test_busy_timeout_keeps_live_owner_then_ascends_and_reads_native_keep_receipt(self):
  with tempfile.TemporaryDirectory() as d:
   c=FakeClient(d,health=20);c.state['guard_busy']=True
   def clear(c,n):
    self.assertFalse(c.heartbeat.closed)
    c.state['guard_busy']=False
   calls=self.configured(c,26,clear);self.finish(c)
   self.assertGreater(calls[0],26);self.assertEqual(['scan','navigate'],c.actions)
   self.assertFalse((c.out/'park-fallback.json').exists())
   wait=json.loads((c.out/'park-defense-wait.json').read_text())
   self.assertEqual('WAIT_OWNED_PVE_GUARD',wait['action'])
   self.assertFalse(wait['confirmed']);self.assertTrue(wait['heartbeat_retained'])
   self.assertTrue((c.out/'stock-safety.json').exists())
 def test_guard_clearing_after_timeout_does_not_turn_the_timeout_into_logout(self):
  with tempfile.TemporaryDirectory() as d:
   c=FakeClient(d,health=20);c.state['guard_busy']=True
   self.configured(c,6,lambda c,n:c.state.update(guard_busy=False))
   self.finish(c)
   self.assertEqual(['scan','navigate'],c.actions)
   self.assertFalse((c.out/'park-fallback.json').exists())
 def test_original_native_navigation_is_not_replaced_while_waiting(self):
  with tempfile.TemporaryDirectory() as d:
   c=FakeClient(d,health=20);c.state.update(guard_busy=True,navigating=True,native_material_busy=True)
   def settle(c,n):
    c.state['guard_busy']=False
    if n>25:c.state.update(navigating=False,native_material_busy=False)
   self.configured(c,10,settle);request=c.request
   def dispatch(op,**kw):
    self.assertFalse(c.state['navigating'] or c.state['native_material_busy'])
    return request(op,**kw)
   c.request=dispatch;self.finish(c);self.assertEqual(['scan','navigate'],c.actions)
 def test_manual_takeover_wait_sends_no_navigation_or_logout(self):
  with tempfile.TemporaryDirectory() as d:
   c=FakeClient(d,health=20);c.state['guard_busy']=True
   self.configured(c,12,lambda c,n:c.state.update(manual_movement=True))
   self.finish(c);self.assertFalse(c.actions);self.assertTrue(c.heartbeat.closed)
 def test_critical_health_preserves_real_logout_and_hold(self):
  with tempfile.TemporaryDirectory() as d:
   c=FakeClient(d,health=20);c.state['guard_busy']=True
   self.configured(c,12,lambda c,n:c.state.update(health=13,time=300))
   self.finish(c);self.assertEqual(['safe_logout'],c.actions)
   self.assertTrue(json.loads((c.root/'material-health-hold.json').read_text())['active'])
 def test_foreign_revision_wait_yields_without_commands(self):
  with tempfile.TemporaryDirectory() as d:
   c=FakeClient(d,health=20);c.state['guard_busy']=True
   def handoff(c,n):raise Handoff('Foreign revision')
   self.configured(c,12,handoff);self.finish(c);self.assertFalse(c.actions);self.assertTrue(c.heartbeat.closed)
 def test_explicit_disconnect_still_accepts_real_logout_receipt(self):
  with tempfile.TemporaryDirectory() as d:
   c=FakeClient(d,health=20);c.remote_finish='disconnect'
   def close():
    c.heartbeat.closed=True
    (c.root/'supervision-receipt-test.json').write_text(json.dumps({
     'confirmed':True,'action':'LOGOUT','cause':'controller_finished',
     'lease':'test','job_session':'task','snapshot':c.state}))
   c.heartbeat.close=close;self.finish(c)
   receipt=json.loads((c.out/'stock-safety.json').read_text())
   self.assertTrue(receipt['confirmed']);self.assertEqual('LOGOUT',receipt['action'])

if __name__=='__main__':unittest.main()
