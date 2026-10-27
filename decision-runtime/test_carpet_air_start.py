import unittest
from material_jobs.local_air_path import plan
from material_jobs.protocol import JobBlocked

class CarpetAirStartTest(unittest.TestCase):
 def row(self):return dict(pos=[0,64,0],state='Block{minecraft:light_gray_carpet}',solid=False,passable=False,fluid=False,block_entity=False)
 def test_feet_above_known_thin_carpet_begin_above_its_voxel(self):
  result=plan([self.row()],[.5,64.6425,.5],[2.5,65.1,.5],[-1,63,-1],[4,69,2],foot_offset=.1)
  self.assertEqual(result[0],[.5,65.1,.5])
 def test_below_surface_or_unknown_carpet_never_authorizes_escape(self):
  for name,height in [('light_gray_carpet',64.02),('pale_moss_carpet',64.6425)]:
   row=self.row();row['state']='Block{minecraft:'+name+'}'
   with self.assertRaises(JobBlocked):plan([row],[.5,height,.5],[2.5,65.1,.5],[-1,63,-1],[4,69,2],foot_offset=.1)

if __name__=='__main__':unittest.main()
