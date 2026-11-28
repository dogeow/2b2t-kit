import unittest
import json,math
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from material_jobs.honeycomb import smoke_plan,harvest,extinguishing_shovel,fire_cells_clear
class SmokeColumnPlanTest(unittest.TestCase):
 def test_fire_placement_requires_current_clear_entity_evidence(self):
  scene={'scan_entity_scope':'current_client_loaded_entities_intersecting_scan_AABB_sampled_at_scan_end_not_whole_herd','scan_entities':[]}
  self.assertTrue(fire_cells_clear(scene,[0,64,0]))
  bee={'alive':True,'bounds':{'min':[.2,64.5,.2],'max':[.8,65.2,.8]}}
  self.assertFalse(fire_cells_clear({**scene,'scan_entities':[bee]},[0,64,0]))
  self.assertFalse(fire_cells_clear({**scene,'scan_entities':[{'alive':True}]},[0,64,0]))
  self.assertFalse(fire_cells_clear({'scan_entities':[]},[0,64,0]))
 def test_extinguishing_tool_accepts_carried_netherite_and_requires_one(self):
  self.assertEqual('minecraft:netherite_shovel',extinguishing_shovel({'minecraft:netherite_shovel':1}))
  with self.assertRaisesRegex(RuntimeError,'shovel'):extinguishing_shovel({})
 def test_only_ripe_nest_with_clear_short_smoke_column_and_existing_soil(self):
  nest={'pos':[0,67,0],'state':'Block{minecraft:bee_nest}[facing=south,honey_level=5]'}
  soil={'pos':[0,63,0],'state':'Block{minecraft:grass_block}[snowy=false]','solid':True,'fluid':False,'block_entity':False}
  p=smoke_plan([soil,nest],nest);self.assertEqual([0,64,0],p['campfire']);self.assertEqual([0,65,0],p['cover']);self.assertEqual(3,p['smoke_distance'])
  self.assertIsNone(smoke_plan([soil,nest,{'pos':[0,66,0],'state':'Block{minecraft:oak_log}'}],nest))
  self.assertIsNone(smoke_plan([soil],{**nest,'state':nest['state'].replace('honey_level=5','honey_level=4')}))
  hive={**nest,'state':nest['state'].replace('minecraft:bee_nest','minecraft:beehive')}
  self.assertEqual([0,64,0],smoke_plan([soil,hive],hive)['campfire'])
 def test_protected_nest_requires_exact_authorization_before_actions(self):
  nest={'pos':[0,67,0],'state':'Block{minecraft:bee_nest}[facing=south,honey_level=5]'}
  plan={'nest':nest,'campfire':[0,64,0],'cover':[0,65,0],'support':{'pos':[0,63,0]}}
  class C:world='world'
  with TemporaryDirectory() as d,patch('material_jobs.honeycomb._protected',return_value=True):
   with self.assertRaisesRegex(RuntimeError,'without exact authorization'):
    harvest(C(),plan,{},Path(d)/'denied',lambda:{})
   with self.assertRaises(ValueError):
    harvest(C(),plan,{},Path(d)/'invalid',lambda:{},authorized_nests=[[0,67,'0']])
   with self.assertRaisesRegex(RuntimeError,'smoke source'):
    harvest(C(),plan,{},Path(d)/'authorized',lambda:{'inventory':[]},authorized_nests=[[0,67,0]])
   unripe={**plan,'nest':{**nest,'state':nest['state'].replace('honey_level=5','honey_level=4')}}
   with self.assertRaisesRegex(RuntimeError,'ripe nest'):
    harvest(C(),unripe,{},Path(d)/'unripe',lambda:{'inventory':[]},authorized_nests=[[0,67,0]])
 def test_uncertain_campfire_use_keeps_intent_and_never_shears_or_replays(self):
  nest={'pos':[0,67,0],'state':'Block{minecraft:bee_nest}[facing=south,honey_level=5]'}
  soil={'pos':[0,63,0],'state':'Block{minecraft:grass_block}[snowy=false]','solid':True,'fluid':False,'block_entity':False};rows=[nest,soil]
  class C:
   world='world';last='';uses=0;moves=0
   def status(self):return {'pos':[2.,64.1,.5],'stock':Counter({'minecraft:campfire':1,'minecraft:stone_slab':2,'minecraft:shears':1,'minecraft:netherite_shovel':1})}
   def checked(self,op,**kw):
    self.last=op
    if op=='navigate':self.moves+=1
    if op=='interact':self.uses+=1;raise RuntimeError('unknown native receipt')
    return {'phase':'done'}
   def request(self,op,**kw):return {'phase':'done','blocks':rows,'scan_cells_read':math.prod(b-a+1 for a,b in zip(kw['min'],kw['max'])),'scan_entities':[],'scan_entity_scope':'current_client_loaded_entities_intersecting_scan_AABB_sampled_at_scan_end_not_whole_herd'}
  c=C()
  def cell(_,p):return next((r for r in rows if r['pos']==p),{'pos':p,'state':'Block{minecraft:air}'})
  with TemporaryDirectory()as d,patch('material_jobs.honeycomb._protected',return_value=False),patch('material_jobs.honeycomb.inventory_counts',lambda s:s['stock']),patch('material_jobs.honeycomb.cell_at',side_effect=cell),patch('material_jobs.honeycomb.approach_faces',return_value='up'):
   out=Path(d)/'harvest'
   with self.assertRaisesRegex(RuntimeError,'unknown native receipt'):harvest(c,smoke_plan(rows,nest),{},out,c.status)
   self.assertEqual('one_normal_campfire_placement',json.loads((out/'honeycomb.json').read_text())['pending']['kind'])
  self.assertEqual(1,c.uses)
  self.assertEqual(0,c.moves)
