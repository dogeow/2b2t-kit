from unittest import TestCase
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from roof_access_route import prepare
from material_jobs.protocol import JobBlocked
from roof_slab_window_plan import SLAB
class Builder:
 def __init__(self,y=63):self.client=self;self.pos=[4.5,y,4.5];self.calls=[];self.unconfirmed_native_request=None
 def status(self):return self.check()
 def check(self):return {'health':20,'guard_busy':False,'world_session':'world','pos':self.pos,'manual_movement':False,'screen':''}
 def n(self,op,**kw):self.calls.append(op);return {'phase':'done'}
class RoofAccessTest(TestCase):
 model={'expected':[{'pos':[x,72,z],'state':SLAB}for x in range(1,9)for z in range(1,9)]}
 def test_above_roof_does_not_move_or_change_inventory(self):
  with TemporaryDirectory()as d:
   b=Builder(74.1)
   with patch('roof_access_route.move')as travel:r=prepare(b,self.model,Path(d)/'proof');travel.assert_not_called()
   self.assertTrue(r['ready']);self.assertEqual([],b.calls)
 def test_existing_air_route_is_used_without_mining(self):
  with TemporaryDirectory()as d:
   b=Builder()
   def travel(client,target,*args,**kw):b.pos=target
   with patch('roof_access_route.move',side_effect=travel):r=prepare(b,self.model,Path(d)/'proof')
   self.assertTrue(r['ready']);self.assertFalse(r['mining_sent']);self.assertEqual(['select_item'],b.calls)
 def test_blocked_preflight_never_mines_an_escape_tunnel(self):
  with TemporaryDirectory()as d:
   b=Builder()
   with patch('roof_access_route.move',side_effect=JobBlocked('closed')):r=prepare(b,self.model,Path(d)/'proof')
   self.assertFalse(r['ready']);self.assertEqual(['select_item'],b.calls)
 def test_unknown_native_request_does_not_try_a_second_route(self):
  with TemporaryDirectory()as d:
   b=Builder();b.unconfirmed_native_request={'id':'unknown'}
   with patch('roof_access_route.move',side_effect=JobBlocked('unknown'))as travel:
    with self.assertRaises(JobBlocked):prepare(b,self.model,Path(d)/'proof')
    self.assertEqual(1,travel.call_count)
