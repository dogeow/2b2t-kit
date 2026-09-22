import unittest,tempfile,zipfile,json
from pathlib import Path
from recipe_catalog import RecipeCatalog
class Tests(unittest.TestCase):
 def catalog(self,recipes,tags={}):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);p=Path(t.name)/'recipes.jar'
  with zipfile.ZipFile(p,'w') as z:
   for k,v in recipes.items():z.writestr('data/minecraft/recipe/'+k+'.json',json.dumps(v))
   for k,v in tags.items():z.writestr('data/minecraft/tags/item/'+k+'.json',json.dumps({'values':v}))
  return RecipeCatalog(p)
 def test_repeated_slots_and_workbench_alignment(self):
  c=self.catalog({'slab':{'type':'minecraft:crafting_shaped','pattern':['##'],'key':{'#':'minecraft:stone'},'result':{'id':'minecraft:stone_pressure_plate'}}})
  r=c.choose('minecraft:stone_pressure_plate',{'minecraft:stone':2},3);self.assertEqual(r['ingredients'],{'minecraft:stone':[1,2]});self.assertFalse(r['missing_for_one'])
 def test_tag_selects_carried_material_without_inventing_inventory(self):
  c=self.catalog({'planks':{'type':'minecraft:crafting_shapeless','ingredients':['#minecraft:logs'],'result':{'id':'minecraft:oak_planks','count':4}}},{'logs':['minecraft:oak_log','minecraft:stripped_oak_log']})
  r=c.choose('minecraft:oak_planks',{'minecraft:stripped_oak_log':1});self.assertEqual(r['ingredients'],{'minecraft:stripped_oak_log':[1]});self.assertFalse(r['missing_for_one'])
 def test_missing_items_and_uncraftable_outputs_stay_explicit(self):
  c=self.catalog({'x':{'type':'minecraft:crafting_shapeless','ingredients':['minecraft:diamond'],'result':{'id':'minecraft:test'}}})
  self.assertEqual(c.choose('minecraft:test',{})['missing_for_one'],{'minecraft:diamond':1})
  with self.assertRaises(ValueError):c.choose('minecraft:nether_star',{})
if __name__=='__main__':unittest.main()
