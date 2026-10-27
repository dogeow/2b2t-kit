import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from material_client import MaterialClient, Handoff
from stuck_damage import StuckDamageWitness


def state(t, health, **changes):
    return {'connected': True, 'world_session': 'world', 'control_revision': 7,
            'supervision_lease': {'id': 'lease', 'job_session': 'task', 'kind': 'materials',
                                 'world_session': 'world', 'revision': 7},
            'time': 100_000 + t, 'recent_hurt_at': 100_000 + t,
            'health': health, 'pos': [10.5, 78.06, 20.5], 'recent_attacker': '未知',
            'screen': '', 'manual_movement': False, 'entities': [],
            'guard_armed': True, 'guard_pve_only': True, 'guard_busy': True,
            'phase': 'waiting', **changes}


def samples():
    return [state(t, hp) for t, hp in ((0, 19.9), (2500, 19.8), (5000, 19.7),
                                      (7500, 19.6), (10500, 19.5))]


class StuckDamageTests(unittest.TestCase):
    def witness(self):
        return StuckDamageWitness('world', 'task', 'lease')

    def observe(self, witness, s, **changes):
        return witness.observe(s, revision=7, native_idle=changes.get('native_idle', True))

    def test_real_stationary_repeated_unknown_damage_emits_once_after_ten_seconds(self):
        w = self.witness()
        for s in samples()[:-1]:
            self.assertIsNone(self.observe(w, s))
        proof = self.observe(w, samples()[-1])
        self.assertEqual(5, proof['distinct_damage_events'])
        self.assertEqual(10.5, proof['stationary_seconds'])
        self.assertFalse(proof['automatic_reconnect_allowed'])
        self.assertIsNone(self.observe(w, state(13000, 19.4)))

    def test_one_minor_hit_stale_hurt_or_brief_unknown_injury_never_causes_exit(self):
        for sequence in (
                [state(t, 19.9, recent_hurt_at=100_000) for t in (0, 500, 2000, 11000)],
                [state(t, hp) for t, hp in ((0, 19.9), (1000, 19.8), (2000, 19.7), (3000, 19.6))],
                [state(t, 19.9) for t in (0, 4000, 8000, 12000)]):
            w = self.witness()
            self.assertTrue(all(self.observe(w, s) is None for s in sequence))

    def test_quiet_recovery_or_real_escape_resets_the_unhandled_window(self):
        for recovery in (state(11500, 19.8, recent_hurt_at=107500),
                         state(8000, 19.5, pos=[11.5, 78.06, 20.5])):
            w = self.witness()
            for s in samples()[:-1] + [recovery, state(13000, 19.4)]:
                self.assertIsNone(self.observe(w, s))

    def test_partial_regeneration_does_not_erase_repeated_unknown_damage(self):
        w = self.witness()
        pattern = ((0, 19.9), (2000, 19.5), (2500, 19.8),
                   (4000, 19.4), (4500, 19.8), (6000, 19.3),
                   (6500, 19.8), (8000, 19.2), (8500, 19.7))
        for t, hp in pattern:
            self.assertIsNone(self.observe(w, state(t, hp)))
        proof = self.observe(w, state(10500, 19.1))
        self.assertEqual(6, proof['distinct_damage_events'])
        self.assertFalse(proof['environmental_damage'])
        self.assertFalse(proof['automatic_reconnect_allowed'])

    def test_separated_unknown_hits_do_not_accumulate_across_quiet_intervals(self):
        w = self.witness()
        for t, hp in ((0, 19.9), (4000, 19.8), (8000, 19.7), (12000, 19.6)):
            self.assertIsNone(self.observe(w, state(t, hp)))

    def test_captured_fire_pattern_exits_before_the_fourteen_health_threshold(self):
        w=self.witness()
        self.assertIsNone(self.observe(w,state(0,19.398079,recent_attacker='火')))
        proof=self.observe(w,state(2000,19.3,recent_attacker='火'))
        self.assertTrue(proof['environmental_damage'])
        self.assertEqual(2,proof['distinct_damage_events'])
        self.assertGreater(proof['latest']['health'],19)
        self.assertIsNone(self.observe(w,state(3000,19,recent_attacker='火')))

    def test_partial_healing_does_not_erase_current_fire_but_a_quiet_interval_does(self):
        w=self.witness()
        self.assertIsNone(self.observe(w,state(0,19.4,recent_attacker='火')))
        self.assertIsNone(self.observe(w,state(400,19.6,recent_attacker='火',recent_hurt_at=100000)))
        self.assertTrue(self.observe(w,state(1000,19,recent_attacker='火'))['environmental_damage'])
        w=self.witness()
        self.assertIsNone(self.observe(w,state(0,19.4,recent_attacker='火')))
        self.assertIsNone(self.observe(w,state(4000,19.3,recent_attacker='火')))

    def test_environmental_tick_duplicates_and_single_fall_are_not_repeated_fire(self):
        w=self.witness()
        for t in (0,100,200,300,400,1000):
            self.assertIsNone(self.observe(w,state(t,19.4,recent_attacker='火',recent_hurt_at=100000)))
        w=self.witness()
        for t in (0,500,1000):
            self.assertIsNone(self.observe(w,state(t,19.4,recent_attacker='摔落',recent_hurt_at=100000)))

    def test_unknown_damage_is_not_relabelled_as_two_environmental_losses(self):
        w=self.witness()
        self.assertIsNone(self.observe(w,state(0,19.8)))
        self.assertIsNone(self.observe(w,state(1000,19.4,recent_attacker='火')))
        self.assertTrue(self.observe(w,state(2000,19.3,recent_attacker='火'))['environmental_damage'])

    def test_manual_control_hostiles_active_work_or_unknown_scope_suppresses_exit(self):
        changes = ({'manual_movement': True}, {'screen': 'InventoryScreen'},
                   {'entities': [{'hostile': True, 'alive': True, 'health': 10}]},
                   {'entities': None}, {'navigating': True}, {'native_material_busy': True},
                   {'air_return_active': True}, {'phase': 'running'},
                   {'professional_printer': {'owned': True}}, {'build_job': {'active': True}},
                   {'world_session': 'other'}, {'control_revision': 8}, {'guard_armed': False},
                   {'connected': False}, {'safety_hold': {'active': True}}, {'health': float('nan')},
                   {'supervision_lease': {'id': 'other'}}, {'supervision_lease': 'bad'})
        for change in changes:
            with self.subTest(change=change):
                w = self.witness()
                for s in samples():
                    self.assertIsNone(self.observe(w, {**s, **change}))
        w = self.witness()
        for s in samples():
            self.assertIsNone(self.observe(w, s, native_idle=False))

    def test_repeated_status_frames_do_not_become_distinct_damage_events(self):
        w = self.witness()
        for _ in range(30):
            self.assertIsNone(self.observe(w, samples()[0]))
        self.assertIsNone(self.observe(w, samples()[-1]))

    def client(self, directory):
        c = MaterialClient.__new__(MaterialClient)
        c.root = Path(directory) / 'automation'; c.root.mkdir()
        c.out = Path(directory) / 'work'; c.out.mkdir()
        c.world, c.task, c.rev, c.last = 'world', 'task', 7, 'known-idle'
        c.heartbeat = SimpleNamespace(id='lease', touch=Mock(), close=Mock())
        c.native_inflight = None
        return c

    def test_normal_raw_observation_uses_the_same_owner_for_one_exit_and_persistent_holds(self):
        with tempfile.TemporaryDirectory() as d:
            c = self.client(d)
            def logout(op, **kwargs):
                self.assertEqual('safe_logout', op)
                c.last = 'logout-once'
                return {'connected': False, 'phase': 'done'}
            c.request = Mock(side_effect=logout)
            with patch('material_client.Client.raw', side_effect=samples()):
                for _ in range(4): c.raw()
                with self.assertRaises(Handoff): c.raw()
            c.request.assert_called_once()
            hold = json.loads((c.root / 'assistant-control-hold.json').read_text())
            self.assertTrue(hold['active']); self.assertTrue(hold['explicit_user_resume_required'])
            self.assertFalse(hold['automatic_reconnect_allowed'])
            self.assertTrue(json.loads((c.root / 'material-health-hold.json').read_text())['active'])
            with self.assertRaises(Handoff): c._exit_stuck_damage({'latest': samples()[-1]})
            c.request.assert_called_once()

    def test_uncertain_dispatched_logout_is_retained_and_never_replayed(self):
        with tempfile.TemporaryDirectory() as d:
            c = self.client(d)
            def unknown(op, **kwargs):
                c.last = 'logout-once'
                raise RuntimeError('Original outcome unknown')
            c.request = Mock(side_effect=unknown)
            with self.assertRaises(Handoff): c._exit_stuck_damage({'latest': samples()[-1]})
            book = json.loads((c.out / 'stuck-damage-safety-exit.json').read_text())
            self.assertEqual('one_safe_logout', book['pending'])
            self.assertTrue(book['logout_request_published']); self.assertFalse(book['logout_replayed'])
            self.assertTrue(json.loads((c.root / 'assistant-control-hold.json').read_text())['active'])
            c.request.assert_called_once()

    def test_manual_handoff_before_logout_dispatch_does_not_create_a_health_exit_hold(self):
        with tempfile.TemporaryDirectory() as d:
            c = self.client(d); c.request = Mock(side_effect=Handoff('Player took over'))
            with self.assertRaises(Handoff): c._exit_stuck_damage({'latest': samples()[-1]})
            self.assertFalse((c.root / 'assistant-control-hold.json').exists())
            self.assertFalse((c.root / 'material-health-hold.json').exists())
            book = json.loads((c.out / 'stuck-damage-safety-exit.json').read_text())
            self.assertFalse(book['logout_request_published'])


if __name__ == '__main__':
    unittest.main()
