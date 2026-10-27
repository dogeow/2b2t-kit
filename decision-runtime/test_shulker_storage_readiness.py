import unittest
import test_shulker_storage_click as fixtures

class ShulkerWindowReadinessTests(unittest.TestCase):
 def fixture(self):return fixtures.ShulkerClickTests().fixture()
 def test_window_settles_before_exactly_one_native_click(self):
  from village_queue import VillageQueue
  from unittest.mock import patch
  from copy import deepcopy
  s,p=self.fixture();s['time']=1;busy=deepcopy(s);busy['native_material_busy']=True
  second=deepcopy(s);second['time']=2;third=deepcopy(s);third['time']=3
  q=VillageQueue.__new__(VillageQueue);q.world='w';q.lease={'job_session':'t'}
  states=iter([busy,second,third]);q.status=lambda **kw:next(states);q._owned_menu=lambda state,**kw:True
  clicks=[];q.native=lambda op,**params:clicks.append((op,params))or {'id':'one'}
  with patch('village_queue.time.sleep'):
   self.assertEqual(q.shulker_storage_click(**p),{'id':'one'})
  self.assertEqual(len(clicks),1);self.assertIsNone(q._shulker_storage_click)

if __name__=='__main__':unittest.main()
