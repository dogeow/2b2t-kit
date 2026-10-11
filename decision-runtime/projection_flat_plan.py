"""Deterministic flat projection batches; no client, files or game actions.

The caller supplies a complete native model/audit and current inventory. World
coordinates, retained targets and lights are job data, never module constants.
Planning does not authorize replay or acknowledge a placement.
"""
from collections import Counter
import math

from projection_completion import block_state
from projection_patch_plan import connected_mask
from projection_stock_plan import plan_stock
from material_jobs.projection_spatial_cache import native_content_hash

AIR = {'Block{minecraft:air}', 'Block{minecraft:cave_air}', 'Block{minecraft:void_air}'}
PLAIN_BLOCKS = {
    'stone', 'cobblestone', 'granite', 'diorite', 'andesite', 'deepslate', 'tuff',
    'sandstone', 'red_sandstone', 'mud_bricks', 'dripstone_block', 'lodestone',
    'mushroom_stem', 'terracotta', 'dirt', 'grass_block', 'netherrack',
    'raw_iron_block', 'raw_copper_block', 'raw_gold_block',
}


def position(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3 or any(type(n) is not int for n in value):
        raise ValueError('Exact integer XYZ coordinates required')
    return tuple(value)


def policy(value):
    if not isinstance(value, dict) or type(value.get('schema')) is not int or value['schema'] != 1:
        raise ValueError('Flat map policy schema1 required')
    digest = value.get('content_hash')
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Explicit native projection content hash required')
    limit = value.get('max_cells_per_build', 128)
    if type(limit) is not int or not 1 <= limit <= 256:
        raise ValueError('Flat map build cap must be1..256')
    result = dict(value, max_cells_per_build=limit)
    for key in ('excluded_positions', 'registered_lights'):
        rows = value.get(key, [])
        if not isinstance(rows, list) or len(rows) > 65536:
            raise ValueError('Bounded exact position list required: ' + key)
        points = [position(row) for row in rows]
        if len(set(points)) != len(points):
            raise ValueError('Duplicate registered position: ' + key)
        result[key] = frozenset(points)
    return result


def full_block(state, item):
    name, props = block_state(state)
    short = name.removeprefix('minecraft:')
    return (name == item and (short in PLAIN_BLOCKS or short.endswith(('_planks', '_concrete', '_terracotta')))
            and (not props or plain_mushroom_stem(state,item) or vertical_deepslate(state,item)))


def vertical_deepslate(state,item):
    name,props=block_state(state)
    return name==item=='minecraft:deepslate' and props=={'axis':'y'}


def plain_mushroom_stem(state,item):
    name,props=block_state(state)
    return (name==item=='minecraft:mushroom_stem'
            and props=={face:'true'for face in ('down','east','north','south','up','west')})


class FlatLayout:
    def __init__(self, model, config):
        self.config = policy(config)
        if (not isinstance(model, dict) or type(model.get('model_schema')) is not int or model['model_schema'] != 1
                or model.get('content_hash') != self.config['content_hash']
                or model.get('loaded_chunks_verified') is not True
                or model.get('loaded_server_chunks_verified') is not True
                or not isinstance(model.get('placement_key'), str) or not model['placement_key']):
            raise ValueError('Complete current server flat model and matching content hash required')
        bounds = model.get('bounds', {})
        self.low, self.high = position(bounds.get('min')), position(bounds.get('max'))
        if self.low[1] != self.high[1] or any(a > b for a, b in zip(self.low, self.high)):
            raise ValueError('One horizontal projection layer required')
        volume = math.prod(b - a + 1 for a, b in zip(self.low, self.high))
        rows = model.get('expected')
        if not 1 <= volume <= 65536 or type(model.get('total')) is not int or model['total'] != volume or not isinstance(rows, list) or len(rows) != volume:
            raise ValueError('Complete bounded rectangular non-air projection required')
        if native_content_hash(rows) != self.config['content_hash']:
            raise ValueError('Model cells do not match the pinned native content hash')
        self.expected = {}
        for row in rows:
            p = position(row.get('pos'))
            if p in self.expected or not self.contains(p):
                raise ValueError('Duplicate or outside model position')
            name, _ = block_state(row.get('state', ''))
            if name in ('minecraft:air', 'minecraft:cave_air', 'minecraft:void_air') or name != row.get('item'):
                raise ValueError('Exact non-air item/state mapping required')
            self.expected[p] = dict(row)
        self.key = model['placement_key']
        self.fillable = frozenset(p for p, row in self.expected.items() if full_block(row['state'], row['item']))
        self.single_seed_only = frozenset(p for p in self.fillable
            if plain_mushroom_stem(self.expected[p]['state'],self.expected[p]['item']))
        self.axis_targets = frozenset(p for p in self.fillable
            if vertical_deepslate(self.expected[p]['state'],self.expected[p]['item']))
        # Same-type adjacency hides a stem face, so an all-true state must be isolated.
        self.fillable -= {p for p in self.single_seed_only
            if any(self.expected.get(n,{}).get('item')=='minecraft:mushroom_stem'for n in neighbors(p))}
        if not self.config['excluded_positions'] <= self.expected.keys():
            raise ValueError('Retained targets must belong to this projection')
        if any(p[1] != self.low[1] + 1 or (p[0], self.low[1], p[2]) not in self.expected
               for p in self.config['registered_lights']):
            raise ValueError('Registered lights must be one block above this projection')

    def contains(self, p):
        return all(a <= n <= b for n, a, b in zip(p, self.low, self.high))

    def observed(self, audit):
        rows = audit.get('mismatches')
        if (audit.get('audit_schema') != 2 or audit.get('placement_key') != self.key
                or audit.get('loaded_chunks_verified') is not True
                or audit.get('loaded_server_chunks_verified') is not True
                or audit.get('kinds', {}).get('unloaded')
                or type(audit.get('observed_at')) is not int or audit['observed_at'] <= 0
                or type(audit.get('matched')) is not int or not 0 <= audit['matched'] <= len(self.expected)
                or type(audit.get('total')) is not int or audit['total'] != len(self.expected) or not isinstance(rows, list)
                or audit['matched'] + len(rows) != len(self.expected)
                or audit.get('enclosed_air_conflicts')):
            raise ValueError('Complete current physical audit required')
        actual = {p: row['state'] for p, row in self.expected.items()}
        seen = set()
        for row in rows:
            p = position(row.get('pos'))
            if p in seen or p not in actual or row.get('expected') != self.expected[p]['state']:
                raise ValueError('Audit/model cell identity differs')
            seen.add(p)
            if (row.get('kind') != 'missing' or row.get('actual') not in AIR
                    or any(row.get(k) is not False for k in ('fluid', 'adjacent_fluid', 'block_entity'))
                    or row.get('neighbors_loaded') is not True):
                raise ValueError('Flat fill only accepts actual empty dry cells; use existing repair adapters')
            actual.pop(p)
        return actual


def neighbors(p):
    x, y, z = p
    return ((x - 1, y, z), (x + 1, y, z), (x, y, z - 1), (x, y, z + 1))


def _inventory(rows):
    if (not isinstance(rows, list) or len(rows) != 43
            or any(not isinstance(r, dict) or type(r.get('slot')) is not int
                   or not isinstance(r.get('item'), str) or type(r.get('count')) is not int
                   or type(r.get('max_stack')) is not int or not 1 <= r['max_stack'] <= 99
                   or not 0 <= r['count'] <= r['max_stack']
                   or (r['item'] == 'minecraft:air') != (r['count'] == 0) for r in rows)
            or {r['slot'] for r in rows} != set(range(43))):
        raise ValueError('Complete current typed43 native inventory required')
    return [r for r in rows if r['slot'] < 36]


def next_batch(layout, actual, snapshot, *, cell_budget=None):
    """Choose one nearest supported window, one seed, or one supply requirement.

    Only freshly matched model cells are support. Pending missing coordinates
    cannot bridge a mask. A matching retained coordinate may be actual support,
    without changing its old receipt. Named/packed/offhand stock is not spent.
    """
    if (not isinstance(actual, dict) or any(p not in layout.expected or state != layout.expected[p]['state']
                                          for p, state in actual.items())):
        raise ValueError('Exact caller-observed matching model cells required')
    feet = snapshot.get('pos')
    if not isinstance(feet, (list, tuple)) or len(feet) != 3 or any(type(n) not in (int, float) or not math.isfinite(n) for n in feet):
        raise ValueError('Current finite player position required')
    if snapshot.get('projection_selection', {}).get('key') != layout.key:
        raise ValueError('Current projection selection differs')
    rows = _inventory(snapshot.get('inventory'))
    budget = layout.config['max_cells_per_build'] if cell_budget is None else cell_budget
    if type(budget) is not int or not 1 <= budget <= layout.config['max_cells_per_build']:
        raise ValueError('Known positive bounded remaining cell budget required')
    missing = layout.expected.keys() - actual.keys()
    base = {'schema': 1, 'placement_key': layout.key, 'remaining_cells': len(missing),
            'planning_only': True, 'placement_credit': 0}
    if not missing:
        return {**base, 'phase': 'done', 'operation': 'physical_complete'}
    candidates = (missing - layout.config['excluded_positions']) & layout.fillable
    if snapshot.get('projection_mushroom_stem_seed_protocol')!=1:
        candidates-=layout.single_seed_only
    if snapshot.get('projection_air_seed_axis_protocol')!=1:
        candidates-=layout.axis_targets
    if not candidates:
        return {**base, 'phase': 'blocked', 'operation': 'review',
                'detail': '仅剩保留坐标或需要专用状态修复的方块'}
    stacks = [r for r in rows if set(r) == {'slot', 'item', 'count', 'max_stack'} and r['count'] > 2]
    by_item = {}
    for p in candidates:
        by_item.setdefault(layout.expected[p]['item'], set()).add(p)
    choices = []
    for stack in stacks:
        item = stack['item']
        targets = by_item.get(item, set())
        ready = {p for p in targets if p not in layout.single_seed_only and p not in layout.axis_targets
                 and any(n in actual for n in neighbors(p))}
        buckets = {(int((p[0] - layout.low[0]) // 4), int((p[2] - layout.low[2]) // 4)) for p in ready}
        for bx, bz in buckets:
            low = (layout.low[0] + bx * 4, layout.low[1], layout.low[2] + bz * 4)
            high = (min(low[0] + 3, layout.high[0]), low[1], min(low[2] + 3, layout.high[2]))
            mask = connected_mask(targets-layout.axis_targets, actual, low, high, min(16, budget, stack['count'] - 2),
                                  excluded=layout.config['excluded_positions'])
            if not mask:
                continue
            station = [(low[0] + high[0] + 1) / 2, low[1] + 2.75, (low[2] + high[2] + 1) / 2]
            choices.append((math.dist(feet, station), -len(mask), item, stack['slot'],
                            {**base, 'phase': 'ready', 'operation': 'print', 'item': item,
                             'positions': [list(p) for p in mask], 'station': station,
                             'patch_min': list(low), 'patch_max': list(high), 'slot': stack['slot'],
                             'stack_before': stack['count'], 'retained_after': stack['count'] - len(mask)}))
    if choices:
        return min(choices, key=lambda r: r[:4])[4]
    if type(snapshot.get('projection_air_seed_protocol')) is int and snapshot['projection_air_seed_protocol'] == 1:
        seeds = [(math.dist(feet, [p[0] + .5, p[1] + 2.75, p[2] + .5]), p, s)
                 for s in stacks for p in candidates if layout.expected[p]['item'] == s['item']
                 and (p not in layout.single_seed_only or snapshot.get('projection_mushroom_stem_seed_protocol')==1)]
        if seeds:
            _, p, stack = min(seeds, key=lambda r: (r[0], r[1], r[2]['slot']))
            return {**base, 'phase': 'ready', 'operation': 'air_seed', 'item': stack['item'],
                    'positions': [list(p)], 'station': [p[0] + .5, p[1] + 2.75, p[2] + .5],
                    'patch_min': list(p), 'patch_max': list(p), 'slot': stack['slot'],
                    'stack_before': stack['count'], 'retained_after': stack['count'] - 1}
    needs = Counter(layout.expected[p]['item'] for p in candidates)
    known_sizes = snapshot.get('target_stack_sizes', {})
    if not isinstance(known_sizes, dict) or any(type(v) is not int or not 1 <= v <= 99 for v in known_sizes.values()):
        raise ValueError('Actual or explicitly registered stack limits required')
    offers = []
    preferred=snapshot.get('preferred_materials',[])
    if (not isinstance(preferred,list)or len(preferred)>256
            or any(not isinstance(item,str)for item in preferred)):
        raise ValueError('Bounded material priority list required')
    for item, amount in needs.items():
        sizes = {r['max_stack'] for r in rows if r['item'] == item and r['count']}
        if item in known_sizes:
            sizes.add(known_sizes[item])
        if len(sizes) != 1:
            continue
        size = next(iter(sizes))
        if type(size) is not int or not 1 <= size <= 99:
            continue
        load = plan_stock(snapshot['inventory'], item, min(amount, budget), size,
                          stack_metadata={'item': item, 'max_stack': size})
        if load['construction_cells'] and load['withdraw_amount'] and not load.get('protected_different_metadata_target_slots'):
            priority=preferred.index(item)if item in preferred else len(preferred)
            offers.append((priority,-load['usable_before'], -load['construction_cells'], item, load))
    if offers:
        load = min(offers, key=lambda r: r[:4])[4]
        return {**base, 'phase': 'waiting', 'operation': 'supply', 'item': load['item'],
                'requirements': {load['item']: load['stock_total_target']}, 'load_plan': load,
                'detail': '按实际容量补一批材料；取料、配方及加工由现有材料调度器计算'}
    return {**base, 'phase': 'blocked', 'operation': 'review',
            'detail': '没有可用堆叠、已验证支撑或补料容量；保留现场待核对'}
