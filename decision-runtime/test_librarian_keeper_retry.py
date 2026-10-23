import unittest
from librarian_round_robin import wake_paid_keeper_candidates

class KeeperRetryTest(unittest.TestCase):
 def fixture(self):
  return {'source'},{'source':{'uuid':'paid','work':[10,64,13],'pos':[10.5,64.5625,16.3],'deferred_at':0,'refresh_key':'same-reset','paid_history_verified':True}},{'paid':{'health':20,'is_baby':False,'pos':[10.5,64.5625,15.3],'villager':{'profession':'minecraft:librarian'}}},{'paid':{'sleeping':False}},{},{'same-reset':2}
 def test_moved_adult_on_bed_can_retry_a_read_from_the_trade_window(self):
  b,d,a,f,c,t=self.fixture();self.assertEqual(wake_paid_keeper_candidates(b,d,a,f,21,c,t),['source']);self.assertFalse(b);self.assertFalse(d);self.assertEqual(c,{'same-reset':1});self.assertNotIn('same-reset',t)
 def test_visible_bed_foot_still_allows_only_a_fresh_read_attempt(self):
  b,d,a,f,c,t=self.fixture();a['paid']['pos']=[10.5,64.5625,15.5]
  self.assertEqual(wake_paid_keeper_candidates(b,d,a,f,21,c,t),['source'])
 def test_movement_does_not_override_sleep_paid_identity_health_or_cooldown(self):
  for mode in ['sleeping','unpaid','injured','baby','early','unchanged','far','wrong_job','missing']:
   b,d,a,f,c,t=self.fixture();now=21
   if mode=='sleeping':f['paid']['sleeping']=True
   if mode=='unpaid':d['source']['paid_history_verified']=False
   if mode=='injured':a['paid']['health']=19
   if mode=='baby':a['paid']['is_baby']=True
   if mode=='early':now=19
   if mode=='unchanged':d['source']['pos']=a['paid']['pos'][:]
   if mode=='far':a['paid']['pos']=[10.5,64.5625,16.0]
   if mode=='wrong_job':a['paid']['villager']['profession']='minecraft:none'
   if mode=='missing':a.clear()
   with self.subTest(mode=mode):self.assertEqual(wake_paid_keeper_candidates(b,d,a,f,now,c,t),[]);self.assertIn('source',b);self.assertEqual(t,{'same-reset':2})
 def test_retry_budget_and_unchanged_observation_expiry_remain_bounded(self):
  for mode in ['limit','unchanged']:
   b,d,a,f,c,t=self.fixture()
   if mode=='limit':c['same-reset']=3
   else:d['source']['pos']=a['paid']['pos'][:]
   self.assertEqual(wake_paid_keeper_candidates(b,d,a,f,100,c,t),[]);self.assertFalse(d);self.assertIn('source',b)
if __name__=='__main__':unittest.main()
