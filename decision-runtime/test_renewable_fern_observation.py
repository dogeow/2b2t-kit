import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from material_jobs.renewable_fern import observe,SMALL,LOWER

class FernObservationTest(unittest.TestCase):
 def test_delayed_growth_is_observed_without_another_fertilization(self):
  tick=0
  def status():
   nonlocal tick
   tick+=100;return {'time':tick}
  c=SimpleNamespace(status=status,checked=Mock())
  with patch('material_jobs.renewable_fern.cell_at',side_effect=[{'state':SMALL},{'state':LOWER},{'state':LOWER}]),patch('material_jobs.renewable_fern.time.sleep'):
   observe(c,[1,64,2],LOWER,lambda:None)
  c.checked.assert_not_called()
 def test_missing_growth_never_repeats_the_original_use(self):
  c=SimpleNamespace(status=lambda:{'time':100},checked=Mock())
  with patch('material_jobs.renewable_fern.cell_at',return_value={'state':SMALL}),self.assertRaisesRegex(RuntimeError,'no repeat'):
   observe(c,[1,64,2],LOWER,lambda:None,timeout=0)
  c.checked.assert_not_called()

if __name__=='__main__':unittest.main()
