import copy
import unittest
from unittest.mock import patch
from material_client import Client,Handoff
from native_recovery_pause import waiting_for_residual_fire


def state():
    return dict(connected=True,world_session='w',control_revision=3,dimension='minecraft:overworld',screen='',
        manual_movement=False,health=19.64,guard_armed=True,guard_pve_only=True,
        safe_residual_fire_wait_protocol=1,residual_fire_wait=dict(active=True,phase='waiting_for_fire'))


class NativeRecoveryPauseTests(unittest.TestCase):
    def client(self,frames):
        c=Client.__new__(Client);c.world='w';c.rev=3;c.dimension='minecraft:overworld'
        iterator=iter(frames);c.raw=lambda **kw:copy.deepcopy(next(iterator));return c
    def test_only_the_typed_native_pause_allows_waiting(self):
        self.assertTrue(waiting_for_residual_fire(state()))
        for change in [dict(health=17.9),dict(manual_movement=True),dict(screen='ChatScreen'),
                       dict(safety_hold=dict(active=True)),dict(guard_armed=False),
                       dict(residual_fire_wait=dict(active='true',phase='waiting_for_fire'))]:
            self.assertFalse(waiting_for_residual_fire({**state(),**change}))
    def test_status_waits_for_recovery_without_dispatching_or_restarting_work(self):
        ready={**state(),'health':20,'residual_fire_wait':dict(active=False,phase='idle')}
        c=self.client([state(),ready])
        with patch('material_client.time.sleep')as sleep,patch('material_client.time.monotonic',side_effect=[0,1]):
            self.assertEqual(20,c.status()['health'])
        sleep.assert_called_once();self.assertEqual(1,c.native_recovery_pause_seconds)
    def test_cancellation_can_read_during_the_pause(self):
        c=self.client([state()])
        with patch('material_client.time.sleep')as sleep:
            self.assertEqual(19.64,c.status(wait_interface=False)['health'])
        sleep.assert_not_called()
    def test_manual_takeover_is_not_waited_out(self):
        c=self.client([{**state(),'manual_movement':True}])
        with self.assertRaises(Handoff):c.status()
    def test_stale_native_pause_has_a_bound(self):
        c=self.client([state(),state()])
        with patch('material_client.time.sleep'),patch('material_client.time.monotonic',side_effect=[0,26]),\
             self.assertRaisesRegex(RuntimeError,'exceeded its bound'):
            c.status()
    def test_new_user_printer_mode_yields_but_still_allows_owned_cancellation(self):
        changed={**state(),'professional_printer':dict(external_mode_revision=4)}
        c=self.client([changed,changed]);c.printer_handoff_revision=3
        with self.assertRaisesRegex(Handoff,'printer mode'):c.status()
        self.assertEqual(19.64,c.status(wait_interface=False)['health'])


if __name__=='__main__':unittest.main()
