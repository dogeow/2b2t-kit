import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from farm_preparation import journal_directory, _scope
from potato_farm_cli import execute

class SharedFieldLockTest(unittest.TestCase):
    def state(self):
        return {'server':'simpcraft.com','dimension':'minecraft:overworld','world_session':'w',
                'connected':True,'screen':'','manual_movement':False,'health':20,'food':20,'pos':[1.5,140,2.5]}
    def test_prepare_pending_blocks_both_crops_before_client_creation(self):
        with tempfile.TemporaryDirectory() as d:
            game=Path(d);root=game/'config/twob2tkit/automation';state=self.state()
            request={'authorized':True,'center':[1,63,2],'radius':2}
            directory,journal=journal_directory(root,state,request)
            journal.write_text(json.dumps({'scope':_scope(state,request),'world_session':'w','pending':{'op':'bucket_place'}}))
            for crop in ['potato','wheat']:
                with self.subTest(crop=crop),patch('potato_farm_cli.read_fresh',return_value=state),patch('potato_farm_cli.require_unlocked'),patch('potato_farm_cli.MaterialClient') as factory:
                    with self.assertRaisesRegex(RuntimeError,'unresolved'):
                        execute(game,[1,63,2],2,24,crop=crop)
                    factory.assert_not_called()
    def test_plant_keeps_shared_lock_until_inner_execution_returns(self):
        import fcntl
        with tempfile.TemporaryDirectory() as d:
            game=Path(d);root=game/'config/twob2tkit/automation';state=self.state()
            def inner(*args,**kwargs):
                files=list((root/'farm-preparation/locks').glob('*.lock'));self.assertEqual(1,len(files))
                with files[0].open('r') as stream:
                    with self.assertRaises(BlockingIOError):fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                return {'phase':'done'}
            with patch('potato_farm_cli.read_fresh',return_value=state),patch('potato_farm_cli.require_unlocked'),patch('potato_farm_cli._execute_locked',side_effect=inner):
                self.assertEqual('done',execute(game,[1,63,2],2,24)['phase'])
            with next((root/'farm-preparation/locks').glob('*.lock')).open('r') as stream:
                fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(stream,fcntl.LOCK_UN)

class SettledWaitFinishTest(unittest.TestCase):
    def test_full_health_read_only_wait_can_park_but_pending_or_injury_cannot(self):
        from potato_farm_cli import normal_finish_allowed
        from unittest.mock import Mock
        c=Mock();c.world='w';c.rev=3;c.task='t';c.heartbeat.id='l'
        state={'connected':True,'world_session':'w','control_revision':3,'manual_movement':False,
               'screen':'','health':20,'food':20,'recent_hurt_at':0,'guard_armed':True,'guard_busy':False,
               'supervision_lease':{'id':'l','job_session':'t','kind':'materials'}}
        result={'phase':'waiting','code':'WAIT_SCAN'};book={'pending':None}
        self.assertFalse(normal_finish_allowed(c,state,result,book,0))
        self.assertTrue(normal_finish_allowed(c,state,result,book,0,True))
        self.assertFalse(normal_finish_allowed(c,state,{**result,'code':'WAIT_RECONCILE'},book,0,True))
        self.assertFalse(normal_finish_allowed(c,state,result,{'pending':{'op':'bucket_place'}},0,True))
        self.assertFalse(normal_finish_allowed(c,state,result,{'cleanup_pending':{'op':'material_job_pause'}},0,True))
        self.assertFalse(normal_finish_allowed(c,{**state,'health':19.5},result,book,0,True))

class ReadOnlyRecoveryTest(unittest.TestCase):
    def test_only_confirmed_read_only_pause_can_adopt_new_session_and_original_bytes_remain(self):
        from farm_preparation_cli import recover_read_only_session
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state={'server':'example.com','dimension':'minecraft:overworld','world_session':'old'}
            request={'authorized':True,'center':[1,63,2],'radius':2,'water_source':None}
            directory,journal=journal_directory(root,state,request)
            book={'schema':1,'scope':_scope(state,request),'world_session':'old','water_source':None,
                  'pending':None,'actions':[{'op':'acquire_control'},{'op':'material_job_pause','receipt':{'phase':'done','id':'original-pause','world_session':'old'}}]}
            journal.write_text(json.dumps(book));original=journal.read_bytes()
            recover_read_only_session(root,{**state,'world_session':'new'},request)
            fresh=json.loads(journal.read_text());self.assertEqual('new',fresh['world_session']);self.assertEqual([],fresh['actions'])
            self.assertEqual(original,(Path(fresh['recovery']['archive'])/'journal.json').read_bytes())
            self.assertEqual(0,fresh['recovery']['world_actions_replayed'])
    def test_unknown_or_world_mutation_cannot_be_archived_by_read_only_recovery(self):
        from farm_preparation_cli import recover_read_only_session
        for unknown,world_op in [(True,False),(False,True)]:
            with self.subTest(unknown=unknown),tempfile.TemporaryDirectory() as d:
                root=Path(d);state={'server':'example.com','dimension':'minecraft:overworld','world_session':'old'}
                request={'authorized':True,'center':[1,63,2],'radius':2,'water_source':None}
                directory,journal=journal_directory(root,state,request)
                book={'schema':1,'scope':_scope(state,request),'world_session':'old','pending':{'op':'bucket_place'} if unknown else None,
                      'actions':[{'op':'bucket_place' if world_op else 'acquire_control'},{'op':'material_job_pause','receipt':{'phase':'done','id':'pause','world_session':'old'}}]}
                journal.write_text(json.dumps(book));original=journal.read_bytes()
                with self.assertRaisesRegex(RuntimeError,'read-only'):
                    recover_read_only_session(root,{**state,'world_session':'new'},request)
                self.assertEqual(original,journal.read_bytes())

if __name__=='__main__':unittest.main()
