from collections import Counter
import math
import unittest

from singleplayer_trial_bridge import Paused
from survival_world import World, cell, center
from trial_safety_preparation import find_shelter_site, prepare_small_shelter, prepare_sword, shelter_site


def block(point, name='stone', **extra):
    return {'pos': list(point), 'state': 'Block{minecraft:' + name + '}',
            'solid': True, 'passable': False, 'fluid': False, 'block_entity': False, **extra}


class Skills:
    def __init__(self, inv=None):
        self.rows = {tuple(value['pos']): value for value in
                     [block((x, 0, z)) for x in range(-1, 2) for z in range(-1, 2)]
                     + [block((0, 0, z)) for z in (2, 3)]}
        self.inv = Counter(inv or {'dirt': 48, 'oak_door': 1})
        self.stations, self.owned, self.excluded = {}, {}, set()
        self.b = self
        self.halted, self.pending_mutations = False, {}
        self.events, self.placements, self.walks, self.interactions, self.recipes, self.gathers = [], [], [], [], [], []
        self.requests = []
        self.partial_scan = False
        self.unknown_mine = False
        self.fail_place, self.fail_gather = False, False
        self.state = {'world_id': '/tmp/trial-a', 'dimension': 'minecraft:overworld',
                      'world_session': 'session-a', 'control_revision': 1,
                      'pos': [.5, 1, 3.5], 'on_ground': True, 'time': 100}

    def read(self):
        return {**self.state, 'inventory': [{'item': 'minecraft:' + item, 'count': n}
                                          for item, n in self.inv.items() if n]}
    def scan(self):
        x, y, z = cell(self.state['pos'])
        return World(list(self.rows.values()), [x - 10, y - 6, z - 10], [x + 10, y + 6, z + 10])
    def request(self, op, **arguments):
        self.requests.append((op, arguments))
        if op == 'scan':
            low, high = arguments['min'], arguments['max']
            volume = math.prod(b - a + 1 for a, b in zip(low, high))
            rows = [value for value in self.rows.values()
                    if all(a <= p <= b for a, p, b in zip(low, value['pos'], high))]
            return {**self.read(), 'blocks': rows, 'scan_cells_read': volume - int(self.partial_scan),
                    'scan_total_cells': volume}
        if op == 'mine_block':
            point = tuple(arguments['pos'])
            if self.rows[point]['state'] != arguments['expected_state']: raise AssertionError('Stale mining state')
            if not self.unknown_mine: self.rows.pop(point)
            return {'phase': 'waiting' if self.unknown_mine else 'done', 'id': 'plant-mine',
                    'server_confirmed': not self.unknown_mine, 'outcome_pending': self.unknown_mine}
        raise AssertionError(op)
    def event(self, kind, **data): self.events.append((kind, data))
    def gather(self, names, wanted, total):
        self.gathers.append((names, wanted, total))
        if self.fail_gather: raise Paused('No reachable dirt')
        item = next(iter(wanted))
        self.inv[item] += max(0, total - sum(self.inv[name] for name in wanted))
    def planks(self, amount):
        while self.inv['oak_planks'] < amount:
            if not self.inv['oak_log']: raise Paused('No carried wood')
            self.craft('oak_planks', {(0, 0): 'oak_log'}, width=2, produces=4)
        return 'oak_planks'
    def sticks(self, amount):
        while self.inv['stick'] < amount:
            plank = self.planks(2)
            self.craft('stick', {(0, 0): plank, (1, 0): plank}, width=2, produces=4)
    def craft(self, output, cells, width=3, produces=1):
        self.recipes.append((output, width, produces))
        needed = Counter(cells.values())
        if any(self.inv[item] < count for item, count in needed.items()): raise Paused('Missing actual ingredients')
        self.inv.subtract(needed)
        self.inv[output] += produces
    def place(self, item, point):
        point = tuple(point)
        if self.scan().name(point) == item: return
        self.placements.append((item, point))
        if self.fail_place:
            self.pending_mutations['placement'] = {'op': 'interact'}
            raise Paused('Unknown native placement')
        if not self.inv[item]: raise AssertionError('No real placement stock')
        if self.scan().name(point) != 'air': raise AssertionError('Cannot overwrite a block')
        self.inv[item] -= 1
        self.rows[point] = block(point, item)
        self.owned[','.join(map(str, point))] = item
        if item.endswith('_door'):
            for height, half in ((point[1], 'lower'), (point[1] + 1, 'upper')):
                pos = (point[0], height, point[2])
                self.rows[pos] = block(pos, item, solid=False,
                    state='Block{minecraft:' + item + '}[half=' + half + ',open=false]')
            self.state['pos'] = [.5, 1, 3.5]  # Exercise actual entry after outside door placement.
    def go_near(self, target):
        world = self.scan()
        parents = world.paths(self.state['pos'])
        stance = world.approach(parents, tuple(target))
        if stance is None: raise Paused('No safe door approach')
        self.walk(world.route(parents, stance))
    def walk(self, route):
        self.walks.append(route)
        if route: self.state['pos'] = center(route[-1])
    def interact(self, point, **unused):
        self.interactions.append(tuple(point))
        for height in (point[1], point[1] + 1):
            value = self.rows[(point[0], height, point[2])]
            value['state'] = value['state'].replace('open=false', 'open=true') if 'open=false' in value['state'] else value['state'].replace('open=true', 'open=false')
    def select(self, item): self.selected = item


