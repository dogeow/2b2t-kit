import unittest
from resident_health_progress import observe
class HealthProgressTest(unittest.TestCase):
 def test_healing_raises_required_floor_and_cannot_hide_a_later_decline(self):
  floors=observe([dict(uuid='patient',health=16)],{'patient':11.39});self.assertEqual(16,floors['patient'])
  with self.assertRaises(RuntimeError):observe([dict(uuid='patient',health=15)],floors)
 def test_other_residents_must_remain_full(self):
  with self.assertRaises(RuntimeError):observe([dict(uuid='other',health=19)],{'patient':11.39})
 def test_invalid_observations_fail(self):
  for h in [float('nan'),float('inf'),0,21]:
   with self.assertRaises(RuntimeError):observe([dict(uuid='patient',health=h)],{'patient':11.39})
