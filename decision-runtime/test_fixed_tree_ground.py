import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from material_jobs.fixed_tree_ground import prepare,ready
from material_jobs.protocol import JobBlocked

class FixedTreeGroundTests(unittest.TestCase):
    def test_hovering_at_exact_floor_height_is_not_a_grounded_native_start(self):
        self.assertFalse(ready({'on_ground':False,'flight':True,'pos':[.5,64,.5]}))
        self.assertFalse(ready({'on_ground':True,'flight':True}))
        self.assertTrue(ready({'on_ground':True,'flight':False}))
    def test_no_ground_walk_is_sent_from_a_higher_unknown_or_unsafe_pose(self):
        c=Mock();c.world='w';c.task='t';c.status.return_value={'world_session':'w','health':20,'guard_armed':True,'guard_pve_only':True,
            'supervision_lease':{'job_session':'t'},'pos':[.5,67.5,.5],'on_ground':False,'flight':True}
        with self.assertRaises(JobBlocked):prepare(c,lambda:None)
        c.checked.assert_not_called()
    def test_passable_dry_torch_is_preserved_and_ground_walk_is_confirmed(self):
        with tempfile.TemporaryDirectory() as d:
            class C:
                world='w';task='t';last=None;out=Path(d);ground=False;tick=0
                def status(self):
                    self.tick+=1
                    return {'world_session':'w','health':20,'guard_armed':True,'guard_pve_only':True,
                        'supervision_lease':{'job_session':'t'},'pos':[.5,64,.5],
                        'on_ground':self.ground,'flight':not self.ground,'time':self.tick}
                def checked(self,op,**kwargs):
                    self.last=op
                    if op=='scan':return {'scan_cells_read':3,'scan_total_cells':3,'blocks':[
                        {'pos':[0,63,0],'state':'Block{minecraft:grass_block}','solid':True,'fluid':False,'block_entity':False},
                        {'pos':[0,64,0],'state':'Block{minecraft:torch}','solid':False,'passable':True,'fluid':False,'block_entity':False}]}
                    self.assert_walk=op;self.ground=True;return {'phase':'done'}
            c=C()
            with patch('material_jobs.fixed_tree_ground.time.sleep'):
                result=prepare(c,lambda:None)
            self.assertTrue(ready(result));self.assertEqual('walk',c.assert_walk)
    def test_non_passable_or_wet_light_is_not_accepted(self):
        c=Mock();c.world='w';c.task='t';c.status.return_value={'world_session':'w','health':20,'guard_armed':True,'guard_pve_only':True,
            'supervision_lease':{'job_session':'t'},'pos':[.5,64,.5],'on_ground':False,'flight':True}
        c.checked.return_value={'scan_cells_read':3,'scan_total_cells':3,'blocks':[
            {'pos':[0,63,0],'state':'Block{minecraft:grass_block}','solid':True,'fluid':False,'block_entity':False},
            {'pos':[0,64,0],'state':'Block{minecraft:torch}','solid':False,'passable':True,'fluid':True,'block_entity':False}]}
        with self.assertRaises(JobBlocked):prepare(c,lambda:None)
        self.assertEqual(['scan'],[call.args[0] for call in c.checked.call_args_list])

if __name__=='__main__':unittest.main()
