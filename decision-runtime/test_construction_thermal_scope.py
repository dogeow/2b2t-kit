import unittest,time,copy
from types import SimpleNamespace
from construction_thermal_scope import original_source_work,allows
from stuck_damage import StuckDamageWitness
from test_stuck_damage import state

class ConstructionThermalScopeTests(unittest.TestCase):
 def client(self):return SimpleNamespace(world='world',task='task')
 def snapshot(self,t=0,hp=19.688961):
  return state(t,hp,recent_attacker='火',food=19,minor_thermal_work_protocol=1,minor_thermal_work_allowed=True,
   model_water_construction_options_protocol=1,projection_selection={'key':'projection'})
 def test_recorded_fire_during_explicit_source_work_does_not_trigger_idle_logout(self):
  c=self.client();w=StuckDamageWitness('world','task','lease')
  with original_source_work(c,'projection',enabled=True):
   for t,hp in [(0,19.688961),(717,19.533442),(1400,19.7)]:
    s=self.snapshot(t,hp);self.assertTrue(allows(c,s))
    self.assertIsNone(w.observe(s,revision=7,native_idle=True,construction_thermal=allows(c,s)))
  self.assertFalse(hasattr(c,'original_source_thermal_scope'))
 def test_current_client_observer_honors_only_bounded_construction_scope(self):
  from material_client import MaterialClient
  from unittest.mock import Mock
  c=MaterialClient.__new__(MaterialClient);c.world='world';c.task='task';c.rev=7
  c.heartbeat=SimpleNamespace(id='lease');c.native_inflight=None;c.unconfirmed_native_request=None
  c._exit_stuck_damage=Mock()
  with original_source_work(c,'projection',enabled=True):
   c._observe_stuck_damage(self.snapshot());c._observe_stuck_damage(self.snapshot(717,19.533442))
  c._exit_stuck_damage.assert_not_called()
  c._observe_stuck_damage(self.snapshot(2000,19.688961));c._observe_stuck_damage(self.snapshot(2717,19.533442))
  c._exit_stuck_damage.assert_called_once()
 def test_same_heat_while_standby_retains_previous_detection(self):
  w=StuckDamageWitness('world','task','lease')
  self.assertIsNone(w.observe(self.snapshot(),revision=7,native_idle=True))
  self.assertIsNotNone(w.observe(self.snapshot(717,19.533442),revision=7,native_idle=True))
 def test_expiry_wrong_world_task_projection_old_host_and_unknown_heat_fail_closed(self):
  c=self.client()
  with original_source_work(c,'projection',enabled=True):
   for key,value in [('world_session','other'),('projection_selection',{'key':'other'}),('model_water_construction_options_protocol',0),('minor_thermal_work_protocol',0),('minor_thermal_work_allowed',False),('health',18.99),('health',float('nan')),('food',17),('under_water',True),('in_lava',True)]:
    s=self.snapshot();s[key]=value;self.assertFalse(allows(c,s),key)
   c.task='other';self.assertFalse(allows(c,self.snapshot()));c.task='task'
   c.original_source_thermal_scope['until']=time.monotonic()-1;self.assertFalse(allows(c,self.snapshot()))
 def test_exception_and_nesting_restore_outer_scope_without_mutating_new_owner(self):
  c=self.client()
  with original_source_work(c,'projection',enabled=True):
   outer=c.original_source_thermal_scope
   with self.assertRaises(ValueError):
    with original_source_work(c,'second',enabled=True):raise ValueError('test')
   self.assertIs(c.original_source_thermal_scope,outer)
  self.assertFalse(hasattr(c,'original_source_thermal_scope'))
  with original_source_work(c,'projection',enabled=True):c.original_source_thermal_scope={'new_owner':True}
  self.assertEqual({'new_owner':True},c.original_source_thermal_scope)
 def test_invalid_native_thermal_evidence_cannot_disable_stuck_damage(self):
  for changed in [{'minor_thermal_work_allowed':False},{'health':18.9},{'food':17}]:
   w=StuckDamageWitness('world','task','lease');a=self.snapshot();a.update(changed);b=self.snapshot(717,19.533442);b.update(changed)
   if 'health'in changed:b['health']=18.7
   self.assertIsNone(w.observe(a,revision=7,native_idle=True,construction_thermal=True))
   self.assertIsNotNone(w.observe(b,revision=7,native_idle=True,construction_thermal=True))
if __name__=='__main__':unittest.main()
