import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from drop_collection import collect_nearby_plant_shape
class PlantShapePickupTest(unittest.TestCase):
 def client(self,out,unknown=False):
  class C:
   world='world';last='';native_inflight=None;unconfirmed_native_request=None;calls=0;time=0;count=0
   def status(self):
    self.time+=1
    return {'time':self.time,'pos':[0.,85.1,0.],'health':20,'flight':True,'guard_armed':True,'guard_pve_only':True,'entities':[]if self.count else [drop],'inventory':[{'slot':0,'item':'minecraft:bamboo','count':self.count}]}
   def request(self,op,**kw):
    self.calls+=1;self.last='movement'
    if unknown:raise RuntimeError('unknown movement')
    self.count=5;return {'phase':'done'}
  drop={'uuid':'d','type':'minecraft:item','pos':[1.25,85.,0.],'stack':{'item':'minecraft:bamboo','count':5}}
  c=C();c.out=out;return c,drop
 def test_one_small_native_real_shape_step_requires_actual_stack_gain_and_disappearance(self):
  with TemporaryDirectory()as d:
   c,drop=self.client(Path(d));self.assertTrue(collect_nearby_plant_shape(c,drop,0));self.assertEqual(1,c.calls)
 def test_unknown_movement_never_replayed_or_followed_by_more_input(self):
  with TemporaryDirectory()as d:
   c,drop=self.client(Path(d),True)
   with self.assertRaisesRegex(RuntimeError,'unknown movement'):collect_nearby_plant_shape(c,drop,0)
   self.assertEqual(1,c.calls)
