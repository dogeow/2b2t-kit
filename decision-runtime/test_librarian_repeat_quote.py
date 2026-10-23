import unittest
from librarian_repeat_quote import fresh_generation
class RepeatQuoteTest(unittest.TestCase):
 def fixture(self):return {'offers_fingerprint':'fixed-paper-and-bookshelf','opening_request_id':'new'},{'old_fingerprint':'fixed-paper-and-bookshelf','old_opening':'old','pending':False,'station_restored':True,'unemployment_observed':True,'native_sequence':7,'server_ack_sequence':7}
 def test_real_new_job_generation_may_draw_identical_fixed_offers(self):self.assertTrue(fresh_generation(*self.fixture()))
 def test_unconfirmed_or_old_generation_never_qualifies(self):
  for key,value in[('pending',True),('station_restored',False),('unemployment_observed',False),('native_sequence',-1),('server_ack_sequence',6),('old_opening','new')]:
   m,p=self.fixture();p[key]=value
   with self.subTest(key=key):self.assertFalse(fresh_generation(m,p))
 def test_new_fingerprint_does_not_require_an_exception(self):m,p=self.fixture();m['offers_fingerprint']='new-book';self.assertTrue(fresh_generation(m,p))
