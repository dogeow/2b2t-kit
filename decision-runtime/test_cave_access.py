import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from material_jobs.cave_access import plan,run
from material_jobs.dry_hover_harvest import harvest_context

def row(p,name='stone',**kw):return {'pos':p,'state':'Block{minecraft:'+name+'}','fluid':False,'block_entity':False,'solid':True,**kw}

class CaveAccessTest(unittest.TestCase):
    def test_pickup_outside_survey_requests_a_new_window_without_more_mining(self):
        state={'health':20,'food':20,'flight':True,'guard_armed':True,'guard_pve_only':True,
               'pos':[.5,-1.2,.5],'inventory':[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(36)]}
        c=SimpleNamespace(world='w',last='scan',status=lambda:state)
        region={'authorized':True,'source':'natural_survey','min':[-3,1,-3],'max':[3,8,3]}
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.cave_access._scan',return_value=[]),\
             patch('material_jobs.cave_access.harvest',return_value={'initial':0,'verified_count':0,'receipts':[]}),\
             patch('material_jobs.cave_access.plan')as planner:
            result=run(c,{},region,64,d,lambda:None)
        self.assertEqual('WAIT_SURVEY_REFRAME',result['code']);planner.assert_not_called();self.assertIsNone(result['pending'])
    def world(self):
        return [row([0,4,0],'dripstone_block')]+[row([1,y,z])for y in range(1,9)for z in range(-3,4)]
    def test_two_cell_wall_can_reach_real_material_without_changing_its_floor(self):
        result=plan(self.world(),[-3,1,-3],[4,8,3],[3.5,4.2,.5],budget=2)
        self.assertIsNotNone(result);self.assertEqual(2,len(result['opening']))
        self.assertEqual([0,4,0],result['target'])
        self.assertTrue(all(r['pos'][1]>=3 for r in result['opening']))
    def test_budget_does_not_authorize_a_larger_excavation(self):
        self.assertIsNone(plan(self.world(),[-3,1,-3],[4,8,3],[3.5,4.2,.5],budget=1))
    def test_protected_target_does_not_drive_any_extra_wall_excavation(self):
        self.assertIsNone(plan(self.world(),[-3,1,-3],[4,8,3],[3.5,4.2,.5],budget=8,protected={(0,4,0)}))
    def test_quarantined_old_wall_mining_cells_cannot_be_reused_as_an_access_route(self):
        walls={tuple(r['pos'])for r in self.world()if r['pos'][0]==1}
        self.assertIsNone(plan(self.world(),[-3,1,-3],[4,8,3],[3.5,4.2,.5],budget=32,protected=walls))
    def test_liquid_or_container_in_the_wall_is_never_opened(self):
        for name,kw in [('water',{'fluid':True}),('chest',{'block_entity':True}),('infested_stone',{})]:
            rows=[row(r['pos'],name,**kw)if r['pos'][0]==1 else r for r in self.world()]
            self.assertIsNone(plan(rows,[-3,1,-3],[4,8,3],[3.5,4.2,.5],budget=8))
    def test_attached_root_support_is_not_removed_for_access(self):
        cone=row([1,3,0],'pointed_dripstone',solid=False)
        cone['state']+='[vertical_direction=down,waterlogged=false,thickness=tip]'
        rows=[r for r in self.world()if r['pos']!=[1,3,0]]+[cone]
        result=plan(rows,[-3,1,-3],[4,8,3],[3.5,4.2,.5],budget=4)
        if result:self.assertFalse(any(r['pos']==[1,4,0]for r in result['opening']))

if __name__=='__main__':unittest.main()
