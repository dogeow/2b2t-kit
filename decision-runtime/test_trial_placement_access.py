import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from singleplayer_trial import TrialSkills, TrialWorld
from singleplayer_trial_bridge import Paused, TrialInteractionRejected
from survival_world import center
from trial_placement_access import placement_access_plan
from trial_station_access import visible_full_faces
from test_singleplayer_trial import row


FIXTURE = Path(__file__).parent / 'fixtures/trial_shelter_placement_20261007.json'


class PlacementBridge:
    world = 'trial'
    halted = False
    pending_mutations = {}
    def __init__(self, data):
        self.data = data
        self.rows = {tuple(r['pos']): copy.deepcopy(r) for r in data['blocks']}
        self.state = {'world_id': '/tmp/trial', 'dimension': 'minecraft:overworld',
            'world_session': 'session', 'control_revision': 6, 'pos': data['feet'],
            'hand': {'item': 'minecraft:dirt'}, 'inventory': [{'item': 'minecraft:dirt', 'count': 21}],
            'menu': {'id': 0, 'type': 'InventoryMenu', 'cursor': {'count': 0}, 'slots': []},
            'bridge_version': 4}
        self.origin, self.calls, self.reject_first, self.unknown = list(self.state['pos']), [], False, False
    def read(self): return copy.deepcopy(self.state)
    def close(self): pass
    def select(self, item): self.state['hand']['item'] = 'minecraft:' + item
    def request(self, op, **args):
        self.calls.append((op, args))
        if op == 'scan':
            return {**self.read(), 'blocks': [r for p, r in self.rows.items()
                    if all(a <= v <= b for a, v, b in zip(args['min'], p, args['max']))]}
        if op == 'walk_path':
            self.state['pos'] = args['path'][-1]
            return self.read()
        if op == 'interact':
            if self.reject_first:
                self.reject_first = False
                raise TrialInteractionRejected(args, {'detail': 'Target interaction face is occluded or out of reach',
                    'request_id': 'rejected-with-no-use'})
            if self.unknown:
                self.halted = True
                self.pending_mutations = {'uncertain-use': {'op': 'interact'}}
                raise Paused('Unknown dispatched native use')
            world = TrialWorld(list(self.rows.values()), self.data['min'], self.data['max'])
            assert args['face'] in visible_full_faces(world, self.state['pos'], tuple(args['pos']))
            directions = {'up': (0, 1, 0), 'down': (0, -1, 0), 'east': (1, 0, 0),
                          'west': (-1, 0, 0), 'north': (0, 0, -1), 'south': (0, 0, 1)}
            target = tuple(a + b for a, b in zip(args['pos'], directions[args['face']]))
            assert list(target) == self.data['planned_target']
            self.rows[target] = row(target, 'dirt')
            return self.read()
        raise AssertionError(op)


