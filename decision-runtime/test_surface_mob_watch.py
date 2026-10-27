import unittest
from unittest.mock import patch
from surface_mob_watch import observe
class SurfaceMobWatchTests(unittest.TestCase):
 class Builder:
  root='unused';calls=0
  def check(self):return dict(world_session='w',day_time=18000)
  def scan(self,*args):
   self.calls+=1
   good=dict(uuid='a',type='minecraft:zombie',alive=True,health=20,is_baby=False,has_custom_name=False,pos=[0,64,0])
   return dict(world_session='w',scan_entities=[good,{**good,'uuid':'baby','is_baby':True},{**good,'uuid':'hurt','health':19},{**good,'uuid':'named','has_custom_name':True}]),{}
 def test_bright_sky_does_not_dispatch_search_even_with_raw_midnight(self):
  b=self.Builder()
  with patch('surface_mob_watch.daylight',return_value={'period':'bright'}):r=observe(b,[0,62,0],[2,68,2])
  self.assertEqual(b.calls,0);self.assertEqual(r['next'],'do_other_work_while_bright')
 def test_missing_sky_never_creates_a_timed_wait(self):
  b=self.Builder()
  with patch('surface_mob_watch.daylight',return_value=None):r=observe(b,[0,62,0],[2,68,2])
  self.assertEqual(b.calls,0);self.assertEqual(r['capture_credit'],0)
 def test_dark_sky_surveys_once_and_only_healthy_unnamed_adults_are_candidates(self):
  b=self.Builder()
  with patch('surface_mob_watch.daylight',return_value={'period':'dark'}):r=observe(b,[0,62,0],[2,68,2])
  self.assertEqual(b.calls,1);self.assertEqual([e['uuid']for e in r['candidates']],['a']);self.assertEqual(r['capture_credit'],0)
if __name__=='__main__':unittest.main()
