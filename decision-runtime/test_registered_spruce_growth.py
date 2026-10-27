import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from test_material_tree_regrowth import NativeTreeClient,native_cell
from material_jobs.acquisition import grow_registered_spruce,Unavailable


class RegisteredSpruceGrowthTest(unittest.TestCase):
 def setup(self):
  c=NativeTreeClient('Block{minecraft:spruce_sapling}[stage=0]')
  profile={'resource_regions':[{'item':'minecraft:spruce_log','source':'owned_seeded_spruce_tree_farm',
   'renewable':True,'root':[2,64,3],'min':[-1,64,0],'max':[5,80,6]}]}
  return c,profile
 def test_registered_sapling_is_grown_without_crediting_logs_or_replanting(self):
  c,p=self.setup()
  with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path.move')as move,patch('material_jobs.acquisition._apply_bone_meal',return_value={'stage':'grown','bone_meal_used':2})as grow:
   result=grow_registered_spruce(c,'minecraft:spruce_log',p,Path(d),lambda:None)
   self.assertIsNone(result);self.assertEqual(1,grow.call_count);self.assertEqual(1,move.call_count)
   book=json.loads(next(Path(d).rglob('progress.json')).read_text());self.assertIsNone(book['pending']);self.assertEqual(0,book['raw_inventory_credit'])
 def test_missing_bone_meal_returns_a_dependency_without_moving(self):
  c,p=self.setup();c.items['minecraft:bone_meal']=0
  with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path.move')as move,patch('material_jobs.acquisition._apply_bone_meal')as grow:
   result=grow_registered_spruce(c,'minecraft:spruce_log',p,Path(d),lambda:None)
   self.assertEqual({'minecraft:bone_meal':32},result['requirements']);move.assert_not_called();grow.assert_not_called()
 def test_unknown_original_access_is_retained_and_not_repeated(self):
  c,p=self.setup()
  with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path.move',side_effect=RuntimeError('Original movement unknown'))as move:
   with self.assertRaisesRegex(RuntimeError,'movement unknown'):grow_registered_spruce(c,'minecraft:spruce_log',p,Path(d),lambda:None)
   with self.assertRaises(Unavailable):grow_registered_spruce(c,'minecraft:spruce_log',p,Path(d),lambda:None)
   self.assertEqual(1,move.call_count)
 def test_known_budget_without_growth_stays_at_registered_farm(self):
  c,p=self.setup()
  with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path.move'),patch('material_jobs.acquisition._apply_bone_meal',return_value={'bone_meal_used':6}):
   result=grow_registered_spruce(c,'minecraft:spruce_log',p,Path(d),lambda:None)
   self.assertEqual('owned_tree_growth_wait',result['code'])
