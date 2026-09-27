"""Conservative, one-layer surface dirt acquisition for material jobs.

Only exposed dirt is taken, one exact block per worker call. A
verified inventory receipt is required before another block may be mined.
"""
from __future__ import annotations

import math
import time

from drop_collection import collect_drop
from kit_runtime.journal import write_json
from material_trip_policy import carried, room_for_item


ITEM = 'minecraft:dirt'
SOURCES = {'minecraft:dirt'}
GROUND = SOURCES | {'minecraft:grass_block', 'minecraft:coarse_dirt', 'minecraft:rooted_dirt',
                    'minecraft:podzol', 'minecraft:mycelium', 'minecraft:clay',
                    'minecraft:stone', 'minecraft:deepslate', 'minecraft:granite',
                    'minecraft:diorite', 'minecraft:andesite', 'minecraft:tuff',
                    'minecraft:calcite'}
NEARBY = GROUND | {'minecraft:coal_ore', 'minecraft:iron_ore',
                   'minecraft:copper_ore', 'minecraft:short_grass',
                   'minecraft:tall_grass', 'minecraft:fern', 'minecraft:large_fern'}
UNSTARTED = {'Mining target out of reach', 'mining target moved out of reach',
             'mining target is occluded', 'Current footing is protected'}
BUFFER = 3
MAX_SCANS = 12


def _name(row):
    state = row.get('state', '')
    return state[6:state.index('}')] if state.startswith('Block{') and '}' in state else 'unknown'


def _box(value):
    if not isinstance(value, dict):
        return None
    low, high = value.get('min'), value.get('max')
    if (not isinstance(low, list) or not isinstance(high, list)
            or len(low) != 3 or len(high) != 3
            or any(type(v) is not int for v in low + high)
            or any(a > b for a, b in zip(low, high))):
        return None
    return low, high


def validate_region(region, profile, selection):
    """Require a small authorized patch outside every known build/depot column."""
    bounds = _box(region)
    if bounds is None:
        raise ValueError('Dirt patch needs bounded integer coordinates')
    low, high = bounds
    if (high[0] - low[0] > 31 or high[1] - low[1] > 15
            or high[2] - low[2] > 31 or low[1] < 58 or high[1] > 160):
        raise ValueError('Dirt patch must be at surface height within 32×16×32 blocks')
    protected = profile.get('protected_regions')
    if not isinstance(protected, list) or not protected or any(_box(b) is None for b in protected):
        raise ValueError('Dirt mining requires explicit valid protected site regions')
    boxes = list(protected)
    if selection and ('min' in selection or 'max' in selection):
        if _box(selection) is None:
            raise ValueError('Current projection bounds are incomplete')
        boxes.append(selection)
    for box in boxes:
        a, b = _box(box)
        if not (high[0] + 16 < a[0] or low[0] - 16 > b[0]
                or high[2] + 16 < a[2] or low[2] - 16 > b[2]):
            raise ValueError('Dirt patch intersects the protected site buffer')
    sites = list(profile.get('depots', [])) + list(profile.get('furnace_positions', []))
    sites += [profile[k] for k in ('workbench', 'ender_chest', 'shulker_pad', 'search_origin') if k in profile]
    station = profile.get('concrete_station')
    if isinstance(station, dict) and station.get('support') is not None:
        sites.append(station['support'])
    for pos in sites:
        if (not isinstance(pos, list) or len(pos) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in pos)):
            raise ValueError('Dirt protection contains an invalid site position')
        if low[0] - 48 <= pos[0] <= high[0] + 48 and low[2] - 48 <= pos[2] <= high[2] + 48:
            raise ValueError('Dirt patch is too close to an approved depot or work site')
    return low, high


def candidate(rows, pos, index=None):
    """One exposed, dry natural top block with sound ground and no nearby build."""
    x, y, z = pos
    if index is None:
        index = {tuple(row['pos']): row for row in rows}
    target = index.get((x, y, z))
    if (target is None or _name(target) not in SOURCES or target.get('solid') is not True
            or target.get('fluid') is not False or target.get('block_entity') is not False):
        return False
    if any((x, y + dy, z) in index for dy in range(1, 6)):
        return False
    for dx, dz in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
        level = y - 1 if dx == dz == 0 else y
        ground = index.get((x + dx, level, z + dz))
        if (ground is None or _name(ground) not in GROUND or ground.get('solid') is not True
                or ground.get('fluid') is not False or ground.get('block_entity') is not False):
            return False
    for px in range(x - BUFFER, x + BUFFER + 1):
        for py in range(y - 3, y + 4):
            for pz in range(z - BUFFER, z + BUFFER + 1):
                row = index.get((px, py, pz))
                if row is not None and (row.get('fluid') is not False
                                        or row.get('block_entity') is not False
                                        or _name(row) not in NEARBY):
                    return False
    return True