class PlacementAccessTests(unittest.TestCase):
    def fixture(self): return json.loads(FIXTURE.read_text())
    def skills(self, root):
        data = self.fixture()
        bridge = PlacementBridge(data)
        skills = TrialSkills(bridge, root)
        skills.save = Mock()
        return data, bridge, skills

    def test_real_wall_scan_refuses_old_up_and_uses_existing_wall_south_after_one_step(self):
        data = self.fixture()
        self.assertEqual(data['scan_cells_read'], data['scan_total_cells'])
        world = TrialWorld(data['blocks'], data['min'], data['max'])
        self.assertNotIn('up', visible_full_faces(world, data['feet'], tuple(data['old_arguments']['pos'])))
        plan = placement_access_plan(world, {'pos': data['feet']}, data['planned_target'])
        self.assertEqual((9, 63, -78), plan['support'])
        self.assertEqual('south', plan['face'])
        self.assertEqual([(10, 63, -77)], plan['route'])
        self.assertEqual(tuple(data['planned_target']), plan['target'])

    def test_real_runner_uses_new_stance_keeps_target_and_does_not_remove_two_walls(self):
        with tempfile.TemporaryDirectory() as root:
            data, bridge, skills = self.skills(root)
            original = {p: copy.deepcopy(bridge.rows[p]) for p in ((9, 63, -79), (9, 63, -78))}
            skills.place('dirt', data['planned_target'])
            self.assertTrue(any(op == 'walk_path' for op, unused in bridge.calls))
            used = [args for op, args in bridge.calls if op == 'interact']
            self.assertEqual(1, len(used))
            self.assertEqual([9, 63, -78], used[0]['pos'])
            self.assertEqual('south', used[0]['face'])
            self.assertEqual('dirt', skills.owned['9,63,-77'])
            self.assertFalse(any(op == 'mine_block' for op, unused in bridge.calls))
            for p, value in original.items(): self.assertEqual(value, bridge.rows[p])

    def test_roof_uses_actual_reachable_raised_natural_stance_and_final_center_side(self):
        data = self.fixture()
        # This is a pure planning regression for future verified stages. The
        # runtime never installs these hypothetical rows in its world model.
        rows = {tuple(value['pos']): value for value in data['blocks']}
        for p in data['shelter']['walls']: rows[tuple(p)] = row(tuple(p), 'dirt')
        world = TrialWorld(list(rows.values()), data['min'], data['max'])
        first = tuple(data['shelter']['roof'][0])
        plan = placement_access_plan(world, {'pos': data['feet']}, first)
        self.assertIsNotNone(plan)
        self.assertGreaterEqual(plan['route'][-1][1], 64)
        self.assertEqual('up', plan['face'])
        self.assertEqual(first, plan['target'])
        for p in data['shelter']['roof'][:-1]: rows[tuple(p)] = row(tuple(p), 'dirt')
        world = TrialWorld(list(rows.values()), data['min'], data['max'])
        center_roof = tuple(data['shelter']['roof'][-1])
        plan = placement_access_plan(world, {'pos': data['feet']}, center_roof)
        self.assertIsNotNone(plan)
        self.assertEqual('south', plan['face'])
        self.assertEqual([], plan['route'])

    def test_unknown_dispatched_use_is_preserved_without_alternative_replay(self):
        with tempfile.TemporaryDirectory() as root:
            data, bridge, skills = self.skills(root)
            bridge.unknown = True
            with self.assertRaisesRegex(Paused, 'Unknown dispatched'): skills.place('dirt', data['planned_target'])
            self.assertTrue(bridge.halted)
            self.assertTrue(bridge.pending_mutations)
            self.assertEqual(1, sum(op == 'interact' for op, unused in bridge.calls))

    def test_predispatch_refusal_can_reobserve_then_choose_a_different_access(self):
        with tempfile.TemporaryDirectory() as root:
            data, bridge, skills = self.skills(root)
            bridge.reject_first = True
            skills.place('dirt', data['planned_target'])
            indices = [i for i, (op, unused) in enumerate(bridge.calls) if op == 'interact']
            self.assertEqual(2, len(indices))
            self.assertIn('scan', [op for op, unused in bridge.calls[indices[0] + 1:indices[1]]])
            self.assertFalse(bridge.halted)
            self.assertEqual('dirt', skills.owned['9,63,-77'])

    def test_unknown_terrain_and_container_support_cannot_authorize_placement(self):
        target = (1, 1, 0)
        rows = [row((0, 0, 0), 'stone'), {**row((1, 0, 0), 'chest'), 'block_entity': True}]
        world = TrialWorld(rows, [-2, -1, -2], [3, 3, 2])
        self.assertIsNone(placement_access_plan(world, {'pos': [.5, 1, .5]}, target))
        self.assertIsNone(placement_access_plan(world, {'pos': [.5, 1, .5]}, (8, 1, 0)))


if __name__ == '__main__': unittest.main()
