import copy
import unittest

from singleplayer_trial_bridge import Paused
from survival_world import World, center
from trial_surface_recovery import plan_upward, protected_cells, recover_upward


def block(point, name='stone', **properties):
    return {'pos': list(point), 'state': 'Block{minecraft:' + name + '}',
            'solid': True, 'passable': False, 'fluid': False,
            'block_entity': False, **properties}


class Skills:
    def __init__(self, rows, high=(6, 10, 6)):
        self.rows = {tuple(value['pos']): copy.deepcopy(value) for value in rows}
        self.high = high
        self.stations = {}
        self.owned = {}
        self.events = []
        self.scan_count = 0
        self.walks = []
        self.b = self
        self.halted = False
        self.pending_mutations = {}
        self.mines = []
        self.unconfirmed = False
        self.false_arrival = False
        self.state = {'pos': [.5, 1, .5], 'on_ground': True}

    def read(self): return self.state

    def scan(self):
        self.scan_count += 1
        return World(list(self.rows.values()), [-6, -4, -6], self.high)

    def event(self, kind, **data): self.events.append((kind, data))

    def request(self, op, **arguments):
        if op != 'mine_block': raise AssertionError(op)
        point = tuple(arguments['pos'])
        self.mines.append(point)
        if self.rows[point]['state'] != arguments['expected_state']:
            raise AssertionError('Expected state must be fresh')
        if not self.unconfirmed: self.rows.pop(point)
        return {'phase': 'done' if not self.unconfirmed else 'waiting',
                'server_confirmed': not self.unconfirmed, 'outcome_pending': self.unconfirmed,
                'id': 'mine-' + str(len(self.mines))}

    def walk(self, route):
        # This fake validates the same freshly observed graph before arrival.
        parents = self.scan().paths(self.state['pos'])
        if route[-1] not in parents: raise AssertionError('No real normal walking route')
        self.walks.append(list(route))
        if not self.false_arrival: self.state['pos'] = center(route[-1])


def one_step():
    return [block((0, 0, 0)), block((1, 1, 0)), block((0, 3, 0)),
            block((1, 2, 0)), block((1, 3, 0))]


class SurfaceRecoveryTests(unittest.TestCase):
    def test_candidate_gate_is_pure_and_rejects_unstable_or_owned_steps(self):
        skills = Skills(one_step())
        world = skills.scan()
        option = plan_upward(world, skills.state, protected_cells(skills))
        self.assertEqual((1, 2, 0), option['target'])
        self.assertEqual((1, 1, 0), option['support'])
        self.assertIsNone(plan_upward(world, {**skills.state, 'on_ground': False}))
        self.assertIsNone(plan_upward(world, {**skills.state, 'pos': [.8, 1, .5]}))
        self.assertIsNone(plan_upward(world, skills.state, {(1, 1, 0)}))
        self.assertIsNone(plan_upward(world, skills.state, max_mined=2))
        self.assertEqual([], skills.mines)
        self.assertEqual([], skills.walks)

    def test_headroom_is_confirmed_and_rescanned_before_normal_ascent_without_mining_support(self):
        skills = Skills(one_step())
        result = recover_upward(skills, max_rises=1)
        self.assertEqual([(0, 3, 0), (1, 2, 0), (1, 3, 0)], skills.mines)
        self.assertIn((0, 0, 0), skills.rows)
        self.assertIn((1, 1, 0), skills.rows)
        self.assertEqual([[(1, 2, 0)]], skills.walks)
        self.assertEqual(1, result['actual_rise'])
        self.assertEqual('progress', result['phase'])
        self.assertFalse(result['surface_confirmed'])
        self.assertGreaterEqual(skills.scan_count, len(skills.mines) + 1)
        names = [kind for kind, unused in skills.events]
        self.assertEqual(3, names.count('surface_recovery_headroom_confirmed'))
        self.assertEqual('surface_recovery_ascent_confirmed', names[-1])

    def test_ready_supported_step_needs_no_excavation(self):
        skills = Skills([block((0, 0, 0)), block((1, 1, 0))])
        result = recover_upward(skills, max_rises=1, max_mined=0)
        self.assertEqual(1, result['actual_rise'])
        self.assertEqual([], skills.mines)
        self.assertEqual(1, len(skills.walks))

    def test_unknown_liquid_container_owned_and_gravity_obstacles_never_receive_dig_or_walk(self):
        for failure in ('unknown', 'liquid', 'container', 'owned', 'facility_step', 'gravity', 'falling_above'):
            with self.subTest(failure=failure):
                rows = one_step()
                skills = Skills(rows)
                if failure == 'unknown': skills.high = (0, 10, 6)
                elif failure == 'liquid': skills.rows[(0, 4, 0)] = block((0, 4, 0), 'water', fluid=True, solid=False)
                elif failure == 'container': skills.rows[(1, 2, 0)] = block((1, 2, 0), 'chest', block_entity=True)
                elif failure == 'owned': skills.owned['1,2,0'] = 'stone'
                elif failure == 'facility_step': skills.stations['crafting_table'] = [1, 1, 0]
                elif failure == 'gravity': skills.rows[(1, 2, 0)] = block((1, 2, 0), 'sand')
                elif failure == 'falling_above': skills.rows[(0, 4, 0)] = block((0, 4, 0), 'gravel')
                result = recover_upward(skills)
                self.assertEqual('blocked', result['phase'])
                self.assertEqual([], skills.mines)
                self.assertEqual([], skills.walks)

    def test_unknown_mining_outcome_latches_without_replaying_in_this_or_next_batch(self):
        skills = Skills(one_step())
        skills.unconfirmed = True
        with self.assertRaisesRegex(Paused, 'unconfirmed'):
            recover_upward(skills)
        self.assertTrue(skills.halted)
        with self.assertRaisesRegex(Paused, 'preserved'):
            recover_upward(skills)
        self.assertEqual([(0, 3, 0)], skills.mines)
        self.assertEqual([], skills.walks)

    def test_false_walk_arrival_is_not_height_progress_and_is_not_replayed(self):
        skills = Skills([block((0, 0, 0)), block((1, 1, 0))])
        skills.false_arrival = True
        with self.assertRaisesRegex(Paused, 'actual height gain'):
            recover_upward(skills)
        with self.assertRaises(Paused): recover_upward(skills)
        self.assertEqual(1, len(skills.walks))

    def test_batch_cannot_partially_excavate_a_step_that_exceeds_remaining_budget(self):
        rows = [block((0, 0, 0)), block((0, 3, 0))]
        rows += [block((x, y, 0)) for x in range(1, 6) for y in range(0, 10)]
        skills = Skills(rows)
        result = recover_upward(skills)
        self.assertEqual(2, result['steps'])
        self.assertEqual(2, result['actual_rise'])
        self.assertEqual(6, result['mined'])
        self.assertIn('budget', result['reason'])
        self.assertNotIn((3, 4, 0), skills.mines)

    def test_invalid_or_unresolved_start_never_scans_or_moves(self):
        skills = Skills(one_step())
        for arguments in ({'max_rises': 5}, {'max_mined': 9}, {'max_rises': True}):
            with self.assertRaises(ValueError): recover_upward(skills, **arguments)
        skills.pending_mutations['old'] = {'op': 'mine_block'}
        with self.assertRaises(Paused): recover_upward(skills)
        self.assertEqual(0, skills.scan_count)
        self.assertEqual([], skills.mines)


if __name__ == '__main__':
    unittest.main()
