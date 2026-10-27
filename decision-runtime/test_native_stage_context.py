import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from native_stage_context import require_player,free_slots
from iron_water_sources import enclosed,STONE

class NativeStageContextTests(unittest.TestCase):
 def state(self):return {'connected':True,'world_session':'w','health':20,'screen':'','manual_movement':False,'supervision_lease':{'job_session':'t'}}
 def test_current_healthy_owner(self):
  state=self.state();c=SimpleNamespace(world='w',task='t',status=lambda:state);self.assertIs(state,require_player(c))
 def test_health_manual_and_foreign_scope_remain_blocked(self):
  for delta in [{'connected':False},{'world_session':'other'},{'health':19},{'manual_movement':True},{'screen':'ChatScreen'},{'health_recovery_hold':True},{'safety_hold':{'active':True}},{'supervision_lease':{'job_session':'other'}}]:
   with self.subTest(delta=delta):
    state={**self.state(),**delta}
    with self.assertRaises(RuntimeError):require_player(SimpleNamespace(world='w',task='t',status=lambda:state))
 def test_only_actual_empty_main_slots(self):
  self.assertEqual(1,free_slots({'inventory':[{'slot':0,'count':0},{'slot':1,'count':64},{'slot':40,'count':0}]}))
 def test_removed_strategy_commands_cannot_execute(self):
  from village_project import execute
  for action in ['harness_iron_next','harness_iron_stage','harness_prepare_space']:
   with tempfile.TemporaryDirectory()as d,patch('village_project._safe'):
    with self.assertRaisesRegex(ValueError,'Unsupported bounded village stage'):execute(Mock(),{'action':action},Path(d),lambda:{})
 def test_contained_sources_remain_independent_of_external_planner(self):
  rows={};x,y,z=761077,95,797805
  for xx in range(x-2,x+3):
   for zz in range(z-1,z+2):rows[xx,y-1,zz]={'state':STONE}
  for xx in range(x-2,x+3):
   for zz in (z-1,z+1):rows[xx,y,zz]={'state':STONE}
  for xx in (x-2,x+2):rows[xx,y,z]={'state':STONE}
  bounds={'min':[x-2,y-1,z-1],'max':[x+2,y+2,z+1]}
  self.assertTrue(enclosed(rows,[x,y,z],bounds));del rows[x,y,z-1];self.assertFalse(enclosed(rows,[x,y,z],bounds))
