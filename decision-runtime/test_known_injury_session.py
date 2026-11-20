import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'work'/'village-trading-20261017'))
from known_injury_session import KnownInjurySession
from village_resource_health import ProtectedResidentHealthError

class KnownInjurySessionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.state={'connected':True,'world_session':'w','health':20,'manual_movement':False,'screen':'','loaded_villagers':{'villagers':[{'uuid':'old','health':1,'pos':[1.,64.,1.]},{'uuid':'other','health':20,'pos':[2.,64.,1.]}]}}
  self.session=KnownInjurySession.__new__(KnownInjurySession);self.session.q=Mock();self.session.q.status.side_effect=lambda:self.state;self.session.out=Path(self.temp.name);self.session.scope_world='w';self.session.protected_ids={'old','other'};self.session.home_min=[0,60,0];self.session.home_max=[10,70,10];self.session.known_health_floors={'old':1.0}
 def test_known_injury_remains_protected_and_floor_only_increases(self):
  self.assertIs(self.session.check(),self.state)
  self.state['loaded_villagers']['villagers'][0]['health']=12
  self.session.check();self.assertEqual(self.session.known_health_floors['old'],12)
  self.state['loaded_villagers']['villagers'][0]['health']=11
  with self.assertRaises(ProtectedResidentHealthError):self.session.check()
 def test_new_damage_to_other_resident_stops(self):
  self.state['loaded_villagers']['villagers'][1]['health']=19
  with self.assertRaises(ProtectedResidentHealthError):self.session.check()
 def test_player_safety_not_relaxed(self):
  self.state['health']=19
  with self.assertRaises(RuntimeError):self.session.check()
if __name__=='__main__':unittest.main()
