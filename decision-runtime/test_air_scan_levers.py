import unittest
from types import SimpleNamespace
from material_jobs.navigation import _air_scan

class AirScanLeversTest(unittest.TestCase):
    def scan(self,row):
        c=SimpleNamespace(world='w',request=lambda *a,**k:dict(phase='done',world_session='w',blocks=[row]))
        return _air_scan(c,[0,64,0],[2,66,2])
    def test_verified_noncolliding_floor_and_wall_levers_remain_untouched(self):
        for face in ('floor','wall'):
            row=dict(pos=[1,64,1],state='Block{minecraft:lever}[face='+face+',facing=east,powered=true]',passable=True,fluid=False,block_entity=False)
            self.assertEqual(self.scan(row),[])
    def test_missing_or_conflicting_evidence_keeps_lever_as_obstacle(self):
        for key,value in [('passable',False),('fluid',True),('block_entity',True),('block_entity',None)]:
            row=dict(pos=[1,64,1],state='Block{minecraft:lever}',passable=True,fluid=False,block_entity=False);row[key]=value
            self.assertEqual(self.scan(row),[row])
    def test_hazards_are_not_allowed_by_passability_alone(self):
        for block in ('fire','water','sweet_berry_bush'):
            row=dict(pos=[1,64,1],state='Block{minecraft:'+block+'}',passable=True,fluid=False,block_entity=False)
            self.assertEqual(self.scan(row),[row])

if __name__=='__main__':unittest.main()
