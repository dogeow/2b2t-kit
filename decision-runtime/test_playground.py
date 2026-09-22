import unittest
from playground import marker_plan
from decisions import DecisionError

class MarkerTests(unittest.TestCase):
    def state(self):return {'connected':True,'server':'singleplayer','dimension':'minecraft:overworld','pos':[6.5,-60,9.5],'health':20,'screen':'','phase':'done','movement_keys':{}}
    def rows(self):
        rows=[{'pos':[x,-61,z],'state':'Block{minecraft:grass_block}[snowy=false]'} for x in range(5,12) for z in range(8,15)]
        special={(6,9):'white_wool',(10,9):'yellow_wool',(6,13):'blue_wool'}
        for row in rows:
            x,_,z=row['pos']
            if (x,z) in special:row['state']='Block{minecraft:'+special[x,z]+'}'
        return rows
    def test_plan_uses_current_position_at_either_marker(self):
        for pos in ([6.5,-60,9.5],[10.4,-60,9.5],[6.7,-60,13.3]):
            plan=marker_plan('走到黄色标记',{**self.state(),'pos':pos},self.rows())
            self.assertEqual(pos,plan['origin']);self.assertIn('yellow',plan['choices']);self.assertIn('wait',plan['choices'])
    def test_obstacle_hole_or_wrong_marker_prevents_movement(self):
        cases=[self.rows()[1:],self.rows()+[{'pos':[8,-60,10],'state':'Block{minecraft:stone}'}]]
        wrong=self.rows()
        for row in wrong:
            if row['pos']==[10,-61,9]:row['state']='Block{minecraft:grass_block}[snowy=false]'
        cases.append(wrong)
        for rows in cases:
            with self.assertRaises(DecisionError):marker_plan('走到黄色标记',self.state(),rows)
    def test_other_world_or_flying_cannot_use_this_demo(self):
        for change in ({'server':'simpcraft.com'},{'pos':[6.5,-55,9.5]},{'pos':[200,-60,200]}):
            with self.assertRaises(DecisionError):marker_plan('走到黄色标记',{**self.state(),**change},self.rows())
    def test_unreachable_target_is_not_offered_to_the_model(self):
        p=marker_plan('走到黄色标记',{**self.state(),'pos':[5.3,-60,14.6]},self.rows())
        self.assertNotIn('yellow',p['choices']);self.assertIn('blue',p['choices'])
if __name__=='__main__':unittest.main()