def candidates(rows, low, high, player, spent_columns=()):
    index = {tuple(row['pos']): row for row in rows}
    spent = set(spent_columns)
    found = [list(pos) for pos, row in index.items()
             if all(low[i] <= pos[i] <= high[i] for i in range(3))
             and (pos[0], pos[2]) not in spent and candidate(rows, pos, index)]
    found.sort(key=lambda p: ((p[0] + .5 - player[0]) ** 2 + (p[2] + .5 - player[2]) ** 2,
                              abs(p[1] + 3.1 - player[1]), p[0], p[2]))
    return found


def _local_scan(c, pos, checkpoint):
    from .acquisition import _scan
    x, y, z = pos
    return _scan(c, [x - BUFFER, y - 3, z - BUFFER],
                 [x + BUFFER, y + 6, z + BUFFER], checkpoint)


def _fresh_drops(before, after, pos):
    previous = {row.get('uuid') for row in before.get('entities', [])
                if row.get('type') == 'minecraft:item'}
    return [row for row in after.get('entities', [])
            if row.get('type') == 'minecraft:item' and isinstance(row.get('uuid'), str)
            and row['uuid'] and row['uuid'] not in previous
            and row.get('stack', {}).get('item') == ITEM
            and len(row.get('pos', [])) == 3
            and sum((a - (b + .5)) ** 2 for a, b in zip(row['pos'], pos)) <= 36]


def _patches(low, high):
    for top in range(high[1], low[1] - 1, -12):
        bottom = max(low[1], top - 11)
        for x in range(low[0], high[0] + 1, 16):
            for z in range(low[2], high[2] + 1, 16):
                yield [x, bottom, z], [min(x + 15, high[0]), top, min(z + 15, high[2])]


def _shovel(state):
    from .acquisition import Unavailable
    rows = state.get('inventory', [])
    # The 26.1.2 dirt loot table yields dirt with or without Silk Touch.
    eligible = [row for row in rows if 0 <= row.get('slot', -1) < 36
                and row.get('count') == 1
                and row.get('item') in ('minecraft:diamond_shovel', 'minecraft:netherite_shovel')
                and row.get('durability', 0) >= 33]
    if not eligible:
        raise Unavailable('需要至少保留 33 耐久的钻石或下界合金铲')
    return max(eligible, key=lambda row: row['durability'])


