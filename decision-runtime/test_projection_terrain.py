import copy
import unittest
import json,tempfile
from pathlib import Path
from unittest.mock import patch
from projection_terrain import candidates,exposed_faces,accessible_room_order,footer_headroom
from projection_terrain import clear_batch

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

class JournaledTerrainTests(unittest.TestCase):
 def fake(self,root,confirmed=True):
  audit,state,row=Tests().fixture();row['actual']='Block{minecraft:stone}'
  actual={'pos':row['pos'],'state':row['actual'],'fluid':False,'block_entity':False,'solid':True,'passable':False}
  state.update(world_session='w',screen='',flight=True,hand={'item':'minecraft:diamond_pickaxe'},entities=[])
  state['inventory'].append({'slot':1,'item':'minecraft:air','count':0})
  class Client:
   world='w';last=None
   def __init__(self):self.root=root;self.out=root;self.mines=0;self.removed=False
   def status(self):return {**state,'world_session':self.world}
   def request(self,op,**kwargs):
    if op=='projection_audit':return {'projection_audit':audit}
    if op=='scan':return {'blocks':[]if self.removed else[actual]}
    if op=='mine_block':
     self.last='mining-once';self.mines+=1;self.removed=confirmed
     return {'id':self.last,'phase':'done'if confirmed else'waiting','world_session':self.world,
             'server_confirmed':confirmed,'native_sequence':7,'server_ack_sequence':7,
             'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack'}
    raise AssertionError(op)
  return Client(),row
 def test_exact_supplied_cell_requires_server_ack_and_never_credits_drops(self):
  with tempfile.TemporaryDirectory()as d:
   c,row=self.fake(Path(d))
   with patch('projection_terrain.require_unlocked'),patch('projection_terrain.approach_faces',return_value='up'),patch('projection_terrain.time.sleep'):
    result=clear_batch(c,1,expected_item='minecraft:stone_bricks',positions=[row['pos']])
   self.assertEqual(1,len(result['removed']));self.assertEqual(1,c.mines)
   intent=json.loads(next((Path(d)/'projection-terrain-intents').glob('*.json')).read_text())
   self.assertIsNone(intent['pending']);self.assertEqual('mining-once',intent['mining_request_id']);self.assertEqual(0,intent['inventory_credit'])
 def test_diagonal_water_is_deferred_before_approach_or_mining(self):
  with tempfile.TemporaryDirectory()as d:
   c,row=self.fake(Path(d));original=c.request
   def read(op,**kwargs):
    result=original(op,**kwargs)
    if op=='scan':result['blocks'].append({'pos':[2,3,4],'state':'Block{minecraft:water}[level=0]','fluid':True})
    return result
   c.request=read
   with patch('projection_terrain.require_unlocked'),patch('projection_terrain.approach_faces')as approach:
    result=clear_batch(c,1,expected_item='minecraft:stone_bricks',positions=[row['pos']])
   self.assertEqual([],result['removed']);self.assertEqual([row['pos']],result['deferred']);self.assertEqual(0,c.mines);approach.assert_not_called()
   self.assertFalse((Path(d)/'projection-terrain-intents').exists())
 def test_unknown_mining_is_durable_and_never_replayed_even_after_reconnect(self):
  with tempfile.TemporaryDirectory()as d:
   c,row=self.fake(Path(d),confirmed=False)
   with patch('projection_terrain.require_unlocked'),patch('projection_terrain.approach_faces',return_value='up'),patch('projection_terrain.time.sleep'):
    with self.assertRaisesRegex(RuntimeError,'unconfirmed'):clear_batch(c,1,expected_item='minecraft:stone_bricks',positions=[row['pos']])
    f=next((Path(d)/'projection-terrain-intents').glob('*.json'));before=f.read_bytes();c.world='new-world'
    with self.assertRaisesRegex(RuntimeError,'no mining replay'):clear_batch(c,1,expected_item='minecraft:stone_bricks',positions=[row['pos']])
   self.assertEqual(before,f.read_bytes());self.assertEqual(1,c.mines)
 def test_other_material_or_position_is_never_excavated(self):
  for options in ({'expected_item':'minecraft:spruce_planks'},{'positions':[[7,2,3]]}):
   with self.subTest(options=options),tempfile.TemporaryDirectory()as d:
    c,row=self.fake(Path(d))
    with patch('projection_terrain.require_unlocked'):
     result=clear_batch(c,1,**options)
    self.assertEqual([],result['removed']);self.assertEqual(0,c.mines)
if __name__=='__main__':unittest.main()
