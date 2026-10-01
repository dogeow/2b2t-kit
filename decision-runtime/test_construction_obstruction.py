import json
from pathlib import Path
import tempfile
import unittest

from construction_obstruction import (HorseNudgeWaiting, HorseObstructionBlocked,
                                      approach_and_nudge_explicit_horse,
                                      explicit_horse_blocker, make_request,
                                      nudge_explicit_horse, spent_key)


CELL = [10, 63, 10]
HORSE = {'id': 42, 'uuid': '12345678-1234-5678-9234-567812345678',
         'type': 'minecraft:horse', 'name': 'Horse', 'visible': True,
         'health': 18.0, 'pos': [12.0, 64.0, 10.5]}


def state(entities=None):
    return {'time': 1000, 'server': 'simpcraft.com', 'dimension': 'minecraft:overworld',
            'world_session': 'world', 'control_revision': 7, 'pos': [9.8, 64.0, 10.5],
            'entities': [HORSE] if entities is None else entities,
            'connected': True, 'screen': '', 'manual_movement': False,
            'velocity': [0.0, 0.0, 0.0],
            'movement_keys': {'forward': False, 'back': False, 'jump': False, 'sneak': False},
            'horse_nudge_protocol': 1, 'guard_armed': True, 'guard_pve_only': True,
            'guard_busy': False, 'kill_aura': True,
            'projection_selection': {'key': 'locked-courtyard'}}


class FakeClient:
    def __init__(self, snapshot, reply):
        self.snapshot = snapshot
        self.reply = reply
        self.requests = []
    def status(self):
        return self.snapshot
    def request(self, op, **params):
        self.requests.append((op, params))
        return self.reply


