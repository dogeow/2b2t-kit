import unittest
from wood_expedition import route,horizontal,landing,sky_path,Expedition
from unittest.mock import patch
class Tests(unittest.TestCase):
 def test_route_has_bounded_contiguous_hops(self):
  home=[761020,140,797854];last=home
  for p in route(home):self.assertLessEqual(horizontal(p,last),160.001);last=p
 def test_landing_requires_clear_column_and_natural_solid_ground(self):
  floor={'pos':[5,63,0],'state':'Block{minecraft:grass_block}[snowy=false]','solid':True,'passable':False}
  self.assertEqual(landing([floor],[0,64,0]),[5.5,64.15,.5])
  roof={'pos':[5,70,0],'state':'Block{minecraft:oak_leaves}','solid':True,'passable':False}
  self.assertIsNone(landing([floor,roof],[0,64,0]))
 def test_water_and_worked_ground_are_not_landing_surfaces(self):
  for block in ['water','farmland','oak_planks']:
   self.assertIsNone(landing([{'pos':[5,63,0],'state':'Block{minecraft:'+block+'}','solid':True}], [0,64,0]))
 def test_unloaded_chunks_are_retried_before_declaring_no_trees(self):
  class Fake:
   n=0
   def request(self,*a,**k):
    self.n+=1;return {'pos':[0,140,0],'tree_survey':{'trees':[],'biomes':{},'loaded_columns':0 if self.n==1 else 37249,'highest_surface':63}}
   def status(self):return {}
  e=Expedition.__new__(Expedition);e.c=Fake();e.item="minecraft:spruce_log";events=[];e.log=lambda event,**data:events.append(data)
  with patch('wood_expedition.time.sleep'):t=e.survey()
  self.assertGreaterEqual(e.c.n,2);self.assertEqual(len(events),1);self.assertEqual(t['loaded_columns'],37249)
 def test_canopy_exit_walks_to_open_sky_without_breaking_blocks(self):
  blocks=[{'pos':[x,63,z],'state':'Block{minecraft:dirt}','solid':True,'passable':False} for x in range(-12,13) for z in range(-12,13)]
  blocks += [{'pos':[x,68,z],'state':'Block{minecraft:spruce_leaves}','solid':True,'passable':False} for x in range(-2,3) for z in range(-2,3)]
  path=sky_path(blocks,[.5,64,.5]);self.assertIsNotNone(path);self.assertGreaterEqual(len(path),4)
  self.assertTrue(abs(path[-1][0]-.5)>=3 or abs(path[-1][2]-.5)>=3)
if __name__=='__main__':unittest.main()