class SafetyPreparationTests(unittest.TestCase):
    def distant_land(self):
        skills = Skills()
        skills.state['pos'] = [.5, 1, .5]
        skills.rows = {tuple(value['pos']): value for value in
                       [block((x, 0, 0)) for x in range(13)]
                       + [block((x, 0, z)) for x in range(13, 16) for z in range(-1, 2)]}
        return skills

    def test_seaside_local_no_site_uses_one_complete_bounded_scan_and_normal_walk_to_land(self):
        skills = self.distant_land()
        self.assertIsNone(shelter_site(skills.scan(), skills.state['pos'], max_distance=10))
        plan = find_shelter_site(skills)
        self.assertEqual([14, 1, 0], plan['inside'])
        self.assertEqual([14.5, 1, .5], skills.state['pos'])
        self.assertEqual(['scan'], [op for op, unused in skills.requests])
        bounds = skills.requests[0][1]
        self.assertEqual(18_513, math.prod(b - a + 1 for a, b in zip(bounds['min'], bounds['max'])))
        self.assertLessEqual(len(skills.walks[0]), 32)
        self.assertEqual([], skills.placements)

    def test_partial_extended_scan_does_not_walk_or_clear_plants(self):
        skills = self.distant_land()
        skills.partial_scan = True
        with self.assertRaisesRegex(Paused, 'partial'):
            find_shelter_site(skills)
        self.assertEqual([], skills.walks)
        self.assertEqual([], skills.placements)
        self.assertEqual(['scan'], [op for op, unused in skills.requests])

    def test_natural_low_plant_is_cleared_only_after_confirmed_mining_and_crops_owned_are_refused(self):
        for name in ('short_grass', 'leaf_litter', 'fern'):
            with self.subTest(name=name):
                skills = Skills()
                skills.rows[(0, 1, 0)] = block((0, 1, 0), name, solid=False, passable=True)
                plan = find_shelter_site(skills)
                self.assertEqual([0, 1, 0], plan['inside'])
                self.assertNotIn((0, 1, 0), skills.rows)
                self.assertEqual(1, sum(op == 'mine_block' for op, unused in skills.requests))
        for name, protected in (('wheat', set()), ('flower_pot', set()), ('fern', {(0, 1, 0)})):
            skills = Skills()
            skills.rows[(0, 1, 0)] = block((0, 1, 0), name, solid=False, passable=True)
            self.assertIsNone(shelter_site(skills.scan(), skills.state['pos'], protected, allow_plants=True))

    def test_unknown_natural_plant_mining_is_not_replayed(self):
        skills = Skills()
        skills.rows[(0, 1, 0)] = block((0, 1, 0), 'short_grass', solid=False, passable=True)
        skills.unknown_mine = True
        with self.assertRaisesRegex(Paused, 'unconfirmed'):
            find_shelter_site(skills)
        with self.assertRaisesRegex(Paused, 'preserved'):
            find_shelter_site(skills)
        self.assertEqual(1, sum(op == 'mine_block' for op, unused in skills.requests))

    def test_site_is_23_blocks_with_supported_door_and_rejects_protected_or_unknown_floor(self):
        skills = Skills()
        plan = shelter_site(skills.scan(), skills.state['pos'])
        self.assertEqual([0, 1, 0], plan['inside'])
        self.assertEqual(23, len(plan['layout']))
        self.assertEqual(9, len(plan['floor']))
        self.assertNotIn(plan['door'], plan['layout'])
        self.assertIsNone(shelter_site(skills.scan(), skills.state['pos'], {(0, 0, 0)}))
        skills.rows.pop((-1, 0, -1))
        self.assertIsNone(shelter_site(skills.scan(), skills.state['pos']))

    def test_actual_supported_house_is_entered_and_door_freshly_closed_without_extra_gather(self):
        skills = Skills()
        result = prepare_small_shelter(skills)
        self.assertTrue(result['verified'])
        self.assertEqual([.5, 1, .5], skills.state['pos'])
        self.assertEqual(23, sum(item == 'dirt' for item, unused in skills.placements))
        self.assertEqual(25, skills.inv['dirt'])
        self.assertEqual([], skills.gathers)
        self.assertEqual(2, len(skills.interactions))
        self.assertIn('open=false', skills.rows[(0, 1, 1)]['state'])
        self.assertEqual('small_shelter_entered_and_closed', skills.events[-1][0])

    def test_only_missing_dirt_is_gathered_and_missing_door_uses_real_six_plank_recipe(self):
        skills = Skills({'dirt': 5, 'oak_log': 2})
        prepare_small_shelter(skills)
        self.assertEqual([({'dirt', 'grass_block'}, {'dirt'}, 23)], skills.gathers)
        self.assertIn(('oak_door', 3, 3), skills.recipes)
        self.assertEqual(2, skills.inv['oak_door'])

    def test_missing_material_and_unknown_placement_do_not_start_or_replay_construction(self):
        skills = Skills({'dirt': 5, 'oak_door': 1})
        skills.fail_gather = True
        with self.assertRaises(Paused): prepare_small_shelter(skills)
        self.assertEqual([], skills.placements)
        skills = Skills()
        skills.fail_place = True
        with self.assertRaises(Paused): prepare_small_shelter(skills)
        with self.assertRaisesRegex(Paused, 'preserved'): prepare_small_shelter(skills)
        self.assertEqual(1, len(skills.placements))
        self.assertEqual([], skills.interactions)

    def test_sword_prefers_carried_then_stone_and_wood_without_upgrade_mining(self):
        for stock, expected in (({'iron_sword': 1}, 'iron_sword'),
                                ({'cobblestone': 2, 'stick': 1}, 'stone_sword'),
                                ({'oak_log': 1}, 'wooden_sword')):
            with self.subTest(expected=expected):
                skills = Skills(stock)
                result = prepare_sword(skills)
                self.assertEqual(expected, result['item'])
                self.assertEqual(expected, skills.selected)
                self.assertEqual([], skills.gathers)
                if expected == 'iron_sword': self.assertEqual([], skills.recipes)

    def test_explicit_stone_upgrade_acquires_only_missing_stone_and_retains_wood_sword(self):
        skills = Skills({'wooden_sword': 1, 'cobblestone': 1, 'stick': 3})
        result = prepare_sword(skills, upgrade_stone=True)
        self.assertEqual('stone_sword', result['item'])
        self.assertEqual([({'stone', 'cobblestone'}, {'cobblestone'}, 2)], skills.gathers)
        self.assertEqual(1, skills.inv['wooden_sword'])
        self.assertEqual(1, skills.inv['stone_sword'])
        self.assertEqual('stone_sword', skills.selected)
        skills = Skills({'iron_sword': 1})
        self.assertEqual('iron_sword', prepare_sword(skills, upgrade_stone=True)['item'])
        self.assertEqual([], skills.gathers)
        self.assertEqual([], skills.recipes)

    def test_failed_stone_acquisition_preserves_the_working_sword(self):
        skills = Skills({'wooden_sword': 1, 'cobblestone': 1, 'stick': 3})
        skills.fail_gather = True
        with self.assertRaises(Paused): prepare_sword(skills, upgrade_stone=True)
        self.assertEqual(1, skills.inv['wooden_sword'])
        self.assertEqual([], skills.recipes)


if __name__ == '__main__':
    unittest.main()