def acquire_dirt(c, target, profile, regions, path, ledger, checkpoint):
    """Mine one exact source block and persist its server/inventory receipt."""
    from .acquisition import Unavailable, _safe, _scan, _choose_tool, _travel

    selection = c.status().get('projection_selection', {})
    try:
        for region in regions:
            validate_region(region, profile, selection)
    except ValueError as error:
        raise Unavailable(str(error)) from error
    scans = 0
    for region in regions:
        low, high = region['min'], region['max']
        for lo, hi in _patches(low, high):
            window_key = 'dirt-window-' + ':'.join(map(str, lo + hi))
            if ledger['visited'].get(window_key, {}).get('state') == 'empty_or_unsafe':
                continue
            if scans >= MAX_SCANS:
                return {'phase': 'waiting', 'detail': '本轮已核验 12 个泥土小区域，下一轮继续'}
            rows = _scan(c, [lo[0] - BUFFER, lo[1] - 3, lo[2] - BUFFER],
                         [hi[0] + BUFFER, hi[1] + 6, hi[2] + BUFFER], checkpoint)
            scans += 1
            state = c.status(); _safe(state)
            spent = {(v['pos'][0], v['pos'][2]) for k, v in ledger['visited'].items()
                     if k.startswith('dirt-block-') and isinstance(v.get('pos'), list)
                     and len(v['pos']) == 3}
            available = candidates(rows, lo, hi, state['pos'], spent)
            if not available:
                ledger['visited'][window_key] = {'state': 'empty_or_unsafe', 'min': lo,
                                                   'max': hi, 'observed_at': state.get('time')}
                write_json(path, ledger)
                continue
            pos = available[0]
            key = 'dirt-block-' + ':'.join(map(str, pos))
            fresh = _local_scan(c, pos, checkpoint)
            if not candidate(fresh, pos):
                ledger['visited'][key] = {'state': 'skipped', 'pos': pos,
                                          'reason': 'source_or_buffer_changed'}
                write_json(path, ledger)
                return {'phase': 'waiting', 'detail': '泥土候选在操作前改变，已跳过该列'}
            if state.get('flight') is not True:
                raise Unavailable('表层挖掘需要已确认飞行状态，避免失去脚下支撑')
            tool = _shovel(state)
            trace = []
            try:
                _travel(c, [pos[0] + .5, pos[1] + 3.1, pos[2] + .5], checkpoint, trace)
            except Unavailable as error:
                if error.detail not in ('资源区入口或航线仍有障碍；不会穿越地层或挖开区域外建筑',
                                        '前往资源区的安全路线没有到达，保留本次位置'):
                    raise
                ledger['visited'][key] = {'state': 'skipped', 'pos': pos,
                                          'reason': 'safe_route_unavailable', 'route': trace}
                write_json(path, ledger)
                return {'phase': 'waiting', 'detail': '泥土候选无法沿已核验空气航线抵达，已跳过该列'}
            state = c.status(); _safe(state)
            if state.get('flight') is not True:
                raise Unavailable('表层挖掘需要已确认飞行状态，避免失去脚下支撑')
            if room_for_item(state, ITEM) < 1:
                raise Unavailable('泥土背包空间已耗尽，请先存放本批物资', 'waiting')
            fresh = _local_scan(c, pos, checkpoint)
            if not candidate(fresh, pos):
                ledger['visited'][key] = {'state': 'skipped', 'pos': pos,
                                          'reason': 'source_changed_after_travel'}
                write_json(path, ledger)
                return {'phase': 'waiting', 'detail': '接近后泥土方块或保护缓冲区改变，已跳过该列'}
            _choose_tool(c, tool, checkpoint)
            before = c.status(); _safe(before)
            expected = next(row['state'] for row in fresh if row['pos'] == pos)
            entry = {'state': 'inflight', 'pos': pos, 'expected_state': expected,
                     'before': carried(before, ITEM), 'route': trace,
                     'world_session': c.world, 'observed_at': before.get('time')}
            ledger['visited'][key] = entry; write_json(path, ledger)
            checkpoint()
            reply = c.request('mine_block', pos=pos, face='up', expected_state=expected, seconds=20)
            native_id = getattr(c, 'last', None)
            after = c.status(); _safe(after)
            if reply.get('phase') != 'done':
                if (reply.get('detail') in UNSTARTED
                        and carried(after, ITEM) == entry['before']
                        and any(row['pos'] == pos and row['state'] == expected
                                for row in _local_scan(c, pos, checkpoint))):
                    entry.update(state='skipped', reason=reply['detail'],
                                 native_phase=reply.get('phase'))
                    write_json(path, ledger)
                    return {'phase': 'waiting', 'detail': '原生接口未开始挖掘，已跳过此列'}
                return {'phase': 'blocked', 'code': 'native_uncertain',
                        'detail': '泥土挖掘回执不确定，保留在途记录且不重放'}
            # A native success is still not proof that the server removed the
            # exact block, or that the requested dirt reached the main bag.
            if any(row['pos'] == pos for row in _scan(c, pos, pos, checkpoint)):
                return {'phase': 'blocked', 'code': 'block_unconfirmed',
                        'detail': '泥土方块仍占据原位置，保留在途记录且不重放'}
            attempted = set()
            deadline = time.monotonic() + 12
            while True:
                checkpoint(); after = c.status(); _safe(after)
                amount = carried(after, ITEM) - entry['before']
                if amount > 0:
                    entry.update(state='collected', after=carried(after, ITEM), gained=amount,
                                 native_phase='done', native_id=native_id,
                                 observed_at=after.get('time'))
                    write_json(path, ledger)
                    return {'phase': 'done' if carried(after, ITEM) >= target else 'waiting',
                            'detail': f'泥土逐块回收已核验，背包 {carried(after, ITEM)}/{target}',
                            'before': entry['before'], 'after': carried(after, ITEM), 'gained': amount}
                for drop in _fresh_drops(before, after, pos):
                    if drop.get('uuid') in attempted:
                        continue
                    attempted.add(drop.get('uuid'))
                    collect_drop(c, drop, observation=after)
                if time.monotonic() >= deadline:
                    return {'phase': 'blocked', 'code': 'drop_unconfirmed',
                            'detail': '泥土已挖但背包增量未确认，保留在途记录且不挖下一块'}
                time.sleep(.2)
    return {'phase': 'blocked', 'code': 'no_safe_candidate',
            'detail': '已授权野外区域没有新的安全表层泥土；已记录且不扩挖'}
