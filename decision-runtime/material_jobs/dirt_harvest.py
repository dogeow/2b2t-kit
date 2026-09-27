"""Conservative, one-layer surface soil acquisition for material jobs.

Only the requested exposed soil is taken. A verified block and inventory
receipt is required before the next cell in a bounded local batch may be mined.
"""
from __future__ import annotations

import copy
import math
import time

from drop_collection import collect_drop
from kit_runtime.journal import write_json
from material_trip_policy import carried, room_for_item


ITEM = 'minecraft:dirt'
GRASS = 'minecraft:grass_block'
SOURCES = {ITEM, GRASS}
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
LOCAL_BATCH = 4
LOCAL_RADIUS = 4
LOCAL_ASCENT = 5
BATCH_SECONDS = 60


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


def _projection_selection(state):
    """Snapshot the selected build footprint; incomplete observations are unsafe."""
    selected = state.get('projection_selection', {})
    if (not isinstance(selected, dict)
            or selected and (_box(selected) is None
                             or not isinstance(selected.get('key'), str)
                             or not selected['key'])):
        raise ValueError('Current projection selection is incomplete')
    return copy.deepcopy(selected)


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
    if selection:
        if not isinstance(selection, dict) or _box(selection) is None:
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


def candidate(rows, pos, index=None, *, item=ITEM):
    """One exposed, dry natural top block with sound ground and no nearby build."""
    x, y, z = pos
    if index is None:
        index = {tuple(row['pos']): row for row in rows}
    target = index.get((x, y, z))
    if (target is None or _name(target) != item or target.get('solid') is not True
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


def candidates(rows, low, high, player, spent_columns=(), *, item=ITEM):
    index = {tuple(row['pos']): row for row in rows}
    spent = set(spent_columns)
    found = [list(pos) for pos, row in index.items()
             if all(low[i] <= pos[i] <= high[i] for i in range(3))
             and (pos[0], pos[2]) not in spent and candidate(rows, pos, index, item=item)]
    found.sort(key=lambda p: ((p[0] + .5 - player[0]) ** 2 + (p[2] + .5 - player[2]) ** 2,
                              abs(p[1] + 3.1 - player[1]), p[0], p[2]))
    return found


def _local_scan(c, pos, checkpoint):
    from .acquisition import _scan
    x, y, z = pos
    return _scan(c, [x - BUFFER, y - 3, z - BUFFER],
                 [x + BUFFER, y + 6, z + BUFFER], checkpoint)


def _fresh_drops(before, after, pos, item=ITEM):
    previous = {row.get('uuid') for row in before.get('entities', [])
                if row.get('type') == 'minecraft:item'}
    return [row for row in after.get('entities', [])
            if row.get('type') == 'minecraft:item' and isinstance(row.get('uuid'), str)
            and row['uuid'] and row['uuid'] not in previous
            and row.get('stack', {}).get('item') == item
            and len(row.get('pos', [])) == 3
            and sum((a - (b + .5)) ** 2 for a, b in zip(row['pos'], pos)) <= 36]


def _patches(low, high):
    for top in range(high[1], low[1] - 1, -12):
        bottom = max(low[1], top - 11)
        for x in range(low[0], high[0] + 1, 16):
            for z in range(low[2], high[2] + 1, 16):
                yield [x, bottom, z], [min(x + 15, high[0]), top, min(z + 15, high[2])]


def _silk(row):
    return any(isinstance(e, dict) and e.get('id') == 'minecraft:silk_touch'
               and type(e.get('level')) is int and e['level'] > 0
               for e in row.get('enchantments', []))


def _shovel(state, item=ITEM):
    from .acquisition import Unavailable
    rows = state.get('inventory', [])
    # The 26.1.2 dirt loot table yields dirt with or without Silk Touch.
    eligible = [row for row in rows if 0 <= row.get('slot', -1) < 36
                and row.get('count') == 1
                and row.get('item') in ('minecraft:diamond_shovel', 'minecraft:netherite_shovel')
                and row.get('durability', 0) >= 33
                and (item != GRASS or _silk(row))]
    if not eligible:
        raise Unavailable('草方块需要至少保留 33 耐久的精准采集钻石或下界合金铲'
                          if item == GRASS else '需要至少保留 33 耐久的钻石或下界合金铲')
    return max(eligible, key=lambda row: row['durability'])


def _local_batch(available, limit):
    """Reuse one window survey without walking to another part of the patch."""
    anchor = available[0]
    chosen = [anchor]
    for pos in available[1:]:
        if len(chosen) >= limit:
            break
        if (abs(pos[1] - anchor[1]) > 1
                or (pos[0] - anchor[0]) ** 2 + (pos[2] - anchor[2]) ** 2 > LOCAL_RADIUS ** 2
                or (pos[0] - chosen[-1][0]) ** 2
                + (pos[2] - chosen[-1][2]) ** 2 > LOCAL_RADIUS ** 2):
            continue
        # Removing a cardinal neighbour would invalidate the next topsoil
        # cell's required ground support. The fresh scan remains authoritative.
        if any(abs(pos[0] - old[0]) + abs(pos[2] - old[2]) <= 1 for old in chosen):
            continue
        chosen.append(pos)
    return chosen


def _nearby_hover(c, target, checkpoint, trace):
    """Fly only a freshly checked short air corridor from the prior cell."""
    from .acquisition import Unavailable, _safe, _scan, blocks_route
    from .navigation import settled_state

    state = c.status(); _safe(state)
    here = state['pos']
    if state.get('flight') is not True:
        raise Unavailable('表层挖掘需要已确认飞行状态，避免失去脚下支撑')
    if (state.get('air_only_navigation_protocol', 0) < 2
            or here[1] - target[1] > .25
            or target[1] - here[1] > LOCAL_ASCENT
            or math.hypot(target[0] - here[0], target[2] - here[2]) > LOCAL_RADIUS + 1):
        return False
    # Picking up a drop can leave the player at ground level. Ascend only
    # through the freshly scanned current air column before the short hop.
    points = ([here[0], target[1], here[2]],
              [target[0], target[1], here[2]], list(target))
    for point in points:
        checkpoint(); state = c.status(); _safe(state)
        if state.get('flight') is not True:
            raise Unavailable('表层挖掘需要已确认飞行状态，避免失去脚下支撑')
        start = state['pos']
        if math.dist(start, point) <= .3:
            continue
        low = [math.floor(min(start[0], point[0]) - .32),
               math.floor(min(start[1], point[1])),
               math.floor(min(start[2], point[2]) - .32)]
        high = [math.floor(max(start[0], point[0]) + .32),
                math.floor(max(start[1], point[1]) + 1.81),
                math.floor(max(start[2], point[2]) + .32)]
        observed = _scan(c, low, high, checkpoint)
        if any(blocks_route(row, state, point) for row in observed):
            raise Unavailable('资源区入口或航线仍有障碍；不会穿越地层或挖开区域外建筑')
        checkpoint()
        current = c.status(); _safe(current)
        if current.get('flight') is not True:
            raise Unavailable('表层挖掘需要已确认飞行状态，避免失去脚下支撑')
        if math.dist(current['pos'], start) > .3:
            raise Unavailable('前往资源区的安全路线没有到达，保留本次位置', 'waiting')
        reply = c.request('navigate', target=point, arrival=.25, air_only=True, seconds=20)
        actual = settled_state(c, point, .55); _safe(actual)
        trace.append({'target': point, 'actual': actual['pos'], 'phase': reply.get('phase')})
        if reply.get('phase') != 'done' or math.dist(actual['pos'], point) > .55:
            raise Unavailable('前往资源区的安全路线没有到达，保留本次位置', 'waiting')
    return True


def acquire_surface_soil(c, item, target, profile, regions, path, ledger, checkpoint):
    """Mine up to four nearby cells, persisting each server/inventory receipt."""
    from .acquisition import Unavailable, _safe, _scan, _choose_tool, _travel

    if item not in SOURCES:
        raise ValueError('Surface soil item must be dirt or grass_block')
    label = '草方块' if item == GRASS else '泥土'
    prefix = item.split(':', 1)[1]

    try:
        selection = _projection_selection(c.status())
        for region in regions:
            validate_region(region, profile, selection)
    except ValueError as error:
        raise Unavailable(str(error)) from error

    def verify_selection(state, region):
        try:
            current = _projection_selection(state)
            if current != selection:
                raise ValueError('Current projection selection changed during surface mining')
            validate_region(region, profile, current)
        except ValueError as error:
            raise Unavailable(str(error)) from error

    def harvest_cell(pos, region, local):
        checkpoint()
        state = c.status(); _safe(state); verify_selection(state, region)
        if state.get('flight') is not True:
            raise Unavailable('表层挖掘需要已确认飞行状态，避免失去脚下支撑')
        if carried(state, item) >= target:
            return {'phase': 'done', 'gained': 0}
        key = prefix + '-block-' + ':'.join(map(str, pos))
        fresh = _local_scan(c, pos, checkpoint)
        if not candidate(fresh, pos, item=item):
            ledger['visited'][key] = {'state': 'skipped', 'pos': pos,
                                      'reason': 'source_or_buffer_changed'}
            write_json(path, ledger)
            return {'phase': 'waiting', 'detail': f'{label}候选在操作前改变，已跳过该列'}
        tool = _shovel(state, item)
        trace = []
        try:
            destination = [pos[0] + .5, pos[1] + 3.1, pos[2] + .5]
            if not local or not _nearby_hover(c, destination, checkpoint, trace):
                _travel(c, destination, checkpoint, trace)
        except Unavailable as error:
            if error.detail not in ('资源区入口或航线仍有障碍；不会穿越地层或挖开区域外建筑',
                                    '前往资源区的安全路线没有到达，保留本次位置'):
                raise
            ledger['visited'][key] = {'state': 'skipped', 'pos': pos,
                                      'reason': 'safe_route_unavailable', 'route': trace}
            write_json(path, ledger)
            return {'phase': 'waiting', 'detail': f'{label}候选无法沿已核验空气航线抵达，已跳过该列'}
        state = c.status(); _safe(state); verify_selection(state, region)
        if state.get('flight') is not True:
            raise Unavailable('表层挖掘需要已确认飞行状态，避免失去脚下支撑')
        if carried(state, item) >= target:
            return {'phase': 'done', 'gained': 0}
        if room_for_item(state, item) < 1:
            raise Unavailable(f'{label}背包空间已耗尽，请先存放本批物资', 'waiting')
        tool = _shovel(state, item)
        fresh = _local_scan(c, pos, checkpoint)
        if not candidate(fresh, pos, item=item):
            ledger['visited'][key] = {'state': 'skipped', 'pos': pos,
                                      'reason': 'source_changed_after_travel'}
            write_json(path, ledger)
            return {'phase': 'waiting', 'detail': f'接近后{label}或保护缓冲区改变，已跳过该列'}
        _choose_tool(c, tool, checkpoint)
        fresh = _local_scan(c, pos, checkpoint)
        if not candidate(fresh, pos, item=item):
            ledger['visited'][key] = {'state': 'skipped', 'pos': pos,
                                      'reason': 'source_or_buffer_changed_after_tool_selection'}
            write_json(path, ledger)
            return {'phase': 'waiting', 'detail': f'选取铲后{label}或保护缓冲区改变，已跳过该列'}
        before = c.status(); _safe(before); verify_selection(before, region)
        if before.get('flight') is not True:
            raise Unavailable('表层挖掘需要已确认飞行状态，避免失去脚下支撑')
        if carried(before, item) >= target:
            return {'phase': 'done', 'gained': 0}
        if room_for_item(before, item) < 1:
            raise Unavailable(f'{label}背包空间已耗尽，请先存放本批物资', 'waiting')
        if item == GRASS:
            hand = before.get('hand') or {}
            selected = before.get('selected_slot')
            held = next((row for row in before.get('inventory', [])
                         if row.get('slot') == selected), None)
            if (type(selected) is not int or not 0 <= selected < 9
                    or held is None or held.get('item') != hand.get('item')
                    or hand.get('item') != tool['item'] or hand.get('count') != 1
                    or hand.get('durability') != tool['durability']
                    or hand.get('enchantments', []) != tool.get('enchantments', [])
                    or not _silk(hand)
                    or hand.get('durability', 0) < 33
                    or held.get('durability') != hand.get('durability')
                    or held.get('enchantments', []) != hand.get('enchantments', [])
                    or not _silk(held)):
                raise Unavailable('精准采集铲的实际手持槽位或属性未核实；不挖草方块')
        expected = next(row['state'] for row in fresh if row['pos'] == pos)
        entry = {'state': 'inflight', 'pos': pos, 'expected_state': expected,
                 'before': carried(before, item), 'route': trace,
                 'world_session': c.world, 'observed_at': before.get('time')}
        ledger['visited'][key] = entry; write_json(path, ledger)
        checkpoint()
        verify_selection(c.status(), region)
        tool_guard = ({'required_silk_shovel': True, 'expected_tool_slot': selected,
                       'expected_tool_item': tool['item']} if item == GRASS else {})
        reply = c.request('mine_block', pos=pos, face='up', expected_state=expected,
                          seconds=20, **tool_guard)
        native_id = getattr(c, 'last', None)
        after = c.status(); _safe(after)
        if reply.get('phase') != 'done':
            if (reply.get('detail') in UNSTARTED
                    and carried(after, item) == entry['before']
                    and any(row['pos'] == pos and row['state'] == expected
                            for row in _local_scan(c, pos, checkpoint))):
                entry.update(state='skipped', reason=reply['detail'],
                             native_phase=reply.get('phase'))
                write_json(path, ledger)
                return {'phase': 'waiting', 'detail': '原生接口未开始挖掘，已跳过此列'}
            return {'phase': 'blocked', 'code': 'native_uncertain',
                    'detail': f'{label}挖掘回执不确定，保留在途记录且不重放'}
        # A native success is still not proof that the server removed the
        # exact block, or that the requested dirt reached the main bag.
        if any(row['pos'] == pos for row in _scan(c, pos, pos, checkpoint)):
            return {'phase': 'blocked', 'code': 'block_unconfirmed',
                    'detail': f'{label}仍占据原位置，保留在途记录且不重放'}
        attempted = set()
        deadline = time.monotonic() + 12
        while True:
            checkpoint(); after = c.status(); _safe(after)
            amount = carried(after, item) - entry['before']
            if amount > 0:
                entry.update(state='collected', after=carried(after, item), gained=amount,
                             native_phase='done', native_id=native_id,
                             observed_at=after.get('time'))
                write_json(path, ledger)
                return {'phase': 'done' if carried(after, item) >= target else 'waiting',
                        'detail': f'{label}逐块回收已核验，背包 {carried(after, item)}/{target}',
                        'before': entry['before'], 'after': carried(after, item), 'gained': amount}
            for drop in _fresh_drops(before, after, pos, item):
                if drop.get('uuid') in attempted:
                    continue
                attempted.add(drop.get('uuid'))
                collect_drop(c, drop, observation=after)
            if time.monotonic() >= deadline:
                return {'phase': 'blocked', 'code': 'drop_unconfirmed',
                        'detail': f'{label}已挖但背包增量未确认，保留在途记录且不挖下一块'}
            time.sleep(.2)

    scans = 0
    for region in regions:
        low, high = region['min'], region['max']
        for lo, hi in _patches(low, high):
            window_key = prefix + '-window-' + ':'.join(map(str, lo + hi))
            if ledger['visited'].get(window_key, {}).get('state') == 'empty_or_unsafe':
                continue
            if scans >= MAX_SCANS:
                return {'phase': 'waiting', 'detail': f'本轮已核验 12 个{label}小区域，下一轮继续'}
            rows = _scan(c, [lo[0] - BUFFER, lo[1] - 3, lo[2] - BUFFER],
                         [hi[0] + BUFFER, hi[1] + 6, hi[2] + BUFFER], checkpoint)
            scans += 1
            state = c.status(); _safe(state)
            spent = {(v['pos'][0], v['pos'][2]) for k, v in ledger['visited'].items()
                     if k.startswith(prefix + '-block-') and isinstance(v.get('pos'), list)
                     and len(v['pos']) == 3}
            available = candidates(rows, lo, hi, state['pos'], spent, item=item)
            if not available:
                ledger['visited'][window_key] = {'state': 'empty_or_unsafe', 'min': lo,
                                                   'max': hi, 'observed_at': state.get('time')}
                write_json(path, ledger)
                continue
            batch_before = carried(state, item)
            if batch_before >= target:
                return {'phase': 'done', 'detail': f'{label}背包现物已经达到目标',
                        'before': batch_before, 'after': batch_before, 'gained': 0}
            batch = _local_batch(available, min(LOCAL_BATCH, target - batch_before))
            collected = 0
            started = time.monotonic()
            budget_exhausted = False
            for pos in batch:
                if collected and time.monotonic() - started >= BATCH_SECONDS:
                    budget_exhausted = True
                    break
                result = harvest_cell(pos, region, collected > 0)
                if result['phase'] == 'done' and result.get('gained', 0) == 0:
                    break
                if result.get('gained', 0) <= 0:
                    return result
                collected += 1
                if result['phase'] == 'done':
                    break
            checkpoint(); final = c.status(); _safe(final)
            after = carried(final, item)
            return {'phase': 'done' if after >= target else 'waiting',
                    'detail': (f'{label}本轮逐块回收 {collected} 格，背包 {after}/{target}'
                               + ('；已达本轮时限' if budget_exhausted else '')),
                    'before': batch_before, 'after': after,
                    'gained': after - batch_before, 'collected_cells': collected}
    return {'phase': 'blocked', 'code': 'no_safe_candidate',
            'detail': f'已授权野外区域没有新的安全表层{label}；已记录且不扩挖'}


def acquire_dirt(c, target, profile, regions, path, ledger, checkpoint):
    return acquire_surface_soil(c, ITEM, target, profile, regions, path, ledger, checkpoint)
