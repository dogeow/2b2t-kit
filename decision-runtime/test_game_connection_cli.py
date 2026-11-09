import unittest
import tempfile,json
from pathlib import Path
from unittest.mock import patch
from game_connection_cli import pending_screen,connection_screen_seen,connect

class ConnectionObservationTests(unittest.TestCase):
    def test_manual_reentry_hold_prevents_a_new_connection_even_after_native_health_ack(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d)/'automation';root.mkdir()
            (root/'assistant-control-hold.json').write_text(json.dumps({'active':True}))
            state={'client_connection_protocol':1,'connected':False,'screen':'DisconnectedScreen',
                   'account_name':'likunyan','world_session':'w','control_revision':1,'safety_hold':{'active':False}}
            with patch('game_connection_cli.read_fresh',return_value=state):
                with self.assertRaisesRegex(RuntimeError,'offline Kit work'):
                    connect(root,'simpcraft.com','likunyan',Path(d)/'attempt')
            self.assertFalse((root/'request.json').exists())
    def test_pre_gui_title_sample_is_not_a_connection_failure(self):
        self.assertTrue(pending_screen('TitleScreen',False,.1))
        self.assertTrue(pending_screen('ConnectScreen',False,3))
        self.assertTrue(pending_screen('DisconnectedScreen',False,.1))
    def test_return_to_title_or_unrelated_screen_does_not_restart_connection(self):
        self.assertTrue(pending_screen('TitleScreen',True,.1))
        self.assertTrue(pending_screen('TitleScreen',False,2.1))
        self.assertFalse(pending_screen('CodeOfConductScreen',False,.1))
        self.assertTrue(pending_screen('DisconnectedScreen',True,.1))
        self.assertTrue(pending_screen('DisconnectedScreen',False,2.1))
    def test_repeated_original_disconnect_frame_keeps_start_grace(self):
        seen=False
        for elapsed in (.05,.3,.8):
            self.assertTrue(pending_screen('DisconnectedScreen',seen,elapsed))
            seen=connection_screen_seen('DisconnectedScreen',seen)
        self.assertFalse(seen)
        seen=connection_screen_seen('ConnectScreen',seen)
        self.assertTrue(seen)
        self.assertTrue(pending_screen('DisconnectedScreen',seen,1.2))

class DelayedConnectionTests(unittest.TestCase):
    def test_transient_disconnect_after_connecting_is_one_request(self):
        from itertools import count
        from kit_runtime.journal import write_json as real_write
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'automation';root.mkdir();output=Path(tmp)/'out'
            base={'client_connection_protocol':1,'connected':False,'screen':'DisconnectedScreen','account_name':'likunyan','world_session':'old','control_revision':1,'safety_hold':{'active':False}}
            connecting={**base,'screen':'ConnectScreen'}
            online={**base,'connected':True,'screen':'','server':'simpcraft.com','player_name':'likunyan','world_session':'new','game_version':'v','kit_version':'k','runtime_version':'r'}
            states=iter([base]+[base]*6+[connecting,base,online]);ticks=count();sent=[]
            def write(path,value):
                real_write(path,value)
                if Path(path)==root/'request.json':
                    sent.append(value);real_write(root/('reply-'+value['id']+'.json'),{'id':value['id'],'phase':'done'})
            with patch('game_connection_cli.require_unlocked'),patch('game_connection_cli.read_fresh',side_effect=lambda *a,**kw:next(states)),patch('game_connection_cli.write_json',side_effect=write),patch('game_connection_cli.time.monotonic',side_effect=lambda:next(ticks)),patch('game_connection_cli.time.sleep'):
                result=connect(root,'simpcraft.com','likunyan',output,seconds=60)
            self.assertEqual(result['world_session'],'new');self.assertEqual(len(sent),1)
            self.assertFalse(json.loads((output/'result.json').read_text())['request_replayed'])

    def test_disconnect_until_deadline_never_retries(self):
        from itertools import count
        from kit_runtime.journal import write_json as real_write
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'automation';root.mkdir();output=Path(tmp)/'out';sent=[];ticks=count()
            base={'client_connection_protocol':1,'connected':False,'screen':'DisconnectedScreen','account_name':'likunyan','world_session':'old','control_revision':1,'safety_hold':{'active':False}}
            def write(path,value):
                real_write(path,value)
                if Path(path)==root/'request.json':
                    sent.append(value);real_write(root/('reply-'+value['id']+'.json'),{'id':value['id'],'phase':'done'})
            with patch('game_connection_cli.require_unlocked'),patch('game_connection_cli.read_fresh',return_value=base),patch('game_connection_cli.write_json',side_effect=write),patch('game_connection_cli.time.monotonic',side_effect=lambda:next(ticks)),patch('game_connection_cli.time.sleep'):
                with self.assertRaisesRegex(RuntimeError,'observation expired'):
                    connect(root,'simpcraft.com','likunyan',output,seconds=15)
            self.assertEqual(len(sent),1);self.assertFalse((output/'result.json').exists())
