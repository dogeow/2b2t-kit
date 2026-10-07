"""Kit-owned local Clef Flash survival experiment, independent of a chat window.

This is a real bootstrap and exploration controller, not a completed dragon
speedrunner. Unsupported progression remains visible as waiting_capability.
All world inputs are existing verified native skills; model output is a typed
choice among locally constructed macros and never executable code.
"""
import argparse
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
import fcntl
import heapq
import json
import math
import os
from pathlib import Path
import signal
import time

from decisions import DecisionError, choose, status, validated_answer
from ollama_decision import OllamaDecision, checked_image
from singleplayer_trial_bridge import (Paused, TrialBridge, TrialDeath, TrialMovementBlocked, TrialGuardBusy, validate_registry,
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
    'gather_food': '先核验燃料，再烹饪已有生食或获取缺少的食物',
    'gather_cooking_fuel': '用现有镐采集已观察到的煤并核对烹饪燃料入包',
    'eat_carried_food': '正常食用背包内已确认的食物',
    'gather_shelter_material': '采集小庇护所材料，不挖脚底和工作设施',
    'build_shelter': '实际搭建和验证小庇护所',
    'prepare_iron_equipment': '采集露天铁矿、熔炼、合成和穿戴铁装备',
    'explore_nearby': '沿扫描验证的正常步行路线探索附近资源',
    'recover_after_death': '记录已发生死亡后通过原生正常复活继续试验',
    'recover_surface_access': '保留实体台阶，清理必要净空并正常逐级上升',
    'prepare_small_shelter': '先寻找安全平地，建造小屋并进屋关门',
    'prepare_sword': '用现货准备并装备近身防御剑',
    'upgrade_stone_sword': '仅补齐必要圆石，合成并装备石剑',
    'enter_small_shelter': '返回已验证小屋并关门守夜',
    'leave_small_shelter': '白天沿已验证门口路线出屋继续任务',
    'wait': '当前没有可信宏动作推进目标；等待新证据或缺失能力',
}
CRITERIA = {
    'collect_log_drops': 'Collect currently observed log item drops first using the checked normal walking route. Verify actual logs gained in inventory; item existence or a mining ACK is not pickup success.',
    'gather_starting_wood': 'Collect the needed logs from trees already observed as reachable nearby. Prefer using this available wood over exploring for other wood.',
    'craft_wooden_tools': 'Use the carried logs or planks to craft a crafting table and wooden pickaxe now, before looking for more resources.',
    'gather_stone': 'Use the available pickaxe to collect the needed cobblestone from already observed reachable stone.',
    'craft_stone_tools': 'Use carried cobblestone and wood to craft the missing stone tools and furnace now.',
    'gather_food': 'Cook already carried raw food with the verified fuel plan. Hunt an observed animal only for the actual raw-food deficit and only after fuel is ready.',
    'gather_cooking_fuel': 'Collect the actual missing coal from already observed reachable coal ore for the carried raw food. Verify the absolute coal backpack target before cooking.',
    'eat_carried_food': 'Eat already carried food to restore hunger before another macro.',
    'recover_surface_access': 'When no normal scanned exploration route exists, keep existing solid steps, clear only verified headroom and climb at most four levels. Verify actual height gain; do not claim the surface has been reached.',
    'prepare_small_shelter': 'Prioritize a verified supported small house and closed door before roaming, cooking or the next night. The local executor finds a bounded real site and verifies enclosure and actual entry.',
    'prepare_sword': 'Prepare and equip a carried-material sword for defense. Use an existing stronger sword instead of downgrading it.',
    'upgrade_stone_sword': 'Upgrade the carried wooden sword to a stone sword. Gather only enough safe stone for an absolute two-cobblestone target, verify the stone sword in inventory, then equip it.',
    'enter_small_shelter': 'Enter the already verified small house and confirm its door is closed before nighttime work.',
    'leave_small_shelter': 'During daylight leave the verified house through its normal door route, confirm the door is closed behind you and continue the preparation goal.',
    'gather_shelter_material': 'Collect the missing dirt from observed reachable ground for the verified shelter plan.',
    'build_shelter': 'Use carried building material to construct and verify the observed shelter plan.',
    'prepare_iron_equipment': 'Use the observed iron materials and normal crafting to obtain and equip iron gear.',
    'explore_nearby': 'Explore a new scanned safe route when no carried-material or reachable-resource macro can meet the current short-term goal.',
    'wait': 'Wait if none of the offered macros can advance the short-term goal or the observations conflict.',
}


