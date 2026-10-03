"""Bounded exterior ground lighting through normal Kit operations; no AI/UI.

Saved-scan planning is pure. Runtime uses fresh native loaded scans, an owned
MaterialClient guard lease, and later-frame block/inventory evidence. It does
not implement cave lighting or claim a dedicated placement acknowledgement.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import time

from potato_farm import valid_entity_scope

SCOPE = 'bounded_exterior_safe_ground_loaded_block_light_only'
EVIDENCE = 'normal_generic_interact_later_loaded_block_and_exact_inventory_no_dedicated_ack'
MAX_SCAN_CELLS = 50_000
PASSIVE_OVERPASS_TYPES=frozenset('minecraft:'+n for n in ('cow','sheep','pig','chicken','horse','donkey','mule','rabbit'))
TORCH = 'minecraft:torch'
GRASS = 'minecraft:grass_block'
# Explicit support allowlist, not a blanket `solid` permission. Wood, farming
# blocks, containers, liquid-bearing blocks and arbitrary building blocks stay
# excluded. Real loaded light/spawn geometry and a roof-free column are required.
SAFE_SUPPORTS = frozenset('minecraft:' + name for name in (
    'grass_block', 'dirt', 'coarse_dirt', 'rooted_dirt', 'sand', 'red_sand',
    'stone', 'cobblestone', 'stone_bricks', 'andesite', 'diorite', 'granite',
    'polished_andesite', 'polished_diorite', 'polished_granite',
    'deepslate', 'cobbled_deepslate', 'polished_deepslate',
    'deepslate_bricks', 'deepslate_tiles'))


class LightingBlocked(RuntimeError):
    pass


def point(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(type(v) is not int for v in value)):
        raise ValueError('A block position needs three integers')
    return tuple(value)


def bounds(low, high):
    low, high = point(low), point(high)
    if any(a > b for a, b in zip(low, high)) or low[1] < -64 or high[1] > 319:
        raise ValueError('Bounds must be ordered and within Overworld Y -64..319')
    if math.prod(b - a + 1 for a, b in zip(low, high)) > MAX_SCAN_CELLS:
        raise ValueError('Full-column bounds exceed the native 50,000-cell cap; use smaller explicit boxes')
    return low, high


def validate_movement_bounds(value, placement_low, placement_high):
    """A travel authorization box is not one scan; each actual sweep is capped."""
    if value is None:
        return placement_low, placement_high
    if not isinstance(value, dict) or set(value) != {'min', 'max'}:
        raise ValueError('Movement bounds require exactly min and max positions')
    low, high = point(value['min']), point(value['max'])
    if (any(a > b for a, b in zip(low, high)) or low[1] < -64 or high[1] > 319
            or any(abs(v) > 30_000_000 for pos in (low, high) for v in (pos[0], pos[2]))
            or any(low[i] > placement_low[i] or high[i] < placement_high[i] for i in range(3))):
        raise ValueError('Movement bounds must contain the placement region in bounded Overworld coordinates')
    return low, high


def protection_boxes(values=None):
    """Inclusive placement masks may be much larger than a scan box."""
    result = []
    for value in values or []:
        if not isinstance(value, dict) or set(value) != {'min', 'max'}:
            raise ValueError('Protected boxes require exactly min and max positions')
        low, high = point(value['min']), point(value['max'])
        if (any(a > b for a, b in zip(low, high)) or low[1] < -64 or high[1] > 319
                or any(abs(v) > 30_000_000 for p in (low, high) for v in (p[0], p[2]))):
            raise ValueError('Protected box must have ordered bounded Overworld coordinates')
        result.append({'min': list(low), 'max': list(high)})
    return result


def protected_position(pos, protected):
    return any(all(box['min'][i] <= pos[i] <= box['max'][i] for i in range(3))
               for box in protected or [])


def candidate_protected(support, target, protected):
    return protected_position(support, protected) or protected_position(target, protected)


def validate_budget(max_torches):
    if type(max_torches) is not int or not 1 <= max_torches <= 64:
        raise ValueError('Max torches must be 1..64')
    return max_torches


def block_id(row):
    state = row.get('state')
    return state.split('}', 1)[0].removeprefix('Block{') if isinstance(state, str) else ''


def scan_cells(reply, low, high, world=None):
    """Native scan omits AIR; validate every returned non-AIR coordinate."""
    low, high = bounds(low, high)
    if (not isinstance(reply, dict) or reply.get('phase') not in (None, 'done')
            or world is not None and (reply.get('world_session') != world or reply.get('phase') != 'done')
            or not isinstance(reply.get('blocks'), list)):
        raise LightingBlocked('Complete loaded detailed scan unavailable')
    if (world is not None or 'scan_entity_scope' in reply) and (
            not valid_entity_scope(reply.get('scan_entity_scope'))
            or not isinstance(reply.get('scan_entities'), list)):
        raise LightingBlocked('Current bounded loaded scan entity scope unavailable')
    cells = {}
    for row in reply['blocks']:
        if not isinstance(row, dict):
            raise LightingBlocked('Malformed scan block')
        pos = point(row.get('pos'))
        if pos in cells or any(not low[i] <= pos[i] <= high[i] for i in range(3)):
            raise LightingBlocked('Duplicate or out-of-bounds scan cell')
        if not isinstance(row.get('state'), str):
            raise LightingBlocked('Scan state unavailable')
        cells[pos] = row
    return cells


def risk_counts(cells, protected=None):
    dark = [p for p, v in cells.items() if v.get('zombie_block_light_risk') is True]
    masked = sum(candidate_protected(p, (p[0], p[1] + 1, p[2]), protected) for p in dark)
    return {'zombie_spawn_floor': sum(v.get('zombie_spawn_floor') is True for v in cells.values()),
            'zombie_block_light_risk': len(dark), 'protected_dark_floor': masked,
            'unprotected_dark_floor': len(dark) - masked, 'non_air_rows': len(cells)}


def safe_support(row, *, require_dark=True):
    return (block_id(row) in SAFE_SUPPORTS and row.get('solid') is True
            and row.get('fluid') is False and row.get('block_entity') is False
            and type(row.get('spawn_block_light')) is int and 0<=row['spawn_block_light']<=15
            and type(row.get('monster_spawn_block_light_limit')) is int
            and row.get('zombie_spawn_floor') is True
            and (not require_dark or row['spawn_block_light']<=row['monster_spawn_block_light_limit']
                 and row.get('zombie_block_light_risk') is True))


def safe_dark_support(row):
    return safe_support(row)


def candidates(cells, low, high, start=None, protected=None):
    """Score actual dark safe supports; potential is ordering, never light proof."""
    low, high = bounds(low, high)
    risky = {p for p, v in cells.items() if v.get('zombie_block_light_risk') is True}
    result = []
    park_y = high[1] - 2
    for pos, row in cells.items():
        x, y, z = pos
        if (pos not in risky or not safe_dark_support(row)
                or candidate_protected(pos, (x, y + 1, z), protected)
                or park_y - (y + 1) < 20
                or any((x, h, z) in cells for h in range(y + 1, high[1] + 1))):
            continue
        score = sum(sum(abs(a - b) for a, b in zip(pos, r)) <= 11 for r in risky)
        distance = math.dist(start, [x + .5, y + 2.5, z + .5]) if start else 0
        result.append({'support': list(pos), 'target': [x, y + 1, z],
                       'support_state': row['state'], 'priority_dark_floor_count': score,
                       'distance': distance})
    return sorted(result, key=lambda v: (-v['priority_dark_floor_count'], v['distance'], v['support']))


def body_clear(cells, x, z, foot_y, low, high):
    return (low[0] <= x <= high[0] and low[2] <= z <= high[2]
            and low[1] <= math.floor(foot_y) and math.ceil(foot_y + 1.8) - 1 <= high[1]
            and all((x, y, z) not in cells for y in range(math.floor(foot_y), math.ceil(foot_y + 1.8))))


def cardinal_route(cells, start, goal, foot_y, low, high):
    """A* is unnecessary in a bounded box; BFS yields a shortest clear corridor."""
    first = (math.floor(start[0]), math.floor(start[2]))
    last = (goal[0], goal[2])
    if not body_clear(cells, *first, foot_y, low, high) or not body_clear(cells, *last, foot_y, low, high):
        return None
    queue, parents = deque([first]), {first: None}
    while queue:
        here = queue.popleft()
        if here == last:
            route = []
            while here is not None:
                route.append(here)
                here = parents[here]
            return list(reversed(route))
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = here[0] + dx, here[1] + dz
            if nxt not in parents and body_clear(cells, *nxt, foot_y, low, high):
                parents[nxt] = here
                queue.append(nxt)
    return None


def compress_route(route):
    """Retain turns and endpoints: one navigation per clear straight segment."""
    if not route:
        return []
    out = [route[0]]
    for i in range(1, len(route) - 1):
        before = tuple(route[i][k] - route[i - 1][k] for k in (0, 1))
        after = tuple(route[i + 1][k] - route[i][k] for k in (0, 1))
        if before != after:
            out.append(route[i])
    if route[-1] != out[-1]:
        out.append(route[-1])
    return out


def stock(state):
    """Exact native backpack slots; absent or duplicate slots cannot prove -1."""
    rows = state.get('inventory')
    if not isinstance(rows, list):
        raise LightingBlocked('Exact inventory unavailable')
    slots = {}
    for row in rows:
        if not isinstance(row, dict):
            raise LightingBlocked('Malformed inventory row')
        slot = row.get('slot')
        if type(slot) is not int or not 0 <= slot < 36:
            continue
        if slot in slots or type(row.get('count')) is not int or row['count'] < 0 or not isinstance(row.get('item'), str):
            raise LightingBlocked('Exact inventory slots unavailable')
        slots[slot] = row
    if set(slots) != set(range(36)):
        raise LightingBlocked('Exact inventory requires all 36 backpack slots')
    return sum(row['count'] for row in slots.values() if row['item'] == TORCH)


def later_torch_frame(reply, state, target, world, before_stock, after_time):
    """Require a later real snapshot plus the exact loaded target and stock delta."""
    cells = scan_cells(reply, target, target, world)
    return (state.get('world_session') == world
            and type(state.get('time')) in (int, float) and state['time'] > after_time
            and set(cells) == {tuple(target)} and cells[tuple(target)]['state'] == 'Block{minecraft:torch}'
            and stock(state) == before_stock - 1)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temp.replace(path)


def plan(reply, low, high, max_torches, start=None, protected=None):
    validate_budget(max_torches)
    protected = protection_boxes(protected)
    cells = scan_cells(reply, low, high)
    # This is a shortlist from one saved observation. Runtime must rescan after
    # each torch instead of assuming Manhattan-distance light propagation.
    return {'scope': SCOPE, 'mode': 'saved_scan_plan_only', 'cave_routes_completed': False,
            'bounds': {'min': list(low), 'max': list(high)}, 'max_torches': max_torches,
            'protected_boxes': protected, 'counts': risk_counts(cells, protected),
            'candidates': candidates(cells, low, high, start, protected)[:max_torches],
            'limitation': 'Shortlist within observed bounds only; live placement checks the exact support column to Y319. No actions, inferred post-placement light or completion claim'}


class LightingRun:
    def __init__(self, client, low, high, max_torches, out, initial, protected=None, movement_bounds=None):
        validate_budget(max_torches)
        low, high = bounds(low, high)
        self.protected = protection_boxes(protected)
        self.move_low, self.move_high = validate_movement_bounds(movement_bounds, low, high)
        self.c, self.low, self.high = client, low, high
        self.limit, self.out = max_torches, Path(out)
        self.hurt = initial['recent_hurt_at']
        self.report = {'scope': SCOPE, 'evidence_scope': EVIDENCE, 'cave_routes_completed': False,
                       'bounds': {'min': list(low), 'max': list(high)}, 'max_torches': max_torches,
                       'world_session': client.world, 'task_session': client.task,
                       'protected_boxes': self.protected,
                       'movement_bounds': {'min': list(self.move_low), 'max': list(self.move_high)}, 'placed': [], 'state': 'running',
                       'progress': {'placed_verified': 0, 'placement_limit': max_torches,
                                    'dark_floor_last_observed': None,
                                    'dark_floor_observation_stage': None}}
        self.intent_dir = client.root / 'lighting-intents'
        self.c.start_progress('岛屿补光', self.limit, done=0, phase='本批预算；检查暗处')

    def save(self):
        write_json(self.out / 'report.json', self.report)

    def fresh(self, work=True):
        state = self.c.request('snapshot')
        if (state.get('world_session') != self.c.world or not state.get('connected')
                or state.get('control_revision') != self.c.rev or state.get('manual_movement')):
            raise LightingBlocked('Control or world changed')
        if (not state.get('guard_armed') or not state.get('guard_pve_only') or not state.get('flight')
                or state.get('under_water') or state.get('safety_hold', {}).get('active')
                or state.get('health', 0) < (20 if work else 14)
                or work and (state.get('food', 0) < 18 or state.get('recent_hurt_at', 0) > self.hurt)):
            raise LightingBlocked('Protection, health, injury, or food reserve changed')
        return state

    @staticmethod
    def active_hostiles(state):
        return [entity for entity in state.get('entities', [])
                if isinstance(entity, dict) and entity.get('hostile') is True
                and entity.get('alive') is not False
                and not (type(entity.get('health')) in (int, float) and entity['health'] <= 0)]

    def wait_for_guard(self, *, work=True, stage='placement', seconds=60):
        """Wait for the existing protection owner; never send combat or movement."""
        deadline = time.monotonic() + seconds
        started, samples = None, 0
        while True:
            state = self.fresh(work=work)
            busy = state.get('guard_busy') is True or bool(self.active_hostiles(state))
            if not busy:
                if started is not None:
                    self.report.setdefault('guard_waits', []).append({
                        'stage': stage, 'samples': samples, 'first_observed_at': started,
                        'settled_at': state['time'], 'outcome': 'existing_guard_settled',
                        'input_dispatched': False})
                    self.save()
                return state
            if started is None:
                started = state['time']
                self.c.set_progress(done=len(self.report['placed']), phase='保护处理中；补光暂缓')
            samples += 1
            if time.monotonic() >= deadline:
                self.report.setdefault('guard_waits', []).append({
                    'stage': stage, 'samples': samples, 'first_observed_at': started,
                    'last_observed_at': state['time'], 'outcome': 'bounded_wait_unresolved',
                    'input_dispatched': False})
                self.save()
                raise LightingBlocked('Existing guard stayed busy; no lighting input or interaction dispatched')
            time.sleep(.25)

    def scan(self, low, high, name=None):
        bounds(low, high)
        reply = self.c.request('scan', min=list(low), max=list(high), details=True)
        scan_cells(reply, low, high, self.c.world)
        if name:
            write_json(self.out / name, reply)
        return reply

    def intent_path(self, target):
        key = hashlib.sha256((self.c.world + ':' + ','.join(map(str, target))).encode()).hexdigest()
        return self.intent_dir / (key + '.json')

    def reject_unknown_intents(self):
        for path in self.intent_dir.glob('*.json'):
            record = json.loads(path.read_text())
            if record.get('world_session') != self.c.world or record.get('state') == 'verified':
                continue
            target = point(record.get('target'))
            if all(self.low[i] <= target[i] <= self.high[i] for i in range(3)):
                raise LightingBlocked('Unresolved prior lighting interaction; inspect intent before any replay: ' + str(path))

    def move(self, target, *, allow_entity_overpass=True):
        # Fresh native AIR and entity intersection checks cover the full swept
        # player body, not just endpoint cells. Native air_only checks again.
        state = self.fresh()
        start = state['pos']
        low = [math.floor(min(start[i], target[i]) - (.35 if i != 1 else 0)) for i in range(3)]
        high = [math.floor(max(start[i], target[i]) + (.35 if i != 1 else 1.8)) for i in range(3)]
        if any(low[i] < self.move_low[i] or high[i] > self.move_high[i] for i in range(3)):
            raise LightingBlocked('Movement body sweep exceeds authorized movement bounds')
        sweep = self.scan(low, high)
        if sweep['blocks']:
            raise LightingBlocked('Fresh movement body sweep is occupied')
        entities = sweep.get('scan_entities')
        if not isinstance(entities, list):
            raise LightingBlocked('Current swept entity observation unavailable')
        blockers = [e for e in entities if not isinstance(e, dict)
                    or e.get('type') not in ('minecraft:item', 'minecraft:experience_orb')]
        if blockers:
            # Passive animals in a flat route need a small observed overpass,
            # not an attack or an unchecked collision. Every leg rescans and
            # still uses native air_only; do not recurse into another overpass.
            if not allow_entity_overpass or abs(start[1] - target[1]) > .6:
                raise LightingBlocked('Current entity intersects movement body corridor')
            heights = []
            for entity in blockers:
                box = entity.get('bounds') if isinstance(entity, dict) else None
                if (not isinstance(entity, dict) or entity.get('alive') is not True
                        or entity.get('hostile') is not False or entity.get('type') not in PASSIVE_OVERPASS_TYPES or not isinstance(box, dict)):
                    raise LightingBlocked('Current entity intersects movement body corridor')
                minimum, maximum = box.get('min'), box.get('max')
                if (not isinstance(minimum, list) or not isinstance(maximum, list)
                        or len(minimum) != 3 or len(maximum) != 3
                        or any(type(v) not in (int, float) or not math.isfinite(v) for v in minimum + maximum)
                        or any(minimum[i] >= maximum[i] for i in range(3))):
                    raise LightingBlocked('Current entity intersects movement body corridor')
                heights.append(maximum[1])
            transit_y = max(start[1], target[1], max(heights) + 2)
            if transit_y - min(start[1], target[1]) > 6 or transit_y + 1.8 > self.move_high[1]:
                raise LightingBlocked('Current entity intersects movement body corridor')
            route = [[start[0], transit_y, start[2]],
                     [target[0], transit_y, target[2]], list(target)]
            self.report.setdefault('routes', []).append({'kind': 'passive_entity_overpass',
                'height': transit_y, 'types': sorted(set(e['type'] for e in blockers))})
            acknowledgement=None
            for waypoint in route:
                acknowledgement=self.move(waypoint, allow_entity_overpass=False)
            return acknowledgement
        acknowledgement = self.c.checked('navigate', target=target, arrival=.25, seconds=45, air_only=True)
        after = self.fresh()
        if math.dist(after['pos'], target) > .6:
            raise LightingBlocked('Actual movement arrival not verified; no movement replay')
        return acknowledgement

    @staticmethod
    def at_station(state, support):
        pos = state.get('pos')
        target = [support[0] + .5, support[1] + 2.5, support[2] + .5]
        return (isinstance(pos, list) and len(pos) == 3
                and all(type(value) in (int, float) and math.isfinite(value) for value in pos)
                and math.dist(pos, target) <= .6)

    def approach_station(self, support, state, index, attempt):
        """Defense can move us; reapproach before any placement intent exists."""
        if self.at_station(state, support):
            return
        target = [support[0] + .5, support[1] + 2.5, support[2] + .5]
        start = state['pos']
        low = [math.floor(min(start[i], target[i]) - (.35 if i != 1 else 0)) for i in range(3)]
        high = [math.floor(max(start[i], target[i]) + (.35 if i != 1 else 1.8)) for i in range(3)]
        if any(low[i] < self.move_low[i] or high[i] > self.move_high[i] for i in range(3)):
            raise LightingBlocked('Defended position left authorized movement bounds; no old-target interaction')
        sweep = self.scan(low, high, f'station-{index}-{attempt}-sweep.json')
        entities = sweep['scan_entities']
        clear = not sweep['blocks'] and all(isinstance(entity, dict) and entity.get('type') in
                  ('minecraft:item', 'minecraft:experience_orb') for entity in entities)
        if clear:
            self.move(target)
        else:
            park_y = self.high[1] - 2
            self.move([start[0], park_y, start[2]])
            self.move([target[0], park_y, start[2]])
            self.move([target[0], park_y, target[2]])
            self.move(target)
        self.report.setdefault('station_reapproaches', []).append({
            'index': index, 'attempt': attempt, 'from': start, 'target': target,
            'route': 'fresh_clear_sweep' if clear else 'guarded_high_transit'})
        self.save()

    def place(self, candidate, index):
        x, y, z = point(candidate['support'])
        target = point(candidate['target'])
        if (target != (x, y + 1, z)
                or any(not self.low[i] <= p[i] <= self.high[i]
                       for p in ((x, y, z), target) for i in range(3))
                or candidate_protected((x, y, z), target, self.protected)):
            raise LightingBlocked('Protected or inconsistent placement target; no interaction dispatched')
        target = list(target)
        prior, count_before = None, None
        for attempt in range(3):
            state = self.wait_for_guard(stage='before_station_recheck')
            self.approach_station((x, y, z), state, index, attempt)
            # Recheck after any protection movement. A low survey box may miss
            # a roof; this exact column proves only the current observation.
            column = self.scan([x, y, z], [x, 319, z], f'column-{index}.json')
            if (len(column['blocks']) != 1 or column['blocks'][0]['pos'] != [x, y, z]
                    or column['blocks'][0]['state'] != candidate['support_state']
                    or not safe_support(column['blocks'][0],require_dark=not candidate.get('_planned_batch',False))):
                raise LightingBlocked('Exact support/target/roof column changed')
            state = self.wait_for_guard(stage='before_torch_selection')
            if not self.at_station(state, (x, y, z)):
                continue
            count_before = stock(state)
            if count_before < 1:
                raise LightingBlocked('No exact torch stock remains')
            self.c.checked('select_item', item=TORCH)
            state = self.wait_for_guard(stage='after_torch_selection')
            if not self.at_station(state, (x, y, z)):
                continue
            if stock(state) != count_before:
                raise LightingBlocked('Torch stock changed during selection')
            pre = self.scan([x, y, z], [x, y + 4, z], f'pre-place-{index}.json')
            if (len(pre['blocks']) != 1 or pre['blocks'][0]['pos'] != [x, y, z]
                    or pre['blocks'][0]['state'] != candidate['support_state']
                    or not safe_support(pre['blocks'][0],require_dark=not candidate.get('_planned_batch',False))):
                raise LightingBlocked('Support/AIR changed immediately before interaction')
            if pre['scan_entities']:
                raise LightingBlocked('Current entity occupies support/target/body placement column')
            latest = self.fresh()
            if (latest.get('guard_busy') or self.active_hostiles(latest)
                    or not self.at_station(latest, (x, y, z))
                    or (latest.get('hand') or {}).get('item') != TORCH):
                continue
            if stock(latest) != count_before:
                raise LightingBlocked('Torch stock changed immediately before interaction')
            prior = latest
            break
        if prior is None:
            raise LightingBlocked('Defense repeatedly changed torch station; no interaction intent dispatched')
        intent = {'world_session': self.c.world, 'task_session': self.c.task,
                  'support': [x, y, z], 'target': target, 'state': 'interaction_intent',
                  'before_stock': count_before, 'before_time': prior['time'],
                  'roof_free_column_verified_to_y': 319}
        intent_path = self.intent_path(target)
        write_json(intent_path, intent)
        write_json(self.out / f'inventory-before-{index}.json', prior)
        ack = self.c.checked('interact', pos=[x, y, z], face='up',
                             expected_state=candidate['support_state'], expected_hand=TORCH)
        write_json(self.out / f'interaction-{index}.json', ack)
        deadline, frames, last_time = time.monotonic() + 6, 0, prior['time']
        while True:
            actual = self.scan(target, target)
            state = self.fresh()
            if later_torch_frame(actual, state, target, self.c.world, count_before, last_time):
                frames += 1
                last_time = state['time']
                write_json(self.out / f'actual-torch-{index}-frame-{frames}.json', actual)
                write_json(self.out / f'inventory-after-{index}-frame-{frames}.json', state)
                if frames >= 2:
                    break
            else:
                frames = 0
                if state.get('time', 0) > last_time:
                    last_time = state['time']
            if time.monotonic() >= deadline:
                raise LightingBlocked('Torch outcome unknown; intent retained and interaction will never repeat')
            time.sleep(.2)
        intent.update(state='verified', after_stock=stock(state), after_time=state['time'],
                      later_verified_frames=2, interaction_request=ack.get('id'), evidence_scope=EVIDENCE)
        write_json(intent_path, intent)
        self.report['placed'].append(intent)
        self.report['progress']['placed_verified'] = len(self.report['placed'])
        self.c.set_progress(done=len(self.report['placed']), phase='已核实放置；暗点待复扫')
        self.save()
        return actual

    def work(self):
        self.reject_unknown_intents()
        initial = self.scan(self.low, self.high, 'before-full-column.json')
        self.report['before'] = risk_counts(scan_cells(initial, self.low, self.high), self.protected)
        self.save()
        from lighting_batch_plan import plan as plan_batch
        from lighting_air_route import plan as plan_air
        cells=scan_cells(initial,self.low,self.high)
        state=self.fresh()
        planned=plan_batch(cells,self.low,self.high,state['pos'],self.protected,limit=min(8,self.limit))
        station=list(state['pos']);routes=[]
        for candidate in planned:
            target=[candidate['support'][0]+.5,candidate['support'][1]+2.5,candidate['support'][2]+.5]
            routes.append(plan_air(cells,station,target,self.low,self.high))
            station=target
        write_json(self.out/'batch-plan.json',{'world_session':self.c.world,'source_observed_at':initial.get('scan_ended_at',initial.get('time')),
            'prediction_only':True,'targets':planned,'routes':routes,'complete':False})
        self.report['progress'].update(dark_floor_last_observed=self.report['before']['zombie_block_light_risk'],
            dark_floor_observation_stage='single_initial_batch_scan',eligible_candidates=len(planned),
            planned_positions=len(planned),planning_predictions_are_completion=False)
        for index,candidate in enumerate(planned):
            state=self.fresh();target=[candidate['support'][0]+.5,candidate['support'][1]+2.5,candidate['support'][2]+.5]
            route=routes[index]
            if route is not None and math.dist(state['pos'],route[0])>.8:
                route=plan_air(cells,state['pos'],target,self.low,self.high)
            if route is not None:
                self.report.setdefault('routes',[]).append({'kind':'planned_low_air','waypoints':len(route)-1,
                    'maximum_y':max(p[1] for p in route),'target':candidate['target']})
                if math.dist(state['pos'],route[0])>.05:self.move(route[0])
                for waypoint in route[1:]:self.move(waypoint)
            else:
                # Unknown space never becomes AIR. The existing wider bounded
                # survey picks obstacle height; each issued segment still gets
                # LightingRun's fresh body/entity validation and real receipt.
                from material_jobs.acquisition import _travel
                owner=self
                class CheckedRoute:
                    def __getattr__(self,name):return getattr(owner.c,name)
                    def request(self,op,**params):
                        return owner.move(params['target']) if op=='navigate' else owner.c.request(op,**params)
                trace=[]
                _travel(CheckedRoute(),target,lambda:owner.fresh(),trace,clearance_padding=2.32,obstacle_margin=3.1)
                self.report.setdefault('routes',[]).append({'kind':'observed_obstacle_route','trace':trace,'target':candidate['target']})
            candidate={**candidate,'_planned_batch':True}
            actual=self.place(candidate,index)
            if not isinstance(actual,dict)or actual.get('world_session')!=self.c.world or not isinstance(actual.get('blocks'),list):
                raise LightingBlocked('Verified placement frame missing; batch retained')
            for row in actual['blocks']:cells[tuple(row['pos'])]=row
        final = self.scan(self.low, self.high, 'after-full-column.json')
        self.report['after'] = risk_counts(scan_cells(final, self.low, self.high), self.protected)
        self.report['state'] = 'bounded_run_finished'
        self.report.setdefault('stop_reason', 'Explicit max-torches budget reached')
        self.report['remaining_risk'] = self.report['after']['zombie_block_light_risk']
        self.report['remaining_unprotected_risk'] = self.report['after']['unprotected_dark_floor']
        self.report['progress'].update(
            dark_floor_last_observed=self.report['remaining_risk'],
            dark_floor_observation_stage='after_run',
            protected_dark_floor=self.report['after']['protected_dark_floor'],
            unprotected_dark_floor=self.report['remaining_unprotected_risk'],
            eligible_candidates=len(candidates(scan_cells(final, self.low, self.high),
                                               self.low, self.high, protected=self.protected)))
        self.c.set_progress(done=len(self.report['placed']),
                            phase=f"本批结束；已扫区域暗点 {self.report['remaining_unprotected_risk']}")
        self.save()

    def park(self):
        """Release only after native same-column guarded high parking is proven."""
        # Safe upward cleanup outranks fighting a distant/occluded hostile.
        # The owned native defensive-rise path keeps PvE armed while ascending.
        state = self.fresh(work=False)
        full=self.scan([math.floor(state['pos'][0]-.35),-64,math.floor(state['pos'][2]-.35)],
                       [math.floor(state['pos'][0]+.35),319,math.floor(state['pos'][2]+.35)],'actual-park-ground-column.json')
        ground=max((row['pos'][1]+1 for row in full['blocks'] if row.get('fluid')or not row.get('passable',False)),default=None)
        if ground is None or ground+24>315:raise LightingBlocked('Actual ground lacks bounded safe parking height')
        park = [state['pos'][0], max(state['pos'][1],ground+24), state['pos'][2]]
        low = [math.floor(state['pos'][0] - .35), math.floor(state['pos'][1]) + 1,
               math.floor(state['pos'][2] - .35)]
        high = [math.floor(state['pos'][0] + .35), self.high[1], math.floor(state['pos'][2] + .35)]
        if low[1] <= high[1] and self.scan(low, high, 'final-park-body-column.json')['blocks']:
            raise LightingBlocked('Safe high park column changed; preserve existing guard')
        self.c.park_target = park
        while abs(state['pos'][1] - park[1]) > 2:
            self.c._finish_vertical(state)
            state = self.fresh(work=False)
        self.c.checked('material_job_park', park_target=park)
        native = self.c.request('snapshot')
        lease = native.get('supervision_lease') or {}
        if (lease.get('kind') != 'materials' or lease.get('job_session') != self.c.task
                or lease.get('id') != self.c.heartbeat.id or lease.get('park_target') != park):
            raise LightingBlocked('Native park lease unproven; do not release heartbeat')
        self.c.park_target = park
        self.c._finish_vertical(native)
        arrival = self.fresh(work=False)
        if not self.c.park_near(arrival):
            raise LightingBlocked('Guarded high park arrival not verified')
        write_json(self.out / 'park-arrival.json', arrival)
        revision_before_finish = self.c.rev
        self.c.finish()
        self.confirm_final_park(revision_before_finish, arrival['time'])

    def owned_final_park(self, state, revision_before_finish, after_time):
        lease = state.get('supervision_lease') or {}
        safety = state.get('supervision_safety') or {}
        revision = state.get('control_revision')
        target = lease.get('park_target')
        return (state.get('connected') is True and state.get('world_session') == self.c.world
                and not state.get('manual_movement') and not state.get('under_water')
                and not (state.get('safety_hold') or {}).get('active')
                and state.get('guard_armed') is True and state.get('guard_pve_only') is True
                and state.get('flight') is True and state.get('health', 0) >= 18
                and type(state.get('time')) in (int, float) and state['time'] >= after_time
                and type(revision) is int and revision in (revision_before_finish, revision_before_finish + 1)
                and lease.get('kind') == 'parking' and lease.get('id') == self.c.heartbeat.id
                and lease.get('world_session') == self.c.world and lease.get('job_session') == self.c.task
                and lease.get('revision') == revision and lease.get('remote_finish') == 'guard'
                and isinstance(target, list) and len(target) == 3
                and all(type(value) in (int, float) and math.isfinite(value) for value in target)
                and math.dist(target, self.c.park_target) <= 2 and self.c.park_near(state)
                and safety.get('lease') == self.c.heartbeat.id and safety.get('job_session') == self.c.task
                and safety.get('cause') == 'controller_finished' and safety.get('action') == 'KEEP_PVE_GUARD'
                and type(safety.get('time')) in (int, float) and safety['time'] >= after_time)

    def confirm_final_park(self, revision_before_finish, after_time, seconds=4):
        """Observe asynchronous native finish; never repeat cleanup or rebase."""
        deadline, observations = time.monotonic() + seconds, []
        self.report['park_native_confirmed'] = False
        while True:
            final = self.c.raw()
            lease = final.get('supervision_lease') or {}
            observations.append({'time': final.get('time'), 'revision': final.get('control_revision'),
                                 'lease': lease.get('id'), 'kind': lease.get('kind'),
                                 'lease_revision': lease.get('revision')})
            write_json(self.out / 'final-snapshot.json', final)
            if self.owned_final_park(final, revision_before_finish, after_time):
                self.report['park_native_confirmed'] = True
                break
            # A snapshot may briefly contain the new control revision and old
            # material lease while the finish hook is publishing parking. Only
            # that same owned lease gets the bounded observation window.
            if (final.get('world_session') != self.c.world or not final.get('connected')
                    or final.get('manual_movement') or (final.get('safety_hold') or {}).get('active')
                    or lease.get('id') != self.c.heartbeat.id or lease.get('job_session') != self.c.task
                    or final.get('control_revision') not in (revision_before_finish, revision_before_finish + 1)
                    or time.monotonic() >= deadline):
                break
            time.sleep(.1)
        write_json(self.out / 'final-parking-observations.json', observations)
        self.save()
        if not self.report['park_native_confirmed']:
            raise LightingBlocked('Final owned parking receipt unavailable; cleanup was not replayed')


def preflight(root, low, high):
    from live_snapshot import read_fresh
    from safety_interlock import require_unlocked
    require_unlocked(root)
    state = read_fresh(root)
    require_unlocked(root, state)
    park_y = high[1] - 2
    pos = state.get('pos')
    if (not state.get('connected') or state.get('dimension') != 'minecraft:overworld'
            or state.get('screen') != '' or state.get('manual_movement')
            or state.get('health') != 20 or state.get('food', 0) < 18
            or not state.get('guard_armed') or not state.get('guard_pve_only')
            or not state.get('flight') or state.get('under_water') or state.get('guard_busy')
            or state.get('supervision_lease', {}).get('kind') not in (None, 'parking')
            or any(state.get(k) for k in ('borer_active', 'chopping', 'navigating', 'printing',
                                          'planter_active', 'feeder_active', 'fisher_active'))
            or state.get('professional_printer', {}).get('enabled')
            or state.get('build_job', {}).get('active')
            or not isinstance(pos, list) or len(pos) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in pos)
            or not low[0] + .35 <= pos[0] <= high[0] + .65
            or not low[2] + .35 <= pos[2] <= high[2] + .65
            or abs(pos[1] - park_y) > 2 or pos[1] > park_y
            or 'recent_hurt_at' not in state or stock(state) < 1):
        raise LightingBlocked('Start inside the explicit full-column box at high guarded park with full health/food reserve')
    return state


def run_live(game_dir, low, high, max_torches, out, protected=None, movement_bounds=None):
    low, high = bounds(low, high)
    validate_budget(max_torches)
    protected = protection_boxes(protected)
    validate_movement_bounds(movement_bounds, low, high)
    from material_client import MaterialClient
    root = Path(game_dir) / 'config' / 'twob2tkit' / 'automation'
    initial = preflight(root, low, high)
    park = [initial['pos'][0], high[1] - 2, initial['pos'][2]]
    client = MaterialClient(root, out, server=initial['server'], remote_finish='guard',
                            park_target=park, record_experience=False)
    runner = LightingRun(client, low, high, max_torches, out, initial, protected, movement_bounds)
    try:
        runner.work()
    except BaseException as error:
        runner.report.update(state='blocked', error=type(error).__name__ + ': ' + str(error))
        client.set_progress(done=len(runner.report['placed']), phase='暂停；查看补光报告')
        runner.save()
    finally:
        try:
            runner.park()
        except BaseException as error:
            runner.report['cleanup_error'] = type(error).__name__ + ': ' + str(error)
            # Do not mark finished against an unverified park. Keep the guard
            # lease alive for bounded operator handoff, then native watchdog owns
            # safety. Do not issue another work or interaction operation.
            runner.report['heartbeat_handoff_window_seconds'] = 60
            runner.save()
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and not client.heartbeat.stop.is_set():
                try:
                    current = client.raw()
                    if (current.get('world_session') != client.world or not current.get('connected')
                            or current.get('manual_movement') or current.get('control_revision') != client.rev):
                        client.heartbeat.close()
                        break
                except BaseException:
                    break
                time.sleep(1)
        runner.save()
    return runner.report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, help='Game directory containing config/twob2tkit/automation')
    parser.add_argument('--min', nargs=3, type=int, required=True, dest='low', metavar=('X', 'Y', 'Z'))
    parser.add_argument('--max', nargs=3, type=int, required=True, dest='high', metavar=('X', 'Y', 'Z'))
    parser.add_argument('--max-torches', type=int, default=8)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plan-only', action='store_true')
    parser.add_argument('--movement-bounds', nargs=6, type=int,
                        metavar=('MIN_X', 'MIN_Y', 'MIN_Z', 'MAX_X', 'MAX_Y', 'MAX_Z'),
                        help='Explicit larger travel box; torch placement remains inside --min/--max')
    parser.add_argument('--protect-box', nargs=6, type=int, action='append', default=[],
                        metavar=('MIN_X', 'MIN_Y', 'MIN_Z', 'MAX_X', 'MAX_Y', 'MAX_Z'),
                        help='Repeat inclusive support/target placement exclusions; overhead flight is allowed')
    parser.add_argument('--protect-file', type=Path,
                        help='JSON array of inclusive {min:[X,Y,Z],max:[X,Y,Z]} protected placement boxes')
    parser.add_argument('--scan', type=Path, help='Explicit saved native details=true scan; required for --plan-only')
    parser.add_argument('--start', nargs=3, type=float, metavar=('X', 'Y', 'Z'), help='Optional saved planning start only')
    args = parser.parse_args(argv)
    try:
        low, high = bounds(args.low, args.high)
        validate_budget(args.max_torches)
        movement = ({'min': args.movement_bounds[:3], 'max': args.movement_bounds[3:]}
                    if args.movement_bounds is not None else None)
        validate_movement_bounds(movement, low, high)
        protected = []
        if args.protect_file is not None:
            protected = json.loads(args.protect_file.read_text())
            if not isinstance(protected, list):
                raise ValueError('Protected file must contain a JSON array of boxes')
        protected += [{'min': box[:3], 'max': box[3:]} for box in args.protect_box]
        protected = protection_boxes(protected)
        if args.start and any(not math.isfinite(v) for v in args.start):
            raise ValueError('Start coordinates must be finite')
        if args.plan_only:
            if args.scan is None:
                parser.error('--plan-only requires an explicit --scan; it never queries the game')
            result = plan(json.loads(args.scan.read_text()), low, high, args.max_torches, args.start, protected)
            write_json(args.out / 'plan.json', result)
        else:
            if args.game_dir is None or args.scan is not None or args.start is not None:
                parser.error('Live runs require --game-dir and do not accept saved --scan/--start')
            args.out.mkdir(parents=True, exist_ok=True)
            result = run_live(args.game_dir, low, high, args.max_torches, args.out, protected, movement)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get('state') != 'blocked' and not result.get('cleanup_error') else 2
    except Exception as error:
        print(json.dumps({'scope': SCOPE, 'state': 'blocked', 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
