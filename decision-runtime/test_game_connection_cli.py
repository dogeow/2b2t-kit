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
        self.assertFalse(pending_screen('TitleScreen',True,.1))
        self.assertFalse(pending_screen('TitleScreen',False,2.1))
        self.assertFalse(pending_screen('CodeOfConductScreen',False,.1))
        self.assertFalse(pending_screen('DisconnectedScreen',True,.1))
        self.assertFalse(pending_screen('DisconnectedScreen',False,2.1))
    def test_repeated_original_disconnect_frame_keeps_start_grace(self):
        seen=False
        for elapsed in (.05,.3,.8):
            self.assertTrue(pending_screen('DisconnectedScreen',seen,elapsed))
            seen=connection_screen_seen('DisconnectedScreen',seen)
        self.assertFalse(seen)
        seen=connection_screen_seen('ConnectScreen',seen)
        self.assertTrue(seen)
        self.assertFalse(pending_screen('DisconnectedScreen',seen,1.2))
