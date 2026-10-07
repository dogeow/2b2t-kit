"""Kit-owned local Clef Flash survival experiment, independent of a chat window.

This is a real bootstrap and exploration controller, not a completed dragon
speedrunner. Unsupported progression remains visible as waiting_capability.
All world inputs are existing verified native skills; model output is a typed
choice among locally constructed macros and never executable code.
"""
import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import time

from decisions import DecisionError, choose, status, validated_answer
from ollama_decision import OllamaDecision, checked_image
from singleplayer_trial_bridge import (Paused, TrialBridge, TrialDeath, TrialMovementBlocked, validate_registry,
                                      validate_scope)
from survival import Runner, LOGS, FOOD
from survival_bridge import inventory
from survival_world import World, Paths, cell, center, distance, shelter
from singleplayer_trial_capabilities import capability_scene

GOAL = 'Defeat the Ender Dragon in this registered disposable Survival trial using normal game interactions.'
GAPS = ['nether_portal_construction', 'blaze_rod_collection', 'ender_pearl_collection',
        'stronghold_location_and_portal', 'end_crystal_and_dragon_combat']
LABELS = {
    'collect_log_drops': '先拾取本世界当前已确认的原木掉落并核对入包',
    'gather_starting_wood': '采集已观察到的开局木材并核对入包',
    'craft_wooden_tools': '实际合成工作台、木镐和所需木棍',
    'gather_stone': '用木镐采集已观察到的石料并核对入包',
    'craft_stone_tools': '实际合成石镐、石斧和熔炉',
    'gather_food': '正常获取附近食物并使用熔炉烹饪',
    'eat_carried_food': '正常食用背包内已确认的食物',
    'gather_shelter_material': '采集小庇护所材料，不挖脚底和工作设施',
    'build_shelter': '实际搭建和验证小庇护所',
    'prepare_iron_equipment': '采集露天铁矿、熔炼、合成和穿戴铁装备',
    'explore_nearby': '沿扫描验证的正常步行路线探索附近资源',
    'recover_after_death': '记录已发生死亡后通过原生正常复活继续试验',
    'wait': '当前没有可信宏动作推进目标；等待新证据或缺失能力',
}
CRITERIA = {
    'collect_log_drops': 'Collect currently observed log item drops first using the checked normal walking route. Verify actual logs gained in inventory; item existence or a mining ACK is not pickup success.',
    'gather_starting_wood': 'Collect the needed logs from trees already observed as reachable nearby. Prefer using this available wood over exploring for other wood.',
    'craft_wooden_tools': 'Use the carried logs or planks to craft a crafting table and wooden pickaxe now, before looking for more resources.',
    'gather_stone': 'Use the available pickaxe to collect the needed cobblestone from already observed reachable stone.',
    'craft_stone_tools': 'Use carried cobblestone and wood to craft the missing stone tools and furnace now.',
    'gather_food': 'Get food from observed nearby animals and cook it in the available furnace.',
    'eat_carried_food': 'Eat already carried food to restore hunger before another macro.',
    'gather_shelter_material': 'Collect the missing dirt from observed reachable ground for the verified shelter plan.',
    'build_shelter': 'Use carried building material to construct and verify the observed shelter plan.',
    'prepare_iron_equipment': 'Use the observed iron materials and normal crafting to obtain and equip iron gear.',
    'explore_nearby': 'Explore a new scanned safe route when no carried-material or reachable-resource macro can meet the current short-term goal.',
    'wait': 'Wait if none of the offered macros can advance the short-term goal or the observations conflict.',
}


def short_term_goal(state, candidates, pending_log_drops=0):
    """Derive one immediate milestone from actual stock and prechecked macros."""
    inv = inventory(state)
    if 'collect_log_drops' in candidates:
        return 'Pick up the already observed reachable dropped logs and verify actual inventory gain before chopping another tree or exploring elsewhere.'
    if pending_log_drops and 'explore_nearby' in candidates:
        return 'Follow the scanned normal ground route toward the already observed dropped logs and reobserve the items before pickup. Do not cut another tree or explore away.'
    if 'eat_carried_food' in candidates and state.get('food', 20) < 16:
        return 'Eat carried food now to restore hunger before continuing Survival preparation.'
    starting = not any(inv.get(name) for name in ('wooden_pickaxe', 'stone_pickaxe', 'iron_pickaxe'))
    if starting:
        if 'craft_wooden_tools' in candidates:
            return 'Craft a crafting table and wooden pickaxe now using the already carried wood, before exploring.'
        if 'gather_starting_wood' in candidates:
            return 'Collect starting logs from the already observed reachable nearby trees and verify the inventory gain. Prioritize gathering this wood over exploration.'
        return 'Find reachable starting wood along a newly scanned safe walking route.'
    goals = (
        ('craft_stone_tools', 'Craft the missing stone pickaxe, stone axe and furnace now from carried materials.'),
        ('gather_stone', 'Collect the needed cobblestone from already observed reachable stone for stone tools and a furnace.'),
        ('gather_food', 'Obtain and cook a reserve of food from the observed nearby food source.'),
        ('gather_starting_wood', 'Replenish logs from the already observed reachable nearby trees for crafting and cooking.'),
        ('build_shelter', 'Build and verify the available shelter plan using the carried construction materials.'),
        ('gather_shelter_material', 'Collect the missing material from nearby observed ground for the shelter plan.'),
        ('prepare_iron_equipment', 'Obtain, craft and equip the missing iron equipment using the observed ore or carried iron.'),
    )
    for action, goal in goals:
        if action in candidates:
            return goal
    if not inv.get('stone_pickaxe') and not inv.get('iron_pickaxe'):
        return 'Find reachable stone for the next stone tools and furnace along a scanned safe route.'
    if sum(inv.get(name, 0) for name in FOOD) < 4:
        return 'Find an accessible food source along a newly scanned safe route.'
    if 'explore_nearby' in candidates:
        return 'Explore a newly scanned safe route for the next missing Survival resources without repeating refused routes.'
    return 'Wait for new observations or a supported macro that advances the next Survival milestone.'


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temp.replace(path)


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def dead(state):
    return state.get('player_dead') is True or state.get('health', 0) <= 0


