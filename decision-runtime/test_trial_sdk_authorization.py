"""Trial SDK authorization stays local while material/server holds remain intact."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from material_manufacture import _inventory_execute
from safety_interlock import require_unlocked
from singleplayer_trial import _TrialCraftClient
from singleplayer_trial_bridge import Paused, TrialBridge
import test_singleplayer_trial as fixtures


class TrialSdkAuthorizationTests(unittest.TestCase):
    def hold(self, root):
        root.mkdir(parents=True, exist_ok=True)
        path = root / 'safety-hold.json'
        content = json.dumps({'active': True, 'reason': 'Earlier non-trial health exit', 'time': 123})
        path.write_text(content)
        return path, content

    def fixture(self, game):
        reg = fixtures.registry(game)
        current = fixtures.state(reg, safety_hold={'active': False}, health_recovery_hold=False,
                        inventory_cursor_precondition_protocol=1,
                        inventory_isolation={'supported': True, 'active': True})
        current['trial_identity']['process_alive'] = True
        root = Path(game) / 'automation'
        root.mkdir()
        bridge = TrialBridge(root, reg, reg['run_id'], reader=lambda _: copy.deepcopy(current))
        client = _TrialCraftClient(bridge, game)
        bridge.request = Mock(side_effect=AssertionError('Rejected scope must never dispatch a click'))
        return current, bridge, client

    def test_active_exact_trial_crafts_under_its_native_scope_with_old_hold_preserved(self):
        with tempfile.TemporaryDirectory() as game, patch('kit_runtime.inventory.time.sleep'):
            skills, bridge = fixtures.TrialSdkCraftTests().skills(game, 2, {'minecraft:oak_log': 3},
                                                       {1: 'minecraft:oak_log'}, 'minecraft:oak_planks', 4)
            path, content = self.hold(bridge.root)
            with self.assertRaisesRegex(RuntimeError, 'Safety lock active'):
                require_unlocked(bridge.root, bridge.snapshot)
            with patch('material_manufacture.require_unlocked',
                       side_effect=AssertionError('Trial SDK must use its own controller scope')):
                result = skills.craft('oak_planks', {(0, 0): 'oak_log'}, 2, 4)
            self.assertEqual(4, sum(row['count'] for row in result['inventory']
                                    if row['item'] == 'minecraft:oak_planks'))
            self.assertTrue(bridge.calls)
            self.assertEqual(content, path.read_text())
            with self.assertRaisesRegex(RuntimeError, 'Safety lock active'):
                require_unlocked(bridge.root, result)

    def test_workbench_sdk_uses_the_same_trial_authorization_with_old_hold_preserved(self):
        with tempfile.TemporaryDirectory() as game, patch('kit_runtime.inventory.time.sleep'):
            recipe = {2: 'minecraft:cobblestone', 5: 'minecraft:cobblestone', 8: 'minecraft:stick'}
            skills, bridge = fixtures.TrialSdkCraftTests().skills(
                game, 3, {'minecraft:cobblestone': 2, 'minecraft:stick': 1},
                recipe, 'minecraft:stone_sword')
            path, content = self.hold(bridge.root)
            result = skills.craft('stone_sword', {(0, 1): 'cobblestone',
                (1, 1): 'cobblestone', (2, 1): 'stick'})
            self.assertEqual(1, sum(row['count'] for row in result['inventory']
                                    if row['item'] == 'minecraft:stone_sword'))
            self.assertTrue(all(arguments['menu_id'] == 7 for _, arguments in bridge.calls))
            self.assertEqual(content, path.read_text())

    def test_other_world_run_session_and_native_scope_refuse_before_dispatch(self):
        cases = {
            'server': lambda current, bridge: current.update(server='example.org'),
            'world': lambda current, bridge: current.update(world_id='/tmp/OtherSave'),
            'unregistered': lambda current, bridge: current['trial_identity'].update(registered=False),
            'native run lost': lambda current, bridge: current['trial_identity'].update(run_id=''),
            'native run replaced': lambda current, bridge: current['trial_identity'].update(run_id='other-run'),
            'bridge run replaced': lambda current, bridge: setattr(bridge, 'run_id', 'other-run'),
            'session': lambda current, bridge: current.update(world_session='other-session'),
            'dimension': lambda current, bridge: current.update(dimension='minecraft:the_nether'),
            'process ended': lambda current, bridge: current['trial_identity'].update(process_alive=False),
            'native hold active': lambda current, bridge: current.update(safety_hold={'active': True}),
            'native hold absent': lambda current, bridge: current.pop('safety_hold'),
            'recovery hold': lambda current, bridge: current.update(health_recovery_hold=True),
            'manual input': lambda current, bridge: current.update(manual_movement=True),
            'revision': lambda current, bridge: current.update(control_revision=5),
            'registry disabled': lambda current, bridge: bridge.registry.update(enabled=False),
            'death opt-in removed': lambda current, bridge: bridge.registry.update(allow_death_respawn=False),
        }
        for label, change in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as game:
                current, bridge, client = self.fixture(game)
                path, content = self.hold(bridge.root)
                change(current, bridge)
                with self.assertRaises(Paused):
                    client.checked('slot_click', menu_id=0, slot=9)
                bridge.request.assert_not_called()
                self.assertEqual(content, path.read_text())

    def test_stale_and_future_observations_refuse_even_with_custom_reader(self):
        for stamp in (int(time.time() * 1000) - 4000, int(time.time() * 1000) + 10000):
            with self.subTest(stamp=stamp), tempfile.TemporaryDirectory() as game:
                current, bridge, client = self.fixture(game)
                current['time'] = stamp
                with self.assertRaisesRegex(Paused, 'fresh native observation'):
                    client.checked('slot_click', menu_id=0, slot=9)
                bridge.request.assert_not_called()

    def test_malformed_observation_cannot_authorize_sdk_inventory(self):
        for stamp in (None, True, float('nan')):
            with self.subTest(stamp=stamp), tempfile.TemporaryDirectory() as game:
                current, bridge, client = self.fixture(game)
                current['time'] = stamp
                with self.assertRaisesRegex(Paused, 'fresh native observation'):
                    client.authorize_inventory(current)
                bridge.request.assert_not_called()

    def test_default_material_executor_keeps_the_disk_hold_before_any_click(self):
        with tempfile.TemporaryDirectory() as game:
            root = Path(game)
            path, content = self.hold(root)
            client = Mock(root=root)
            client.status.return_value = {'safety_hold': {'active': False}}
            spec = {'width': 2, 'ingredients': {'minecraft:oak_log': [1]},
                    'output': 'minecraft:oak_planks', 'produces': 4}
            with self.assertRaisesRegex(RuntimeError, 'Safety lock active'):
                _inventory_execute(client, spec, 4)
            client.checked.assert_not_called()
            self.assertEqual(content, path.read_text())


if __name__ == '__main__':
    unittest.main()
