import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from village_queue import VillageQueue
from kit_runtime.journal import write_json
class WorkbenchCapacityTests(unittest.TestCase):
 def case(self,directory):
  q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'id':'l','job_session':'t'};q.prefix='observe';q.index=0;q.closing_menu=None;d=q.out/'old';d.mkdir();(q.out/'control').mkdir();write_json(q.out/'command.json',{'id':'old','action':'manufacture','targets':{'minecraft:iron_door':3}});cert={'type':'CraftingMenu','id':4,'world_session':'w','task_session':'t','lease_id':'l','control_revision':3};write_json(q.out/'owned-material-menu.json',cert);r={'complete':False,'steps':[{'item':'minecraft:iron_door','state':'waiting_for_inventory_space'}],'remaining_targets':{'minecraft:iron_door':3},'owned_menu':cert};write_json(d/'result.json',r);s={'screen':'CraftingScreen','interface_paused':False,'inventory_interface_paused':False,'control_revision':3,'last_request':'last','inventory':[],'menu':{'type':'CraftingMenu','id':4,'cursor':{'count':0},'slots':[{'count':0}for _ in range(10)]}};e={'request_id':'last','phase':'done','world_session':'w','revision_after':3,'params':{'task_session':'t'}};(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n');q.status=lambda **kw:s;return q,d,s,e
 def test_only_observes_and_keeps_partial_result(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,s,e=self.case(directory);raw=(d/'result.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':
     sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_empty_workbench_inventory_wait()
   self.assertEqual(['snapshot'],[v['op']for v in sent]);self.assertEqual(raw,(d/'result.json').read_bytes())
 def test_pending_cursor_grid_unknown_or_changed_menu_stays_fenced(self):
  for mode in ['cursor','grid','unknown','menu','native']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as directory:
    q,d,s,e=self.case(directory)
    if mode=='cursor':s['menu']['cursor']['count']=1
    if mode=='grid':s['menu']['slots'][1]['count']=1
    if mode=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if mode=='menu':s['menu']['id']=5
    if mode=='native':e['phase']='waiting'
    (q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n')
    with self.assertRaises(RuntimeError):q.observe_empty_workbench_inventory_wait()
if __name__=='__main__':unittest.main()
