import copy
import tempfile
import unittest
from pathlib import Path

from material_trip_policy import carried
from sand_frontier_driver import (SandFrontierLedger,
                                  conservative_storage_after_gravel, drive,
                                  validate_plan)


OLD_FOUR_CHESTS = {'chests': [
    {'pos': [761019, 64, 797852], 'free_slots': 0,
     'items': {'minecraft:gravel': 458, 'minecraft:sand': 28}},
    {'pos': [761021, 64, 797852], 'free_slots': 0,
     'items': {'minecraft:sand': 79}},
    {'pos': [761011, 64, 797852], 'free_slots': 6,
     'items': {'minecraft:gravel': 128}},
    {'pos': [761015, 64, 797852], 'free_slots': 8,
     'items': {'minecraft:sand': 7}},
]}


def patch(name, x):
    return {'id': name, 'region': [x, 64, 100, x + 15, 66, 115],
            'park_high': [x + 8, 100, 108],
            'verification': {'source': 'automation_scan',
                             'server': 'simpcraft.com:25565',
                             'dimension': 'minecraft:overworld',
                             'world_session': 'sample-world',
                             'dry_sand_count': 20, 'at_ms': 1000}}


def plan():
    return {'version': 1, 'server': 'simpcraft.com:25565',
            'dimension': 'minecraft:overworld',
            'world_session': 'sample-world', 'site_center': [0, 0],
            'patches': [patch('a', 100), patch('b', 140)]}


class FakeClient:
    def __init__(self, sand=0, world='sample-world'):
        self.anchor = [108, 100, 108]
        self.pos = list(self.anchor)
        self.world = world
        self.inventory = [{'slot': i, 'item': 'minecraft:air', 'count': 0}
                          for i in range(36)]
        if sand:
            self.inventory[0] = {'slot': 0, 'item': 'minecraft:sand', 'count': sand}
        self.moves = []

    def status(self):
        return {'server': 'simpcraft.com:25565', 'dimension': 'minecraft:overworld',
                'world_session': self.world, 'time': 2000,
                'pos': list(self.pos), 'inventory': copy.deepcopy(self.inventory),
                'health': 20, 'guard_armed': True, 'under_water': False,
                'safety_hold': {'active': False}}

    def request(self, op, **params):
        assert op == 'navigate'
        self.moves.append(params['target'])
        self.pos = list(params['target'])
        return {'phase': 'done'}

    def add_sand(self, count):
        slot = self.inventory[0]
        if slot['item'] == 'minecraft:air':
            self.inventory[0] = {'slot': 0, 'item': 'minecraft:sand', 'count': count}
        else:
            slot['count'] += count


class SandFrontierDriverTest(unittest.TestCase):
    def test_old_four_chests_guarantee_sand_room_after_250_gravel(self):
        result = conservative_storage_after_gravel(OLD_FOUR_CHESTS, 250, 722)
        self.assertEqual(10, result['free_slots_after_gravel'])
        self.assertEqual(142, result['existing_sand_partial_capacity'])
        self.assertEqual(782, result['guaranteed_new_sand_capacity'])
        self.assertEqual(60, result['sand_capacity_margin'])
        self.assertFalse(result['early_crafting_needed_for_space'])
        # More incoming gravel can erase the margin; never generalize the
        # 250-block snapshot into a permanent storage guarantee.
        self.assertTrue(conservative_storage_after_gravel(
            OLD_FOUR_CHESTS, 375, 722)['early_crafting_needed_for_space'])

    def test_requires_nonoverlapping_same_world_surveyed_patches(self):
        client = FakeClient()
        validate_plan(plan(), client.status(), client.anchor)
        overlap = plan()
        overlap['patches'][1]['region'] = [110, 64, 100, 125, 66, 115]
        overlap['patches'][1]['park_high'] = [118, 100, 108]
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            validate_plan(overlap, client.status(), client.anchor)
        wrong_world = plan()
        wrong_world['world_session'] = 'other-world'
        with self.assertRaisesRegex(RuntimeError, 'another world'):
            validate_plan(wrong_world, client.status(), client.anchor)

    def test_exhausted_patch_is_skipped_on_same_session_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / 'ledger.json'
            ledger = SandFrontierLedger(ledger_path)
            client = FakeClient()
            calls = []

            def fake_harvest(client, low, high, target, out):
                calls.append(low[0])
                before = carried(client.status(), 'minecraft:sand')
                if low[0] == 140:
                    client.add_sand(5)
                amount = carried(client.status(), 'minecraft:sand')
                return {'before': before, 'after': amount, 'gained': amount - before,
                        'target_reached': amount >= target, 'bag_full': False}

            first = drive(client, plan(), ledger, directory, 5, fake_harvest)
            self.assertEqual([100, 140], calls)
            self.assertEqual(5, first['gained'])
            self.assertTrue(first['target_reached'])
            self.assertEqual('exhausted', ledger.get(plan()['patches'][0], client.status())['status'])
            resumed = FakeClient()
            reloaded_ledger = SandFrontierLedger(ledger_path)
            calls.clear()
            second = drive(resumed, plan(), reloaded_ledger, directory, 5, fake_harvest)
            self.assertEqual([140], calls)
            self.assertEqual(['a'], second['skipped_exhausted'])

    def test_no_patch_is_scanned_once_carried_goal_is_met(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient(sand=5)
            ledger = SandFrontierLedger(Path(directory) / 'ledger.json')
            result = drive(client, plan(), ledger, directory, 5,
                           lambda *_: self.fail('No harvest should start'))
            self.assertTrue(result['target_reached'])
            self.assertFalse(client.moves)

    def test_interrupted_patch_is_retryable_not_marked_exhausted(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            ledger = SandFrontierLedger(Path(directory) / 'ledger.json')
            with self.assertRaisesRegex(RuntimeError, 'server interrupted'):
                drive(client, plan(), ledger, directory, 5,
                      lambda *_: (_ for _ in ()).throw(RuntimeError('server interrupted')))
            self.assertEqual('interrupted', ledger.get(plan()['patches'][0], client.status())['status'])


if __name__ == '__main__':
    unittest.main()
