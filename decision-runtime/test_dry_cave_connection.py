import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from material_jobs.dry_cave_connection import air_cells
class CurrentAirConnectionTest(unittest.TestCase):
 def test_unknown_air_leg_stops_the_route_without_another_waypoint(self):
  class C:
   world='world'
   def status(self):return {'pos':[.5,30.1,.5]}
  c=C();cells=[[x,30,0]for x in range(14)]
  with TemporaryDirectory()as d,patch('material_jobs.dry_cave_connection.move',side_effect=RuntimeError('unknown original leg'))as move:
   with self.assertRaisesRegex(RuntimeError,'unknown original leg'):air_cells(c,cells,Path(d)/'route',c.status)
   self.assertEqual(1,move.call_count)