class TrialWorld(World):
    def safe_two_block_descent(self, source, target, actual=None):
        if (source[1] - target[1] != 2 or abs(source[0] - target[0]) + abs(source[2] - target[2]) != 1
                or not self.stand(source) or not self.stand(target)
                or self.row((target[0], target[1] - 1, target[2])).get('block_entity')):
            return False
        if actual is not None and (math.hypot(actual[0] - source[0] - .5, actual[2] - source[2] - .5) > .2
                                   or abs(actual[1] - source[1]) > .2):
            return False
        # At centred waypoints the 0.6-wide body fits inside each column. The
        # landing column's entire falling body/head sweep must remain known,
        # dry and open; vanilla collision still owns the actual movement.
        return all(self.open((target[0], height, target[2]))
                   for height in range(target[1], source[1] + 2))

    def pickup_paths(self, start, limit=2500):
        parents = self.paths(start, limit)
        queue = deque(parents)
        while queue and len(parents) < limit:
            source = queue.popleft()
            x, y, z = source
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                for dy in (0, 1, -1, -2):
                    target = (x + dx, y + dy, z + dz)
                    if target in parents or not self.stand(target):
                        continue
                    if dy == -2 and not self.safe_two_block_descent(source, target):
                        continue
                    if dy == 1 and not self.open((x, y + 2, z)):
                        continue
                    if dy == -1 and not self.open((x + dx, y + 1, z + dz)):
                        continue
                    parents[target] = source
                    queue.append(target)
                    break
        return parents

    def sight(self, feet, target):
        # These plants allow walking but their OUTLINE shapes can intercept a
        # vanilla dig ray. Choose a clear stance instead of treating them as
        # mining air. No grass removal is counted as gathered wood.
        start = [feet[0] + .5, feet[1] + 1.62, feet[2] + .5]
        end = [v + .5 for v in target]
        steps = max(2, math.ceil(distance(start, end) * 10))
        for index in range(1, steps):
            ratio = index / steps
            position = cell([a + (b - a) * ratio for a, b in zip(start, end)])
            if position == tuple(target):
                return True
            if self.name(position) in {'short_grass', 'tall_grass', 'fern', 'large_fern'} or not self.open(position):
                return False
        return True

    def resource(self, feet, names, excluded=()):
        if not set(names).issubset(LOGS):
            return super().resource(feet, names, excluded)
        # Logs float naturally; safely exposed trunk sides can be broken first.
        # The old earth/stone top-down rule prevented bare-handed high trees.
        paths = self.paths(feet)
        choices = []
        for point, row in self.blocks.items():
            if point in excluded or self.name(point) not in names or row.get('block_entity'):
                continue
            if point == (math.floor(feet[0]), math.floor(feet[1]) - 1, math.floor(feet[2])):
                continue
            if any(not self.safe((point[0] + dx, point[1] + dy, point[2] + dz))
                   for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
                                      (0, -1, 0), (0, 0, 1), (0, 0, -1))):
                continue
            stance = self.approach(paths, point)
            if stance is not None:
                route = self.route(paths, stance)
                choices.append((len(route) + distance(feet, center(point)) * .1, point, route))
        return min(choices, default=(None, None, None))[1:] if choices else None