class ApproachClient:
    world = 'world'
    def __init__(self, nudge_phase='done', move_horse_at_hover=False, ground=True,
                 fail_ascent=False, horse_after_scout_polls=0, scout_entities=None,
                 unsafe_wait_poll=None, unsafe_field='health', first_scout_drift=False,
                 second_scout_drift=False, initial_scout_offset=0.0,
                 recenter_time_regression=False):
        self.task = 'task-a'
        self.heartbeat = type('Heartbeat', (), {'id': 'lease-a'})()
        self.current = {**state([]), 'pos': [10.5, 90.0, 10.5], 'flight': True,
                        'on_ground': False, 'health': 20, 'air_return_active': False,
                        'supervision_lease': {'id': 'lease-a', 'kind': 'materials', 'job_session': self.task,
                         'world_session': self.world, 'revision': 7}}
        self.requests = []
        self.nudge_phase = nudge_phase
        self.move_horse_at_hover = move_horse_at_hover
        self.ground = ground
        self.fail_ascent = fail_ascent
        self.horse_after_scout_polls = horse_after_scout_polls
        self.scout_entities = scout_entities
        self.unsafe_wait_poll = unsafe_wait_poll;self.unsafe_field = unsafe_field
        self.scout_polls = 0
        self.frame_time = 1000;self.first_scout_drift = first_scout_drift
        self.second_scout_drift = second_scout_drift;self.after_recenter_polls = 0
        self.initial_scout_offset = initial_scout_offset
        self.recenter_time_regression = recenter_time_regression;self.drift_frame_time = None
        self.navigate_count = 0
    def status(self):
        self.frame_time += 50;self.current = {**self.current, 'time': self.frame_time}
        if self.navigate_count == 1 and self.current['pos'][1] == 74:
            self.scout_polls += 1
            if self.first_scout_drift and self.scout_polls == 2:
                self.current = {**self.current, 'pos': [11.3, 74.0, 10.5]}
                self.drift_frame_time = self.frame_time
            if self.unsafe_wait_poll == self.scout_polls:
                if self.unsafe_field == 'manual_movement':
                    self.current = {**self.current, 'manual_movement': True}
                elif self.unsafe_field == 'guard_armed':
                    self.current = {**self.current, 'guard_armed': False}
                elif self.unsafe_field == 'lease_id':
                    self.current = {**self.current, 'supervision_lease': {
                        **self.current['supervision_lease'], 'id': 'foreign-lease'}}
                elif self.unsafe_field == 'missing_lease_id':
                    lease = dict(self.current['supervision_lease']);lease.pop('id', None)
                    self.current = {**self.current, 'supervision_lease': lease}
                elif self.unsafe_field == 'revision_type':
                    self.current = {**self.current, 'control_revision': 7.0,
                                    'supervision_lease': {
                                     **self.current['supervision_lease'], 'revision': 7.0}}
                elif self.unsafe_field == 'state_world':
                    self.current = {**self.current, 'world_session': 'foreign-world'}
                else:self.current = {**self.current, 'health': 18}
            if self.scout_entities is not None:
                self.current = {**self.current, 'entities': self.scout_entities}
            elif self.scout_polls > self.horse_after_scout_polls:
                self.current = {**self.current, 'entities': [HORSE]}
        if self.first_scout_drift and self.navigate_count == 2 and self.current['pos'][1] == 74:
            self.after_recenter_polls += 1
            if (self.recenter_time_regression and self.after_recenter_polls == 1
                    and self.drift_frame_time is not None):
                self.current = {**self.current, 'time': self.drift_frame_time - 50}
            if self.second_scout_drift and self.after_recenter_polls == 2:
                self.current = {**self.current, 'pos': [11.3, 74.0, 10.5]}
        return self.current
    def request(self, op, **params):
        self.requests.append((op, params))
        if op == 'scan':
            rows = []
            if self.ground and params['min'][1] <= 63 <= params['max'][1]:
                for x in range(params['min'][0], params['max'][0] + 1):
                    for z in range(params['min'][2], params['max'][2] + 1):
                        rows.append({'pos': [x, 63, z], 'state': 'Block{minecraft:dirt}',
                                     'solid': True, 'passable': False, 'fluid': False,
                                     'block_entity': False})
            return {'phase': 'done', 'world_session': self.world, 'blocks': rows}
        if op == 'navigate':
            self.navigate_count += 1
            if self.fail_ascent and self.current.get('flight') is False:
                return {'phase': 'waiting', 'detail': 'ascent changed'}
            horse = HORSE
            if self.move_horse_at_hover and self.navigate_count == 2:
                horse = {**HORSE, 'pos': [HORSE['pos'][0] + .8, *HORSE['pos'][1:]]}
            entities = [] if self.navigate_count == 1 else [horse]
            target = list(params['target'])
            if self.navigate_count == 1:target[0] += self.initial_scout_offset
            self.current = {**self.current, 'pos': target, 'entities': entities,
                            'flight': True, 'on_ground': False}
            return {'phase': 'done'}
        if op == 'walk':
            self.current = {**self.current, 'pos': list(params['target']), 'entities': [HORSE],
                            'flight': False, 'on_ground': True}
            return {'phase': 'done'}
        if op == 'nudge_horse':
            evidence = {'spent_key': params['spent_key'], 'expected_uuid': HORSE['uuid'],
                        'attack_count': 1, 'same_uuid_observed': True, 'alive': True,
                        'health': 17, 'clearance_distance': 6.1,
                        'pve_guard_armed': True, 'kill_aura_can_target_horse': False}
            return {'phase': self.nudge_phase, 'detail': 'observed', 'horse_nudge': evidence}
        raise AssertionError(op)


class Clock:
    def __init__(self):self.now = 0.0
    def monotonic(self):return self.now
    def sleep(self, seconds):self.now += seconds


