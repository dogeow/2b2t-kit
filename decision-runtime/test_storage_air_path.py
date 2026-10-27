import math,unittest
from storage_air_path import flight_nodes
class StorageAirPathTests(unittest.TestCase):
 def test_recorded_plus_point05_braking_stays_inside_two_cell_corridor(self):
  pose=flight_nodes([[.5,66,.5]])[0]
  for drift in [-.05,.05]:
   feet=pose[1]+drift;self.assertGreater(feet,66);self.assertLess(feet+1.8,68)
 def test_only_collinear_vertical_nodes_compress_and_turns_remain(self):
  nodes=[[.5,y,.5]for y in range(90,65,-2)]+[[.5,66,1.5],[.5,65,1.5]];out=flight_nodes(nodes)
  self.assertLess(len(out),len(nodes));self.assertIn([.5,66.1,.5],out);self.assertIn([.5,66.1,1.5],out)
  for a,b in zip(out,out[1:]):
   self.assertLessEqual(sum(abs(x-y)>1e-7 for x,y in zip(a,b)),1)
   if a[0]==b[0]and a[2]==b[2]:self.assertLessEqual(abs(a[1]-b[1]),16)
 def test_compressed_vertical_path_crosses_exactly_the_same_voxels(self):
  nodes=[[.5,y,.5]for y in range(90,65,-2)]
  def cells(points):
   found=set()
   for a,b in zip(points,points[1:]):
    count=math.ceil(math.dist(a,b)*20)
    for n in range(count+1):found.add(tuple(math.floor(a[i]+(b[i]-a[i])*n/count)for i in range(3)))
   return found
  self.assertEqual(cells([[p[0],p[1]+.1,p[2]]for p in nodes]),cells(flight_nodes(nodes)))
if __name__=='__main__':unittest.main()