class TrialSkills(Runner):
    def __init__(self, bridge, output):
        super().__init__(bridge, None, output, max_minutes=15, max_calls=0)
        self.explored = set()
        self.explore_target = None
        self.station_anchor = None
        self.tried_grids = set()
        self.rejected_routes = set()
        self.log_drops = {}
        self.pickup_target = None

    def scan(self):
        self.check()
        x, y, z = cell(self.b.state['pos'])
        lo, hi = [x - 10, y - 6, z - 10], [x + 10, y + 6, z + 10]
        result = self.b.request('scan', min=lo, max=hi, details=True)
        self.world = TrialWorld(result['blocks'], lo, hi)
        return self.world

    def reset_budget(self):
        self.start = time.monotonic()
        self.deadline = self.start + 15 * 60

    def observe(self):
        world = self.scan()
        if self.camp is None:
            self.camp = world.camp(self.b.state['pos'])
        if self.station_anchor is None:
            paths = world.paths(self.b.state['pos'])
            anchor = min(paths, key=lambda p: distance(center(p), self.b.state['pos']), default=None)
            if anchor is not None:
                self.station_anchor = list(anchor)
        return world

    def remember_log_drops(self, state):
        now = state.get('time', 0)
        found = {}
        for entity in state.get('entities', []):
            stack = entity.get('stack', {})
            name = stack.get('item', '').removeprefix('minecraft:')
            pos, identity = entity.get('pos'), entity.get('uuid')
            if (entity.get('type') != 'minecraft:item' or name not in LOGS or not isinstance(identity, str)
                    or type(stack.get('count')) is not int or stack['count'] <= 0
                    or not isinstance(pos, list) or len(pos) != 3
                    or not all(type(n) in (int, float) and math.isfinite(n) for n in pos)):
                continue
            found[identity] = {'uuid': identity, 'item': name, 'count': stack['count'],
                               'pos': list(pos), 'observed_at': now, 'visible': entity.get('visible') is True}
        self.log_drops = {identity: row for identity, row in self.log_drops.items()
                          if 0 <= now - row.get('observed_at', 0) <= 240_000
                          and (identity in found or distance(row['pos'], state['pos']) > 13)}
        self.log_drops.update(found)
        return found

    def pickup_plan(self, world, state, rows=None):
        rows = rows if rows is not None else self.remember_log_drops(state)
        parents = world.pickup_paths(state['pos'])
        choices = []
        for row in rows.values():
            if row.get('visible') is not True:
                continue
            for stance in parents:
                pos = center(stance)
                if (math.hypot(pos[0] - row['pos'][0], pos[2] - row['pos'][2]) > .8
                        or not pos[1] - .35 <= row['pos'][1] <= pos[1] + 1.9):
                    continue
                route = world.route(parents, stance)
                if len(route) <= 32 and tuple(route) not in self.rejected_routes:
                    choices.append((len(route), row['uuid'], stance, route))
        return min(choices)[1:] if choices else None

    def walk_pickup_route(self, route):
        batch = []
        previous = cell(self.b.read()['pos'])
        for target in route:
            if previous[1] - target[1] == 2:
                if batch:
                    super().walk(batch)
                    batch = []
                fresh = self.scan()
                current = self.b.read()
                if not current.get('on_ground', False) or not fresh.safe_two_block_descent(previous, target, current['pos']):
                    raise Paused('Fresh dry two-block landing/body clearance is not verified')
                result = self.b.request('walk', target=center(target), arrival=.18, seconds=8, restore_flight=False)
                if distance(result['pos'], center(target)) > .7 or result.get('health', 0) <= 0:
                    raise Paused('Normal two-block descent arrival/alive result is not verified')
                self.event('normal_two_block_descent', health_before=current['health'], health_after=result['health'],
                           verified_position=result['pos'], flight_used=False)
            else:
                batch.append(target)
            previous = target
        if batch:
            super().walk(batch)

    def collect_log_drops(self):
        before = sum(inventory(self.b.read()).get(name, 0) for name in LOGS)
        for unused in range(8):
            state = self.b.read()
            found = self.remember_log_drops(state)
            world = self.scan()
            plan = self.pickup_plan(world, self.b.read(), found)
            if not plan:
                break
            identity, stance, route = plan
            # The stored location never substitutes for the current item.
            current = self.remember_log_drops(self.b.read()).get(identity)
            if current is None:
                continue
            try:
                self.walk_pickup_route(route)
            except TrialMovementBlocked:
                self.rejected_routes.add(tuple(route))
                raise
            self.b.wait(.8)
            after = self.b.read()
            self.remember_log_drops(after)
            if sum(inventory(after).get(name, 0) for name in LOGS) > before:
                return after
            self.rejected_routes.add(tuple(route))
        self.event('log_drops_pending', observed_count=sum(row['count'] for row in self.log_drops.values()),
                   inventory_before=before, pickup_confirmed=False)
        raise Paused('Observed log drops are still pending; no inventory gain or reachable pickup route was verified')

    def collect(self, wanted):
        if set(wanted).issubset(LOGS):
            if self.remember_log_drops(self.b.read()):
                self.collect_log_drops()
            return
        return super().collect(wanted)

    def station(self, name):
        # A crafting station needs safe reach and footing. It does not need the
        # 5x5 completely empty footprint required for the later shelter.
        if self.camp is not None:
            return super().station(name)
        if self.station_anchor is None:
            self.observe()
        if self.station_anchor is None:
            raise Paused('No observed safe station footing')
        previous = self.camp
        self.camp = list(self.station_anchor)
        try:
            return super().station(name)
        finally:
            self.camp = previous

    def exploration(self, world):
        paths = world.pickup_paths(self.b.state['pos']) if self.log_drops else world.paths(self.b.state['pos'])
        start = self.b.state['pos']
        choices = []
        for point in paths:
            key = (math.floor(point[0] / 8), math.floor(point[2] / 8))
            if (not self.log_drops and (key in self.explored or key in self.tried_grids or distance(start, center(point)) < 7)
                    or any(self.stations.get(name) == list(point) for name in self.stations)):
                continue
            route = world.route(paths, point)
            if route and len(route) <= 32 and tuple(route) not in self.rejected_routes:
                if self.log_drops:
                    old = min(distance(start, row['pos']) for row in self.log_drops.values())
                    new = min(distance(center(point), row['pos']) for row in self.log_drops.values())
                    if new > old - .5:
                        continue
                    choices.append((new, len(route), point, route))
                else:
                    choices.append((-distance(start, center(point)), len(route), point, route))
        if not choices:
            return None
        _, _, point, route = min(choices)
        return point, route

    def reject_exploration(self):
        if self.explore_target is None:
            return
        point, route = self.explore_target
        self.tried_grids.add((math.floor(point[0] / 8), math.floor(point[2] / 8)))
        self.rejected_routes.add(tuple(route))
        self.explore_target = None

    def candidates(self, state, world):
        inv = inventory(state)
        has = lambda name: inv.get(name, 0) > 0
        candidates = {'wait': LABELS['wait']}
        if state.get('dimension') != 'minecraft:overworld':
            return candidates
        found = self.remember_log_drops(state)
        self.pickup_target = self.pickup_plan(world, state, found)
        if self.pickup_target:
            candidates['collect_log_drops'] = LABELS['collect_log_drops']
        if self.log_drops:
            # A server-confirmed broken log is still pending until it enters
            # inventory. Never abandon known drops to cut additional trees.
            if state.get('food', 20) < 16 and any(inv.get(name) for name in FOOD):
                candidates['eat_carried_food'] = LABELS['eat_carried_food']
            self.explore_target = self.exploration(world)
            if self.explore_target:
                candidates['explore_nearby'] = '只沿已扫描正常路线接近本世界待取原木；不去新的树区'
            return candidates
        # Long macro workflows only appear when their locally checked inputs
        # can actually be used. The typed model cannot manufacture resources.
        if state.get('food', 20) < 16 and any(has(name) for name in FOOD):
            candidates['eat_carried_food'] = LABELS['eat_carried_food']
        starting = not has('wooden_pickaxe') and not has('stone_pickaxe') and not has('iron_pickaxe')
        station_possible = self.camp is not None or self.station_anchor is not None
        logs = sum(inv.get(name, 0) for name in LOGS)
        protected = {tuple(point) for point in self.stations.values()}
        if self.camp:
            cx, cy, cz = self.camp
            protected.update(p for p in world.blocks if abs(p[0] - cx) <= 3 and abs(p[2] - cz) <= 3)
        if ((starting and logs < 12) or (not starting and logs < 4)) and world.resource(state['pos'], LOGS, protected):
            candidates['gather_starting_wood'] = LABELS['gather_starting_wood']
        if starting and station_possible and (logs >= 4 or sum(v for k, v in inv.items() if k.endswith('_planks')) >= 12):
            candidates['craft_wooden_tools'] = LABELS['craft_wooden_tools']
        stone_needed = (0 if has('stone_pickaxe') or has('iron_pickaxe') else 3)
        stone_needed += (0 if has('stone_axe') else 3) + (0 if has('furnace') or 'furnace' in self.stations else 8)
        if not starting and inv.get('cobblestone', 0) < stone_needed and world.resource(state['pos'], {'stone', 'cobblestone'}, protected):
            candidates['gather_stone'] = LABELS['gather_stone']
        if not starting and station_possible and stone_needed and inv.get('cobblestone', 0) >= stone_needed:
            candidates['craft_stone_tools'] = LABELS['craft_stone_tools']
        food = sum(inv.get(name, 0) for name in FOOD)
        animals = [e for e in state.get('entities', [])
                   if e.get('type') in {'minecraft:cow', 'minecraft:pig', 'minecraft:sheep', 'minecraft:chicken'}
                   and e.get('health', 0) > 0]
        if has('stone_axe') and station_possible and (has('furnace') or 'furnace' in self.stations) and food < 4 and animals:
            candidates['gather_food'] = LABELS['gather_food']
        if self.camp and has('stone_pickaxe') and has('stone_axe') and food >= 4:
            layout, door = shelter(self.camp)
            missing = [p for p in layout if not world.earth(p)]
            if inv.get('dirt', 0) < len(missing) and world.resource(state['pos'], {'dirt', 'grass_block'}, protected):
                candidates['gather_shelter_material'] = LABELS['gather_shelter_material']
            elif missing or not world.name(door).endswith('_door'):
                candidates['build_shelter'] = LABELS['build_shelter']
            else:
                self.camp_completed = True
            iron = inv.get('iron_ingot', 0) + inv.get('raw_iron', 0)
            armor = {'head': 'iron_helmet', 'chest': 'iron_chestplate',
                     'legs': 'iron_leggings', 'feet': 'iron_boots'}
            equipped = state.get('equipment', {})
            ready = has('iron_pickaxe') and has('iron_sword') and all(
                has(name) or equipped.get(slot, {}).get('item') == 'minecraft:' + name
                for slot, name in armor.items())
            if self.camp_completed and not ready and (iron >= 31 or world.resource(state['pos'], {'iron_ore', 'deepslate_iron_ore'}, protected)):
                candidates['prepare_iron_equipment'] = LABELS['prepare_iron_equipment']
        self.explore_target = self.exploration(world)
        if self.explore_target and len(self.explored | self.tried_grids) < 64:
            candidates['explore_nearby'] = LABELS['explore_nearby']
        return candidates

    def execute(self, choice):
        self.reset_budget()
        self.stage = choice
        self.planned(choice, LABELS[choice], {})
        if choice == 'collect_log_drops':
            self.collect_log_drops()
        elif choice == 'gather_starting_wood':
            inv = inventory(self.b.read())
            initial = not any(inv.get(n) for n in ('wooden_pickaxe', 'stone_pickaxe', 'iron_pickaxe'))
            self.gather(LOGS, LOGS, 12 if initial else 6)
        elif choice == 'craft_wooden_tools':
            plank = self.planks(12)
            if not self.count('crafting_table') and 'crafting_table' not in self.stations:
                self.craft('crafting_table', {(0, 0): plank, (0, 1): plank, (1, 0): plank, (1, 1): plank}, 2)
            self.tool('wooden_pickaxe', plank)
        elif choice == 'gather_stone':
            inv = inventory(self.b.read())
            needed = (0 if inv.get('stone_pickaxe') or inv.get('iron_pickaxe') else 3)
            needed += (0 if inv.get('stone_axe') else 3) + (0 if inv.get('furnace') or 'furnace' in self.stations else 8)
            self.gather({'stone', 'cobblestone'}, {'cobblestone'}, needed)
        elif choice == 'craft_stone_tools':
            self.tool('stone_pickaxe', 'cobblestone')
            self.tool('stone_axe', 'cobblestone')
            if not self.count('furnace') and 'furnace' not in self.stations:
                self.craft('furnace', {(r, c): 'cobblestone' for r in range(3) for c in range(3) if (r, c) != (1, 1)})
        elif choice == 'gather_food':
            self.food()
            self.eat_if_needed()
        elif choice == 'eat_carried_food':
            self.eat_if_needed()
        elif choice == 'gather_shelter_material':
            layout, _ = shelter(self.camp)
            world = self.scan()
            needed = sum(not world.earth(p) for p in layout)
            self.gather({'dirt', 'grass_block'}, {'dirt'}, needed)
        elif choice == 'build_shelter':
            layout, door = shelter(self.camp)
            plank = self.planks(6)
            door_item = plank.removesuffix('_planks') + '_door'
            if not self.count(door_item) and not self.scan().name(door).endswith('_door'):
                self.craft(door_item, {(r, c): plank for r in range(3) for c in range(2)}, produces=3)
            for point in layout:
                self.eat_if_needed()
                self.place('dirt', point)
            self.place(door_item, door)
            world = self.scan()
            if not all(world.earth(p) for p in layout) or not world.name(door).endswith('_door'):
                raise Paused('Native shelter blocks did not pass the final scan')
            self.camp_completed = True
        elif choice == 'prepare_iron_equipment':
            self.iron_equipment()
        elif choice == 'explore_nearby':
            if self.explore_target is None:
                raise Paused('No scanned safe route available')
            point, route = self.explore_target
            try:
                if self.log_drops:
                    self.walk_pickup_route(route)
                else:
                    self.walk(route)
            except TrialMovementBlocked:
                self.reject_exploration()
                raise
            if distance(self.b.read()['pos'], center(point)) > .9:
                raise Paused('Exploration arrival did not pass native position check')
            self.explored.add((math.floor(point[0] / 8), math.floor(point[2] / 8)))
            # A camp remains an actual coordinate in this save. Do not silently
            # move it merely because exploration crossed a scan boundary.
        else:
            raise Paused('No supported local macro for selected action')
        self.b.close()
        return self.b.read()


