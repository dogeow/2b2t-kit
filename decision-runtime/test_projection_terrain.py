import copy
import unittest
from projection_terrain import candidates,exposed_faces,accessible_room_order,footer_headroom

class Tests(unittest.TestCase):
 def fixture(self):
  row={'pos':[1,2,3],'actual':'Block{minecraft:dirt}','expected':'Block{minecraft:stone_bricks}',
       'kind':'occupied','block_entity':False,'fluid':False,'adjacent_fluid':False,'neighbors_loaded':True}
  state={'time':10000,'server':'s','dimension':'minecraft:overworld','pos':[4,4,4],'on_ground':False,
         'projection_selection':{'key':'house','min':[0,0,0],'max':[9,9,9]},
         'inventory':[{'slot':0,'item':'minecraft:stone_bricks','count':1}]}
  audit={'audit_schema':2,'observed_at':10000,'server':'s','dimension':'minecraft:overworld','loaded_chunks_verified':True,
         'enclosed_air_conflicts':[],'placement_key':'house','matched':0,'total':1,'mismatches':[row]}
  return audit,state,row
 def test_terrain_needs_available_replacement_and_reserves_in_batch(self):
  a,s,r=self.fixture();self.assertEqual(len(candidates(a,s)),1)
  self.assertEqual(candidates(a,s,{'minecraft:stone_bricks':1}),[])
  s['inventory']=[];self.assertEqual(candidates(a,s),[])
 def test_only_enclosed_designed_air_can_be_cleared_without_materials(self):
  a,s,r=self.fixture();a.update(total=0,mismatches=[]);r.update(kind='enclosed_air_candidate',expected='Block{minecraft:air}')
  a['enclosed_air_conflicts']=[r];s['inventory']=[]
  self.assertEqual(len(candidates(a,s)),1)
  a['audit_schema']=1
  with self.assertRaises(RuntimeError):candidates(a,s)
 def test_container_liquid_footing_and_player_structure_are_preserved(self):
  for changes in [{'block_entity':True},{'adjacent_fluid':True},{'neighbors_loaded':False},{'actual':'Block{minecraft:oak_planks}'}]:
   a,s,r=self.fixture();r.update(changes);self.assertEqual(candidates(a,s),[])
  a,s,r=self.fixture();s.update(on_ground=True,pos=[1.5,3,3.5]);self.assertEqual(candidates(a,s),[])
 def test_stale_world_and_out_of_bounds_rejected(self):
  for field,value in [('observed_at',0),('server','other'),('placement_key','other')]:
   a,s,r=self.fixture();a[field]=value
   with self.assertRaises((ValueError,RuntimeError)):candidates(a,s)
  a,s,r=self.fixture();r['pos']=[12,2,3]
  with self.assertRaises(ValueError):candidates(a,s)
 def test_nonair_neighbors_need_explicit_passability(self):
  rows=[{'pos':[1,3,3],'passable':False},{'pos':[0,2,3],'passable':True,'fluid':True},
        {'pos':[2,2,3],'passable':True,'fluid':False}]
  faces=exposed_faces([1,2,3],rows)
  self.assertNotIn('up',faces);self.assertNotIn('west',faces);self.assertIn('east',faces)
 def test_thin_hatch_can_be_considered_but_native_route_must_prove_access(self):
  rows=[{'pos':[1,3,3],'passable':False,'solid':False,'fluid':False}]
  self.assertIn('up',exposed_faces([1,2,3],rows))
  rows[0]['fluid']=True
  self.assertNotIn('up',exposed_faces([1,2,3],rows))
class RoomOrderTests(unittest.TestCase):
 def test_lower_partner_opens_walkable_room_before_more_upper_pockets(self):
  lower={'pos':[2,62,3],'expected':'Block{minecraft:air}'}
  upper={'pos':[1,63,3],'expected':'Block{minecraft:air}'}
  observations=[{'pos':lower['pos'],'passable':False},{'pos':[2,61,3],'passable':False},
                {'pos':upper['pos'],'passable':False},{'pos':[1,62,3],'passable':False},{'pos':[1,64,3],'passable':False}]
  self.assertEqual(accessible_room_order([upper,lower],observations,[1,62,3])[0],lower)
class FooterAccessTests(unittest.TestCase):
 def test_lower_foundation_requires_two_clear_cells_and_dry_ladder_is_supported(self):
  self.assertTrue(footer_headroom([1,60,3],{}))
  cell={'state':'Block{minecraft:dirt}','passable':False,'fluid':False}
  self.assertFalse(footer_headroom([1,60,3],{(1,62,3):cell}))
  cell={'state':'Block{minecraft:ladder}[waterlogged=false]','passable':False,'fluid':False}
  self.assertTrue(footer_headroom([1,60,3],{(1,61,3):cell}))
  cell['fluid']=True
  self.assertFalse(footer_headroom([1,60,3],{(1,62,3):cell}))
if __name__=='__main__':unittest.main()