class ConstructionObstructionTest(unittest.TestCase):
    def test_only_one_explicit_visible_healthy_horse_is_eligible(self):
        self.assertEqual(explicit_horse_blocker(state(), CELL)['uuid'], HORSE['uuid'])
        with self.assertRaises(HorseObstructionBlocked):
            explicit_horse_blocker(state([{**HORSE, 'type': 'minecraft:cow'}]), CELL)
        with self.assertRaises(HorseObstructionBlocked):
            explicit_horse_blocker(state([HORSE, {**HORSE, 'id': 43,
                'uuid': '22345678-1234-5678-9234-567812345678'}]), CELL)
        with self.assertRaises(HorseObstructionBlocked):
            explicit_horse_blocker(state([{**HORSE, 'health': 7.9}]), CELL)
        with self.assertRaises(HorseObstructionBlocked):
            explicit_horse_blocker(state([{**HORSE, 'visible': False}]), CELL)

    def test_request_pins_observation_scope_and_deterministic_spent_key(self):
        request = make_request(state(), CELL, [17.1, 64, 10.5],
                               'Block{minecraft:stone_bricks}')
        self.assertEqual(request['expected_uuid'], HORSE['uuid'])
        self.assertEqual(request['expected_pos'], HORSE['pos'])
        self.assertEqual(request['expected_health'], HORSE['health'])
        self.assertEqual(request['observed_at'], 1000)
        self.assertEqual(request['spent_key'], spent_key(state(), CELL, HORSE))
        self.assertEqual(request['spent_key'], make_request(
            state(), CELL, [17.1, 64, 10.5], 'Block{minecraft:stone_bricks}')['spent_key'])

    def test_done_requires_same_living_horse_six_blocks_clear_and_pve_guard(self):
        params = make_request(state(), CELL, [17.1, 64, 10.5],
                              'Block{minecraft:stone_bricks}')
        evidence = {'spent_key': params['spent_key'], 'expected_uuid': HORSE['uuid'],
                    'attack_count': 1, 'same_uuid_observed': True, 'alive': True,
                    'health': 17, 'clearance_distance': 6.1,
                    'pve_guard_armed': True, 'kill_aura_can_target_horse': False}
        client = FakeClient(state(), {'phase': 'done', 'horse_nudge': evidence})
        self.assertEqual(nudge_explicit_horse(client, CELL, [17.1, 64, 10.5],
                                             'Block{minecraft:stone_bricks}')['phase'], 'done')
        self.assertEqual([op for op, _ in client.requests], ['nudge_horse'])
        bad = FakeClient(state(), {'phase': 'done', 'horse_nudge': {**evidence,
                         'clearance_distance': 5.99}})
        with self.assertRaises(HorseNudgeWaiting):
            nudge_explicit_horse(bad, CELL, [17.1, 64, 10.5],
                                 'Block{minecraft:stone_bricks}')

    def test_waiting_receipt_is_surfaced_without_a_second_request(self):
        params = make_request(state(), CELL, [17.1, 64, 10.5],
                              'Block{minecraft:stone_bricks}')
        client = FakeClient(state(), {'phase': 'waiting', 'detail': 'did not clear',
            'horse_nudge': {'spent_key': params['spent_key'], 'attack_count': 1}})
        with self.assertRaises(HorseNudgeWaiting):
            nudge_explicit_horse(client, CELL, [17.1, 64, 10.5],
                                 'Block{minecraft:stone_bricks}')
        self.assertEqual(len(client.requests), 1)

    def test_any_spent_error_is_waiting_but_pre_send_error_is_blocked(self):
        params = make_request(state(), CELL, [17.1, 64, 10.5],
                              'Block{minecraft:stone_bricks}')
        spent = FakeClient(state(), {'phase': 'error', 'detail': 'survival not confirmed',
            'horse_nudge': {'spent_key': params['spent_key'], 'attack_count': 1}})
        with self.assertRaises(HorseNudgeWaiting):
            nudge_explicit_horse(spent, CELL, [17.1, 64, 10.5],
                                 'Block{minecraft:stone_bricks}')
        rejected = FakeClient(state(), {'phase': 'error', 'detail': 'preflight rejected'})
        with self.assertRaises(HorseObstructionBlocked):
            nudge_explicit_horse(rejected, CELL, [17.1, 64, 10.5],
                                 'Block{minecraft:stone_bricks}')
        self.assertEqual(len(spent.requests), 1)
        self.assertEqual(len(rejected.requests), 1)

    def test_bounded_approach_scans_scouts_lands_nudges_once_and_returns_to_air(self):
        client = ApproachClient()
        result = approach_and_nudge_explicit_horse(
            client, CELL, 'Block{minecraft:stone_bricks}', scout_y=74, sleep=lambda _: None)
        self.assertEqual(result['phase'], 'done')
        operations = [op for op, _ in client.requests]
        self.assertEqual(operations.count('nudge_horse'), 1)
        self.assertEqual(operations.count('walk'), 1)
        self.assertGreaterEqual(operations.count('scan'), 4)
        self.assertLess(operations.index('walk'), operations.index('nudge_horse'))
        self.assertEqual(operations[-1], 'navigate')
        self.assertTrue(client.current['flight'])
        self.assertAlmostEqual(client.current['pos'][1], 74)
        walk = next(params for op, params in client.requests if op == 'walk')
        self.assertIs(walk['restore_flight'], False)

    def test_waiting_nudge_still_ascends_and_never_retries(self):
        client = ApproachClient(nudge_phase='waiting')
        with self.assertRaises(HorseNudgeWaiting):
            approach_and_nudge_explicit_horse(
                client, CELL, 'Block{minecraft:stone_bricks}', scout_y=74, sleep=lambda _: None)
        operations = [op for op, _ in client.requests]
        self.assertEqual(operations.count('nudge_horse'), 1)
        self.assertEqual(operations[-1], 'navigate')
        self.assertTrue(client.current['flight'])

    def test_no_scanned_ground_or_moved_horse_stops_before_nudge(self):
        for client in (ApproachClient(ground=False), ApproachClient(move_horse_at_hover=True)):
            with self.subTest(client=client):
                with self.assertRaises(HorseObstructionBlocked):
                    approach_and_nudge_explicit_horse(
                        client, CELL, 'Block{minecraft:stone_bricks}', scout_y=74,
                        sleep=lambda _: None)
                self.assertNotIn('nudge_horse', [op for op, _ in client.requests])

    def test_spent_nudge_receipt_survives_an_unconfirmed_guarded_ascent(self):
        client = ApproachClient(fail_ascent=True)
        with self.assertRaises(HorseNudgeWaiting) as caught:
            approach_and_nudge_explicit_horse(
                client, CELL, 'Block{minecraft:stone_bricks}', scout_y=74,
                sleep=lambda _: None)
        self.assertEqual(caught.exception.reply['phase'], 'done')
        self.assertEqual([op for op, _ in client.requests].count('nudge_horse'), 1)

    def test_horse_appearing_after_bounded_scout_polls_can_proceed_once(self):
        client = ApproachClient(horse_after_scout_polls=3);clock = Clock()
        result = approach_and_nudge_explicit_horse(
            client, CELL, 'Block{minecraft:stone_bricks}', scout_y=74,
            wait_for_horse_seconds=2, sleep=clock.sleep, monotonic=clock.monotonic)
        self.assertEqual(result['phase'], 'done')
        self.assertGreaterEqual(client.scout_polls, 4)
        self.assertEqual([op for op, _ in client.requests].count('nudge_horse'), 1)

    def test_never_appearing_horse_times_out_high_without_walk_or_attack(self):
        client = ApproachClient(horse_after_scout_polls=999);clock = Clock()
        with self.assertRaisesRegex(HorseObstructionBlocked, 'before timeout'):
            approach_and_nudge_explicit_horse(
                client, CELL, 'Block{minecraft:stone_bricks}', scout_y=74,
                wait_for_horse_seconds=.6, sleep=clock.sleep, monotonic=clock.monotonic)
        operations = [op for op, _ in client.requests]
        self.assertEqual(operations, ['scan', 'navigate'])
        self.assertTrue(client.current['flight']);self.assertEqual(client.current['pos'][1], 74)

    def test_wrong_or_multiple_clearance_entities_block_without_descent(self):
        cow = {**HORSE, 'type': 'minecraft:cow', 'uuid': '32345678-1234-5678-9234-567812345678'}
        for entities in ([cow], [HORSE, cow]):
            with self.subTest(entities=entities):
                client = ApproachClient(scout_entities=entities);clock = Clock()
                with self.assertRaisesRegex(HorseObstructionBlocked, 'non-horse or multiple'):
                    approach_and_nudge_explicit_horse(
                        client, CELL, 'Block{minecraft:stone_bricks}', scout_y=74,
                        wait_for_horse_seconds=2, sleep=clock.sleep, monotonic=clock.monotonic)
                operations = [op for op, _ in client.requests]
                self.assertEqual(operations, ['scan', 'navigate'])

    def test_wait_aborts_on_manual_health_or_guard_change_without_descent(self):
        for field in ('manual_movement', 'health', 'guard_armed', 'lease_id',
                      'missing_lease_id', 'revision_type', 'state_world'):
            with self.subTest(field=field):
                client = ApproachClient(horse_after_scout_polls=999,
                    unsafe_wait_poll=2, unsafe_field=field);clock = Clock()
                with self.assertRaisesRegex(HorseObstructionBlocked, 'lost'):
                    approach_and_nudge_explicit_horse(
                        client, CELL, 'Block{minecraft:stone_bricks}', scout_y=74,
                        wait_for_horse_seconds=2, sleep=clock.sleep, monotonic=clock.monotonic)
                operations = [op for op, _ in client.requests]
                self.assertEqual(operations, ['scan', 'navigate'])

    def test_one_real_drift_gets_one_scanned_recenter_then_succeeds(self):
        with tempfile.TemporaryDirectory() as folder:
            client = ApproachClient(first_scout_drift=True, initial_scout_offset=-3.982)
            client.out = Path(folder)
            result = approach_and_nudge_explicit_horse(
                client, CELL, 'Block{minecraft:stone_bricks}', scout_y=74,
                wait_for_horse_seconds=2, sleep=lambda _: None)
            self.assertEqual(result['phase'], 'done')
            self.assertEqual([op for op, _ in client.requests].count('nudge_horse'), 1)
            receipt = json.loads((client.out / 'horse-scout-stability.json').read_text())
            self.assertEqual(receipt['status'], 'stable')
            self.assertEqual(receipt['recenter_count'], 1)
            self.assertEqual(len(receipt['stable_frames']), 2)
            self.assertAlmostEqual(receipt['initial']['pos'][0], 6.518, places=3)

    def test_second_drift_after_recenter_aborts_high_with_zero_nudge(self):
        with tempfile.TemporaryDirectory() as folder:
            client = ApproachClient(first_scout_drift=True, second_scout_drift=True)
            client.out = Path(folder)
            with self.assertRaisesRegex(HorseObstructionBlocked, 'drifted again'):
                approach_and_nudge_explicit_horse(
                    client, CELL, 'Block{minecraft:stone_bricks}', scout_y=74,
                    wait_for_horse_seconds=2, sleep=lambda _: None)
            operations = [op for op, _ in client.requests]
            self.assertEqual(operations, ['scan', 'navigate', 'scan', 'navigate'])
            self.assertNotIn('nudge_horse', operations);self.assertNotIn('walk', operations)
            receipt = json.loads((client.out / 'horse-scout-stability.json').read_text())
            self.assertEqual(receipt['status'], 'blocked')
            self.assertEqual(receipt['recenter_count'], 1)

    def test_recenter_rejects_a_time_regressed_cached_frame_before_any_descent(self):
        with tempfile.TemporaryDirectory() as folder:
            client = ApproachClient(first_scout_drift=True, recenter_time_regression=True)
            client.out = Path(folder)
            with self.assertRaisesRegex(HorseObstructionBlocked, 'newer status frame'):
                approach_and_nudge_explicit_horse(
                    client, CELL, 'Block{minecraft:stone_bricks}', scout_y=74,
                    wait_for_horse_seconds=2, sleep=lambda _: None)
            operations = [op for op, _ in client.requests]
            self.assertEqual(operations, ['scan', 'navigate', 'scan', 'navigate'])
            self.assertNotIn('walk', operations);self.assertNotIn('nudge_horse', operations)


if __name__ == '__main__':
    unittest.main()