class TrialWorker:
    def __init__(self, game, parent_pid, *, reader=status, bridge_factory=TrialBridge,
                 model_factory=OllamaDecision, sleeper=time.sleep):
        self.game = Path(game).resolve()
        self.root = self.game / 'config/twob2tkit/singleplayer-trial'
        self.automation = self.game / 'config/twob2tkit/automation'
        self.output = self.root / 'worker'
        self.output.mkdir(parents=True, exist_ok=True)
        self.parent_pid = parent_pid
        self.reader = reader
        self.bridge_factory = bridge_factory
        self.model_factory = model_factory
        self.sleeper = sleeper
        self.stopping = False
        self.command = 'pause'
        self.control_id = None
        self.registry = None
        self.run_id = None
        self.bridge = None
        self.skills = None
        self.model_calls = 0
        self.steps = 0
        self.deaths = 0
        self.last_respawn = 0
        self.last_death_epoch = None
        self.seen_death_epoch = None
        self.death_seen_at = 0
        self.failures = {}
        self.phase = 'paused'
        self.reason = '从 Kit 单人试验页面开始'
        self.completion_state = None
        self.checkpoint_signature = None
        self.restoring_checkpoint = False
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='trial-clef')
        self.inference = None
        self.experience = None
        try:
            from singleplayer_experience import TrialExperienceStore
            self.experience = TrialExperienceStore(self.root / 'experience')
        except ImportError:
            # Worker packaging verifies this import; a missing optional store
            # cannot grant new game permissions or invent experience.
            pass

    def event(self, kind, **data):
        with (self.output / 'journal.jsonl').open('a') as stream:
            stream.write(json.dumps({'time': int(time.time() * 1000), 'event': kind,
                                     'trial_id': self.registry.get('trial_id') if self.registry else None,
                                     'run_id': self.run_id, **data}, ensure_ascii=False, allow_nan=False) + '\n')

    def publish(self, phase=None, reason=None, state=None):
        if phase is not None:
            self.phase = phase
        if reason is not None:
            self.reason = reason
        value = {'protocol': 1, 'time': int(time.time() * 1000), 'pid': os.getpid(),
                 'phase': self.phase, 'reason': self.reason, 'command': self.command,
                 'goal': 'defeat_ender_dragon', 'run_id': self.run_id,
                 'trial_id': self.registry.get('trial_id') if self.registry else None,
                 'world_id': self.registry.get('world_id') if self.registry else None,
                 'model_calls': self.model_calls, 'steps': self.steps, 'deaths': self.deaths,
                 'implemented': sorted(LABELS.keys() - {'wait', 'recover_after_death'}),
                 'missing_capabilities': GAPS,
                 'dragon_defeated': bool(state and state.get('dragon_defeated') is True)}
        if state:
            value.update({key: state.get(key) for key in ('world_session', 'health', 'food', 'pos', 'control_revision')})
        if self.skills:
            value.update(stage=self.skills.stage, camp=self.skills.camp,
                         camp_completed=self.skills.camp_completed,
                         pending_log_drops=sum(row['count'] for row in self.skills.log_drops.values()))
        atomic_json(self.output / 'status.json', value)
        if state and self.skills and self.registry and not self.restoring_checkpoint:
            from singleplayer_trial_hot_update import checkpoint_from_skills
            checkpoint = checkpoint_from_skills(self.registry, state, self.skills,
                                               getattr(self.bridge, 'pending_mutations', {}))
            signature_value = {key: val for key, val in checkpoint.items() if key != 'observed_at'}
            signature = json.dumps(signature_value, sort_keys=True)
            if signature != self.checkpoint_signature:
                atomic_json(self.output / 'checkpoint.json', checkpoint)
                self.checkpoint_signature = signature

    def heartbeat(self, state):
        atomic_json(self.root / 'heartbeat.json', {'time': int(time.time() * 1000),
                    'trial_id': self.registry['trial_id'], 'run_id': self.run_id,
                    'world_session': state['world_session'], 'world_id': self.registry['world_id'],
                    'control_revision': state['control_revision'], 'pid': os.getpid()})
        self.publish(state=state)

    def control(self):
        if self.stopping or not alive(self.parent_pid):
            raise Paused('Owning Minecraft JVM stopped')
        value = json.loads((self.root / 'registry.json').read_text())
        registry = validate_registry(value, self.game)
        if self.registry and (registry['trial_id'] != self.registry['trial_id'] or registry['world_id'] != self.registry['world_id']):
            self.command = 'pause'
            raise Paused('Trial registry changed; no old-save actions continue')
        self.registry = registry
        path = self.root / 'control.json'
        if path.exists():
            control = json.loads(path.read_text())
            if (control.get('trial_id') == registry['trial_id']
                    and control.get('run_id') == registry.get('run_id')
                    and isinstance(control.get('id'), str) and control['id'] != self.control_id
                    and control.get('command') in {'start', 'pause', 'resume', 'cancel'}):
                self.control_id = control['id']
                self.command = control['command']
                if self.command in {'start', 'resume'}:
                    if not isinstance(registry.get('run_id'), str) or not registry['run_id']:
                        raise Paused('Native Start must create a run identity')
                    if self.command == 'start' or self.run_id != registry['run_id']:
                        self.bridge = None
                        self.skills = None
                    elif self.command == 'resume':
                        # Native Resume is the explicit new revision binding.
                        # Preserve observed camp coordinates in this same save,
                        # but do not re-send any old native request envelope.
                        self.bridge = None
                    self.run_id = registry['run_id']
                self.event('control', command=self.command, control_id=self.control_id)
        if self.command not in {'start', 'resume'}:
            raise Paused('Kit trial ' + self.command)
        if self.registry.get('run_id') != self.run_id:
            raise Paused('Native run changed; wait for its explicit Start')

    def bind(self):
        old = self.skills
        self.bridge = self.bridge_factory(self.automation, self.registry, self.run_id,
                      check_control=self.control, heartbeat=self.heartbeat,
                      events=self.event, reader=self.reader, sleeper=self.sleeper)
        self.skills = TrialSkills(self.bridge, self.output / 'bootstrap')
        if old:
            for name in ('camp', 'stations', 'owned', 'camp_completed', 'explored', 'station_anchor',
                         'tried_grids', 'rejected_routes', 'log_drops'):
                setattr(self.skills, name, getattr(old, name))
        else:
            from singleplayer_trial_hot_update import load_checkpoint, restore_checkpoint
            checkpoint = load_checkpoint(self.game, self.registry, self.bridge.state)
            if checkpoint:
                self.restoring_checkpoint = True
                try:
                    result = restore_checkpoint(self.skills, checkpoint, self.registry, self.bridge.state)
                    self.event('checkpoint_revalidated', **result)
                finally:
                    self.restoring_checkpoint = False

    def model_config(self):
        settings = self.game / 'config/twob2tkit/decision-advisor'
        config = json.loads((settings / 'settings.json').read_text())
        if (config.get('provider') != 'ollama' or config.get('enabled') is not True
                or config.get('local_model') != 'clef-flash' or config.get('keep_loaded') is not True):
            raise Paused('本试验需要 Kit 本地 Clef Flash 已启用并保持常驻')
        return settings, config

    def decide(self, candidates, before):
        self.control()
        if self.inference is not None and not self.inference.done():
            raise Paused('Previous model request is still in flight; do not overlap it')
        settings, config = self.model_config()
        image = None
        visual = config.get('vision_mode') == 'always' or (
            config.get('vision_mode') == 'auto' and 'explore_nearby' in candidates and len(candidates) <= 3)
        rules = self.experience.reusable_rules(before, limit=4) if self.experience else []
        rules = [{key: row[key] for key in ('rule', 'observed_attempts', 'advisory_only')} for row in rules]
        # Keep full snapshots in the journal, and a small factual decision
        # scene within the configured context. No arbitrary experience prose.
        scene = {'singleplayer_trial': True, 'stage': self.skills.stage,
                 'health': before['health'], 'food': before['food'],
                 'dimension': before['dimension'], 'inventory': inventory(before),
                 'camp_available': self.skills.camp is not None,
                 'camp_completed': self.skills.camp_completed,
                 'long_term_goal': 'defeat_ender_dragon',
                 'scope': {'only_offered_macros_are_executable': True}, 'experience': rules,
                 'capabilities': capability_scene(candidates, before, max_bytes=1800)}
        pending_logs = sum(row['count'] for row in self.skills.log_drops.values())
        scene['pending_log_drops'] = pending_logs
        immediate_goal = short_term_goal(before, candidates, pending_logs)
        criteria = {key: CRITERIA.get(key, description) for key, description in candidates.items()}
        if pending_logs and 'explore_nearby' in criteria:
            criteria['explore_nearby'] = 'Follow only the prechecked normal route closer to this save\'s observed pending log drops, then rediscover actual item entities. Do not search for new trees or treat memory as pickup success.'
        from decisions import question
        payload = {'model': 'kit-clef-flash', 'state': {'goal': immediate_goal, 'scene': scene},
                   'questions': question(criteria), 'keep_alive': -1}
        payload_bytes = len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf8'))
        if visual and payload_bytes > config['context_length'] - 1792:
            if config.get('vision_mode') == 'always':
                raise Paused('完整能力和状态超过图像上下文预算，未裁剪事实；等待增加上下文或改用文字')
            self.event('vision_skipped_budget', text_bytes=payload_bytes,
                       image_text_budget=config['context_length'] - 1792,
                       retained='complete_structured_facts_and_capabilities')
            visual = False
        if payload_bytes > config['context_length'] - 256:
            raise Paused('完整能力和状态超过文字上下文预算，未裁剪事实')
        if visual:
            capture = self.bridge.request('decision_screenshot')
            image = checked_image(capture.get('decision_image'), self.automation, capture)
            before = self.bridge.read()
        def inference():
            model = self.model_factory(settings, config, image=image)
            try:
                return choose(model, immediate_goal, criteria, scene)
            finally:
                model.close()
        self.inference = self.pool.submit(inference)
        deadline = time.monotonic() + min(35, config.get('timeout_seconds', 10) + 5)
        self.publish('thinking', 'Clef Flash 从当前可执行宏步骤中选择', before)
        while not self.inference.done():
            self.control()
            current = self.bridge.read()
            if distance(current['pos'], before['pos']) > .5:
                raise Paused('Player moved during model inference; discard choice')
            if time.monotonic() >= deadline:
                raise Paused('Model response is still unknown; no overlapping decision')
            self.sleeper(.2)
        result = self.inference.result()
        self.model_calls += 1
        after = self.bridge.read()
        if (after['world_session'] != before['world_session']
                or after['control_revision'] != before['control_revision']
                or distance(after['pos'], before['pos']) > .5):
            raise Paused('Model choice belongs to a changed trial observation')
        self.event('decision', candidates=list(candidates), result=result, short_term_goal=immediate_goal,
                   uncertainty={'low_confidence': result['confidence'] < .55,
                                'execution_gate': 'typed_choice_and_native_trial_validation',
                                'confidence_is_observation_only': True},
                   before={key: before.get(key) for key in ('time', 'health', 'food', 'pos', 'world_session', 'control_revision')})
        return result

    def reflect(self, action, before, after, receipt=None):
        """One bounded, typed model reflection; no game action is dispatched."""
        from singleplayer_experience import proposal_question, RULES
        settings, config = self.model_config()
        if self.inference is not None and not self.inference.done():
            return None
        def facts(state):
            return {key: state.get(key) for key in ('health', 'food', 'player_dead', 'trial_deaths', 'dimension')} | {'inventory': inventory(state)}
        questions = proposal_question()
        observed = {'position_changed': False, 'observed_displacement_blocks': None,
                    'native_receipt_phase': 'unconfirmed', 'native_receipt_class': 'unconfirmed'}
        if (isinstance(before.get('pos'), list) and isinstance(after.get('pos'), list)
                and len(before['pos']) == len(after['pos']) == 3
                and before.get('world_session') == after.get('world_session')
                and before.get('dimension') == after.get('dimension')):
            displacement = distance(before['pos'], after['pos'])
            observed['position_changed'] = displacement > .2
            observed['observed_displacement_blocks'] = round(displacement, 2)
        if (isinstance(receipt, dict) and receipt.get('native') is True
                and receipt.get('id') == receipt.get('request_id')
                and receipt.get('world_session') == before.get('world_session') == after.get('world_session')
                and receipt.get('phase') in {'done', 'waiting', 'stopped', 'error'}):
            observed['native_receipt_phase'] = receipt['phase']
            observed['native_receipt_class'] = ('terrain_movement_refusal'
                if receipt.get('receipt_class') == 'terrain_movement_refusal' and receipt.get('code') == 'path_blocked'
                else 'normal_terminal_result')
        context = {'goal': 'Record a supported advisory lesson from this actual Survival trial attempt.',
                   'scene': {'action': action, 'before': facts(before), 'after': facts(after),
                             'observed_effect': observed,
                             'completion_claim': 'Only observed facts; no guaranteed cause or skill'}}
        def inference():
            model = self.model_factory(settings, config)
            try:
                response = model.predict(context, questions)
                answer = validated_answer({'answers': {'action': response.get('answers', {}).get('lesson')}},
                                          questions['lesson']['criteria'])
                lesson = answer['choice']
                if lesson == 'no_lesson':
                    return {'lesson': 'no_lesson'}
                return {'lesson': lesson, 'category': RULES[lesson]['category'],
                        'confidence': 'high' if answer['confidence'] >= .8 else 'medium' if answer['confidence'] >= .55 else 'low'}
            finally:
                model.close()
        self.inference = self.pool.submit(inference)
        deadline = time.monotonic() + min(35, config.get('timeout_seconds', 10) + 5)
        while not self.inference.done():
            self.control()
            current = self.bridge.read(allow_dead=True)
            if current['world_session'] != after['world_session']:
                return None
            if time.monotonic() >= deadline:
                return None
            self.sleeper(.2)
        proposal = self.inference.result()
        self.model_calls += 1
        self.event('model_experience_proposal', action=action, proposal=proposal)
        return proposal

    def attempt_record(self, action, before, after, receipt=None):
        self.event('attempt', action=action, before=before, after=after,
                   receipt=receipt)
        if self.experience:
            proposal = None
            try:
                proposal = self.reflect(action, before, after, receipt)
            except (DecisionError, OSError, ValueError):
                # Journal evidence is already durable even if reflection fails.
                pass
            try:
                self.experience.record_attempt(self.registry['trial_id'], action, before,
                                               after, receipt=receipt, proposal=proposal)
            except Exception as error:
                # Experience persistence is secondary to the already durable
                # native attempt. It cannot turn an observed macro success into
                # a game failure or authorize another game operation.
                try:
                    self.event('experience_store_error', action=action,
                               error_type=type(error).__name__)
                except OSError:
                    pass

    def death_recovery(self, state):
        epoch = state.get('trial_deaths', state.get('death_epoch'))
        if type(epoch) is not int or epoch < 1:
            raise Paused('Native death epoch is missing; cannot safely respawn')
        if epoch != self.seen_death_epoch:
            self.seen_death_epoch = epoch
            self.death_seen_at = time.monotonic()
        if epoch == self.last_death_epoch:
            self.publish('death_wait', '同一次死亡的复活请求已发送，保留结果不重放', state)
            return
        if time.monotonic() - self.last_respawn < 30 or time.monotonic() - self.death_seen_at < 3:
            self.publish('death_cooldown', '正常死亡复活冷却，避免连续快速重试', state)
            return
        # Every death is recorded before any respawn. Unknown macro outcomes
        # stay in the journal; this never upgrades them to successful actions.
        before = dict(state)
        self.last_death_epoch = epoch
        self.last_respawn = time.monotonic()
        self.deaths = max(self.deaths, epoch)
        self.publish('respawning', '记录试验死亡后正常复活', state)
        after = self.bridge.request('trial_respawn', death_epoch=epoch, seconds=15)
        if dead(after):
            raise Paused('Native respawn result still reports death')
        self.attempt_record('recover_after_death', before, after, self.bridge.last_receipt)
        self.skills = TrialSkills(self.bridge, self.output / 'bootstrap')
        self.failures = {}
        self.publish('running', '正常复活已确认，依据当前背包重新规划', after)

    def cycle(self):
        self.control()
        passive = validate_scope(self.reader(self.automation), self.registry,
                                 run_id=self.run_id, allow_dead=True)
        if dead(passive) and self.bridge is not None:
            # Native death handling released the old trial inputs and may
            # advance its revision. This rebind is only for the observed same
            # save/run death, never for a manual takeover or ordinary timeout.
            if self.bridge.active:
                self.event('death_ended_unknown_native', request_id=self.bridge.active,
                           previous_session=self.bridge.session)
            self.bridge = None
            self.skills = None
        if self.bridge is None:
            self.bind()
        state = self.bridge.read(allow_dead=True)
        if state.get('dragon_defeated') is True:
            self.completion_state = state
            self.publish('complete', '原生确认已击败末影龙', state)
            return
        if dead(state):
            self.death_recovery(state)
            return
        if state['dimension'] != 'minecraft:overworld':
            self.publish('waiting_capability', '当前维度缺少已实现的通关宏能力', state)
            return
        self.skills.reset_budget()
        self.publish('observing', '读取有限范围的真实地形与背包', state)
        world = self.skills.observe()
        before = self.bridge.read()
        candidates = self.skills.candidates(before, world)
        candidates = {key: value for key, value in candidates.items()
                      if key == 'wait' or self.failures.get(key, 0) < 3}
        if len(candidates) < 2:
            reason = ('原木掉落仍待取，当前没有已验证的正常落地拾取路线；尚未入包'
                      if self.skills.log_drops else '附近已验证宏能力无法推进；尚未实现完整下界和打龙流程')
            self.publish('waiting_capability', reason, before)
            return
        decision = self.decide(candidates, before)
        action = decision['choice']
        if action == 'wait':
            self.publish('waiting_model', '模型选择等待，未执行游戏动作', before)
            return
        self.publish('running', LABELS[action], before)
        receipt_start = len(self.bridge.receipts)
        try:
            after = self.skills.execute(action)
            self.steps += 1
            self.failures[action] = 0
            self.attempt_record(action, before, after, self.bridge.last_receipt)
            self.publish('running', '宏步骤通过当前游戏状态核对：' + LABELS[action], after)
        except TrialDeath:
            after = self.reader(self.automation)
            self.attempt_record(action, before, after, self.bridge.last_receipt)
            self.publish('death_wait', '试验过程中已死亡，下一轮正常复活', after)
        except TrialMovementBlocked as error:
            after = self.bridge.read()
            self.attempt_record(action, before, after, error.receipt)
            self.publish('replanning', '原生已停止拒绝的步行路线；重新扫描并选择其他目标', after)
        except (Paused, OSError, ValueError, DecisionError) as error:
            self.failures[action] = self.failures.get(action, 0) + 1
            after = self.reader(self.automation)
            receipt = self.bridge.last_receipt if len(self.bridge.receipts) > receipt_start else None
            self.attempt_record(action, before, after, receipt)
            self.publish('waiting_capability' if not self.bridge.halted else 'paused', str(error), after)
            if self.bridge.halted:
                self.command = 'pause'

    def run(self, poll_seconds=.5):
        lock = (self.root / 'worker.lock').open('a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise Paused('A Kit trial worker already owns this local service')
        try:
            self.publish()
            while not self.stopping and alive(self.parent_pid):
                try:
                    self.cycle()
                except TrialDeath:
                    self.publish('death_wait', '已死亡，等待正常复活检查')
                except (Paused, OSError, ValueError, DecisionError) as error:
                    self.publish('cancelled' if self.command == 'cancel' else 'paused', str(error))
                    # Service warming is a passive wait. A revoked native
                    # revision/manual takeover never autonomously rebinds.
                    if self.bridge and self.bridge.halted:
                        self.command = 'pause'
                if self.command == 'cancel' or self.phase == 'complete':
                    break
                delay = 5 if self.phase in {'waiting_model', 'waiting_capability'} else poll_seconds
                until = time.monotonic() + delay
                while not self.stopping and time.monotonic() < until:
                    self.sleeper(min(.2, max(0, until - time.monotonic())))
        finally:
            if self.bridge:
                self.bridge.stop_owned()
            self.pool.shutdown(wait=False, cancel_futures=True)
            if self.experience:
                self.experience.close()
            if self.completion_state is not None:
                self.publish('complete', '原生确认已击败末影龙，试验服务正常结束', self.completion_state)
            else:
                self.publish('cancelled' if self.command == 'cancel' else 'stopped',
                             '本试验已取消，原生结果和经验保留' if self.command == 'cancel' else '本试验服务已结束')
            lock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--parent-pid', type=int, required=True)
    parser.add_argument('--poll-seconds', type=float, default=.5)
    args = parser.parse_args()
    if args.parent_pid <= 1 or not .1 <= args.poll_seconds <= 5:
        raise Paused('Invalid JVM ownership or bounded poll interval')
    worker = TrialWorker(args.game, args.parent_pid)
    def stop(signum, frame):
        worker.stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    worker.run(args.poll_seconds)


if __name__ == '__main__':
    try:
        main()
    except (Paused, OSError, ValueError, DecisionError) as error:
        raise SystemExit('单人试验已停止：' + str(error)) from None
