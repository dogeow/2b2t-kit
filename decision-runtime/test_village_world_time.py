import unittest
from village_world_time import classify
class WorldTimeTests(unittest.TestCase):
 def evidence(self,**kw):return dict(scope='current_client_world_environment',observed_at=10000,sky_darken=11,dark_outside=True,bright_outside=False,time_changer_active=False,overworld_clock_ticks=0,**kw)
 def test_darkness_can_be_proven_even_when_raw_clock_modulo_looks_like_day(self):self.assertEqual(classify(self.evidence(),10001)['period'],'dark')
 def test_raw_midnight_cannot_override_observed_bright_sky(self):
  e={**self.evidence(),'overworld_clock_ticks':18000,'sky_darken':0,'dark_outside':False,'bright_outside':True};self.assertEqual(classify(e,10001)['period'],'bright')
 def test_unknown_visual_override_stale_or_contradictory_sky_is_not_night(self):
  for update in [{'time_changer_active':True},{'time_changer_active':None},{'observed_at':8000},{'sky_darken':0},{'dark_outside':False},{'bright_outside':True},{'sky_darken':True}]:
   self.assertIsNone(classify({**self.evidence(),**update},10001))
 def test_legacy_frame_without_environment_is_unknown(self):self.assertIsNone(classify(None,10000))
if __name__=='__main__':unittest.main()
