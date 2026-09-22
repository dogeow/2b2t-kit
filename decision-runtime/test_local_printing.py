import unittest
from local_printing import support_faces
class FixtureTest(unittest.TestCase):
 def test_hanging_lantern_only_approaches_underside_of_real_roof(self):
  rows=[{'pos':[2,4,5],'state':'Block{minecraft:stone}','fluid':False},{'pos':[2,2,5],'state':'Block{minecraft:stone}','fluid':False}]
  candidates=support_faces([2,3,5],'Block{minecraft:lantern}[hanging=true,waterlogged=false]',rows)
  self.assertEqual([(f,r['pos']) for f,r in candidates],[('down',[2,4,5])])
 def test_air_or_fluid_cannot_supply_a_placement_anchor(self):
  rows=[{'pos':[2,4,5],'state':'Block{minecraft:water}[level=0]','fluid':True}]
  self.assertEqual(support_faces([2,3,5],'Block{minecraft:lantern}[hanging=true,waterlogged=false]',rows),[])
if __name__=='__main__':unittest.main()
