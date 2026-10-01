import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import kit_cli
from potato_farm_cli import journal_directory, main

class FarmCliTest(unittest.TestCase):
    def state(self,world='w'):
        return {'server':'SIMPCraft.com:25565','dimension':'minecraft:overworld','world_session':world}
    def request(self):return {'authorized':True,'center':[1,63,2],'radius':2}
    def test_same_farm_cannot_change_directory_to_skip_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'proof'
            a,path=journal_directory(root,self.state(),self.request(),out)
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{"pending":{"operation":"plant"}}')
            with self.assertRaisesRegex(RuntimeError,'changing output'):
                journal_directory(root,self.state(),self.request(),root/'new')
            self.assertTrue(path.exists())
            self.assertEqual(a,journal_directory(root,self.state(),self.request())[0])
    def test_new_world_cannot_adopt_original_journal(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);journal_directory(root,self.state(),self.request())
            with self.assertRaisesRegex(RuntimeError,'another scope/world'):
                journal_directory(root,self.state('new'),self.request())
    def test_parser_forwards_exact_center_and_no_move(self):
        with patch('potato_farm_cli.execute',return_value={'phase':'done'}) as execute,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--center','1','63','2','--max-cells','4','--no-move']),0)
        self.assertEqual(execute.call_args.args[1:],([1,63,2],2,4,None,True))
    def test_kit_topic_is_a_direct_api_delegate(self):
        with patch('potato_farm_cli.main',return_value=0) as delegated:
            self.assertEqual(kit_cli.main(['--game-dir','/test','farm','plant','--center','1','63','2','--no-move']),0)
        self.assertEqual(delegated.call_args.args[0],['--game-dir','/test','--center','1','63','2','--radius','2','--max-cells','24','--no-move'])
    def test_invalid_radius_never_calls_game(self):
        with patch('potato_farm_cli.execute') as execute,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):main(['--center','1','63','2','--radius','3'])
        execute.assert_not_called()

class FarmFinishTest(unittest.TestCase):
    def setup_client(self, root):
        from unittest.mock import Mock
        c = Mock(); c.world='w';c.rev=2;c.task='t';c.heartbeat.id='l';c.out=root;c.job_progress=None
        state={'connected':True,'world_session':'w','control_revision':2,'manual_movement':False,
               'screen':'','health':20,'food':20,'recent_hurt_at':0,'guard_armed':True,'guard_busy':False,
               'pos':[1,140,2],'supervision_lease':{'id':'l','job_session':'t','kind':'materials'}}
        c.status.return_value=state
        return c,state
    def test_injury_and_unknown_steps_never_run_ordinary_finish_or_navigation(self):
        from potato_farm_cli import finish_or_yield
        import json
        for injury,pending in [(True,None),(False,{'operation':'plant'})]:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);j=root/'j.json';j.write_text(json.dumps({'pending':pending}))
                c,state=self.setup_client(root)
                if injury:state['health']=19;state['recent_hurt_at']=1
                finish_or_yield(c,{'phase':'done'},j,0,140,False)
                c.finish.assert_not_called();c.checked.assert_not_called()
                c.request.assert_called_once_with('material_job_pause',release=False)
                c.heartbeat.close.assert_called_once()
    def test_success_without_native_park_proof_is_not_success(self):
        from potato_farm_cli import finish_or_yield
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);j=root/'j.json';j.write_text('{"pending":null}')
            c,state=self.setup_client(root)
            with self.assertRaisesRegex(RuntimeError,'parking was not confirmed'):
                finish_or_yield(c,{'phase':'done'},j,0,140,True)
            c.heartbeat.close.assert_called_once()

class FarmFactoryTest(unittest.TestCase):
    def test_execute_reaches_client_factory_with_a_path_before_any_game_action(self):
        from potato_farm_cli import execute
        state={'server':'simpcraft.com','dimension':'minecraft:overworld','world_session':'w',
               'connected':True,'screen':'','manual_movement':False,'health':20,'food':20,'pos':[1.5,140,2.5]}
        with tempfile.TemporaryDirectory() as d,patch('potato_farm_cli.read_fresh',return_value=state),patch('potato_farm_cli.require_unlocked'),patch('potato_farm_cli.MaterialClient',side_effect=RuntimeError('factory intercepted')) as factory:
            with self.assertRaisesRegex(RuntimeError,'factory intercepted'):
                execute(Path(d),[1,63,2],2,24,no_move=True)
            self.assertIsInstance(factory.call_args.args[1],Path)
            self.assertTrue(factory.call_args.args[1].name.startswith('control-'))
