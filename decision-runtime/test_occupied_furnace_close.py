import json,tempfile,unittest
from pathlib import Path
from village_queue import VillageQueue
from kit_runtime.journal import write_json

class OccupiedFurnaceCloseTests(unittest.TestCase):
 def fixture(self,root):
  q=VillageQueue.__new__(VillageQueue);q.out=Path(root);q.world='w';q.lease={'job_session':'t'};d=q.out/'old';d.mkdir();(q.out/'control').mkdir();write_json(q.out/'command.json',{'id':'old','action':'smelt_material'});write_json(d/'intent.json',{'id':'old','action':'smelt_material'});write_json(d/'result.json',{'phase':'blocked','detail':'指定熔炉有未处理物品，请先收回或选择空炉'});write_json(d/'smelting.json',{'world_session':'w','batches':[],'complete':False});state={'screen':'FurnaceScreen','menu':{'type':'FurnaceMenu','material_owned':True,'cursor':{'count':0}},'health':20,'manual_movement':False};q.status=lambda:state;sent=[];q.native=lambda op:sent.append(op);return q,d,state,sent
 def test_only_closes_without_changing_recipe_or_items(self):
  with tempfile.TemporaryDirectory()as root:
   q,d,s,sent=self.fixture(root);original=(d/'smelting.json').read_bytes();q.close_unloaded_occupied_furnace();self.assertEqual(sent,['close_menu']);self.assertEqual(original,(d/'smelting.json').read_bytes());self.assertIsNone(q._unloaded_furnace_close)
 def test_loaded_unknown_manual_or_foreign_furnace_is_retained(self):
  for change in ['batch','unknown','cursor','foreign','health','manual','world','different_result']:
   with self.subTest(change=change),tempfile.TemporaryDirectory()as root:
    q,d,s,sent=self.fixture(root)
    if change=='batch':write_json(d/'smelting.json',{'world_session':'w','batches':[{}],'complete':False})
    if change=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if change=='cursor':s['menu']['cursor']['count']=1
    if change=='foreign':s['menu']['material_owned']=False
    if change=='health':s['health']=19
    if change=='manual':s['manual_movement']=True
    if change=='world':write_json(d/'smelting.json',{'world_session':'other','batches':[],'complete':False})
    if change=='different_result':write_json(d/'result.json',{'phase':'blocked','detail':'unknown output'})
    with self.assertRaises(RuntimeError):q.close_unloaded_occupied_furnace()
    self.assertEqual(sent,[])
if __name__=='__main__':unittest.main()
