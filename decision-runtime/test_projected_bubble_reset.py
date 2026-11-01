import unittest
from projected_bubble_reset import plan,mined,resume_plugs,mining_preflight_refused,inert_floor,SOURCE,BUBBLE,MAGMA,FLOW
class ResetPlanTest(unittest.TestCase):
    def setUp(self):
        self.targets=[[x,62,z]for x in range(3)for z in range(2)]
        self.goals={tuple(p):'Block{minecraft:water}[level=1]'for p in self.targets}
        self.rows={tuple(p):BUBBLE for p in self.targets}
        for x,y,z in self.targets:self.goals[x,y-1,z]=self.rows[x,y-1,z]=MAGMA
    def test_complete_connected_group(self):self.assertEqual(len(plan(self.targets,self.goals,self.rows)),6)
    def test_original_source_is_protected(self):
        self.goals[0,62,0]='Block{minecraft:water}[level=0]'
        with self.assertRaises(ValueError):plan(self.targets,self.goals,self.rows)
    def test_original_magma_is_preserved(self):
        self.rows[0,61,0]='Block{minecraft:dirt}'
        with self.assertRaises(ValueError):plan(self.targets,self.goals,self.rows)
    def test_omitted_adjacent_source(self):
        with self.assertRaises(ValueError):plan(self.targets[:-1],self.goals,self.rows)
    def test_disconnected_group(self):
        with self.assertRaises(ValueError):plan([self.targets[0],self.targets[-1]],self.goals,self.rows)
    def test_duplicate_and_noninteger(self):
        for targets in [[self.targets[0]]*2,[[0,62.0,0]]]:
            with self.assertRaises(ValueError):plan(targets,self.goals,self.rows)
    def test_plain_flow_is_not_destroyed(self):
        self.rows[0,62,0]=next(iter(FLOW))
        with self.assertRaises(ValueError):plan(self.targets,self.goals,self.rows)
    def test_resume_preserves_confirmed_plug_without_second_placement(self):
        p=self.targets[0];self.rows[tuple(p)]='Block{minecraft:dirt}'
        self.assertEqual(len(plan(self.targets,self.goals,self.rows,confirmed_plugs=[p])),6)
        with self.assertRaises(ValueError):plan(self.targets,self.goals,self.rows)
    def test_resume_refuses_pending_or_mined_stage(self):
        original={'pending':None,'complete':False,'targets':self.targets,'removed_plugs':[],
                  'automatic_retry_allowed':False,'plugs':{'0,62,0':self.targets[0]}}
        self.assertEqual(len(resume_plugs(original,self.targets)),1)
        for patch in [{'pending':{'kind':'input'}},{'removed_plugs':[self.targets[0]]},{'complete':True},
                      {'targets':self.targets[:-1]},{'plugs':{'wrong-key':self.targets[0]}}]:
            with self.assertRaises(ValueError):resume_plugs({**original,**patch},self.targets)
    def test_resume_cannot_remove_an_original_source(self):
        p=self.targets[0];self.rows[tuple(p)]='Block{minecraft:dirt}';self.goals[tuple(p)]='Block{minecraft:water}[level=0]'
        with self.assertRaises(ValueError):plan(self.targets,self.goals,self.rows,confirmed_plugs=[p])
    def test_before_task_refusal_does_not_clear_real_mining(self):
        r={'phase':'error','detail':'Six loaded pinned neighbors with only water fluids required'}
        self.assertTrue(mining_preflight_refused(r))
        for patch in [{'phase':'waiting'},{'native_sequence':-1},{'mining_target':[0,62,0]},
                      {'outcome_pending':True},{'server_confirmed':False},{'detail':'different error'}]:
            self.assertFalse(mining_preflight_refused({**r,**patch}))
    def test_explicit_plain_source_group_preserves_stair_shape(self):
        dry='Block{minecraft:cobblestone_stairs}[facing=west,half=bottom,shape=straight,waterlogged=false]'
        for p in self.targets:
            x,y,z=p;self.rows[x,y,z]=SOURCE;self.goals[x,y-1,z]=dry
            self.rows[x,y-1,z]=dry.replace('waterlogged=false','waterlogged=true')
        self.assertEqual(len(plan(self.targets,self.goals,self.rows,allow_plain_sources=True)),6)
        with self.assertRaises(ValueError):plan(self.targets,self.goals,self.rows)
    def test_plain_sources_do_not_include_original_source(self):
        with self.assertRaises(ValueError):plan(self.targets,self.goals,self.rows,allow_plain_sources='yes')
        self.rows[0,62,0]=SOURCE;self.goals[0,62,0]=SOURCE
        with self.assertRaises(ValueError):plan(self.targets,self.goals,self.rows,allow_plain_sources=True)
    def test_extra_plain_source_may_not_be_omitted(self):
        self.rows[3,62,0]=SOURCE;self.goals[3,62,0]=next(iter(FLOW));self.goals[3,61,0]=self.rows[3,61,0]=MAGMA
        with self.assertRaises(ValueError):plan(self.targets,self.goals,self.rows,allow_plain_sources=True)
    def test_inert_floor_rejects_container_and_shape_change(self):
        dry='Block{minecraft:cobblestone_stairs}[facing=west,half=bottom,shape=straight,waterlogged=false]'
        self.assertFalse(inert_floor(dry.replace('west','east'),dry))
        self.assertFalse(inert_floor('Block{minecraft:chest}','Block{minecraft:chest}'))
    def test_native_mining_requires_matching_ack(self):
        self.assertTrue(mined({'phase':'done','server_confirmed':True,'native_sequence':8,'server_ack_sequence':8}))
        for r in [{'phase':'done'},{'phase':'done','server_confirmed':True,'native_sequence':8,'server_ack_sequence':7},
                  {'phase':'done','server_confirmed':True,'native_sequence':True,'server_ack_sequence':True}]:self.assertFalse(mined(r))
if __name__=='__main__':unittest.main()
