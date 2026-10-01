"""Conservative surface-snow acquisition for material jobs.

Only freshly observed natural-looking surface snow is touched.  Silk Touch is
required when the requested item is a snow layer/block; ordinary snowballs
require an explicitly non-Silk-Touch shovel.  Every block removal and exact
inventory increase is journaled before another cell may be mined.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import re
import time

from drop_collection import collect_drop
from kit_runtime.journal import write_json
from material_trip_policy import carried, room_for_item


SNOW = 'minecraft:snow'
SNOW_BLOCK = 'minecraft:snow_block'
SNOWBALL = 'minecraft:snowball'
PRODUCTS = frozenset((SNOW, SNOW_BLOCK, SNOWBALL))
SOURCES = frozenset((SNOW, SNOW_BLOCK))

GROUND = frozenset('minecraft:' + name for name in (
    'grass_block', 'dirt', 'coarse_dirt', 'rooted_dirt', 'podzol', 'mycelium',
    'moss_block', 'stone', 'deepslate', 'granite', 'diorite', 'andesite',
    'tuff', 'calcite', 'clay', 'gravel', 'sand', 'red_sand', 'snow_block',
    'ice', 'packed_ice', 'blue_ice'))
NATURAL_NEARBY = GROUND | SOURCES | frozenset('minecraft:' + name for name in (
    'coal_ore', 'iron_ore', 'copper_ore', 'gold_ore', 'emerald_ore',
    'short_grass', 'tall_grass', 'fern', 'large_fern', 'dead_bush'))
UNSTARTED = {'Mining target out of reach', 'mining target moved out of reach',
             'mining target is occluded', 'Current footing is protected'}
BUFFER = 3
MAX_SCANS = 12
LOCAL_BATCH = 4
LOCAL_RADIUS = 4
LOCAL_ASCENT = 5
BATCH_SECONDS = 60
_LAYERS = re.compile(r'(?:\[|,)layers=([1-8])(?:,|\])')


def _name(row):
    text = row.get('state', '')
    return text[6:text.index('}')] if text.startswith('Block{') and '}' in text else 'unknown'


def _layers(row):
    if _name(row) != SNOW:
        return None
    match = _LAYERS.search(row.get('state', ''))
    return int(match.group(1)) if match else None


def source_yield(row, item):
    """Return the exact vanilla drop count for an eligible source/tool pair."""
    name = _name(row)
    layers = _layers(row)
    if item == SNOW:
        return layers if layers is not None and layers < 8 else 0
    if item == SNOW_BLOCK:
        return 1 if name == SNOW_BLOCK or layers == 8 else 0
    if item == SNOWBALL:
        return layers if layers is not None else 4 if name == SNOW_BLOCK else 0
    raise ValueError('Unsupported snow product: ' + str(item))


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
    selected = state.get('projection_selection', {})
    if (not isinstance(selected, dict)
            or selected and (_box(selected) is None
                             or not isinstance(selected.get('key'), str)
                             or not selected['key'])):
        raise ValueError('Current projection selection is incomplete')
    return copy.deepcopy(selected)


def validate_region(region, profile, selection):
    """Require a bounded surface patch far from every registered work site."""
    bounds = _box(region)
    if bounds is None:
        raise ValueError('Snow patch needs bounded integer coordinates')
    low, high = bounds
    if (high[0] - low[0] > 31 or high[1] - low[1] > 31
            or high[2] - low[2] > 31 or low[1] < 58 or high[1] > 315):
        raise ValueError('Snow patch must be a surface region within 32x32x32 blocks')
    protected = profile.get('protected_regions')
    if not isinstance(protected, list) or not protected or any(_box(b) is None for b in protected):
        raise ValueError('Snow harvesting requires explicit valid protected site regions')
    boxes = list(protected)
    if selection:
        if _box(selection) is None:
            raise ValueError('Current projection bounds are incomplete')
        boxes.append(selection)
    for box in boxes:
        a, b = _box(box)
        if not (high[0] + 16 < a[0] or low[0] - 16 > b[0]
                or high[2] + 16 < a[2] or low[2] - 16 > b[2]):
            raise ValueError('Snow patch intersects the protected site buffer')
    sites = list(profile.get('depots', [])) + list(profile.get('furnace_positions', []))
    sites += [profile[k] for k in ('workbench', 'ender_chest', 'shulker_pad', 'search_origin') if k in profile]
    station = profile.get('concrete_station')
    if isinstance(station, dict) and station.get('support') is not None:
        sites.append(station['support'])
    for pos in sites:
        if (not isinstance(pos, list) or len(pos) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in pos)):
            raise ValueError('Snow protection contains an invalid site position')
        if low[0] - 48 <= pos[0] <= high[0] + 48 and low[2] - 48 <= pos[2] <= high[2] + 48:
            raise ValueError('Snow patch is too close to an approved depot or work site')
    return low, high


def candidate(rows, pos, item, index=None, *, allow_natural_snowpack=False):
    """One exposed source with natural support and no nearby structure marker."""
    if item not in PRODUCTS:
        raise ValueError('Unsupported snow product')
    x, y, z = pos
    index = index if index is not None else {tuple(row['pos']): row for row in rows}
    target = index.get((x, y, z))
    if (target is None or source_yield(target, item) <= 0
            or target.get('fluid') is not False or target.get('block_entity') is not False):
        return False
    support = index.get((x, y - 1, z))
    support_name=_name(support or {})
    natural_leaf=allow_natural_snowpack and support_name.endswith('_leaves')
    if (support is None or support_name not in GROUND and not natural_leaf
            or support.get('solid') is not True
            or support.get('fluid') is not False or support.get('block_entity') is not False):
        return False
    if _name(support) == SNOW_BLOCK and not allow_natural_snowpack:
        # A layer on a snow-block wall and a stacked snow block are both
        # indistinguishable from an igloo/player build in a client scan.
        return False
    if any((row := index.get((x, y + dy, z))) is not None
           and (row.get('fluid') is not False or not row.get('passable', False))
           for dy in range(1, 6)):
        return False
    # A vertical or connected snow-block wall can be an igloo or player build.
    # Only isolated surface blocks are accepted as block/snowball sources.
    if _name(target) == SNOW_BLOCK and any(
            _name(index.get((x + dx, y + dy, z + dz), {})) == SNOW_BLOCK
            for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1), (0, 1, 0))):
        return False
    if _name(target) == SNOW and not allow_natural_snowpack and any(
            _name(row) == SNOW_BLOCK for row in index.values()
            if abs(row['pos'][0]-x) <= BUFFER and abs(row['pos'][1]-y) <= 3
            and abs(row['pos'][2]-z) <= BUFFER):
        return False
    if allow_natural_snowpack:
        # The relaxed path exists only for a Bobby-current, live-snowy region.
        # It harvests surface layers, never a solid snow construction.  A
        # generated snow-block support must join ordinary natural terrain
        # within the freshly scanned three-block-down column.
        if _name(target) != SNOW:
            return False
        column_ground=any(
            (below:=index.get((x,y-depth,z))) is not None
            and _name(below) in GROUND-{SNOW_BLOCK}
            and below.get('solid') is True and below.get('fluid') is False
            and below.get('block_entity') is False for depth in (2,3))
        if support_name == SNOW_BLOCK and not column_ground:
            return False
    for px in range(x - BUFFER, x + BUFFER + 1):
        for py in range(y - 3, y + 4):
            for pz in range(z - BUFFER, z + BUFFER + 1):
                row = index.get((px, py, pz))
                if row is not None and (row.get('fluid') is not False
                                        or row.get('block_entity') is not False
                                        or (_name(row) not in NATURAL_NEARBY
                                            and not (allow_natural_snowpack
                                                     and _name(row).endswith('_leaves')))):
                    return False
    return True


def candidates(rows, low, high, player, item, spent=(), *,
               allow_natural_snowpack=False):
    index = {tuple(row['pos']): row for row in rows}
    spent = set(spent)
    found = [(list(pos), source_yield(row, item)) for pos, row in index.items()
             if all(low[i] <= pos[i] <= high[i] for i in range(3))
             and pos not in spent and candidate(
                 rows, pos, item, index,
                 allow_natural_snowpack=allow_natural_snowpack)]
    found.sort(key=lambda entry: (
        (entry[0][0] + .5 - player[0]) ** 2 + (entry[0][2] + .5 - player[2]) ** 2,
        abs(entry[0][1] + 3.1 - player[1]), entry[0][0], entry[0][2]))
    return found


def _local_scan(c, pos, checkpoint):
    from .acquisition import _scan
    x, y, z = pos
    return _scan(c, [x - BUFFER, y - 3, z - BUFFER],
                 [x + BUFFER, min(319, y + 6), z + BUFFER], checkpoint)


def _fresh_drops(before, after, pos, item):
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


def _shovel(state, item, minimum=33):
    require_silk = item != SNOWBALL
    eligible = [row for row in state.get('inventory', [])
                if 0 <= row.get('slot', -1) < 36 and row.get('count') == 1
                and row.get('item') in ('minecraft:diamond_shovel', 'minecraft:netherite_shovel')
                and row.get('durability', 0) >= minimum and _silk(row) is require_silk]
    if not eligible:
        requirement = '带精准采集' if require_silk else '不带精准采集'
        from .acquisition import Unavailable
        raise Unavailable(f'需要剩余耐久至少 {minimum}、{requirement}的钻石或下界合金铲')
    return max(eligible, key=lambda row: row['durability'])


def _local_batch(available, limit):
    anchor = available[0][0]
    chosen = [available[0]]
    for entry in available[1:]:
        pos = entry[0]
        if len(chosen) >= limit:
            break
        previous = chosen[-1][0]
        if (abs(pos[1] - anchor[1]) > 1
                or (pos[0] - anchor[0]) ** 2 + (pos[2] - anchor[2]) ** 2 > LOCAL_RADIUS ** 2
                or (pos[0] - previous[0]) ** 2 + (pos[2] - previous[2]) ** 2 > LOCAL_RADIUS ** 2):
            continue
        chosen.append(entry)
    return chosen


def _resource_route_transition(c, state, *, final=False, detail=None):
    """Keep the discovery route ledger consistent with the acquisition return."""
    raw=getattr(c,'snow_expedition_resource_path',None)
    if raw is None:return
    path=Path(raw);ledger=json.loads(path.read_text())
    from .seed_snow_search import ledger_state
    seed=ledger_state(ledger);active=seed.get('active_route')
    route_id=getattr(c,'snow_expedition_route_id',None)
    if (not isinstance(active,dict) or active.get('route_id')!=route_id
            or active.get('world_session')!=c.world):
        raise RuntimeError('种子雪地发现路线与当前返航令牌不一致')
    active.update(state=state)
    if detail is not None:active['detail']=detail
    if final:
        seed['routes'].append(dict(active));seed['active_route']=None
    write_json(path,ledger)


def _return_seed_home(c, checkpoint, path=None, ledger=None):
    """Use the still-live host permit; the host supplies the unique home/origin."""
    token=getattr(c,'snow_expedition_token',None)
    if not isinstance(token,str) or not token:return None
    route_id=getattr(c,'snow_expedition_route_id',None)
    record={'state':'inflight','route_id':route_id,'world_session':c.world,
            'started_at':c.status().get('time'),'host_target':True}
    if ledger is not None and path is not None:
        ledger['seed_return']=record
        expedition=ledger.get('seed_expedition')
        if isinstance(expedition,dict):expedition['state']='return_inflight'
        write_json(path,ledger)
    _resource_route_transition(c,'return_inflight')
    checkpoint()
    try:
        reply=c.request('navigate',snow_expedition_token=token,
                        snow_expedition_return=True,arrival=8,seconds=5340)
        state=c.status()
    except Exception as error:
        record.update(state='uncertain',detail=str(error))
        if ledger is not None and path is not None:
            expedition=ledger.get('seed_expedition')
            if isinstance(expedition,dict):expedition['state']='return_uncertain'
            write_json(path,ledger)
        try:_resource_route_transition(c,'return_uncertain',detail=str(error))
        except Exception:pass
        for name in ('snow_expedition_token','snow_expedition_route_id','snow_expedition_route'):
            if hasattr(c,name):delattr(c,name)
        from .acquisition import Unavailable
        raise Unavailable('雪地采集返航结果未知；令牌已消费且不会重放',
                          'waiting',code='route_uncertain') from error
    if (reply.get('phase')!='done' or reply.get('id')!=getattr(c,'last',None)
            or reply.get('world_session')!=c.world or state.get('world_session')!=c.world
            or state.get('navigating') or state.get('native_material_busy')):
        record.update(state='uncertain',detail=reply.get('detail'),
                      observed_at=state.get('time'))
        if ledger is not None and path is not None:
            expedition=ledger.get('seed_expedition')
            if isinstance(expedition,dict):expedition['state']='return_uncertain'
            write_json(path,ledger)
        try:_resource_route_transition(c,'return_uncertain',detail=str(reply.get('detail')))
        except Exception:pass
        for name in ('snow_expedition_token','snow_expedition_route_id','snow_expedition_route'):
            if hasattr(c,name):delattr(c,name)
        from .acquisition import Unavailable
        raise Unavailable('雪地采集返航回执不确定；短期令牌已消费，不自动重放',
                          'waiting',code='route_uncertain')
    try:_resource_route_transition(c,'home_arrived',final=True)
    except Exception as error:
        record.update(state='uncertain',detail='resource route ledger: '+str(error),
                      observed_at=state.get('time'))
        if ledger is not None and path is not None:
            expedition=ledger.get('seed_expedition')
            if isinstance(expedition,dict):expedition['state']='return_uncertain'
            write_json(path,ledger)
        for name in ('snow_expedition_token','snow_expedition_route_id','snow_expedition_route'):
            if hasattr(c,name):delattr(c,name)
        from .acquisition import Unavailable
        raise Unavailable('返航已到达但资源路线账本未闭环；停止等待核对',
                          'waiting',code='route_uncertain') from error
    result={'route_id':route_id,
            'returned_at':state.get('time'),'host_target':True}
    record.update(state='home_arrived',returned_at=state.get('time'))
    if ledger is not None and path is not None:
        expedition=ledger.get('seed_expedition')
        if isinstance(expedition,dict):expedition['state']='home_arrived'
        write_json(path,ledger)
    c.anchor=list(state['pos'])
    for name in ('snow_expedition_token','snow_expedition_route_id','snow_expedition_route'):
        if hasattr(c,name):delattr(c,name)
    return result


def _return_remote_home(c, checkpoint, path=None, ledger=None, *, reason='completed'):
    """Close whichever exact long-distance snow route this process owns."""
    if hasattr(c, 'snow_expedition_token'):
        return _return_seed_home(c, checkpoint, path, ledger)
    if hasattr(c, 'bobby_snow_route_id'):
        from .bobby_snow_route import return_home
        return return_home(c, checkpoint, acquisition_path=path,
                           acquisition_ledger=ledger, reason=reason)
    return None


def _require_remote_return(c, path, ledger, observed_at):
    if hasattr(c, 'snow_expedition_token'):
        ledger['seed_return']={'state':'required',
            'route_id':getattr(c,'snow_expedition_route_id',None),
            'world_session':c.world,'required_at':observed_at,
            'host_target':True}
        expedition=ledger.get('seed_expedition')
        if isinstance(expedition,dict):expedition['state']='return_required'
    elif hasattr(c, 'bobby_snow_route_id'):
        ledger['bobby_return']={'state':'required',
            'route_id':getattr(c,'bobby_snow_route_id',None),
            'world_session':c.world,'required_at':observed_at,
            'same_route':True}
        expedition=ledger.get('bobby_expedition')
        if isinstance(expedition,dict):expedition['state']='return_required'
    else:
        return False
    write_json(path,ledger)
    return True


def acquire_surface_snow(c, item, target, profile, regions, path, ledger, checkpoint):
    """Mine at most four nearby snow sources with exact item receipts."""
    from .acquisition import (Unavailable, _safe, _scan, _choose_tool, _travel,
                              _paused_guard_hold, _resource_route_scope,
                              _route_region_key, record_route_failure)
    from .dirt_harvest import _nearby_hover
    from .protocol import JobPaused

    if item not in PRODUCTS:
        raise ValueError('Unsupported snow product')
    label = {SNOW: '雪层', SNOW_BLOCK: '雪块', SNOWBALL: '雪球'}[item]
    prefix = item.split(':', 1)[1]
    initial = c.status()
    if initial.get('snow_harvest_protocol', 0) < 1:
        raise Unavailable('当前 Kit 主包缺少雪地采集工具锁；未移动或挖掘')
    try:
        selection = _projection_selection(initial)
        for region in regions:
            validate_region(region, profile, selection)
    except ValueError as error:
        raise Unavailable(str(error)) from error

    def verify_selection(state, region):
        try:
            current = _projection_selection(state)
            if current != selection:
                raise ValueError('Current projection selection changed during snow harvesting')
            validate_region(region, profile, current)
        except ValueError as error:
            raise Unavailable(str(error)) from error

    def natural_snowpack(region):
        from .bobby_snow_route import authorizes_natural_snowpack
        return authorizes_natural_snowpack(c,region)

    def harvest_cell(pos, expected_gain, region, local):
        checkpoint(); state = c.status(); _safe(state); verify_selection(state, region)
        if state.get('flight') is not True:
            raise Unavailable('表层雪采集需要已确认飞行状态，避免失去脚下支撑')
        before_count = carried(state, item)
        if before_count >= target:
            return {'phase': 'done', 'gained': 0}
        key = prefix + '-block-' + ':'.join(map(str, pos))
        fresh = _local_scan(c, pos, checkpoint)
        relaxed=natural_snowpack(region)
        if not candidate(fresh, pos, item, allow_natural_snowpack=relaxed):
            ledger['visited'][key] = {'state': 'skipped', 'pos': pos,
                                      'reason': 'source_or_buffer_changed'}
            write_json(path, ledger)
            return {'phase': 'waiting', 'detail': f'{label}候选在操作前改变，已跳过该格'}
        expected_gain = source_yield(next(row for row in fresh if row['pos'] == pos), item)
        tool = _shovel(state, item, expected_gain + 32)
        trace = []
        destination = [pos[0] + .5, pos[1] + 3.1, pos[2] + .5]
        try:
            if not local or not _nearby_hover(c, destination, checkpoint, trace):
                _travel(c, destination, checkpoint, trace,
                        route_scope=_resource_route_scope(profile, region))
        except JobPaused as error:
            _paused_guard_hold(c, ledger, path, region, pos, pos, destination,
                               trace, str(error), profile, item)
            raise
        except Unavailable as error:
            if error.code in ('guard_displaced','route_geometry_blocked','route_uncertain'):
                current = c.status()
                ledger['visited'][key] = {
                    'state': 'route_hold', 'pos': pos,
                    'region_key': _route_region_key(region),
                    'route_code': error.code, 'reason': error.detail,
                    'entry_target': destination, 'player_pos': list(current['pos']),
                    'world_session': c.world, 'observed_at': current.get('time'),
                    'route': trace, 'route_evidence': error.evidence}
                write_json(path, ledger)
                record_route_failure(c, profile, item, region, error.code,
                                     error.detail, destination, error.evidence)
                raise
            if error.detail not in ('资源区入口或航线仍有障碍；不会穿越地层或挖开区域外建筑',
                                    '前往资源区的安全路线没有到达，保留本次位置'):
                raise
            ledger['visited'][key] = {'state': 'skipped', 'pos': pos,
                                      'reason': 'safe_route_unavailable', 'route': trace}
            write_json(path, ledger)
            return {'phase': 'waiting', 'detail': f'{label}候选无法沿已核验空气航线抵达，已跳过该格'}
        state = c.status(); _safe(state); verify_selection(state, region)
        if state.get('flight') is not True:
            raise Unavailable('表层雪采集需要已确认飞行状态，避免失去脚下支撑')
        if carried(state, item) >= target:
            return {'phase': 'done', 'gained': 0}
        fresh = _local_scan(c, pos, checkpoint)
        if not candidate(fresh, pos, item, allow_natural_snowpack=relaxed):
            ledger['visited'][key] = {'state': 'skipped', 'pos': pos,
                                      'reason': 'source_changed_after_travel'}
            write_json(path, ledger)
            return {'phase': 'waiting', 'detail': f'接近后{label}或保护缓冲区改变，已跳过该格'}
        expected_gain = source_yield(next(row for row in fresh if row['pos'] == pos), item)
        if room_for_item(state, item) < expected_gain:
            returned=_return_remote_home(c,checkpoint,path,ledger,
                                         reason='inventory_capacity')
            raise Unavailable(f'{label}背包空间不足以接收当前自然雪源；请先存放本批物资', 'waiting')
        tool = _shovel(state, item, expected_gain + 32)
        _choose_tool(c, tool, checkpoint)
        fresh = _local_scan(c, pos, checkpoint)
        if not candidate(fresh, pos, item, allow_natural_snowpack=relaxed):
            ledger['visited'][key] = {'state': 'skipped', 'pos': pos,
                                      'reason': 'source_changed_after_tool_selection'}
            write_json(path, ledger)
            return {'phase': 'waiting', 'detail': f'选取铲后{label}或保护缓冲区改变，已跳过该格'}
        before = c.status(); _safe(before); verify_selection(before, region)
        hand = before.get('hand') or {}
        selected = before.get('selected_slot')
        held = next((row for row in before.get('inventory', []) if row.get('slot') == selected), None)
        require_silk = item != SNOWBALL
        if (type(selected) is not int or not 0 <= selected < 9 or held is None
                or held.get('item') != hand.get('item') or hand.get('item') != tool['item']
                or hand.get('count') != 1 or hand.get('durability') != tool['durability']
                or hand.get('enchantments', []) != tool.get('enchantments', [])
                or _silk(hand) is not require_silk or _silk(held) is not require_silk
                or hand.get('durability', 0) < expected_gain + 32):
            raise Unavailable('雪地采集铲的实际手持槽位、精准采集属性或耐久未核实；不挖雪')
        expected = next(row['state'] for row in fresh if row['pos'] == pos)
        entry = {'state': 'inflight', 'pos': pos, 'expected_state': expected,
                 'expected_gain': expected_gain, 'before': carried(before, item),
                 'tool_mode': 'silk_touch' if require_silk else 'plain_shovel',
                 'route': trace, 'world_session': c.world, 'observed_at': before.get('time')}
        ledger['visited'][key] = entry; write_json(path, ledger)
        checkpoint(); verify_selection(c.status(), region)
        guard = {'expected_tool_slot': selected, 'expected_tool_item': tool['item'],
                 'required_silk_shovel': True} if require_silk else {
                 'expected_tool_slot': selected, 'expected_tool_item': tool['item'],
                 'required_plain_shovel': True}
        reply = c.request('mine_block', pos=pos, face='up', expected_state=expected,
                          seconds=20, **guard)
        native_id = getattr(c, 'last', None)
        after = c.status(); _safe(after)
        if reply.get('phase') != 'done':
            if (reply.get('detail') in UNSTARTED and carried(after, item) == entry['before']
                    and any(row['pos'] == pos and row['state'] == expected
                            for row in _local_scan(c, pos, checkpoint))):
                entry.update(state='skipped', reason=reply['detail'], native_phase=reply.get('phase'))
                write_json(path, ledger)
                return {'phase': 'waiting', 'detail': '原生接口未开始挖雪，已跳过此格'}
            return {'phase': 'blocked', 'code': 'native_uncertain',
                    'detail': f'{label}挖掘回执不确定，保留在途记录且不重放'}
        if any(row['pos'] == pos for row in _scan(c, pos, pos, checkpoint)):
            return {'phase': 'blocked', 'code': 'block_unconfirmed',
                    'detail': f'{label}来源仍占据原位置，保留在途记录且不重放'}
        attempted = set(); deadline = time.monotonic() + 12
        while True:
            checkpoint(); after = c.status(); _safe(after)
            amount = carried(after, item) - entry['before']
            if amount == expected_gain:
                entry.update(state='collected', after=carried(after, item), gained=amount,
                             native_phase='done', native_id=native_id,
                             observed_at=after.get('time'))
                if carried(after,item)>=target:
                    _require_remote_return(c,path,ledger,after.get('time'))
                write_json(path, ledger)
                returned=(_return_remote_home(c,checkpoint,path,ledger,
                                              reason='target_reached')
                          if carried(after,item)>=target else None)
                return {'phase': 'done' if carried(after, item) >= target else 'waiting',
                        'detail': f'{label}逐格回收已核验，背包 {carried(after, item)}/{target}',
                        'before': entry['before'], 'after': carried(after, item), 'gained': amount,
                        **({'return_home':returned} if returned else {})}
            if amount > expected_gain:
                return {'phase': 'blocked', 'code': 'inventory_ambiguous',
                        'detail': f'{label}背包增量超过当前雪源的确定掉落，保留回执且不挖下一格'}
            for drop in _fresh_drops(before, after, pos, item):
                if drop.get('uuid') in attempted:
                    continue
                attempted.add(drop.get('uuid'))
                collect_drop(c, drop, observation=after)
            if time.monotonic() >= deadline:
                return {'phase': 'blocked', 'code': 'drop_unconfirmed',
                        'detail': f'{label}已挖但精确背包增量未确认，保留在途记录且不挖下一格'}
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
                         [hi[0] + BUFFER, min(319, hi[1] + 6), hi[2] + BUFFER], checkpoint)
            scans += 1
            state = c.status(); _safe(state)
            spent = {tuple(v['pos']) for k, v in ledger['visited'].items()
                     if k.startswith(prefix + '-block-') and isinstance(v.get('pos'), list)
                     and len(v['pos']) == 3}
            available = candidates(
                rows, lo, hi, state['pos'], item, spent,
                allow_natural_snowpack=natural_snowpack(region))
            if not available:
                ledger['visited'][window_key] = {'state': 'empty_or_unsafe', 'min': lo,
                                                  'max': hi, 'observed_at': state.get('time')}
                write_json(path, ledger)
                continue
            batch_before = carried(state, item)
            if batch_before >= target:
                _require_remote_return(c,path,ledger,state.get('time'))
                returned=_return_remote_home(c,checkpoint,path,ledger,
                                             reason='target_already_carried')
                return {'phase': 'done', 'detail': f'{label}背包现物已经达到目标',
                        'before': batch_before, 'after': batch_before, 'gained': 0,
                        **({'return_home':returned} if returned else {})}
            remaining = target - batch_before
            useful = [entry for entry in available if entry[1] <= remaining] or available
            batch = _local_batch(useful, LOCAL_BATCH)
            collected = 0; started = time.monotonic(); budget_exhausted = False
            return_home = None
            for pos, expected_gain in batch:
                if collected and time.monotonic() - started >= BATCH_SECONDS:
                    budget_exhausted = True; break
                result = harvest_cell(pos, expected_gain, region, collected > 0)
                if result['phase'] == 'done' and result.get('gained', 0) == 0:
                    break
                if result.get('gained', 0) <= 0:
                    return result
                collected += 1
                if result.get('return_home'):return_home=result['return_home']
                if result['phase'] == 'done':
                    break
            checkpoint(); final = c.status(); _safe(final)
            after = carried(final, item)
            if after>=target:
                _require_remote_return(c,path,ledger,final.get('time'))
            returned=return_home or (_return_remote_home(
                c,checkpoint,path,ledger,reason='target_reached') if after>=target else None)
            return {'phase': 'done' if after >= target else 'waiting',
                    'detail': (f'{label}本轮逐格回收 {collected} 格，背包 {after}/{target}'
                               + ('；已达本轮时限' if budget_exhausted else '')),
                    'before': batch_before, 'after': after,
                    'gained': after - batch_before, 'collected_cells': collected,
                    **({'return_home':returned} if returned else {})}
    returned=_return_remote_home(c,checkpoint,path,ledger,
                                 reason='candidate_exhausted')
    return {'phase': 'blocked', 'code': 'no_safe_candidate',
            'detail': f'已授权野外区域没有新的安全自然{label}来源；已记录且不扩挖',
            **({'return_home':returned} if returned else {})}
