import unittest
from projection_transit import stairwells
class TransitTest(unittest.TestCase):
 def row(self,x,y,z):return {'pos':[x,y,z],'state':'Block{minecraft:oak_stairs}[facing=north,half=bottom,shape=straight,waterlogged=false]'}
 def test_requires_a_contiguous_rising_run_not_single_furniture(self):
  rows=[self.row(0,y,5-y) for y in range(5)]+[self.row(4,1,1)]
  runs=stairwells(rows);self.assertEqual(len(runs),1);self.assertEqual(len(runs[0]),5);self.assertEqual(runs[0][-1]['pos'],[0,4,1])
 def test_gap_or_water_is_not_a_stairwell(self):
  self.assertEqual(stairwells([self.row(0,0,5),self.row(0,1,4),self.row(0,3,2)]),[])
  rows=[self.row(0,y,5-y) for y in range(3)];rows[1]['state']=rows[1]['state'].replace('waterlogged=false','waterlogged=true');self.assertEqual(stairwells(rows),[])
if __name__=='__main__':unittest.main()
