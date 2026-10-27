import unittest
from stopped_air_observation import guard_rise,incidental_drops
class Tests(unittest.TestCase):
 def test_only_bounded_incidental_mob_loot_may_differ(self):
  a={'inventory':[{'item':'minecraft:oak_boat','count':1,'slot':0}]};b={'inventory':a['inventory']+[{'item':'minecraft:rotten_flesh','count':8,'slot':1}]};self.assertTrue(incidental_drops(a,b))
  for after in [{'inventory':[]},{'inventory':a['inventory']+[{'item':'minecraft:diamond','count':1,'slot':1}]},{'inventory':a['inventory']+[{'item':'minecraft:rotten_flesh','count':65,'slot':1}]}]:self.assertFalse(incidental_drops(a,after))
 def test_small_guard_rise_can_be_observed_without_arrival_credit(self):
  r=dict(id='r',phase='waiting',detail='air-only path changed; no blocks were excavated',pos=[1,79.8,3]);e=dict(request_id='r',phase=r['phase'],detail=r['detail'],guard_pause_ms=7600);s=dict(last_request='r',guard_busy=False,pos=[1,80.6,3]);self.assertTrue(guard_rise(r,e,s))
  for edit in [dict(pos=[2,80.6,3]),dict(pos=[1,83,3]),dict(last_request='other'),dict(guard_busy=True)]:self.assertFalse(guard_rise(r,e,dict(s,**edit)))
  self.assertFalse(guard_rise(r,dict(e,guard_pause_ms=0),s));self.assertFalse(guard_rise(dict(r,phase='done'),e,s))
