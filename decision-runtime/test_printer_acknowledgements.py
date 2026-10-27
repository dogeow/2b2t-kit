from unittest import TestCase
from printer_acknowledgements import acknowledged_delta

class PrinterAcknowledgementTests(TestCase):
 def state(self,total,station=0,**kw):return {'world_session':'w','professional_printer':{'server_confirmed_epoch':'process','server_confirmed_total':total,'server_confirmed':station,**kw}}
 def test_many_station_resets_do_not_lose_acknowledgements(self):
  self.assertEqual(32,acknowledged_delta(self.state(100,8),self.state(132,2)))
 def test_no_new_server_acknowledgement_is_zero(self):self.assertEqual(0,acknowledged_delta(self.state(100),self.state(100,10)))
 def test_legacy_or_restarted_process_cannot_prove_a_delta(self):
  for after in [self.state(132,server_confirmed_epoch='other'),{'world_session':'w','professional_printer':{'server_confirmed':32}}]:
   with self.assertRaises(RuntimeError):acknowledged_delta(self.state(100),after)
 def test_old_world_or_decreasing_or_boolean_counts_are_rejected(self):
  for after in [{**self.state(132),'world_session':'other'},self.state(99),self.state(True),self.state(-1)]:
   with self.assertRaises(RuntimeError):acknowledged_delta(self.state(100),after)
