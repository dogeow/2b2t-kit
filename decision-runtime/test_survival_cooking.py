"""Current-JAR cooking plans and real SDK clicks in an ordinary-slot fixture."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from survival import Runner
from survival_bridge import Paused, inventory
from survival_cooking import cooking_plan, RAW
from test_inventory_session import Client as SlotClient

JAR = Path('/Applications/.minecraft/versions/26.1.2/26.1.2.jar')


def snapshot(items, entities=None):
    return {'inventory': [{'slot': i, 'item': 'minecraft:' + item, 'count': count}
                          for i, (item, count) in enumerate(items.items())],
            'pos': [0.5, 1, 0.5], 'entities': entities or []}


class FurnaceBridge:
    def __init__(self, root, items):
        self.root = Path(root);self.world = 'Trial';self.origin = [.5, 1, .5]
        self.core = SlotClient(furnace=True)
        self.core.state['menu']['slots'] = [dict(slot=i, item='minecraft:air', count=0, max_stack=64)
                                           for i in range(39)]
        for i, (item, count) in enumerate(items.items(), 3):
            self.core.state['menu']['slots'][i].update(item='minecraft:' + item, count=count)
        self.requests = [];self.halted = False;self.fail_fuel = False
        self.wrong_output = False;self.delay_food = False
        self.fuel_deposits = 0;self.fail_fuel_number = None;self.second_fuel_gap = False
        self.fuel_ticks = 0;self.clock = None
        self.close_count = 0;self.fail_partial_raw_return = False
        self.read()

    def read(self):
        menu = copy.deepcopy(self.core.state['menu'])
        self.state = {'world_id': '/saves/Trial', 'world_session': 's', 'control_revision': 2,
            'connected': True, 'pos': [.5, 1, .5], 'menu': menu,
            'inventory': [dict(row, slot=i) for i, row in enumerate(menu['slots'][3:])], 'entities': []}
        return self.state

    def open(self):
        self.core.state['menu']['id'] += 1;self.core.burned = 0;self.fuel_ticks = 0
        return self.read()

    def close(self):self.close_count += 1
    def wait(self, seconds):
        if self.clock is not None:self.clock[0] += seconds
        self.read()

    @staticmethod
    def duration(item):
        if item in ('minecraft:coal', 'minecraft:charcoal'):return 1600
        if item in ('minecraft:leaf_litter', 'minecraft:stick'):return 100
        return 300

    def _cook(self):
        menu = self.core.state['menu'];inp, fuel, out = menu['slots'][:3]
        if not inp['count'] or self.delay_food:
            return
        source = inp['item']
        while inp['count']:
            if self.fuel_ticks < 200:
                if not fuel['count']:break
                self.fuel_ticks += self.duration(fuel['item']);fuel['count'] -= 1
                if not fuel['count']:fuel['item'] = 'minecraft:air'
            if self.fuel_ticks < 200:continue
            self.fuel_ticks -= 200;inp['count'] -= 1
            out.update(item='minecraft:diamond' if self.wrong_output else RAW[source], count=out['count'] + 1)
            if not inp['count']:inp['item'] = 'minecraft:air'

    def request(self, op, **args):
        self.requests.append((op, args))
        if op != 'slot_click':raise AssertionError('Only ordinary SDK clicks are expected')
        menu = self.core.state['menu'];row = menu['slots'][args['slot']]
        assert (row['item'], row['count']) == (args['expected_item'], args['expected_count'])
        if args.get('kind') == 'quick_move':
            for dest in sorted(menu['slots'][3:], key=lambda r: not r['count']):
                if dest['count'] and dest['item'] != row['item']:continue
                moved = min(row['count'], 64 - dest['count'])
                dest.update(item=row['item'], count=dest['count'] + moved);row['count'] -= moved
                if not row['count']:
                    row['item'] = 'minecraft:air';break
        else:
            if args['slot'] == 1 and menu['cursor']['count']:
                self.last_fuel = menu['cursor']['item']
                self.fuel_deposits += 1
                if self.second_fuel_gap and self.fuel_deposits == 2:
                    # Burning stopped long enough for the fractional recipe
                    # progress to cool. Nominal total fuel still equals800.
                    self.fuel_ticks = 0
                before_fuel = row['count'];deposited = menu['cursor']['count']
                if not before_fuel:self.core.burned = 0
            else:before_fuel = deposited = None
            self.core.checked(op, **args)
            if deposited is not None:
                consumed = before_fuel + deposited - menu['slots'][1]['count']
                self.fuel_ticks += consumed * self.duration(self.last_fuel)
        self._cook()
        if args['slot'] == 0 and args.get('kind') == 'quick_move' and self.fail_partial_raw_return:
            raise Paused('Partial raw return outcome unknown')
        if args['slot'] == 1 and (self.fail_fuel or self.fuel_deposits == self.fail_fuel_number):
            raise Paused('Fuel click outcome unknown')
        return self.read()


class CookingRunner(Runner):
    recipe_jar = JAR
    def station(self, name):
        self.asserted_station = name;self.stations[name] = [1, 1, 0];self.b.open()
    def check(self):self.b.read()


@unittest.skipUnless(JAR.is_file(), 'Current Minecraft recipe/fuel JAR unavailable')
class CookingPlanTests(unittest.TestCase):
    def test_current_mixed_owned_fuels_cover_four_food_without_new_coal(self):
        plan = cooking_plan(snapshot({'beef': 3, 'mutton': 2, 'dark_oak_planks': 1,
                                     'leaf_litter': 3, 'stick': 2}), JAR)
        self.assertTrue(plan['ready']);self.assertTrue(plan['fuel_ready'])
        self.assertEqual(plan['coal_requirement'], 0);self.assertEqual(plan['missing'], {})
        self.assertEqual([(r['fuel_item'], r['fuel_count']) for r in plan['batches'][0]['fuel_stages']],
                         [('minecraft:dark_oak_planks', 1), ('minecraft:leaf_litter', 3)])
        self.assertEqual(plan['batches'][1]['amount'], 1)
        self.assertEqual(plan['batches'][1]['fuel_stages'],
                         [{'fuel_item': 'minecraft:stick', 'fuel_count': 2, 'burn_ticks_per_fuel': 100}])
        self.assertTrue(plan['evidence']['extra_fuels_verified'])

    def test_owned_fuel_shortage_still_requires_real_coal_before_cooking(self):
        plan = cooking_plan(snapshot({'beef': 3, 'mutton': 2, 'dark_oak_planks': 1}), JAR)
        self.assertFalse(plan['ready']);self.assertFalse(plan['fuel_ready'])
        self.assertEqual(plan['coal_requirement'], 1)
        self.assertEqual(plan['missing'], {'minecraft:coal': 1})
        self.assertEqual([(r['source'], r['amount'], r['fuel_item'], r['fuel_count']) for r in plan['batches']],
            [('minecraft:beef', 3, 'minecraft:coal', 1),
             ('minecraft:mutton', 1, 'minecraft:dark_oak_planks', 1)])
        self.assertTrue(plan['evidence']['extra_fuels_verified'])
        self.assertEqual({r['cooking_ticks'] for r in plan['batches']}, {200})

    def test_existing_charcoal_is_used_without_new_wood_or_coal(self):
        plan = cooking_plan(snapshot({'beef': 4, 'charcoal': 1}), JAR)
        self.assertTrue(plan['ready']);self.assertEqual(plan['coal_requirement'], 0)
        self.assertEqual(plan['batches'][0]['fuel_item'], 'minecraft:charcoal')

    def test_four_raw_meat_need_only_three_existing_planks(self):
        plan = cooking_plan(snapshot({'beef': 4, 'oak_planks': 3}), JAR)
        self.assertTrue(plan['ready']);self.assertEqual(plan['batches'][0]['fuel_count'], 3)

    def test_known_log_can_fuel_owned_food_without_crafting_planks(self):
        plan = cooking_plan(snapshot({'beef': 4, 'oak_log': 3}), JAR)
        self.assertTrue(plan['ready']);self.assertEqual(plan['batches'][0]['fuel_item'], 'minecraft:oak_log')

    def test_separate_recipe_batches_do_not_guess_lit_fuel_time(self):
        plan = cooking_plan(snapshot({'beef': 2, 'mutton': 2, 'coal': 1}), JAR)
        self.assertFalse(plan['ready']);self.assertEqual(plan['coal_requirement'], 2)
        self.assertEqual([r['fuel_count'] for r in plan['batches']], [1, 1])

    def test_owned_cooked_food_reduces_exact_requested_meat_and_fuel(self):
        plan = cooking_plan(snapshot({'cooked_beef': 3, 'mutton': 6, 'oak_planks': 1}), JAR)
        self.assertTrue(plan['ready']);self.assertEqual(plan['batches'][0]['amount'], 1)
        self.assertEqual(plan['batches'][0]['fuel_count'], 1)

    def test_tools_and_nether_wood_are_not_silently_burned(self):
        plan = cooking_plan(snapshot({'beef': 4, 'wooden_pickaxe': 1,
                                       'warped_planks': 5, 'crimson_stem': 4}), JAR)
        self.assertFalse(plan['ready']);self.assertEqual(plan['missing'], {'minecraft:coal': 1})

    def test_hunting_fuel_is_forecast_before_attacking_and_raw_is_never_claimed_owned(self):
        cow = {'type': 'minecraft:cow', 'health': 10, 'pos': [1, 1, 0]}
        plan = cooking_plan(snapshot({'oak_planks': 1}, [cow]), JAR)
        self.assertFalse(plan['ready']);self.assertFalse(plan['fuel_ready'])
        self.assertEqual(plan['raw_needed'], 4);self.assertEqual(plan['coal_requirement'], 1)
        self.assertEqual(plan['hunting_source'], 'minecraft:beef')
        self.assertEqual(plan['batches'][0]['unowned_input'], 4)

    def test_changed_fuel_semantics_fail_closed_before_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            import zipfile
            jar = Path(tmp) / 'unverified.jar'
            with zipfile.ZipFile(jar, 'w') as archive:
                archive.writestr('version.json', '{"id":"26.1.2"}')
                archive.writestr('net/minecraft/world/level/block/entity/FuelValues.class', b'changed')
            with self.assertRaises(ValueError):cooking_plan(snapshot({'beef': 4, 'coal': 1}), jar)


@unittest.skipUnless(JAR.is_file(), 'Current Minecraft recipe/fuel JAR unavailable')
class CookingSDKTests(unittest.TestCase):
    def test_four_food_precise_sdk_transfers_and_conservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = FurnaceBridge(tmp, {'beef': 4, 'oak_planks': 3, 'diamond': 2})
            runner = CookingRunner(bridge, None, tmp);runner.food()
            self.assertEqual(inventory(bridge.read()), {'cooked_beef': 4, 'diamond': 2})
            self.assertEqual(bridge.state['menu']['cursor']['count'], 0)
            record = json.loads(next((Path(tmp) / 'cooking').glob('batch-*.json')).read_text())
            self.assertTrue(record['complete']);self.assertIsNone(record['pending'])
            self.assertEqual((record['loaded_source'], record['loaded_fuel']), (4, 3))
            self.assertEqual((record['fuel_consumed'], record['fuel_returned']), (3, 0))

    def test_mixed_meat_target_four_leaves_the_extra_raw_meat_and_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = FurnaceBridge(tmp, {'beef': 3, 'mutton': 2, 'coal': 1,
                                         'dark_oak_planks': 1, 'stick': 2, 'wooden_pickaxe': 1})
            CookingRunner(bridge, None, tmp).food()
            self.assertEqual(inventory(bridge.read()), {'cooked_beef': 3, 'cooked_mutton': 1,
                                                       'mutton': 1, 'stick': 2, 'wooden_pickaxe': 1})
            records = [json.loads(p.read_text()) for p in (Path(tmp) / 'cooking').glob('batch-*.json')]
            self.assertEqual(len(records), 2);self.assertTrue(all(r['complete'] for r in records))

    def test_owned_mixed_fuel_stages_make_actual_four_food_and_preserve_extra_meat(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = FurnaceBridge(tmp, {'beef': 3, 'mutton': 2, 'dark_oak_planks': 1,
                                         'leaf_litter': 3, 'stick': 2})
            CookingRunner(bridge, None, tmp).food()
            self.assertEqual(inventory(bridge.read()), {'cooked_beef': 3, 'cooked_mutton': 1, 'mutton': 1})
            records = [json.loads(p.read_text()) for p in (Path(tmp) / 'cooking').glob('batch-*.json')]
            beef = next(r for r in records if r['batch']['source'] == 'minecraft:beef')
            self.assertEqual([(s['fuel_item'], s['loaded'], s['consumed']) for s in beef['fuel_stages']],
                             [('minecraft:dark_oak_planks', 1, 1), ('minecraft:leaf_litter', 3, 3)])
            self.assertTrue(all(r['complete'] for r in records))

    def test_second_fuel_unknown_keeps_stage_intent_and_never_replays(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = FurnaceBridge(tmp, {'beef': 3, 'mutton': 2, 'dark_oak_planks': 1,
                                         'leaf_litter': 3, 'stick': 2})
            bridge.fail_fuel_number = 2;runner = CookingRunner(bridge, None, tmp)
            with self.assertRaisesRegex(Paused, 'journal retained'):runner.food()
            record = json.loads(next((Path(tmp) / 'cooking').glob('batch-*.json')).read_text())
            self.assertEqual(record['active_fuel_index'], 1)
            self.assertEqual(record['pending']['fuel_stage_index'], 1)
            self.assertEqual(record['pending']['item'], 'minecraft:leaf_litter')
            self.assertEqual(record['fuel_stages'][0]['loaded'], 1)
            self.assertEqual(record['fuel_stages'][1]['loaded'], 0)
            calls = len(bridge.requests);bridge.fail_fuel_number = None
            with self.assertRaisesRegex(Paused, 'without replay'):runner.food()
            self.assertEqual(len(bridge.requests), calls)

    def test_interrupted_exact_budget_records_actual_partial_output_and_never_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = FurnaceBridge(tmp, {'beef': 3, 'mutton': 2, 'dark_oak_planks': 1,
                                         'leaf_litter': 3, 'stick': 2})
            bridge.second_fuel_gap = True;bridge.clock = [0.0]
            runner = CookingRunner(bridge, None, tmp)
            with patch('survival_cooking.time.monotonic', side_effect=lambda: bridge.clock[0]):
                with self.assertRaisesRegex(Paused, 'only 2/3'):runner.food()
            record = json.loads(next((Path(tmp) / 'cooking').glob('batch-*.json')).read_text())
            self.assertEqual(record['stage'], 'partial_reconciled');self.assertFalse(record['complete'])
            self.assertIsNone(record['pending']);self.assertFalse(bridge.halted)
            self.assertEqual(record['observed_raw_remaining'], 1)
            self.assertEqual(record['observed_output_in_furnace'], 2)
            self.assertEqual(inventory(bridge.read()).get('cooked_beef', 0), 2)
            self.assertEqual(inventory(bridge.read())['beef'], 1)
            self.assertEqual(inventory(bridge.read())['mutton'], 2)
            self.assertEqual((record['reconciled_output_count'], record['reconciled_raw_count']), (2, 1))
            self.assertTrue(record['reconciled']);self.assertEqual(bridge.close_count, 1)
            # Known partial items are now back in inventory and the owned UI
            # is closed. Its original journal does not block a fuel replan.
            before_calls = len(bridge.requests)
            with self.assertRaisesRegex(Paused, '背包煤目标'):runner.food()
            self.assertEqual(len(bridge.requests), before_calls)

    def test_unknown_partial_recovery_keeps_intent_and_cannot_close_or_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = FurnaceBridge(tmp, {'beef': 3, 'mutton': 2, 'dark_oak_planks': 1,
                                         'leaf_litter': 3, 'stick': 2})
            bridge.second_fuel_gap = True;bridge.fail_partial_raw_return = True;bridge.clock = [0.0]
            runner = CookingRunner(bridge, None, tmp)
            with patch('survival_cooking.time.monotonic', side_effect=lambda: bridge.clock[0]):
                with self.assertRaisesRegex(Paused, 'recovery stopped'):runner.food()
            record = json.loads(next((Path(tmp) / 'cooking').glob('batch-*.json')).read_text())
            self.assertFalse(record['reconciled']);self.assertFalse(record['complete']);self.assertTrue(bridge.halted)
            self.assertEqual(record['pending']['op'], 'recover_known_partial')
            self.assertEqual(record['pending']['item'], 'minecraft:beef')
            self.assertEqual(bridge.close_count, 0);before_calls = len(bridge.requests)
            bridge.fail_partial_raw_return = False
            with self.assertRaisesRegex(Paused, 'without replay'):runner.food()
            self.assertEqual(len(bridge.requests), before_calls)

    def test_missing_fuel_never_opens_station_attacks_animals_or_loads_partial_meat(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = FurnaceBridge(tmp, {'beef': 3, 'mutton': 2, 'dark_oak_planks': 1})
            runner = CookingRunner(bridge, None, tmp)
            with self.assertRaisesRegex(Paused, '背包煤目标 1'):runner.food()
            self.assertFalse(hasattr(runner, 'asserted_station'));self.assertEqual(bridge.requests, [])
            self.assertEqual(inventory(bridge.read())['beef'], 3)

    def test_missing_fuel_is_checked_before_hunting_an_observed_cow(self):
        class ObservedCow(FurnaceBridge):
            def read(self):
                state = super().read()
                state['entities'] = [{'type': 'minecraft:cow', 'health': 10,
                                      'uuid': 'observed-cow', 'pos': [1, 1, 0]}]
                return state
        with tempfile.TemporaryDirectory() as tmp:
            bridge = ObservedCow(tmp, {'oak_planks': 1})
            with self.assertRaisesRegex(Paused, '背包煤目标 1'):CookingRunner(bridge, None, tmp).food()
            self.assertEqual(bridge.requests, [])

    def test_unknown_fuel_click_keeps_original_pending_intent_and_cannot_be_replayed(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = FurnaceBridge(tmp, {'beef': 4, 'coal': 1});bridge.fail_fuel = True
            runner = CookingRunner(bridge, None, tmp)
            with self.assertRaisesRegex(Paused, 'original furnace journal'):runner.food()
            record = json.loads(next((Path(tmp) / 'cooking').glob('batch-*.json')).read_text())
            self.assertFalse(record['complete']);self.assertEqual(record['stage'], 'fuel_loading')
            self.assertEqual(record['pending']['item'], 'minecraft:coal');calls = len(bridge.requests)
            bridge.fail_fuel = False
            with self.assertRaisesRegex(Paused, 'without replay'):runner.food()
            self.assertEqual(len(bridge.requests), calls)

    def test_foreign_initial_furnace_contents_are_preserved_without_sdk_clicks(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = FurnaceBridge(tmp, {'beef': 4, 'coal': 1})
            bridge.core.state['menu']['slots'][2].update(item='minecraft:diamond', count=1)
            with self.assertRaisesRegex(Paused, 'existing contents'):CookingRunner(bridge, None, tmp).food()
            self.assertEqual(bridge.requests, []);self.assertEqual(bridge.core.state['menu']['slots'][2]['count'], 1)

    def test_foreign_output_during_loading_fails_conservation_and_retains_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = FurnaceBridge(tmp, {'beef': 4, 'coal': 1});bridge.wrong_output = True
            with self.assertRaisesRegex(Paused, 'journal retained'):CookingRunner(bridge, None, tmp).food()
            record = json.loads(next((Path(tmp) / 'cooking').glob('batch-*.json')).read_text())
            self.assertFalse(record['complete']);self.assertTrue(record['pending'])
            self.assertFalse(any(args.get('kind') == 'quick_move' for _, args in bridge.requests))


class OwnedFoodTests(unittest.TestCase):
    def test_already_owned_food_needs_no_jar_or_new_fuel(self):
        plan = cooking_plan(snapshot({'bread': 4}), None)
        self.assertTrue(plan['ready']);self.assertEqual(plan['batches'], [])


if __name__ == '__main__':unittest.main()
