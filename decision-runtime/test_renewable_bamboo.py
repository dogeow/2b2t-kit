import unittest
from material_jobs.renewable_bamboo import columns,pickup_side_poses
class BambooColumnsTest(unittest.TestCase):
    def test_only_upper_target_with_confirmed_live_base_and_dry_support(self):
        def r(y,item,**k):return {'pos':[0,y,0],'state':'Block{minecraft:'+item+'}','solid':False,'fluid':False,**k}
        rows=[r(63,'grass_block',solid=True)]+[r(y,'bamboo')for y in range(64,70)]
        self.assertEqual([{'base':[0,64,0],'target':[0,65,0],'height':6}],columns(rows))
        self.assertEqual([],columns(rows[1:]))
        self.assertEqual([],columns(rows[:2]))
    def test_side_work_pose_stays_inside_clear_cell_and_reaches_far_offset_drops(self):
        rows=[{'pos':[1,85,1],'state':'Block{minecraft:bamboo}'}]
        poses=pickup_side_poses(rows,[1,85,1],[.5,85.1,1.5],[-3,83,-3],[5,90,5])
        west=next(p for face,p in poses if face=='west')
        self.assertAlmostEqual(.68,west[0]);self.assertLess(west[0]+.31,1)
        self.assertLess(1.875-west[0],1.3)
