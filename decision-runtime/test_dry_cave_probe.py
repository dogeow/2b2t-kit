import unittest,json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from material_jobs.dry_cave_probe import run
class DryProbeTest(unittest.TestCase):
 def test_unknown_single_mine_keeps_intent_and_sends_no_next_move_or_remine(self):
  row={'pos':[1,42,0],'state':'Block{minecraft:stone}','fluid':False,'block_entity':False};floor={'pos':[0,42,0],'state':'Block{minecraft:stone}'}
  plan={'world_session':'world','maximum_new_mines':32,'actual_planned_mines':1,'start_pose':[.5,43.1,.5],'start_floor':floor,'target_y':42,'steps':[{'standing_column':[0,43,0],'target_column':[1,43,0],'mines':[row],'next_pose':[1.5,42.1,.5]}]}
  class C:
   world='world';last=''
   def __init__(self):self.calls=[]
   def status(self):return {'pos':[.5,43.1,.5],'health':20,'flight':True,'inventory':[{'slot':0,'item':'minecraft:diamond_pickaxe','count':1,'durability':200,'enchantments':[]}]}
   def checked(self,op,**kw):
    self.calls.append(op);self.last=op
    if op=='mine_block':raise RuntimeError('unknown removal')
    return {'phase':'done'}
   def request(self,op,**kw):return {'phase':'done','scan_cells_read':27,'blocks':[row]}
  c=C()
  with TemporaryDirectory()as d,patch('material_jobs.dry_cave_probe.cell_at',return_value=floor),patch('material_jobs.dry_cave_probe.approach_faces'),patch('material_jobs.dry_cave_probe._choose_tool'),patch('material_jobs.dry_cave_probe._protected',return_value=False),patch('material_jobs.dry_cave_probe.room_for_item',return_value=64):
   out=Path(d)/'probe'
   with self.assertRaisesRegex(RuntimeError,'unknown removal'):run(c,plan,{},out,c.status)
   self.assertEqual('one_new_dry_natural_mine',json.loads((out/'probe.json').read_text())['pending']['kind'])
  self.assertEqual(1,c.calls.count('mine_block'));self.assertEqual('mine_block',c.calls[-1])
