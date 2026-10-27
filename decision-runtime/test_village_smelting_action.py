import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from village_project import execute
class VillageSmeltingActionTests(unittest.TestCase):
 def test_reuses_same_owner_and_processing_receipt_without_retry_or_cleanup(self):
  for reply in [{'phase':'done','count':1},{'phase':'blocked','detail':'original loading receipt pending'}]:
   with self.subTest(reply=reply),tempfile.TemporaryDirectory()as directory:
    root=Path(directory);profile={'recipe_jar':'current.jar','furnace_positions':[[1,2,3]]};path=root/'profile.json';path.write_text(json.dumps(profile));recipe={'recipe_id':'minecraft:charcoal','source':'minecraft:dark_oak_log','output':'minecraft:charcoal','fuel_allow_items':['minecraft:dark_oak_planks']};owner=object();checkpoint=lambda:{}
    with patch('village_project._safe'),patch('material_jobs.processing.smelt',return_value=reply)as smelt:
     result=execute(owner,{'action':'smelt_material','profile':str(path),'recipe':recipe,'target':1},root,checkpoint)
    self.assertIs(result,reply);smelt.assert_called_once_with(owner,recipe,1,profile,root,checkpoint)

class VillageSmeltingObservationTests(unittest.TestCase):
 def test_pending_furnace_only_allows_observation_with_same_live_owner(self):
  from village_queue import VillageQueue
  with tempfile.TemporaryDirectory()as directory:
   q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.root=q.out;q.world='w';q.lease={'kind':'materials','id':'l','job_session':'t','world_session':'w'};q.closing_menu=None;d=q.out/'smelt';d.mkdir();command={'id':'smelt','action':'smelt_material','target':1};(q.out/'command.json').write_text(json.dumps(command));(d/'intent.json').write_text(json.dumps(command));state={'connected':True,'world_session':'w','health':20,'manual_movement':False,'supervision_lease':q.lease,'screen':'FurnaceScreen','menu':{'type':'FurnaceMenu','id':4,'cursor':{'count':1}}}
   with patch('village_queue.read_fresh',return_value=state),patch('village_queue.require_unlocked'):
    q.status(observing=True)
    with self.assertRaises(RuntimeError):q.status()
   for change in [{'manual_movement':True},{'health':18},{'world_session':'other'},{'supervision_lease':None},{'screen':'InventoryScreen'}]:
    with patch('village_queue.read_fresh',return_value={**state,**change}),patch('village_queue.require_unlocked'),self.assertRaises(RuntimeError):q.status(observing=True)
   for name in ['error.json','result.json']:
    (d/name).write_text('{}');self.assertFalse(q._smelting_observation(state));(d/name).unlink()

if __name__=='__main__':unittest.main()
