import unittest
from game_connection_cli import pending_screen,connection_screen_seen

class ConnectionObservationTests(unittest.TestCase):
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
