import unittest
from health_exit_watch import ExitWitness


def state(health,**kwargs):
    return {'connected':True,'world_session':'w','health':health,'time':100,
            'supervision_lease':{'kind':'materials','world_session':'w'},**kwargs}


class HealthExitWatchTest(unittest.TestCase):
    def test_minor_live_injury_does_not_stop_or_log_out(self):
        w=ExitWitness('w');self.assertIsNone(w.observe(state(20)));self.assertIsNone(w.observe(state(19)))
    def test_recovered_injury_does_not_misclassify_a_healthy_exit(self):
        w=ExitWitness('w');w.observe(state(20));w.observe(state(19));w.observe(state(20))
        self.assertIsNone(w.observe({'connected':False}))
    def test_actual_exit_after_unrecovered_injury_requires_manual_reentry(self):
        w=ExitWitness('w');w.observe(state(20));w.observe(state(13.5))
        self.assertEqual(13.5,w.observe({'connected':False})['health'])
    def test_native_safety_lock_is_preserved_even_if_health_recovers(self):
        w=ExitWitness('w');w.observe(state(20))
        self.assertIsNotNone(w.observe(state(20,safety_hold={'active':True})))
    def test_manual_takeover_and_other_world_cannot_be_claimed_as_goal_damage(self):
        w=ExitWitness('w');w.observe(state(20));w.observe(state(19,manual_movement=True))
        self.assertIsNone(w.observe({'connected':False}))
        self.assertIsNone(ExitWitness('w').observe(state(10,world_session='other',safety_hold={'active':True})))


if __name__=='__main__':unittest.main()
