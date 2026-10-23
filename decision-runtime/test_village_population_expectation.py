import unittest,copy
from village_population_expectation import expected_population
class Tests(unittest.TestCase):
 def fixture(self):return ({'keeper','old','parent'},{'keeper'},{'user_authorized_replacement':True,'does_not_claim_death':True,'must_observe_uuids':['keeper','parent','new'],'historical_missing_uuids':['old']},{'newborn_verified':True,'samples':[{'observer_time':1,'babies':[{'uuid':'new','is_baby':True,'client_health':20}]},{'observer_time':2,'babies':[{'uuid':'new','is_baby':True,'client_health':20}]}]})
 def test_explicit_witnessed_replacement_and_history_preserved(self):
  a=self.fixture();old=copy.deepcopy(a);self.assertEqual({'keeper','parent','new'},expected_population(*a));self.assertEqual(a,old)
 def test_no_replacement_preserves_original_requirements(self):self.assertEqual({'keeper','old'},expected_population({'keeper','old'},{'keeper'}))
 def test_supplier_or_unrecorded_resident_cannot_be_removed(self):
  a=list(copy.deepcopy(self.fixture()));a[2]['must_observe_uuids'].remove('keeper')
  with self.assertRaises(ValueError):expected_population(*a)
  a=list(copy.deepcopy(self.fixture()));a[2]['historical_missing_uuids']=[]
  with self.assertRaises(ValueError):expected_population(*a)
 def test_stale_wrong_or_unhealthy_birth_is_rejected(self):
  for mode in ['stale','wrong','unhealthy','adult','unverified']:
   a=list(copy.deepcopy(self.fixture()))
   if mode=='stale':a[3]['samples'][1]['observer_time']=1
   elif mode=='wrong':a[3]['samples'][1]['babies'][0]['uuid']='other'
   elif mode=='unhealthy':a[3]['samples'][1]['babies'][0]['client_health']=19
   elif mode=='adult':a[3]['samples'][1]['babies'][0]['is_baby']=False
   else:a[3]['newborn_verified']=False
   with self.subTest(mode=mode),self.assertRaises(ValueError):expected_population(*a)
 def test_replacement_requires_human_authorization(self):
  a=list(copy.deepcopy(self.fixture()));a[2]['user_authorized_replacement']=False
  with self.assertRaises(ValueError):expected_population(*a)
