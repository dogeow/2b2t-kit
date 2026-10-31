import copy,json,tempfile,unittest
from pathlib import Path
from projected_bubble_column import cells_for,scan_bounds,geometry,fill,BUBBLE
LOW=[20,63,30];HIGH=[20,69,30]
class Tests(unittest.TestCase):
 def fixture(self):return json.loads((Path(__file__).parent/'test_fixtures/up-bubble-column.json').read_text())
 def test_exact_original_bubble_and_outlet_have_all_56_pins(self):
  f=self.fixture();p=geometry(f['model'],f['frame'],LOW,HIGH,'unit-world');self.assertEqual(56,len(p['bubble_boundary_pins']));self.assertEqual(7,len(p['bubble_cells']));self.assertEqual([14,69,29],p['outlet_cells'][-1]);self.assertEqual([20,70,30],p['bubble_service_cap'])
 def test_wrong_lift_direction_seal_or_cap_is_not_adopted(self):
  for mode in ['direction','seal','cap']:
   f=self.fixture()
   if mode=='direction':next(v for v in f['model']['expected']if v['pos']==LOW)['state']='Block{minecraft:bubble_column}[drag=true]'
   if mode=='seal':f['frame']['blocks'][0]['state']='Block{minecraft:stone}'
   if mode=='cap':f['frame']['blocks'].append(dict(pos=[20,70,30],state='Block{minecraft:glass}',block_entity=False))
   with self.assertRaises(RuntimeError):geometry(f['model'],f['frame'],LOW,HIGH,'unit-world')
 def test_no_prediction_or_cross_world_evidence_is_accepted(self):
  for key,value in [('world_session','other'),('scan_coherent',False),('scan_cells_read',323)]:
   f=self.fixture();f['frame'][key]=value
   with self.assertRaises(RuntimeError):geometry(f['model'],f['frame'],LOW,HIGH,'unit-world')
 def test_invalid_height_width_and_noninteger_bounds(self):
  for hi in [[21,69,30],[20,68,30],[20,69.0,30]]:
   with self.assertRaises(ValueError):cells_for(LOW,hi)
 def test_preflight_failure_is_not_a_dispatched_water_request(self):
  class Fake:
   task='unit';
   def status(self):return {'projected_bubble_column_protocol':0}
  with tempfile.TemporaryDirectory()as d:
   out=Path(d)/'one'
   with self.assertRaises(RuntimeError):fill(Fake(),LOW,HIGH,LOW,'unit-bubble',out)
   q=json.loads((out/'progress.json').read_text());self.assertFalse(q['dispatch_started']);self.assertIsNone(q['pending'])
