from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock,patch
from material_client import MaterialClient,Client,Handoff
class ExternalPrinterAdmissionTest(TestCase):
 def state(self,enabled=True,owned=False,protocol=1):
  return {'professional_printer':{'enabled':enabled,'owned':owned},'build_job':{'active':False},'supervision_lease':{},'material_protocol':2,'inventory_isolation':{'supported':True},'inventory':[{'item':'minecraft:cooked_beef','count':20,'slot':8}],'printer_idle_admission_protocol':protocol}
 def invoke(self,state,path):
  c=MaterialClient.__new__(MaterialClient);c.root=c.out=Path(path);c.world='world';c.recovery_only=False;c.raw=Mock(return_value=state);c.checked=Mock(return_value={'phase':'done'})
  with patch.object(Client,'__init__',return_value=None),patch.object(Client,'request')as send,patch('material_client.write_manifest'),patch('material_client.SafetyHeartbeat'):
   try:c._init_material(c.root,c.out,'simpcraft.com',False,False,None,'disconnect',None)
   finally:self.assertEqual(0,send.call_count,'No implicit printer stop may be dispatched')
  return c
 def test_user_enabled_mode_is_untouched_and_no_session_is_acquired(self):
  state=self.state();before=deepcopy(state)
  with TemporaryDirectory()as d:
   with self.assertRaisesRegex(Handoff,'leave its mode unchanged'):self.invoke(state,d)
  self.assertEqual(before,state)
 def test_foreign_printer_owner_still_blocks_acquisition(self):
  with TemporaryDirectory()as d:
   with self.assertRaisesRegex(Handoff,'Another task owns printing'):self.invoke(self.state(owned=True),d)
 def test_new_host_gets_explicit_client_thread_idle_precondition(self):
  with TemporaryDirectory()as d:
   c=self.invoke(self.state(enabled=False),d)
  self.assertEqual('material_session',c.checked.call_args.args[0]);self.assertIs(True,c.checked.call_args.kwargs['printer_idle_required'])
 def test_old_host_keeps_its_supported_envelope(self):
  with TemporaryDirectory()as d:c=self.invoke(self.state(enabled=False,protocol=0),d)
  self.assertNotIn('printer_idle_required',c.checked.call_args.kwargs)
