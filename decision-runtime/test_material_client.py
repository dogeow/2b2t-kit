import unittest
from unittest.mock import patch
from material_client import Client,MaterialClient,high_park_clearance,credit_guard_pause,Handoff
BUSY='Construction guard is defending or eating; wait before changing items or starting work'
class Tests(unittest.TestCase):
 def test_combat_pause_extends_only_guarded_native_wait_with_a_cap(self):
  deadline,paused=credit_guard_pause(100,0,35,True)
  self.assertEqual((135,35),(deadline,paused))
  self.assertEqual((135,35),credit_guard_pause(deadline,paused,20,False))
  self.assertEqual((280,180),credit_guard_pause(deadline,paused,200,True))
 def test_ground_level_park_is_rejected_before_material_control(self):
  rows=[{'pos':[10,73,20],'passable':False,'fluid':False}]
  self.assertEqual(1,high_park_clearance(rows,75))
  self.assertEqual(20,high_park_clearance(rows,94))
  with self.assertRaises(Handoff):high_park_clearance([],120)
 def test_high_parking_checks_height_and_horizontal_drift_separately(self):
  c=MaterialClient.__new__(MaterialClient);c.park_target=[100.5,95,200.5]
  self.assertTrue(c.park_near({'pos':[107.5,95,200.5]}))
  self.assertFalse(c.park_near({'pos':[109.5,95,200.5]}))
  self.assertFalse(c.park_near({'pos':[100.5,88,200.5]}))
 def test_only_pre_dispatch_guard_busy_is_retried(self):
  c=MaterialClient.__new__(MaterialClient);c.task='t';c.status=lambda:{}
  with patch.object(Client,'request',side_effect=[{'phase':'error','detail':BUSY},{'phase':'done'}]) as call,patch('material_client.time.sleep'):
   self.assertEqual(c.request('slot_click')['phase'],'done');self.assertEqual(call.call_count,2)
 def test_ambiguous_inventory_errors_are_never_replayed(self):
  c=MaterialClient.__new__(MaterialClient);c.task='t';c.status=lambda:{}
  with patch.object(Client,'request',return_value={'phase':'error','detail':'Inventory transfer not confirmed'}) as call:
   self.assertEqual(c.request('slot_click')['phase'],'error');self.assertEqual(call.call_count,1)
 def test_empty_approved_depot_is_not_reported_as_a_successful_fetch(self):
  c=MaterialClient.__new__(MaterialClient);c.task='t'
  c.status=lambda:{'inventory':[{'slot':0,'item':'minecraft:gravel','count':1}]}
  with patch.object(MaterialClient,'request',return_value={'phase':'done','build_supply':{'taken':{}}}) as call:
   result=c.fetch([1,2,3],{'gravel':16})
   self.assertEqual(result['phase'],'waiting')
   self.assertEqual(result['shortfall'],{'gravel':15})
   self.assertEqual(result['native_phase'],'done')
   self.assertEqual(call.call_count,1)
if __name__=='__main__':unittest.main()
