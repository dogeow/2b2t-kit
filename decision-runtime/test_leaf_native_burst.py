import copy,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from material_jobs.leaf_native_burst import execute

ROW={'pos':[0,1,0],'state':'Block{minecraft:oak_leaves}[distance=2,persistent=false,waterlogged=false]'}
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.c=SimpleNamespace(root=self.root,task='task',world='world',heartbeat=SimpleNamespace(id='lease'))
        self.s={'world_session':'world','control_revision':4,'server':'example.org','dimension':'minecraft:overworld',
                'player_uuid':'player','game_interaction':{'interaction_serial':8},'supervision_lease':{'job_session':'task','id':'lease','world_session':'world','revision':4}}
        self.intents=[];self.change=lambda r:r
    def checkpoint(self):
        p=self.root/'leaf-shear-request.json'
        if p.exists():
            request=json.loads(p.read_text());result={k:request[k]for k in('id','world_session','task_session','lease_id','expected_revision')}
            result.update(protocol=1,phase='done',execution='native_continuous_shears_v1',
                confirmation='vanilla_prediction_retired_and_live_block_observation',attempted=1,
                removed=[{'pos':[0,1,0],'item':'minecraft:oak_leaves','state':'Block{minecraft:air}'}],remaining=[],pending=[])
            (self.root/'leaf-shear-state.json').write_text(json.dumps(self.change(result)))
        return self.s
    def run_burst(self):return execute(self.c,[ROW],self.root/'runs',self.checkpoint,self.intents.append)
    def test_one_burst_uses_one_request_and_retains_exact_identity(self):
        result=self.run_burst();self.assertEqual(len(self.intents),1);self.assertEqual(result['id'],self.intents[0]['id']);self.assertIsNone(self.c.native_leaf_pending)
    def test_unsettled_prediction_is_never_replayed(self):
        self.change=lambda r:{**r,'pending':[{'pos':[0,1,0]}]}
        with self.assertRaises(RuntimeError):self.run_burst()
        self.assertEqual(len(self.intents),1);self.assertIsNotNone(self.c.native_leaf_pending)
    def test_shears_reserve_stop_is_terminal_but_keeps_only_server_removed_credit(self):
        self.change=lambda r:{**r,'phase':'stopped','reason':'shears_changed_or_exhausted','attempted':1}
        result=self.run_burst();self.assertEqual(result['phase'],'stopped');self.assertEqual(result['removed'][0]['pos'],[0,1,0])
        self.assertIsNone(self.c.native_leaf_pending)
    def test_wrong_world_receipt_preserves_original_request(self):
        self.change=lambda r:{**r,'world_session':'different'}
        with self.assertRaises(RuntimeError):self.run_burst()
        self.assertIsNotNone(self.c.native_leaf_pending)
    def test_duplicate_removed_targets_are_rejected(self):
        self.change=lambda r:{**r,'removed':r['removed']*2}
        with self.assertRaises(RuntimeError):self.run_burst()
    def test_foreign_or_busy_lease_does_not_publish(self):
        self.s['supervision_lease']['id']='other'
        with self.assertRaises(RuntimeError):self.run_burst()
        self.assertFalse((self.root/'leaf-shear-request.json').exists())
    def test_remaining_leaf_receipt_can_be_resurveyed_without_completion_credit(self):
        self.change=lambda r:{**r,'attempted':0,'removed':[],'remaining':[{'pos':[0,1,0],'item':'minecraft:oak_leaves','state':ROW['state']}]}
        result=self.run_burst();self.assertEqual(result['removed'],[]);self.assertEqual(len(result['remaining']),1)

if __name__=='__main__':unittest.main()
