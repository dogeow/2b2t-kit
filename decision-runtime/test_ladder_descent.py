import unittest
from projection_access import ladder_descent_geometry

class LadderDescentTest(unittest.TestCase):
 def setUp(self):
  self.ladders=[{'pos':[1,y,3],'state':'Block{minecraft:ladder}[facing=east,waterlogged=false]'}for y in (65,66,67)]
  self.model={'expected':self.ladders}
  self.rows=[{**r,'fluid':False,'block_entity':False}for r in self.ladders]
 def test_complete_dry_original_ladder_identifies_real_shape_margin(self):
  self.assertEqual({'bottom':65,'top':67,'facing':'east'},ladder_descent_geometry(self.model,self.rows,[1,3]))
 def test_missing_replaced_or_wet_ladder_is_rejected(self):
  for rows in (self.rows[:-1],[{**r,'fluid':True}for r in self.rows],[{**r,'state':'Block{minecraft:stone}'}for r in self.rows]):
   with self.subTest(rows=rows),self.assertRaises(RuntimeError):ladder_descent_geometry(self.model,rows,[1,3])
 def test_discontinuous_original_column_is_rejected(self):
  with self.assertRaises(RuntimeError):ladder_descent_geometry({'expected':self.ladders[::2]},self.rows,[1,3])
 def test_closed_hatch_or_low_ceiling_cannot_be_claimed_air(self):
  for y,state in ((68,'Block{minecraft:oak_trapdoor}[open=false,powered=false]'),(69,'Block{minecraft:stone}')):
   with self.subTest(y=y),self.assertRaises(RuntimeError):
    ladder_descent_geometry(self.model,self.rows+[{'pos':[1,y,3],'state':state,'fluid':False}],[1,3])
 def test_open_dry_hatch_is_preserved(self):
  rows=self.rows+[{'pos':[1,68,3],'state':'Block{minecraft:oak_trapdoor}[open=true,powered=false]','fluid':False}]
  self.assertEqual(65,ladder_descent_geometry(self.model,rows,[1,3])['bottom'])

if __name__=='__main__':unittest.main()