def short_term_goal(state, candidates, pending_log_drops=0, cooking=None, safety=None):
    """Derive one immediate milestone from actual stock and prechecked macros."""
    inv = inventory(state)
    if 'collect_log_drops' in candidates:
        return 'Pick up the already observed reachable dropped logs and verify actual inventory gain before chopping another tree or exploring elsewhere.'
    if pending_log_drops and 'explore_nearby' in candidates:
        return 'Follow the scanned normal ground route toward the already observed dropped logs and reobserve the items before pickup. Do not cut another tree or explore away.'
    if 'eat_carried_food' in candidates and state.get('food', 20) < 16:
        return 'Eat carried food now to restore hunger before continuing Survival preparation.'
    if 'enter_small_shelter' in candidates:
        return 'Return to the verified shelter, enter and close its door before continuing nighttime preparation.'
    if 'leave_small_shelter' in candidates:
        return 'Leave the verified small house by its normal door route during daylight, then resume preparation.'
    if 'prepare_small_shelter' in candidates:
        return 'Establish the offered small supported shelter with a real wooden door, enter and close it before further exploration or cooking.'
    if 'prepare_sword' in candidates:
        return 'Prepare and equip the available defensive sword before continuing Survival work.'
    if 'upgrade_stone_sword' in candidates:
        return 'Obtain only the missing cobblestone and upgrade to a real stone sword for defense; preserve the current sword until the upgrade is verified.'
    starting = not any(inv.get(name) for name in ('wooden_pickaxe', 'stone_pickaxe', 'iron_pickaxe'))
    if starting:
        if 'craft_wooden_tools' in candidates:
            return 'Craft a crafting table and wooden pickaxe now using the already carried wood, before exploring.'
        if 'gather_starting_wood' in candidates:
            return 'Collect starting logs from the already observed reachable nearby trees and verify the inventory gain. Prioritize gathering this wood over exploration.'
        return 'Find reachable starting wood along a newly scanned safe walking route.'
    if 'recover_surface_access' in candidates:
        return 'Restore upward access from the confined mining area using the offered verified intact steps and bounded headroom clearing. Confirm actual height gain before seeking surface resources.'
    goals = (
        ('craft_stone_tools', 'Craft the missing stone pickaxe, stone axe and furnace now from carried materials.'),
        ('gather_stone', 'Collect the needed cobblestone from already observed reachable stone for stone tools and a furnace.'),
        ('gather_cooking_fuel', 'Collect the missing cooking coal from already observed reachable ore, then cook the carried raw food. Do not hunt more animals for an already met raw-food target.'),
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
    if safety and not safety.get('sheltered') and safety.get('wood_ready') and safety.get('dirt_deficit',0)>0:
        return 'Find reachable earth along a scanned safe land route for the small shelter before further food hunting or roaming. The local house macro will collect only its actual dirt deficit.'
    if cooking and cooking.get('coal_requirement', 0) > inv.get('coal', 0):
        return 'Find reachable exposed coal along a newly scanned safe route for the carried raw food. Do not search for additional meat while its raw-food target is already met.'
    if sum(inv.get(name, 0) for name in FOOD) < 4:
        return 'Find an accessible food source along a newly scanned safe route.'
    if 'explore_nearby' in candidates:
        return 'Explore a newly scanned safe route for the next missing Survival resources without repeating refused routes.'
    return 'Wait for new observations or a supported macro that advances the next Survival milestone.'


def local_failure_context(skills, state, world=None):
    """Stable local prerequisites, excluding clock and controller revisions."""
    stations = []
    for name, point in sorted(getattr(skills, 'stations', {}).items()):
        if not isinstance(point, (list, tuple)) or len(point) != 3:
            continue
        point = tuple(point)
        observed = world.name(point) if isinstance(world, World) else None
        reachable = None
        if isinstance(world, World) and observed == name:
            parents = world.paths(state['pos'])
            stance = world.approach(parents, point)
            reachable = stance is not None and len(world.route(parents, stance)) <= 32
        stations.append((name, point, observed, reachable))
    return (cell(state['pos']), tuple(sorted((item, count) for item,count in inventory(state).items()
                                            if item != 'air' and count)), tuple(stations))


def local_wait_reason(skills, state, failures=None):
    if getattr(skills.b, 'halted', False) or getattr(skills.b, 'pending_mutations', {}):
        return '仍有未确认的原生动作，保留现场和请求；不会重复施工或重新砍树'
    readiness = getattr(skills, 'safety_readiness', None) or {}
    inv = inventory(state)
    if not readiness.get('sheltered') and readiness.get('wood_deficit', 0) > 0:
        return ('当前小屋材料还缺 ' + str(readiness['wood_deficit'])
                + ' 块同树种木板；当前局部没有可执行的原生砍树或安全探索方案')
    if not readiness.get('sheltered') and readiness.get('dirt_deficit', 0) > 0:
        return ('当前小屋还缺 ' + str(readiness['dirt_deficit'])
                + ' 块泥土；当前扫描内没有能继续采集或建屋的已验证方案')
    if inv.get('wooden_sword') and readiness.get('stone_sword_deficit', 0) > 0:
        return ('石剑还缺 ' + str(readiness['stone_sword_deficit'])
                + ' 块圆石；当前扫描内没有能推进的安全采集方案')
    if any(count >= 3 for count in (failures or {}).values()):
        return '相同位置、材料和站点的方案已连续被拒绝；当前没有能获得新条件的安全路线'
    food = sum(inv.get(item, 0) for item in FOOD)
    return ('当前仍在地表生存准备，已有原木 ' + str(sum(inv.get(item,0) for item in LOGS))
            + '、可食食物 ' + str(food) + '；当前扫描内没有可执行的后续方案')


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
    @staticmethod
    def pickup_reach(feet, item):
        # Vanilla checks the player AABB expanded by (1, .5, 1), not a
        # horizontal radius. Reserve .2 for normal-walk arrival error; the
        # real inventory change remains the sole collection confirmation.
        return (abs(feet[0] - item[0]) <= 1.2 and abs(feet[2] - item[2]) <= 1.2
                and feet[1] - .3 <= item[1] <= feet[1] + 2.1)

    def leaf_access_paths(self, start, limit=2500, max_leaves=3):
        """Hypotheses for a short normal route needing only leaf clearance.

        These paths cannot be walked until each obstructing leaf has actually
        been mined and a fresh scan supplies a normal pickup path. Supports,
        liquids, containers, unknown cells and non-leaf obstacles stay intact.
        """
        ordinary = self.pickup_paths(start, limit)
        if not ordinary:
            return {}, {}
        parents = Paths(ordinary)
        parents.centering = getattr(ordinary, 'centering', None)
        clearances = {point: frozenset() for point in ordinary}
        costs = {point: (0, len(self.route(ordinary, point))) for point in ordinary}
        queue = [(0, length, point) for point, (_, length) in costs.items()]
        heapq.heapify(queue)

        def needed(point, removed):
            if point in removed or self.open(point):
                return frozenset()
            if (self.safe(point) and self.name(point).endswith('_leaves')
                    and not self.row(point).get('block_entity')):
                return frozenset({point})
            return None

        while queue and len(parents) < limit:
            count, length, source = heapq.heappop(queue)
            if costs[source] != (count, length):
                continue
            x, y, z = source
            removed = clearances[source]
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                for dy in (0, 1, -1):
                    target = (x + dx, y + dy, z + dz)
                    support = (target[0], target[1] - 1, target[2])
                    if not self.full(support) or support in removed:
                        continue
                    sweep = [target, (target[0], target[1] + 1, target[2])]
                    if dy == 1:
                        sweep.append((x, y + 2, z))
                    elif dy == -1:
                        sweep.append((target[0], y + 1, target[2]))
                    additions = [needed(point, removed) for point in sweep]
                    if any(value is None for value in additions):
                        continue
                    clearance = removed.union(*additions)
                    if len(clearance) > max_leaves:
                        continue
                    # Do not remove any footing used by the hypothetical
                    # approach, including earlier waypoints in this route.
                    footing = {(p[0], p[1] - 1, p[2]) for p in self.route(parents, source)}
                    footing.add((x, y - 1, z))
                    if clearance & footing:
                        continue
                    cost = (len(clearance), length + 1)
                    if cost >= costs.get(target, (max_leaves + 1, limit + 1)):
                        continue
                    parents[target] = source
                    clearances[target] = clearance
                    costs[target] = cost
                    heapq.heappush(queue, (*cost, target))
        return parents, clearances

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


class _TrialCraftClient:
    """Adapt SDK inventory transactions to the already bound trial controller."""
    def __init__(self, bridge, output):
        self.bridge = bridge
        self.root = bridge.root
        self.out = Path(output)
        self.owned_inventory_crafting = None
        initial = bridge.read()
        self.registry = dict(bridge.registry)
        self.run_id = bridge.run_id
        self.session = initial['world_session']
        self.dimension = initial['dimension']
        self.authorize_inventory(initial)

    def authorize_inventory(self, state):
        """Use live native trial ownership, without unlocking another mode."""
        registry = self.bridge.registry
        if (registry.get('protocol') != 1 or registry.get('enabled') is not True
                or registry.get('allow_death_respawn') is not True
                or registry.get('goal') != 'defeat_ender_dragon'
                or any(registry.get(key) != self.registry.get(key)
                       for key in ('trial_id', 'world_id', 'world_name'))
                or not self.run_id or self.bridge.run_id != self.run_id):
            raise Paused('Trial SDK controller registration changed; preserve the inventory')
        validate_scope(state, self.registry, self.session, self.run_id)
        stamp = state.get('time')
        if (type(stamp) not in (int, float) or not math.isfinite(stamp)
                or not 0 <= time.time() - stamp / 1000 <= 3):
            raise Paused('Trial SDK requires a fresh native observation; no inventory action sent')
        if (state.get('dimension') != self.dimension
                or state.get('trial_identity', {}).get('process_alive') is not True
                or state.get('safety_hold', {}).get('active') is not False
                or state.get('health_recovery_hold') is not False):
            raise Paused('Trial SDK native ownership or safety scope changed; preserve the inventory')

    def status(self):
        state = self.bridge.read()
        self.authorize_inventory(state)
        return state

    def checked(self, op, **arguments):
        if op != 'slot_click':
            raise Paused('Trial SDK crafting only permits ordinary scoped slot clicks')
        self.status()
        return self.bridge.request(op, **arguments)


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
        self.pickup_clearance_target = None
        self.pickup_strategy = None
        self.cooking_readiness = None
        self.small_shelter = None
        self.safety_readiness = None
        self.wood_target_logs = None

    def worktable_available_here(self, state, world):
        if inventory(state).get('crafting_table', 0):
            return True
        point = self.stations.get('crafting_table')
        if (not isinstance(point, (list, tuple)) or len(point) != 3
                or any(type(n) is not int for n in point)):
            return False
        point = tuple(point)
        if world.name(point) != 'crafting_table':
            return False
        parents = world.paths(state['pos'])
        stance = world.approach(parents, point)
        if stance is None:
            return False
        route = world.route(parents, stance)
        return len(route) <= 32 and tuple(route) not in self.rejected_routes

    def planks(self, amount):
        """Choose a carried species which can actually supply this recipe."""
        inv = inventory(self.b.read())
        choices = []
        for log in sorted(LOGS):
            plank = log.removesuffix('_log') + '_planks'
            deficit = max(0, amount - inv.get(plank, 0))
            required_logs = math.ceil(deficit / 4)
            if inv.get(log, 0) >= required_logs:
                choices.append((required_logs, plank, log))
        if not choices:
            raise Paused('没有同一树种的足量木板或原木；保留现有合成材料')
        _, plank, log = min(choices)
        while self.count(plank) < amount:
            if not self.count(log):
                raise Paused('已选树种的原木改变；不重放合成')
            self.craft(plank, {(0, 0): log}, width=2, produces=4)
        return plank

    def cooking_plan(self, state):
        from survival_cooking import cooking_plan
        from smelting_fuel import recipe_jar_for_client
        try:
            self.cooking_readiness = cooking_plan(state, recipe_jar_for_client(self.b))
        except (OSError, ValueError, KeyError) as error:
            self.cooking_readiness = {'ready': False, 'fuel_ready': False,
                                      'coal_requirement': 0, 'raw_needed': 0,
                                      'reason': str(error)[:256]}
        return self.cooking_readiness

    def scan(self):
        self.check()
        x, y, z = cell(self.b.state['pos'])
        lo, hi = [x - 10, y - 6, z - 10], [x + 10, y + 6, z + 10]
        result = self.b.request('scan', min=lo, max=hi, details=True)
        self.world = TrialWorld(result['blocks'], lo, hi)
        return self.world

    def go_near(self, target, reach=3.6):
        """Return to this save's recorded station using fresh, bounded terrain.

        Ordinary resource approaches retain their small local scan. A station
        can lie outside that scan after mining, so consider two bounded scans
        containing both endpoints; no remembered route or unscanned air is
        used as movement evidence.
        """
        target = tuple(target)
        station_name = next((name for name, point in self.stations.items()
                             if tuple(point) == target), None)
        world = self.scan()
        parents = world.paths(self.b.state['pos'])
        stance = world.approach(parents, target, reach)
        if station_name is not None and world.known(target) and world.name(target) != station_name:
            raise Paused('Recorded station changed; preserve its location and carried materials')
        if stance is None and station_name is not None:
            start = cell(self.b.read()['pos'])
            for padding in (4, 8):
                low = [min(a, b) - padding for a, b in zip(start, target)]
                high = [max(a, b) + padding for a, b in zip(start, target)]
                low[1], high[1] = max(-64, low[1]), min(319, high[1])
                volume = math.prod(b - a + 1 for a, b in zip(low, high))
                if volume <= 0 or volume > 30_000:
                    break
                self.check()
                before = self.b.read()
                result = self.b.request('scan', min=low, max=high, details=True)
                if (result.get('scan_cells_read') != volume or result.get('scan_total_cells') != volume
                        or result.get('world_session') != before.get('world_session')
                        or result.get('control_revision') != before.get('control_revision')
                        or distance(result['pos'], before['pos']) > .3):
                    raise Paused('Station corridor scan is incomplete or changed; no route is executed')
                world = TrialWorld(result['blocks'], low, high)
                self.world = world
                if world.name(target) != station_name:
                    raise Paused('Recorded station changed; preserve its location and carried materials')
                parents = world.paths(self.b.state['pos'], limit=min(10_000, volume))
                stance = world.approach(parents, target, reach)
                self.event('station_corridor_observed', station=station_name, target=list(target),
                           bounds={'min': low, 'max': high}, cells=volume,
                           reachable=stance is not None)
                if stance is not None:
                    break
        if stance is None:
            raise Paused('Recorded station has no fresh supported walking route' if station_name
                         else '当前扫描范围内没有安全可达的操作位置。')
        route = world.route(parents, stance)
        if len(route) > 128:
            raise Paused('Recorded station route exceeds the bounded walking budget')
        # Runner.walk sends only normal walk_path batches and verifies arrival;
        # it does not acquire Flight or construct a route from model output.
        self.walk(route)
        if station_name is not None:
            fresh = self.scan()
            actual = self.b.read()['pos']
            eye = [actual[0], actual[1] + 1.62, actual[2]]
            if (fresh.name(target) != station_name
                    or distance(eye, [v + .5 for v in target]) > reach + .25
                    or not fresh.sight(cell(actual), target)):
                raise Paused('Recorded station identity, reach or visibility changed after walking')
            self.event('station_approach_verified', station=station_name, target=list(target),
                       position=list(actual), route_steps=len(route), flight_used=False)

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
                if not world.pickup_reach(pos, row['pos']):
                    continue
                route = world.route(parents, stance)
                if len(route) <= 32 and tuple(route) not in self.rejected_routes:
                    choices.append((len(route), row['uuid'], stance, route))
        return min(choices)[1:] if choices else None

    def pickup_clearance_plan(self, world, state, rows):
        if not any(row.get('visible') is True for row in rows.values()):
            return None
        parents, clearances = world.leaf_access_paths(state['pos'])
        choices = []
        ordinary = world.pickup_paths(state['pos'])
        for row in rows.values():
            if row.get('visible') is not True:
                continue
            for stance, leaves in clearances.items():
                if not leaves or not world.pickup_reach(center(stance), row['pos']):
                    continue
                route = world.route(parents, stance)
                if len(route) > 32:
                    continue
                # Recheck the whole hypothetical route after all removals.
                # Its only purpose is choosing the next currently reachable
                # leaf. No hypothetical air is used to execute movement.
                virtual = TrialWorld([value for point, value in world.blocks.items() if point not in leaves],
                                     world.low, world.high)
                if stance not in virtual.pickup_paths(state['pos']):
                    continue
                protected = {tuple(p) for p in self.stations.values()}
                protected.update(tuple(map(int, key.split(','))) for key in self.owned
                                 if len(key.split(',')) == 3 and all(v.lstrip('-').isdigit() for v in key.split(',')))
                if leaves & protected:
                    continue
                for leaf in leaves:
                    if leaf in self.excluded:
                        continue
                    approach = world.approach(ordinary, leaf)
                    if approach is None:
                        continue
                    approach_route = world.route(ordinary, approach)
                    if tuple(approach_route) in self.rejected_routes:
                        continue
                    choices.append((len(leaves), len(approach_route), len(route), row['uuid'],
                                    leaf, approach_route))
        return min(choices)[3:] if choices else None

    def clear_pickup_leaf(self, identity, leaf, route):
        self.walk_pickup_route(route)
        fresh = self.scan()
        state = self.b.read()
        # Reobserve the current item and exact leaf immediately before mining.
        if identity not in self.remember_log_drops(state):
            return
        under_player = (math.floor(state['pos'][0]), math.floor(state['pos'][1]) - 1,
                        math.floor(state['pos'][2]))
        if (leaf == under_player or not fresh.name(leaf).endswith('_leaves')
                or not fresh.safe(leaf) or fresh.row(leaf).get('block_entity')):
            raise Paused('Pickup leaf clearance changed or would remove current footing')
        receipt = self.b.request('mine_block', pos=list(leaf), expected_state=fresh.row(leaf)['state'], seconds=18)
        if receipt.get('server_confirmed') is not True or receipt.get('outcome_pending') is True:
            raise Paused('Pickup leaf mining outcome is not server-confirmed; preserve request')
        after = self.scan()
        if not after.open(leaf):
            raise Paused('Pickup leaf clearance has no fresh open-cell confirmation')
        self.event('pickup_leaf_cleared', target=list(leaf), item_uuid=identity,
                   pickup_confirmed=False)

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
        attempted = set()
        for unused in range(12):
            state = self.b.read()
            found = self.remember_log_drops(state)
            if sum(inventory(state).get(name, 0) for name in LOGS) > before:
                return state
            world = self.scan()
            plan = self.pickup_plan(world, self.b.read(), found)
            if not plan:
                if self.pickup_strategy == 'direct_pickup':
                    break
                clearance = self.pickup_clearance_plan(world, self.b.read(), found)
                if clearance:
                    self.clear_pickup_leaf(*clearance)
                    continue
                break
            identity, stance, route = plan
            # The stored location never substitutes for the current item.
            current = self.remember_log_drops(self.b.read()).get(identity)
            if current is None:
                continue
            attempt = (identity, stance, tuple(route))
            if attempt in attempted:
                break
            attempted.add(attempt)
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
            # No inventory gain does not prove a route was blocked. Do not
            # persist it as a terrain refusal across hot updates or move it
            # into the bridge's no-replay set. Next cycle gets a fresh entity.
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
        state = self.station_inventory_available()
        if name in self.stations:
            world = self.scan()
            target = tuple(self.stations[name])
            parents = world.paths(self.b.state['pos'])
            if world.name(target) == name and world.approach(parents, target) is not None:
                return super().station(name)
        # A carried station belongs at the current verified footing. Its old
        # coordinates and camp/anchor remain records, not a reason to return
        # to a distant pit before opening this same ordinary workstation.
        if inventory(state).get(name) and name in {'crafting_table', 'furnace'}:
            return self.local_station_fallback(name)
        if name == 'crafting_table' and name not in self.stations:
            inv = inventory(state)
            if any(inv.get(log) for log in LOGS) or any(n.endswith('_planks') and v >= 4 for n,v in inv.items()):
                return self.local_station_fallback(name)
        if name == 'furnace' and name not in self.stations:
            raise Paused('No recorded or carried furnace is available; no phantom station placement')
        if self.camp is not None:
            try:
                return super().station(name)
            except Paused as error:
                if str(error) not in {'Recorded station has no fresh supported walking route',
                                      'Recorded station route exceeds the bounded walking budget'}:
                    raise
                return self.local_station_fallback(name)
        if self.station_anchor is None:
            self.observe()
        if self.station_anchor is None:
            raise Paused('No observed safe station footing')
        previous = self.camp
        self.camp = list(self.station_anchor)
        try:
            try:
                return super().station(name)
            except Paused as error:
                if str(error) not in {'Recorded station has no fresh supported walking route',
                                      'Recorded station route exceeds the bounded walking budget'}:
                    raise
                return self.local_station_fallback(name)
        finally:
            self.camp = previous

    def station_inventory_available(self):
        if self.b.halted or self.b.pending_mutations:
            raise Paused('Unconfirmed native operation preserved; no workstation is opened or placed')
        state = self.b.read()
        menu = state.get('menu', {})
        width = {'InventoryMenu': 2, 'CraftingMenu': 3}.get(menu.get('type'))
        if (menu.get('cursor', {}).get('count', 0)
                or width and any(row.get('count', 0) for row in menu.get('slots', [])[1:width * width + 1])
                or menu.get('type') in {'FurnaceMenu', 'BlastFurnaceMenu', 'SmokerMenu'}
                    and any(row.get('count', 0) for row in menu.get('slots', [])[:3])):
            raise Paused('Occupied workstation grid, furnace or cursor preserved; no workstation is changed')
        return state

    def local_station_fallback(self, name):
        """Place a carried station, or craft a local table when required.

        Keep previous station coordinates protected. Only tables can be made
        here, using a 2x2 inventory recipe which never calls station. Furnaces
        must already exist in inventory; no old furnace is excavated.
        """
        if name not in {'crafting_table', 'furnace'}:
            raise Paused('Recorded station is unreachable; no supported local station fallback')
        state = self.station_inventory_available()
        inv = inventory(state)
        if name == 'furnace' and not inv.get(name):
            raise Paused('Recorded furnace retained; no carried furnace is available for local placement')
        if (not inv.get(name) and not any(n.endswith('_planks') and count >= 4 for n, count in inv.items())
                and not any(inv.get(log, 0) for log in LOGS)):
            raise Paused('Recorded table retained; insufficient carried material for a local crafting table')
        world = self.scan()
        parents = world.paths(self.b.state['pos'])
        protected = {tuple(point) for point in self.stations.values()}
        protected.update(tuple(map(int, key.split(','))) for key in self.owned
                         if len(key.split(',')) == 3 and all(v.lstrip('-').isdigit() for v in key.split(',')))
        actual = self.b.read()['pos']
        spots = []
        for point in parents:
            route = world.route(parents, point)
            x, y, z = point
            body_overlap = (x < actual[0] + .31 and x + 1 > actual[0] - .31
                            and z < actual[2] + .31 and z + 1 > actual[2] - .31
                            and y < actual[1] + 1.8 and y + 1 > actual[1])
            if (point in protected or body_overlap or world.name(point) != 'air'
                    or not world.full((x, y - 1, z)) or world.row((x, y - 1, z)).get('block_entity')
                    or len(route) > 8 or distance(center(point), actual) > 2.5):
                continue
            spots.append((len(route), distance(center(point), actual), point))
        if not spots:
            raise Paused('Recorded table retained; no fresh safe local placement position')
        target = min(spots)[2]
        previous = list(self.stations[name]) if name in self.stations else None
        if not inv.get(name):
            plank = self.planks(4)
            self.craft(name, {(0, 0): plank, (0, 1): plank,
                              (1, 0): plank, (1, 1): plank}, width=2)
        self.place(name, target)
        fresh = self.scan()
        if fresh.name(target) != name:
            raise Paused('Local station placement is unconfirmed; old station retained')
        self.stations[name] = list(target)
        self.save('running')
        self.event('local_station_placed', station=name, previous=previous, target=list(target),
                   previous_record_retained=bool(previous and self.owned.get(','.join(map(str, previous))) == name),
                   source='carried_station_normal_supported_placement' if inv.get(name)
                          else 'carried_material_normal_inventory_craft_and_supported_placement')
        self.go_near(target)
        self.interact(target)
        expected_menu = 'CraftingMenu' if name == 'crafting_table' else 'FurnaceMenu'
        if self.b.state['menu']['type'] != expected_menu:
            raise Paused('Local station did not open its verified menu')

    def craft(self, output, cells, width=3, produces=1):
        """Use the existing SDK's acknowledged clicks, never the stalled macro."""
        from kit_runtime.inventory import InventorySession
        from material_manufacture import _inventory_execute, _inventory_output_room
        from material_plan import inventory_counts
        import stack_recipe

        if (width not in (2, 3) or type(produces) is not int or not 1 <= produces <= 64
                or not isinstance(output, str) or not output or not cells):
            raise Paused('Invalid explicit trial recipe')
        ingredients = {}
        for point, item in sorted(cells.items()):
            if (not isinstance(point, tuple) or len(point) != 2
                    or any(type(n) is not int or not 0 <= n < width for n in point)
                    or not isinstance(item, str) or not item or ':' in item):
                raise Paused('Invalid explicit trial ingredient cell')
            ingredients.setdefault('minecraft:' + item, []).append(1 + point[0] * width + point[1])
        spec = {'recipe_id': 'trial:' + output, 'output': 'minecraft:' + output,
                'width': width, 'produces': produces, 'ingredients': ingredients,
                'missing_for_one': {}}
        # An unresolved earlier click/mining result never gains a fresh recipe.
        if getattr(self.b, 'halted', False) or getattr(self.b, 'pending_mutations', {}):
            raise Paused('Unconfirmed native mutation preserved; no trial craft is started')
        initial = self.b.read()
        if initial['menu']['cursor']['count']:
            raise Paused('Cursor already holds an item; preserve the current trial inventory')
        previous_menu = initial['menu']
        previous_width = {'InventoryMenu': 2, 'CraftingMenu': 3}.get(previous_menu.get('type'))
        if previous_width and any(row['count'] for row in previous_menu['slots'][1:previous_width * previous_width + 1]):
            raise Paused('Crafting grid already holds items; preserve it before opening another station')
        if width == 3:
            self.station('crafting_table')
        else:
            self.b.close()
        state = self.b.read()
        menu = state['menu']
        expected_menu = 'InventoryMenu' if width == 2 else 'CraftingMenu'
        grid = list(range(1, width * width + 1))
        if (menu.get('type') != expected_menu or len(menu.get('slots', [])) < (46 if width == 3 else 45)
                or menu['cursor']['count'] or any(menu['slots'][cell]['count'] for cell in grid)):
            raise Paused('Expected a clear real recipe menu; existing grid and cursor are preserved')
        needed = Counter({item: len(positions) for item, positions in ingredients.items()})
        before = inventory_counts(state)
        if any(before[item] < amount for item, amount in needed.items()):
            raise Paused('Missing actual trial ingredients: ' + output)
        client = _TrialCraftClient(self.b, self.output)
        self.craft_client = client  # Retain ownership evidence if an SDK acknowledgement fails.
        try:
            if width == 2:
                result = _inventory_execute(client, spec, before[spec['output']] + produces,
                                            authorize=client.authorize_inventory)
            else:
                # Reuse the SDK's one-round source selection. Its stack-output
                # capacity is narrowed below for tools and other single items.
                batch = stack_recipe.plan_batch(state, spec, max_rounds=1)
                remaining = {row['slot']: dict(row) for row in menu['slots'][-36:]}
                for action in batch['actions']:
                    row = remaining[action['source']]
                    row['count'] -= action['count']
                    if not row['count']:
                        row['item'] = 'minecraft:air'
                if _inventory_output_room(list(remaining.values()), spec) < produces:
                    raise Paused('No verified trial output space; no ingredient was moved')
                client.owned_inventory_crafting = {'menu_id': menu['id'],
                    'world_session': state.get('world_session'), 'trial_id': self.b.registry['trial_id'],
                    'run_id': self.b.run_id}
                session = InventorySession(client)
                for action in batch['actions']:
                    source = state['menu']['slots'][action['source']]
                    if source['item'] != action['item'] or source['count'] < action['source_count']:
                        raise Paused('Planned trial ingredient changed; no duplicate craft')
                    state = session.place_cell(state, source, action['cell'], action['count'])
                    state = session.wait_grid(state, menu['id'], action['item'], [action['cell']], action['count'])
                state = session.wait_recipe(state, spec['output'])
                if state['menu']['slots'][0]['count'] != produces:
                    raise Paused('Actual trial recipe output quantity differs; ingredients preserved')
                pre_output = inventory_counts(state)
                totals = {item: pre_output[item] + sum(state['menu']['slots'][cell]['count'] for cell in positions)
                          for item, positions in ingredients.items()}
                if _inventory_output_room(state['menu']['slots'][-36:], spec) < produces:
                    raise Paused('Trial output space changed; owned recipe grid preserved')
                state = session.click(state, 0, 'quick_move')
                result = session._wait(state, menu['id'],
                    lambda current: not current['cursor']['count']
                        and not any(current['slots'][cell]['count'] for cell in grid)
                        and sum(row['count'] for row in current['slots'][-36:] if row['item'] == spec['output'])
                            == pre_output[spec['output']] + produces,
                    'trial_workbench_output', confirmations=2, interval=.1, fresh=True)
                final = inventory_counts(result)
                if any(totals[item] - final[item] != amount for item, amount in needed.items()):
                    raise Paused('Trial recipe material balance differs; no further craft')
                client.owned_inventory_crafting = None
            if inventory_counts(result)[spec['output']] < before[spec['output']] + produces:
                raise Paused('Trial craft has no confirmed inventory output')
        except TrialGuardBusy:
            raise
        except (RuntimeError, ValueError) as error:
            # A delayed cursor/grid correction never justifies replaying clicks
            # or closing the container. Native Resume must reobserve its items.
            self.b.halted = True
            if isinstance(error, Paused):
                raise
            raise Paused('Trial SDK crafting stopped without replay: ' + str(error)) from error
        self.b.close()
        self.event('crafted', item=output, count=produces, engine='kit_inventory_sdk')
        return result

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
        self.pickup_clearance_target = (None if self.pickup_target
                                       else self.pickup_clearance_plan(world, state, found))
        if self.pickup_target or self.pickup_clearance_target:
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
        wooden_door = any(name.endswith('_door') and name != 'iron_door' and amount for name,amount in inv.items())
        wood_budget = sum(v for name,v in inv.items() if name.endswith('_planks')) + 4*logs
        door_wood_budget = max((inv.get(log.removesuffix('_log') + '_planks', 0) + 4*inv.get(log, 0)
                               for log in LOGS), default=0)
        table_ready = self.worktable_available_here(state, world)
        door_board_requirement = 6 if table_ready else 10
        has_sword = any(has(name) for name in ('wooden_sword','stone_sword','iron_sword','diamond_sword','netherite_sword','golden_sword'))
        sheltered = bool(self.small_shelter and self.small_shelter.get('verified'))
        self.safety_readiness={'sheltered':sheltered,'wood_ready':bool(wooden_door or door_wood_budget>=door_board_requirement),
                               'table_ready':table_ready,'door_planks_required':0 if wooden_door else door_board_requirement,
                               'wood_deficit':0 if wooden_door else max(0,door_board_requirement-door_wood_budget),
                               'dirt_deficit':max(0,23-inv.get('dirt',0)),
                               'stone_sword_deficit':0 if any(has(n) for n in ('stone_sword','iron_sword','diamond_sword','netherite_sword')) else max(0,2-inv.get('cobblestone',0))}
        clock=state.get('day_time');night=type(clock) in (int,float) and (clock%24000>=11000 or clock%24000<1000)
        if sheltered:
            from trial_safety_preparation import _house_verified, _valid_door
            if world.known(tuple(self.small_shelter['inside'])) and not _house_verified(world,self.small_shelter,self.small_shelter['door_item']):
                self.small_shelter['verified']=False;sheltered=False
        if sheltered:
            inside=distance(state['pos'],center(tuple(self.small_shelter['inside'])))<.75
            if night:
                if not inside or not _valid_door(world,self.small_shelter['door'],self.small_shelter['door_item'],False):
                    candidates['enter_small_shelter']=LABELS['enter_small_shelter']
                return candidates
            if inside:
                candidates['leave_small_shelter']=LABELS['leave_small_shelter']
                return candidates
        house_materials = inv.get('dirt',0)>=23 or world.resource(state['pos'],{'dirt','grass_block'},self.excluded)
        if not sheltered and world.paths(state['pos']) and house_materials and (wooden_door or door_wood_budget >= door_board_requirement):
            candidates['prepare_small_shelter'] = LABELS['prepare_small_shelter']
            return candidates
        # Only the actual next recipe deficit can request another whole tree.
        # Native AutoChopper owns movement, crown verification, loot and cleanup.
        # Known dropped logs above still take priority over a new harvest.
        wood_deficit = (max(0,door_board_requirement-door_wood_budget)
                        if not sheltered and not wooden_door else
                        max(0,12-door_wood_budget) if starting else
                        max(0,4-door_wood_budget) if not has_sword else 0)
        self.wood_target_logs = None
        if wood_deficit:
            from trial_native_chop import observed_chop_plan
            target_logs = logs + math.ceil(wood_deficit/4)
            if observed_chop_plan(self, state, world, target_logs) is not None:
                self.wood_target_logs = target_logs
                candidates['gather_starting_wood'] = LABELS['gather_starting_wood']
                return candidates
        if not starting and not has_sword and (wood_budget >= 4 or inv.get('cobblestone',0) >= 2 and has('stick')):
            candidates['prepare_sword'] = LABELS['prepare_sword']
            return candidates
        if has('wooden_sword') and not any(has(name) for name in ('stone_sword','iron_sword','diamond_sword','netherite_sword')):
            if (has('stick') or wood_budget >= 2) and (inv.get('cobblestone',0) >= 2 or not starting and world.resource(state['pos'],{'stone','cobblestone'},self.excluded)):
                candidates['upgrade_stone_sword'] = LABELS['upgrade_stone_sword']
                return candidates
        protected = {tuple(point) for point in self.stations.values()}
        if self.camp:
            cx, cy, cz = self.camp
            protected.update(p for p in world.blocks if abs(p[0] - cx) <= 3 and abs(p[2] - cz) <= 3)
        if starting and station_possible and (logs >= 4 or sum(v for k, v in inv.items() if k.endswith('_planks')) >= 12):
            candidates['craft_wooden_tools'] = LABELS['craft_wooden_tools']
        stone_needed = (0 if has('stone_pickaxe') or has('iron_pickaxe') else 3)
        stone_needed += (0 if has('stone_axe') else 3) + (0 if has('furnace') or 'furnace' in self.stations else 8)
        if not starting and inv.get('cobblestone', 0) < stone_needed and world.resource(state['pos'], {'stone', 'cobblestone'}, protected):
            candidates['gather_stone'] = LABELS['gather_stone']
        if not starting and station_possible and stone_needed and inv.get('cobblestone', 0) >= stone_needed:
            candidates['craft_stone_tools'] = LABELS['craft_stone_tools']
        food = sum(inv.get(name, 0) for name in FOOD)
        cooking = self.cooking_plan(state) if food < 4 else None
        animals = [e for e in state.get('entities', [])
                   if e.get('type') in {'minecraft:cow', 'minecraft:pig', 'minecraft:sheep', 'minecraft:chicken'}
                   and e.get('health', 0) > 0]
        furnace_available = has('furnace') or 'furnace' in self.stations
        if cooking and furnace_available:
            goal = cooking.get('coal_requirement', 0)
            if (not starting and goal > inv.get('coal', 0)
                    and world.resource(state['pos'], {'coal_ore', 'deepslate_coal_ore'}, protected | self.excluded)):
                candidates['gather_cooking_fuel'] = LABELS['gather_cooking_fuel']
            if (cooking.get('fuel_ready') and (cooking.get('ready')
                    or cooking.get('raw_needed', 0) > 0 and has('stone_axe') and animals)):
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
        elif not self.explore_target and (has('stone_pickaxe') or has('iron_pickaxe')):
            from trial_surface_recovery import plan_upward, protected_cells
            if plan_upward(world, state, protected_cells(self)) is not None:
                candidates['recover_surface_access'] = LABELS['recover_surface_access']
        return candidates

    def execute(self, choice):
        self.reset_budget()
        self.stage = choice
        self.planned(choice, LABELS[choice], {})
        if choice == 'collect_log_drops':
            self.collect_log_drops()
        elif choice == 'gather_starting_wood':
            from trial_native_chop import gather_native_wood
            if self.wood_target_logs is None:
                raise Paused('No current recipe deficit authorizes another native tree')
            gather_native_wood(self, self.wood_target_logs)
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
        elif choice == 'recover_surface_access':
            from trial_surface_recovery import recover_upward
            self.equip_tool('stone')
            result = recover_upward(self)
            self.event('surface_recovery_batch', **result)
            if result['phase'] != 'progress' or result['actual_rise'] < .75:
                raise Paused(result['reason'])
        elif choice == 'gather_food':
            self.food()
            self.eat_if_needed()
        elif choice == 'gather_cooking_fuel':
            plan = self.cooking_plan(self.b.read())
            goal = plan.get('coal_requirement', 0)
            if goal <= self.count('coal'):
                raise Paused('Cooking fuel is already sufficient; reobserve before acquiring more coal')
            self.gather({'coal_ore', 'deepslate_coal_ore'}, {'coal'}, goal)
        elif choice == 'prepare_small_shelter':
            from trial_safety_preparation import prepare_small_shelter
            if not any(name.endswith('_door') and name != 'iron_door' and amount for name,amount in inventory(self.b.read()).items()):
                self.station('crafting_table')
                self.b.close()
            prepare_small_shelter(self)
        elif choice in {'prepare_sword','upgrade_stone_sword'}:
            from trial_safety_preparation import prepare_sword
            prepare_sword(self, upgrade_stone=choice == 'upgrade_stone_sword')
        elif choice in {'enter_small_shelter','leave_small_shelter'}:
            from trial_safety_routing import enter_known_shelter,leave_known_shelter
            if choice=='enter_small_shelter':enter_known_shelter(self)
            else:leave_known_shelter(self)
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
        self.failure_contexts = {}
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

    def actionable_candidates(self, candidates, state, world):
        if self.bridge.halted or self.bridge.pending_mutations:
            return {'wait': LABELS['wait']}
        context = local_failure_context(self.skills, state, world)
        for key in set(candidates) | {'explore_nearby'}:
            if self.failures.get(key, 0) and key in self.failure_contexts and self.failure_contexts[key] != context:
                self.failures[key] = 0
                self.failure_contexts.pop(key, None)
                self.event('macro_failure_scope_changed', action=key, position=state['pos'])
        result = {key: value for key,value in candidates.items()
                  if key == 'wait' or self.failures.get(key, 0) < 3}
        # A priority builder can return only one macro. If that known plan is
        # exhausted here, a normal freshly scanned route can change its local
        # conditions instead of leaving the worker permanently in wait.
        priority = {'prepare_small_shelter', 'gather_starting_wood', 'prepare_sword', 'upgrade_stone_sword'}
        if (len(result) < 2 and priority.intersection(candidates) - result.keys()
                and isinstance(world, World) and self.failures.get('explore_nearby',0) < 3):
            route = self.skills.exploration(world)
            if route is not None:
                self.skills.explore_target = route
                result['explore_nearby'] = '沿已扫描安全路线改变当前失败的局部前置条件，再复核原任务'
        return result

    def record_known_failure(self, action, state, world=None):
        if self.bridge.halted or self.bridge.pending_mutations:
            return False
        context = local_failure_context(self.skills, state, self.skills.world if world is None else world)
        self.failures[action] = (self.failures.get(action, 0) + 1
                                 if self.failure_contexts.get(action) in (None, context) else 1)
        self.failure_contexts[action] = context
        return True

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
            for name in ('camp', 'stations', 'owned', 'excluded', 'camp_completed', 'explored', 'station_anchor',
                         'tried_grids', 'rejected_routes', 'log_drops', 'small_shelter'):
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

    def pickup_visual_options(self, before):
        """A small visual question containing only prechecked pickup options."""
        found = self.skills.remember_log_drops(before)
        direct, access = self.skills.pickup_target, self.skills.pickup_clearance_target
        criteria = {'wait': 'Wait if the image conflicts with the facts or neither offered pickup plan is suitable. Do not invent a route.'}
        plans = {}
        identities = []
        if direct and direct[0] in found and found[direct[0]].get('visible'):
            identity, stance, route = direct
            criteria['direct_pickup'] = 'Use the checked normal walking route to the log pickup box, then confirm an actual inventory gain.'
            plans['direct_pickup'] = {'steps': len(route), 'end': center(stance)}
            identities.append(identity)
        if access and access[0] in found and found[access[0]].get('visible'):
            identity, leaf, route = access
            criteria['leaf_access'] = 'Use the checked approach; clear up to 3 observed non-support leaves with confirmed mining, rescan and walk to collect the log. Confirm inventory gain.'
            plans['leaf_access'] = {'approach_steps': len(route), 'next_leaf': list(leaf), 'max_leaves': 3}
            identities.append(identity)
        if len(criteria) < 2:
            return None
        item = found[min(identities, key=lambda identity: distance(found[identity]['pos'], before['pos']))]
        scene = {'scene_tag': 'pickup_route_strategy_v1', 'singleplayer_trial': True,
                 'health': before['health'], 'food': before['food'],
                 'logs_in_inventory': sum(inventory(before).get(name, 0) for name in LOGS),
                 'camera': {'yaw': before.get('yaw'), 'pitch': before.get('pitch')},
                 'visible_log': {'item': item['item'], 'count': item['count'],
                                 'relative_pos': [round(b - a, 3) for a, b in zip(before['pos'], item['pos'])]},
                 'prechecked_plans': plans,
                 'execution': 'Only these native plans; image cannot authorize unknown terrain, commands or pickup success.'}
        goal = 'Use the game image and fresh log observation to choose an offered pickup strategy. Collect this existing drop before chopping more trees.'
        return goal, criteria, scene, set(identities)

    def decide(self, candidates, before):
        self.control()
        before = {**before, 'pos': list(before['pos'])}
        if self.inference is not None and not self.inference.done():
            raise Paused('Previous model request is still in flight; do not overlap it')
        settings, config = self.model_config()
        image = None
        pickup_visual = (self.pickup_visual_options(before)
                         if 'collect_log_drops' in candidates
                         and config.get('vision_mode') in {'auto', 'always'} else None)
        visual = config.get('vision_mode') == 'always' or (
            config.get('vision_mode') == 'auto' and 'explore_nearby' in candidates and len(candidates) <= 3)
        if pickup_visual:
            visual = True
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
        cooking = getattr(self.skills, 'cooking_readiness', None)
        safety=getattr(self.skills,'safety_readiness',None)
        immediate_goal = short_term_goal(before, candidates, pending_logs, cooking, safety)
        if safety:scene['safety_preparation']=safety
        if cooking:
            scene['cooking'] = {key: cooking.get(key) for key in ('ready', 'fuel_ready', 'coal_requirement', 'raw_needed', 'owned_food', 'reason') if key in cooking}
        criteria = {key: CRITERIA.get(key, description) for key, description in candidates.items()}
        if pending_logs and 'explore_nearby' in criteria:
            criteria['explore_nearby'] = 'Follow only the prechecked normal route closer to this save\'s observed pending log drops, then rediscover actual item entities. Do not search for new trees or treat memory as pickup success.'
        if pickup_visual:
            # This dedicated route question is complete for its narrower
            # purpose. A full Survival capability catalogue would crowd out
            # the image without providing another executable pickup option.
            immediate_goal, criteria, scene, observed_identities = pickup_visual
        from decisions import question
        payload = {'model': 'kit-clef-flash', 'state': {'goal': immediate_goal, 'scene': scene},
                   'questions': question(criteria), 'keep_alive': -1}
        payload_bytes = len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf8'))
        if visual and payload_bytes > config['context_length'] - 1792:
            if pickup_visual or config.get('vision_mode') == 'always':
                raise Paused('完整能力和状态超过图像上下文预算，未裁剪事实；等待增加上下文或改用文字')
            self.event('vision_skipped_budget', text_bytes=payload_bytes,
                       image_text_budget=config['context_length'] - 1792,
                       retained='complete_structured_facts_and_capabilities')
            visual = False
        if payload_bytes > config['context_length'] - 256:
            raise Paused('完整能力和状态超过文字上下文预算，未裁剪事实')
        if visual:
            capture_origin = before
            capture = self.bridge.request('decision_screenshot')
            image = checked_image(capture.get('decision_image'), self.automation, capture)
            current = self.bridge.read()
            before = {**current, 'pos': list(current['pos'])}
            if (before['world_session'] != capture_origin['world_session']
                    or before['control_revision'] != capture_origin['control_revision']
                    or distance(before['pos'], capture_origin['pos']) > .5):
                raise Paused('Game pose or trial scope changed during image capture; discard visual question')
            if pickup_visual:
                current = self.pickup_visual_options(before)
                if current is None or current[3] != observed_identities or set(current[1]) != set(criteria):
                    raise Paused('Visible log pickup plans changed during image capture; discard visual question')
                immediate_goal, criteria, scene, observed_identities = current
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
        if pickup_visual:
            fresh = self.pickup_visual_options(after)
            if fresh is None or fresh[3] != observed_identities or set(fresh[1]) != set(criteria):
                raise Paused('Visible log pickup plans changed during model inference; discard choice')
            strategy = result['choice']
            self.skills.pickup_strategy = strategy if strategy != 'wait' else None
            selected_macro = 'collect_log_drops' if strategy != 'wait' else 'wait'
            self.event('pickup_visual_strategy', result=result, selected_macro=selected_macro,
                       scene_tag=scene['scene_tag'], image_used=image is not None,
                       image_text_bytes=payload_bytes, available_strategies=list(criteria))
            result = {**result, 'choice': selected_macro, 'pickup_strategy': strategy,
                      'probabilities': {'collect_log_drops': sum(value for key, value in result['probabilities'].items()
                                                                  if key != 'wait'),
                                        'wait': result['probabilities']['wait']}}
        else:
            self.skills.pickup_strategy = None
        self.event('decision', candidates=list(candidates), result=result, short_term_goal=immediate_goal,
                   scene_tag=scene.get('scene_tag', 'survival_macro'), image_used=image is not None,
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
        if not dead(passive) and passive.get('screen'):
            self.publish('waiting_interface', '玩家界面仍打开，关闭后自动重新观察；未关闭或操作该界面', passive)
            return
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
        if not state.get('guard_armed') or not state.get('guard_pve_only') or getattr(self,'guard_origin',None) is None or distance(state['pos'],self.guard_origin)>10:
            state = self.bridge.request('guard',pve_only=True)
            self.guard_origin = list(state['pos'])
            self.event('pve_guard_verified', armed=state.get('guard_armed'), pve_only=state.get('guard_pve_only'))
        if state.get('guard_busy'):
            self.publish('waiting_guard','Kit防护正在占用动作；等待结束后自动继续',state)
            return
        if state['dimension'] != 'minecraft:overworld':
            self.publish('waiting_capability', '当前维度缺少已实现的通关宏能力', state)
            return
        self.skills.reset_budget()
        self.publish('observing', '读取有限范围的真实地形与背包', state)
        world = self.skills.observe()
        before = self.bridge.read()
        candidates = self.skills.candidates(before, world)
        candidates = self.actionable_candidates(candidates, before, world)
        if len(candidates) < 2:
            clock=before.get('day_time')
            if getattr(self.skills,'small_shelter',None) and self.skills.small_shelter.get('verified') and type(clock) in (int,float) and (clock%24000>=11000 or clock%24000<1000):
                self.publish('waiting_daylight','已在小屋关门守夜，保持PvE防护；日出后自动继续',before)
                return
            reason = ('原木掉落仍待取，当前没有已验证的正常落地拾取路线；尚未入包'
                      if self.skills.log_drops else local_wait_reason(self.skills, before, self.failures))
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
            self.failure_contexts.pop(action, None)
            self.attempt_record(action, before, after, self.bridge.last_receipt)
            self.publish('running', '宏步骤通过当前游戏状态核对：' + LABELS[action], after)
        except TrialDeath:
            after = self.reader(self.automation)
            self.attempt_record(action, before, after, self.bridge.last_receipt)
            self.publish('death_wait', '试验过程中已死亡，下一轮正常复活', after)
        except TrialMovementBlocked as error:
            after = self.bridge.read()
            self.record_known_failure(action, after)
            self.attempt_record(action, before, after, error.receipt)
            self.publish('replanning', '原生已停止拒绝的步行路线；重新扫描并选择其他目标', after)
        except TrialGuardBusy as error:
            after=self.reader(self.automation)
            self.event('guard_priority_wait',action=action,reason=str(error),native_unresolved=bool(self.bridge.pending_mutations))
            self.publish('waiting_guard','防护先处理战斗或恢复，随后重新观察当前任务',after)
        except (Paused, OSError, ValueError, DecisionError) as error:
            after = self.reader(self.automation)
            self.record_known_failure(action, after)
            self.event('macro_failure', action=action, error_type=type(error).__name__,
                       reason=str(error)[:512],
                       native_dispatch_seen=len(self.bridge.receipts) > receipt_start,
                       native_unresolved=bool(self.bridge.pending_mutations))
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
                    signature = (type(error).__name__, str(error), self.command,
                                 bool(self.bridge and self.bridge.halted))
                    if signature != getattr(self, 'last_wait_signature', None):
                        self.event('worker_wait', error_type=type(error).__name__, reason=str(error)[:512],
                                   bridge_halted=signature[-1],
                                   active_request=getattr(self.bridge, 'active', None),
                                   expected_last_request=getattr(self.bridge, 'last', None),
                                   expected_revision=getattr(self.bridge, 'revision', None))
                        self.last_wait_signature = signature
                    self.publish('cancelled' if self.command == 'cancel' else 'paused', str(error))
                    # Service warming is a passive wait. A revoked native
                    # revision/manual takeover never autonomously rebinds.
                    if self.bridge and self.bridge.halted:
                        self.command = 'pause'
                if self.command == 'cancel' or self.phase == 'complete':
                    break
                delay = 5 if self.phase in {'waiting_model', 'waiting_capability', 'waiting_daylight', 'waiting_interface', 'waiting_guard'} else poll_seconds
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
