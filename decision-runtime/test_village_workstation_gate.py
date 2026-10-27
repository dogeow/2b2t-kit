import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from village_queue import VillageQueue
from kit_runtime.journal import write_json as real_write
class WorkstationGate(unittest.TestCase):
 def test_uncontained_residents_block_all_career_blocks_but_allow_cell_walls(self):
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);out=root/'owner';out.mkdir();q=VillageQueue.__new__(VillageQueue);q.out=out;q.world='w';q.lease={};q.prefix='gate';q.index=0;q.closing_menu=None;q.status=lambda **kw:{'screen':'','hand':{'item':'minecraft:lectern'}}
   (root/'project-state.json').write_text(json.dumps({'workstation_installation_gate':{'new_workstations_prohibited_until_gate_passes':True,'all_contained_verified':False}}))
   for item in ('lectern','composter','fletching_table','barrel','brewing_stand'):
    with self.subTest(item=item),self.assertRaises(RuntimeError):q._send('native',op='interact',params={'expected_hand':'minecraft:'+item})
   self.assertFalse((out/'command.json').exists())
   table=root/'stage.json';table.write_text(json.dumps({'expected':[{'item':'minecraft:lectern'}]}))
   with self.assertRaises(RuntimeError):q._send('build_village_stage',table=str(table))
   sent=[]
   def owner(path,value):
    real_write(path,value)
    if Path(path).name=='command.json':
     sent.append(value);d=out/value['id'];d.mkdir();real_write(d/'result.json',{'phase':'done'})
   with patch('village_queue.write_json',side_effect=owner):q._send('native',op='interact',params={'expected_hand':'minecraft:dark_oak_planks'})
   self.assertEqual(1,len(sent));self.assertEqual('minecraft:dark_oak_planks',sent[0]['params']['expected_hand'])
