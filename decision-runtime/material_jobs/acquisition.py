"""Deterministic acquisition inside configured resource regions, using native Kit jobs.

The caller owns the MaterialClient lease and its checkpoint-aware raw polling.
This adapter does not start another controller, change equipment policy, or finish
the lease. Targets are absolute main-inventory counts, never assumed block drops.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time

from kit_runtime.journal import write_json
from material_trip_policy import carried, room_for_item
from native_sand_quarry import choose_quarry
from wood_expedition import landing
from work_access import approach_faces
from .protocol import JobPaused, server_key


SAPLING_SOILS = {'minecraft:grass_block', 'minecraft:dirt', 'minecraft:coarse_dirt',
                 'minecraft:rooted_dirt', 'minecraft:podzol', 'minecraft:mycelium',
                 'minecraft:moss_block'}


def _apply_bone_meal(c, species_item, sapling_item, pos, result, checkpoint):
    x,y,z=pos;budget=min(6,carried(c.status(),'minecraft:bone_meal'))
    if not budget:
        result.update(stage='sapling_kept_no_bone_meal',detail='树苗已确认，当前没有骨粉')
        return result
    before_rows=_scan(c,[x,y,z],[x,y+1,z],checkpoint)
    expected=next((row for row in before_rows
                   if row['pos']==[x,y,z] and block_id(row)==sapling_item),None)
    if expected is None:
        result.update(stage='sapling_site_changed',detail='催熟前未再看到原树苗；不使用骨粉')
        return result
    approach_faces(c,[x,y,z],expected['state'],['up','north','south','west','east'],
                   seconds=30,stand_distance=1.5)
    checkpoint();nearby=_scan(c,[x,y,z],[x,y+1,z],checkpoint)
    if not any(row['pos']==[x,y,z] and block_id(row)==sapling_item for row in nearby):
        result.update(stage='sapling_site_changed',detail='接近后树苗状态已改变；不使用骨粉')
        return result
    c.checked('select_item',item='minecraft:bone_meal')
    for _ in range(budget):
        checkpoint();state=c.status();_safe(state)
        rows=_scan(c,[x,y,z],[x,y+1,z],checkpoint)
        sapling=next((r for r in rows if r['pos']==[x,y,z] and block_id(r)==sapling_item),None)
        if sapling is None:
            result.update(stage='grown_or_changed',detail='树苗格已改变；停止催熟')
            break
        before=carried(state,'minecraft:bone_meal')
        c.checked('interact',pos=[x,y,z],face='up',expected_state=sapling['state'],expected_hand='minecraft:bone_meal')
        used=False;growth=None;deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            checkpoint();fresh=c.status();_safe(fresh)
            after=_scan(c,[x-2,y,z-2],[x+2,y+18,z+2],checkpoint)
            stump=next((r for r in after if r['pos']==[x,y,z]),None)
            if carried(fresh,'minecraft:bone_meal')<before:used=True
            grown_ids={species_item,species_item.removesuffix('_log')+'_wood',species_item.removesuffix('_log')+'_leaves'}
            if any(block_id(r) in grown_ids and y<=r['pos'][1]<=y+18
                   and abs(r['pos'][0]-x)<=2 and abs(r['pos'][2]-z)<=2 for r in after):
                growth={'root_state':stump['state'] if stump else 'missing',
                        'bone_meal_used':before-carried(fresh,'minecraft:bone_meal'),
                        'observed_at':fresh['time']};break
            if stump and block_id(stump)!=sapling_item:
                result.update(stage='sapling_site_changed',detail='树苗被移除或改成其他方块；停止催熟')
                break
            if used:break
            time.sleep(.15)
        result.setdefault('bone_meal_receipts',[]).append({
            'before':before,'after':carried(c.status(),'minecraft:bone_meal'),
            'consumed':used,'growth_confirmed':bool(growth)})
        if growth:
            result.update(stage='grown',growth_confirmed=True,growth=growth);break
        if not used or result.get('stage')=='sapling_site_changed':
            result.update(stage='sapling_kept_bone_meal_unconfirmed',
                          detail='本次骨粉效果未获服务器确认；没有重复点击');break
        result['bone_meal_used']=result.get('bone_meal_used',0)+1
    result['bone_meal_on_hand']=carried(c.status(),'minecraft:bone_meal')
    return result


def _replant_tree_with_bonemeal(c, species_item, tree_root, plant_cell, drop_baseline,
                                sapling_before, bone_meal_before, out, checkpoint):
    """Recover only sapling drops born at this tree, then regrow on its verified ground cell."""
    from drop_collection import collect_drop

    sapling_item = species_item.removesuffix('_log') + '_sapling'
    x, y, z = plant_cell
    result = {'tree_root': tree_root, 'plant_cell': list(plant_cell),
              'sapling_item': sapling_item, 'drops_collected': [], 'planted': False,
              'bone_meal_before': bone_meal_before}

    # A tree's own sapling can appear a few ticks after its leaves fall. Limit
    # the wait and restrict pickup to a fresh, nearby sapling stack from this chop.
    for _ in range(10):
        checkpoint()
        state = c.status(); _safe(state)
        candidates = []
        for drop in state.get('entities', []):
            stack = drop.get('stack') or {}
            pos = drop.get('pos') or []
            if (drop.get('type') == 'minecraft:item' and stack.get('item') == sapling_item
                    and len(pos) == 3 and abs(pos[0]-x) <= 12 and abs(pos[2]-z) <= 12
                    and y-3 <= pos[1] <= y+40
                    and stack.get('count', 0) > drop_baseline.get(drop.get('uuid'), 0)):
                candidates.append(drop)
        if candidates:
            drop = min(candidates, key=lambda row: math.dist(row['pos'], state['pos']))
            if not collect_drop(c, drop, observation=state, seconds=25):
                result['stage'] = 'sapling_drop_not_recovered'
                result['detail'] = '树苗掉落已看到但未核对拾取，停止此处收尾'
                break
            result['drops_collected'].append(drop.get('uuid'))
            continue
        if carried(state, sapling_item) > sapling_before:
            result['stage'] = 'seed_in_inventory'
            break
        time.sleep(.2)

    # Avoid taking a user's sapling unless bone meal is also available for
    # the requested immediate regrowth. Keep all unsupported cases in inventory.
    state = c.status(); _safe(state)
    initial=_scan(c,[x,y-1,z],[x,y+1,z],checkpoint)
    initial_cells={tuple(r['pos']):r for r in initial}
    initial_soil=initial_cells.get((x,y-1,z));initial_seed=initial_cells.get(tuple(plant_cell))
    if (initial_seed and block_id(initial_seed)==sapling_item and initial_soil
            and block_id(initial_soil) in SAPLING_SOILS and initial_soil.get('solid')
            and not initial_soil.get('fluid') and not initial_soil.get('block_entity')):
        result.update(stage='sapling_already_planted',planted=True,
                      sapling_state=initial_seed['state'],planted_count=0)
        result['saplings_on_hand']=carried(state,sapling_item)
        result=_apply_bone_meal(c,species_item,sapling_item,plant_cell,result,checkpoint)
        result['saplings_on_hand']=carried(c.status(),sapling_item)
        _write_regrowth_receipt(c,species_item,out,result)
        return result
    if result.get('stage') == 'sapling_drop_not_recovered':
        result['saplings_on_hand'] = carried(state, sapling_item)
    elif carried(state, sapling_item) <= sapling_before:
        result.update(stage='no_sapling_drop', detail='本棵树没有核对到新掉落的同种树苗')
    elif carried(state, 'minecraft:bone_meal') <= 0:
        result.update(stage='seed_kept_no_bone_meal', detail='树苗已保留在背包；当前没有骨粉')
    else:
        region = _scan(c, [x, y-1, z], [x, y+2, z], checkpoint)
        actual = {tuple(row['pos']): row for row in region}
        soil = actual.get((x, y-1, z))
        # Native scan is complete for loaded chunks and omits empty blocks.
        target = actual.get((x, y, z), {'state': 'Block{minecraft:air}'})
        head = actual.get((x, y+1, z))
        if (not soil or block_id(target) not in
            ('minecraft:air', 'minecraft:cave_air', 'minecraft:void_air')
                or block_id(soil) not in SAPLING_SOILS
                or soil.get('fluid') or soil.get('block_entity') or not soil.get('solid')
                or target.get('fluid') or target.get('block_entity')
                or head and (not head.get('passable') or head.get('fluid'))):
            result.update(stage='seed_kept_site_not_ready',
                          detail='原树根没有通过可种植土壤和两格净空核验；树苗保留在背包')
        else:
            checkpoint(); c.checked('select_item', item=sapling_item)
            approach_faces(c, [x, y-1, z], soil['state'], ['up'], seconds=30)
            checkpoint(); state = c.status(); _safe(state)
            if carried(state, sapling_item) <= sapling_before:
                raise Unavailable('种树前树苗数量改变；未放置', 'waiting')
            current = _scan(c, [x, y-1, z], [x, y+1, z], checkpoint)
            actual = {tuple(row['pos']): row for row in current}
            soil = actual.get((x, y-1, z))
            target = actual.get((x, y, z), {'state': 'Block{minecraft:air}'})
            if (not soil or block_id(soil) not in SAPLING_SOILS
                    or block_id(target) not in
                    ('minecraft:air', 'minecraft:cave_air', 'minecraft:void_air')
                    or target.get('fluid') or target.get('block_entity')):
                raise Unavailable('树坑在种植前发生变化，树苗未放置', 'waiting')
            c.checked('interact', pos=[x, y-1, z], face='up', expected_state=soil['state'],
                      expected_hand=sapling_item)
            placed = None
            for _ in range(10):
                checkpoint(); fresh = c.status(); _safe(fresh)
                planted = _scan(c, [x, y, z], [x, y, z], checkpoint)
                if (len(planted) == 1 and block_id(planted[0]) == sapling_item
                        and carried(fresh, sapling_item) == carried(state, sapling_item)-1):
                    placed = planted[0]; break
                if planted and block_id(planted[0]) not in ('minecraft:air','minecraft:cave_air','minecraft:void_air',sapling_item):
                    raise Unavailable('种植格被别的方块占用；没有重复放置', 'waiting')
                time.sleep(.15)
            if placed is None:
                raise Unavailable('服务器没有同时确认树苗方块和背包扣减；停止催熟', 'waiting')
            result.update(stage='sapling_planted', planted=True,
                          sapling_state=placed['state'], planted_count=1)

            result=_apply_bone_meal(c,species_item,sapling_item,plant_cell,result,checkpoint)

    result['saplings_on_hand'] = carried(c.status(), sapling_item)
    result['bone_meal_on_hand'] = carried(c.status(), 'minecraft:bone_meal')
    try:
        with (Path(out)/'tree-regrowth.jsonl').open('a') as stream:
            stream.write(json.dumps({'time': int(time.time()*1000), 'world_session': c.world,
                                     'item': species_item, **result}, ensure_ascii=False)+'\n')
    except OSError as error:
        # Optional evidence writes must not invalidate an already confirmed tree harvest.
        result['journal_warning'] = type(error).__name__
    return result


def _write_regrowth_receipt(c,item,out,result):
    try:
        with (Path(out)/'tree-regrowth.jsonl').open('a') as stream:
            stream.write(json.dumps({'time':int(time.time()*1000),'world_session':c.world,
                                     'item':item,**result},ensure_ascii=False)+'\n')
    except OSError as error:
        result['journal_warning']=type(error).__name__


ROCK_SOURCES = {
    'minecraft:cobblestone': {'minecraft:stone'},
    'minecraft:cobbled_deepslate': {'minecraft:deepslate'},
    'minecraft:raw_iron': {'minecraft:iron_ore', 'minecraft:deepslate_iron_ore'},
    'minecraft:raw_iron_block': {'minecraft:raw_iron_block'},
    'minecraft:raw_copper': {'minecraft:copper_ore', 'minecraft:deepslate_copper_ore'},
    'minecraft:coal': {'minecraft:coal_ore', 'minecraft:deepslate_coal_ore'},
    **{'minecraft:'+name: {'minecraft:'+name} for name in ('andesite', 'diorite', 'granite', 'tuff', 'calcite')},
}
NATURAL = {'minecraft:' + name for name in (
    'stone', 'deepslate', 'granite', 'diorite', 'andesite', 'tuff', 'calcite', 'dripstone_block', 'raw_iron_block',
    'dirt', 'grass_block', 'coarse_dirt', 'rooted_dirt', 'podzol', 'mycelium', 'clay',
    'coal_ore', 'deepslate_coal_ore', 'iron_ore', 'deepslate_iron_ore',
    'copper_ore', 'deepslate_copper_ore', 'gold_ore', 'deepslate_gold_ore',
    'redstone_ore', 'deepslate_redstone_ore', 'lapis_ore', 'deepslate_lapis_ore',
    'diamond_ore', 'deepslate_diamond_ore', 'emerald_ore', 'deepslate_emerald_ore')}
LOGS = {'minecraft:' + name + '_log' for name in
        ('oak', 'spruce', 'birch', 'jungle', 'acacia', 'dark_oak', 'mangrove', 'cherry', 'pale_oak')}
LIGHTS = {'minecraft:torch', 'minecraft:wall_torch'}
AIR = {'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'}
FALLING = {'minecraft:sand', 'minecraft:red_sand', 'minecraft:gravel', 'minecraft:anvil',
           'minecraft:chipped_anvil', 'minecraft:damaged_anvil', 'minecraft:dragon_egg'}
MAX_SCANS = 12
OVERWORLD_MIN_Y, OVERWORLD_MAX_Y = -64, 319
CLEAR_RESUPPLY_DETAIL = 'rock quarry backpack reserve exhausted; store materials before resuming'
# Current vanilla OreVeinifier.IRON bounds; surface building blocks remain protected.
RAW_IRON_BLOCK_MIN_Y, RAW_IRON_BLOCK_MAX_Y = -60, -8
DIRECT_ROUTE_LIMIT = 384.0
SEGMENT_ROUTE_LIMIT = 256.0
SEARCH_TILE_MARGIN = 16.0


class Unavailable(Exception):
    def __init__(self, detail, phase='blocked', code=None, evidence=None):
        self.phase, self.detail, self.code = phase, detail, code
        self.evidence = evidence if isinstance(evidence, dict) else {}
        super().__init__(detail)


def block_id(row):
    text = row.get('state', '')
    return text[6:text.index('}')] if text.startswith('Block{') and '}' in text else 'unknown'


def in_box(pos, low, high):
    return len(pos) == 3 and all(low[i] <= pos[i] <= high[i] for i in range(3))


def _bounds(region, *, shaft=False):
    low, high = region.get('min'), region.get('max')
    if (not isinstance(low, list) or not isinstance(high, list) or len(low) != 3 or len(high) != 3
            or any(type(n) is not int for n in low + high) or any(a > b for a, b in zip(low, high))
            or high[0]-low[0] > 127 or high[2]-low[2] > 127
            or not shaft and high[1]-low[1] > 191):
        raise Unavailable('资源区域需要有界整数坐标，单区最多 128×192×128 格')
    # Discovery can join a deep quarry to a surface over 192 blocks above it.
    # Only the complete shaft has this range; native work stays in 18-high slices.
    if shaft and not OVERWORLD_MIN_Y <= low[1] <= high[1] <= OVERWORLD_MAX_Y:
        raise Unavailable('入口竖井必须位于主世界合法高度 -64..319 内')
    return list(low), list(high)


def _safe(state):
    if (state.get('health', 0) < 19 or state.get('food', 0) < 8 or state.get('under_water')
            or not state.get('guard_armed') or not state.get('guard_pve_only')
            or state.get('manual_movement') or state.get('safety_hold', {}).get('active')):
        raise Unavailable('生命、食物或防护不满足材料采集条件')


def _resource_route_scope(profile, region):
    """Canonical proof that a discovered region belongs to one bounded search.

    A direct configured region is not permission for an arbitrarily long
    flight.  Segmentation is enabled only for a discovery-produced region and
    the original finite search origin/radius that authorized it.
    """
    if (not isinstance(profile, dict) or not isinstance(region, dict)
            or region.get('source') != 'natural_survey'):
        return None
    origin = profile.get('search_origin')
    radius = profile.get('search_radius', 256)
    if (not isinstance(origin, list) or len(origin) != 3
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   for value in origin)
            or type(radius) is not int or not 1 <= radius <= 384):
        return None
    low, high = _bounds(region)
    return {'search_origin': list(origin), 'search_radius': radius,
            'region': {'min': low, 'max': high},
            'region_key': _route_region_key(region)}


def _scan(c, low, high, checkpoint):
    if math.prod(high[i]-low[i]+1 for i in range(3)) > 50000:
        raise Unavailable('扫描体积超过原生上限，需继续分段')
    checkpoint()
    reply = c.request('scan', min=low, max=high, details=True)
    if not isinstance(reply.get('blocks'), list):
        raise Unavailable('区域尚未完整加载或扫描失败：' + str(reply.get('detail', '缺少方块回执')), 'waiting')
    return reply['blocks']


def _tool(state, suffix, durability, *, no_silk=False):
    candidates = [row for row in state['inventory'] if 0 <= row.get('slot', -1) < 36
                  and row.get('count') and row.get('item') in
                  ('minecraft:diamond_' + suffix, 'minecraft:netherite_' + suffix)]
    if no_silk and any(row.get('item', '').endswith('_pickaxe') and row.get('count')
                       and any(e['id'] == 'minecraft:silk_touch' and e['level'] > 0
                               for e in row.get('enchantments', [])) for row in state['inventory']):
        raise Unavailable('背包或副手有精准采集镐，区域挖可能自动切换；请先保管后再采普通掉落物')
    eligible = [row for row in candidates if row.get('durability', 0) >= durability]
    if not eligible:
        raise Unavailable(f'需要剩余耐久至少 {durability} 的钻石或下界合金工具：{suffix}')
    return max(eligible, key=lambda row: row['durability'])


def _choose_tool(c, tool, checkpoint):
    checkpoint()
    c.checked('select_item', item=tool['item'], slot=tool['slot'])


def _hovering_on_storage_top(row, state):
    """Flight can keep on_ground false while feet are stationary on a 14/16 chest lid.

    This only supplies a precise broad-phase exception. The native air-only
    navigator must still accept the actual collision shape before moving.
    """
    if (state.get('flight') is not True or row.get('solid') is not False
            or row.get('fluid') is not False or block_id(row) not in
            {'minecraft:chest','minecraft:trapped_chest','minecraft:ender_chest'}):
        return False
    velocity=state.get('velocity')
    if (not isinstance(velocity,(list,tuple)) or len(velocity)!=3
            or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>.025 for v in velocity)):
        return False
    top=row['pos'][1]+14/16
    return top-1e-6 <= state['pos'][1] <= top+.002


def blocks_route(row, state, target):
    if not row.get('fluid') and row.get('passable',False):
        return False
    p=state['pos'];cell=row['pos']
    # Chests/slabs share the floor(feetY) cell with a grounded player without
    # intersecting their body. The native shape check remains authoritative;
    # don't turn that partial supporting block into a solid one-block ceiling.
    rising=target[1]>p[1] and math.hypot(target[0]-p[0],target[2]-p[2])<.01
    partial_support=((state.get('on_ground') or _hovering_on_storage_top(row,state))
                     and rising and not row.get('solid') and not row.get('fluid')
                     and .01<p[1]-math.floor(p[1])<.99 and cell[1]==math.floor(p[1])
                     and math.floor(p[0]-.3)<=cell[0]<=math.floor(p[0]+.3)
                     and math.floor(p[2]-.3)<=cell[2]<=math.floor(p[2]+.3))
    return not partial_support


def _terminal_guard_route(c, reply, state):
    """A waiting reply permits a new route only after the old request ended."""
    rid = getattr(c, 'last', None)
    lease = state.get('supervision_lease') or {}
    return bool(isinstance(rid, str) and rid
                and reply.get('id') == rid and reply.get('world_session') == c.world
                and reply.get('phase') == 'waiting'
                and reply.get('control_revision') == state.get('control_revision')
                and state.get('world_session') == c.world
                and state.get('last_request') == rid and state.get('id') == rid
                and state.get('phase') == 'waiting'
                and state.get('navigating') is False
                and not state.get('native_material_busy')
                and lease.get('kind') == 'materials'
                and lease.get('job_session') == getattr(c, 'task', None)
                and lease.get('revision') == state.get('control_revision')
                and lease.get('world_session') == c.world)


def _combat_displacement(state):
    if state.get('guard_busy') is True:
        return True
    now, hurt = state.get('time'), state.get('recent_hurt_at')
    return (type(now) is int and type(hurt) is int
            and 0 <= now-hurt <= 5000 and bool(state.get('recent_attacker')))


def _confirmed_route_obstacle(c, low, high, state, point):
    """Only a fresh, complete scan with a physical blocker earns geometry hold."""
    try:
        reply=c.request('scan',min=low,max=high,details=True)
        rows=reply.get('blocks')
        if (reply.get('phase') not in (None,'done')
                or reply.get('id')!=getattr(c,'last',None)
                or reply.get('world_session')!=c.world or not isinstance(rows,list)):
            return False
        seen=set();blocked=False
        for row in rows:
            pos=row.get('pos') if isinstance(row,dict) else None
            if (not isinstance(pos,list) or len(pos)!=3
                    or any(type(v) is not int for v in pos)
                    or any(not low[i]<=pos[i]<=high[i] for i in range(3))
                    or tuple(pos) in seen
                    or any(type(row.get(flag)) is not bool
                           for flag in ('solid','passable','fluid','block_entity'))):
                return False
            seen.add(tuple(pos))
            if (row['solid'] or row['fluid']) and blocks_route(row,state,point):
                blocked=True
        return blocked
    except (RuntimeError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def _wait_guard_clear(c, checkpoint, evidence, *, seconds=45):
    """Let native PvE defense finish; never steer around an active hostile."""
    deadline = time.monotonic() + seconds
    stable = 0
    last_time = None
    while time.monotonic() < deadline:
        checkpoint()
        state = c.status()
        lease = state.get('supervision_lease') or {}
        # One half-heart of combat damage is recoverable while stationary.
        # Mining and navigation still require the ordinary >=19 health gate.
        if (state.get('health', 0) < 18 or state.get('food', 0) < 8
                or state.get('under_water') or not state.get('guard_armed')
                or not state.get('guard_pve_only') or state.get('manual_movement')
                or (state.get('safety_hold') or {}).get('active')):
            raise Unavailable('防护清怪期间生命或控制不安全；不移动，保留原路线',
                              'waiting', code='guard_displaced', evidence=evidence)
        if (state.get('world_session') != c.world or not state.get('flight')
                or state.get('navigating') or state.get('native_material_busy')
                or not isinstance(state.get('entities'), list)
                or lease.get('kind') != 'materials'
                or lease.get('job_session') != getattr(c, 'task', None)
                or lease.get('world_session') != c.world
                or lease.get('revision') != state.get('control_revision')):
            raise Unavailable('防护清怪期间世界、飞行或实体观察不确定；保留原路线',
                              'waiting', code='guard_displaced', evidence=evidence)
        if (state.get('health', 0) >= 19 and state.get('guard_busy') is False
                and not any(isinstance(e, dict) and e.get('hostile') is True
                            and (type(e.get('health')) not in (int,float)
                                 or e['health'] > 0) for e in state['entities'])
                and type(state.get('time')) is int
                and (last_time is None or state['time'] > last_time)):
            stable += 1
            if stable >= 3:
                return state
        else:
            stable = 0
        last_time = state.get('time')
        time.sleep(.25)
    raise Unavailable('原路线附近防护仍在清怪，暂停而不改去其他资源区',
                      'waiting', code='guard_displaced', evidence=evidence)


def _segmented_targets(c, target, route_scope):
    """Split one approved long resource route without expanding its scope."""
    here = list(c.status()['pos'])
    distance = math.hypot(target[0]-here[0], target[2]-here[2])
    if distance <= DIRECT_ROUTE_LIMIT:
        return [list(target)], None
    if not isinstance(route_scope, dict):
        raise Unavailable('资源区离当前控制点太远，需由发现路线分段接近', 'waiting')
    origin, radius = route_scope.get('search_origin'), route_scope.get('search_radius')
    region = route_scope.get('region')
    if (not isinstance(origin, list) or len(origin) != 3
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   for value in origin)
            or type(radius) is not int or not 1 <= radius <= 384
            or not isinstance(region, dict)):
        raise Unavailable('资源区的分段路线授权不完整，保留原目标',
                          'waiting', code='route_uncertain')
    low, high = _bounds(region)
    allowance = radius + SEARCH_TILE_MARGIN

    def inside_search(point):
        return (abs(point[0]-origin[0]) <= allowance
                and abs(point[2]-origin[2]) <= allowance)

    corners = [[x, target[1], z] for x in (low[0], high[0]+1)
               for z in (low[2], high[2]+1)]
    horizontal_gap = math.hypot(
        max(low[0]-target[0], 0, target[0]-(high[0]+1)),
        max(low[2]-target[2], 0, target[2]-(high[2]+1)))
    if (not inside_search(here) or not inside_search(target)
            or any(not inside_search(point) for point in corners)
            or horizontal_gap > SEARCH_TILE_MARGIN):
        raise Unavailable('当前位置或原资源区超出已批准搜索范围，不扩大路线',
                          'waiting', code='route_uncertain')
    count = math.ceil(distance / SEGMENT_ROUTE_LIMIT)
    # A radius <=384 plus one frontier-tile margin has a bounded diagonal of
    # less than five 256-block legs.  Refuse malformed scopes that imply more.
    if not 2 <= count <= 5:
        raise Unavailable('分段路线超出已批准搜索直径，不移动',
                          'waiting', code='route_uncertain')
    high_air = max(145.0, here[1], target[1])
    points = []
    for index in range(1, count+1):
        if index == count:
            points.append(list(target))
        else:
            ratio = index/count
            points.append([here[0]+(target[0]-here[0])*ratio, high_air,
                           here[2]+(target[2]-here[2])*ratio])
    return points, {'event': 'segmented_resource_approach',
                    'final_target': list(target), 'segment_count': count,
                    'max_segment': SEGMENT_ROUTE_LIMIT,
                    'search_origin': list(origin), 'search_radius': radius,
                    'region_key': route_scope.get('region_key')}


def _persist_segment_trace(c, target, trace, phase, **extra):
    out = getattr(c, 'out', None)
    if out is None:
        return
    try:
        write_json(Path(out)/'resource-route-segments-latest.json', {
            'world_session': getattr(c, 'world', None), 'final_target': list(target),
            'phase': phase, 'trace': trace, **extra})
    except (OSError, ValueError, TypeError):
        pass


def _travel(c, target, checkpoint, trace, guard_budget=None, route_scope=None, *, clearance_padding=.32, obstacle_margin=3.1):
    """Reach one target through fresh bounded legs; never substitute a deposit."""
    segments, plan = _segmented_targets(c, target, route_scope)
    segmented = plan is not None
    if segmented:
        trace.append(plan)
        _persist_segment_trace(c, target, trace, 'planned')
    guard_budget = {} if guard_budget is None else guard_budget
    replans = guard_budget.get('replans', 0)
    for index, segment in enumerate(segments, 1):
        if segmented:
            trace.append({'event': 'resource_route_segment_start',
                          'segment': index, 'segment_count': len(segments),
                          'segment_target': list(segment), 'final_target': list(target)})
            _persist_segment_trace(c, target, trace, 'segment_start', segment=index)
        try:
            while True:
                try:
                    if clearance_padding == .32 and obstacle_margin == 3.1:
                        _travel_once(c, segment, checkpoint, trace)
                    else:
                        _travel_once(c, segment, checkpoint, trace,
                                     clearance_padding=clearance_padding, obstacle_margin=obstacle_margin)
                    break
                except Unavailable as error:
                    if error.code != 'guard_displaced':
                        raise
                    error.evidence['replans'] = replans
                    if (not error.evidence.get('terminal_verified')
                            or not error.evidence.get('combat_confirmed')
                            or replans >= 2):
                        raise
                    _wait_guard_clear(c, checkpoint, error.evidence)
                    replans += 1
                    guard_budget['replans'] = replans
                    trace.append({'event': 'same_target_replan_after_guard',
                                  'attempt': replans, 'target': list(segment),
                                  **({'final_target': list(target), 'segment': index}
                                     if segmented else {})})
        except JobPaused as error:
            if segmented:
                trace.append({'event': 'resource_route_segment_stopped',
                              'segment': index, 'segment_target': list(segment),
                              'final_target': list(target), 'reason': str(error),
                              'route_code': 'checkpoint_paused'})
                _persist_segment_trace(c, target, trace, 'checkpoint_paused', segment=index)
            raise
        except Unavailable as error:
            if segmented:
                if error.code is None:
                    error.code = 'route_uncertain'
                    error.phase = 'waiting'
                error.evidence.update(final_target=list(target),
                                      segment_target=list(segment), segment=index,
                                      segment_count=len(segments))
                trace.append({'event': 'resource_route_segment_stopped',
                              'segment': index, 'segment_target': list(segment),
                              'final_target': list(target), 'reason': error.detail,
                              'route_code': error.code})
                _persist_segment_trace(c, target, trace, 'stopped', segment=index,
                                       route_code=error.code)
            raise
        if segmented:
            trace.append({'event': 'resource_route_segment_done',
                          'segment': index, 'segment_target': list(segment),
                          'final_target': list(target)})
            _persist_segment_trace(c, target, trace,
                                   'done' if index == len(segments) else 'segment_done',
                                   segment=index)


def _travel_once(c, target, checkpoint, trace, *, clearance_padding=.32, obstacle_margin=3.1):
    """Use inspected axis-aligned clear segments; never fly down through an unmined cap."""
    if (type(clearance_padding) not in (int, float) or type(obstacle_margin) not in (int, float)
            or not .32 <= clearance_padding <= 2.32 or not 3.1 <= obstacle_margin <= 6.1):
        raise ValueError('Flight planning margins are outside the bounded supported range')
    here = list(c.status()['pos'])
    if c.status().get('air_only_navigation_protocol',0)<2:
        raise Unavailable('当前 Kit 缺少仅走空气的材料导航接口，请更新后再开始')
    if math.hypot(target[0]-here[0], target[2]-here[2]) > DIRECT_ROUTE_LIMIT:
        raise Unavailable('资源区离当前控制点太远，需由发现路线分段接近', 'waiting')
    cruise = max(here[1], target[1])
    # Read the complete two-leg flight corridor before picking its height.
    # A ground-level depot must not make the next quarry route cross a roof.
    bend=[target[0],here[1],here[2]]
    for start,end in ((here,bend),(bend,target)):
        axis=0 if abs(start[0]-end[0])>=abs(start[2]-end[2]) else 2
        low=math.floor(min(start[axis],end[axis])-clearance_padding)
        high=math.floor(max(start[axis],end[axis])+clearance_padding)
        for base in range(low,high+1,32):
            lo=[math.floor(min(start[0],end[0])-clearance_padding),math.floor(min(here[1],target[1])),math.floor(min(start[2],end[2])-clearance_padding)]
            hi=[math.floor(max(start[0],end[0])+clearance_padding),319,math.floor(max(start[2],end[2])+clearance_padding)]
            lo[axis]=base;hi[axis]=min(high,base+31)
            observed=_scan(c,lo,hi,checkpoint)
            cruise=max(cruise,max((r['pos'][1]+obstacle_margin for r in observed if r.get('fluid') or not r.get('passable',False)),default=cruise))
    if cruise>=317:
        raise Unavailable('已观察航线上方没有足够净空，不穿过障碍',
                          code='route_geometry_blocked')
    points = [[here[0], cruise, here[2]], [target[0], cruise, here[2]],
              [target[0], cruise, target[2]], list(target)]
    for point in points:
        state = c.status(); _safe(state); start = state['pos']
        if math.dist(start, point) <= .3:
            continue
        low = [math.floor(min(start[0], point[0])-.32), math.floor(min(start[1], point[1])),
               math.floor(min(start[2], point[2])-.32)]
        high = [math.floor(max(start[0], point[0])+.32), math.floor(max(start[1], point[1])+1.81),
                math.floor(max(start[2], point[2])+.32)]
        rows = _scan(c, low, high, checkpoint)
        blocked=[row for row in rows if blocks_route(row,state,point)]
        if blocked:
            # Keep the exact bounded reason, so future diagnoses need not
            # reconstruct a failed route from every scan reply.
            if getattr(c,'out',None):
                try:write_json(Path(c.out)/'route-blocked-latest.json',
                               {'world_session':getattr(c,'world',None),'from':list(start),'target':list(point),
                                'on_ground':state.get('on_ground'),'flight':state.get('flight'),
                                'velocity':state.get('velocity'),'blocking_cells':blocked[:8]})
                except (OSError,ValueError,TypeError):pass
            raise Unavailable('资源区入口或航线仍有障碍；不会穿越地层或挖开区域外建筑',
                              code='route_geometry_blocked')
        checkpoint()
        reply = c.request('navigate', target=point, arrival=.25, air_only=True, seconds=90)
        if reply.get('phase')!='done':
            # Read-only incident capture remains valid even if combat reduced
            # health; the next mutation still passes the ordinary safety gate.
            current=c.status()
            vertical=abs(point[1]-start[1])>.5
            drift=(math.hypot(current['pos'][0]-start[0],current['pos'][2]-start[2]) if vertical
                   else abs(current['pos'][2]-start[2]) if abs(point[0]-start[0])>.5
                   else abs(current['pos'][0]-start[0]))
            changed=reply.get('detail')=='air-only path changed; no blocks were excavated'
            request_id=getattr(c,'last',None)
            terminal=_terminal_guard_route(c,reply,current)
            combat=_combat_displacement(current)
            if changed and (combat or drift>.75):
                code='guard_displaced'
            elif changed:
                geometry=(current.get('health',0)>=19 and not current.get('guard_busy')
                          and terminal and _confirmed_route_obstacle(c,low,high,current,point))
                code='route_geometry_blocked' if geometry else 'route_uncertain'
            else:
                code=None
            evidence = {'request_id': request_id,
                        'terminal_verified': terminal,
                        'combat_confirmed': combat,
                        'world_session': c.world, 'target': list(point)}
            trace.append({'target':point,'actual':current['pos'],'phase':reply.get('phase'),
                          'reason':reply.get('detail'),'route_code':code,
                          'terminal_verified':evidence['terminal_verified'],
                          'request_id':evidence['request_id'],
                          'combat_confirmed':evidence['combat_confirmed'],
                          'observed_at':current.get('time')})
            raise Unavailable('前往资源区的空气航线未确认：'+str(reply.get('detail')),
                              'waiting',code=code,evidence=evidence)
        from .navigation import settled_state
        actual = settled_state(c,point,.55); _safe(actual)
        trace.append({'target': point, 'actual': actual['pos'], 'phase': reply.get('phase')})
        if math.dist(actual['pos'], point) > .55:
            raise Unavailable('前往资源区的安全路线没有到达，保留本次位置', 'waiting')


def _windows(low, high, sand=False):
    width, depth = (16, 12) if sand else (6, 18)
    for top in range(high[1], low[1]-1, -depth):
        bottom = max(low[1], top-depth+1)
        chunk_top = top
        if top == bottom:
            if top < high[1]:chunk_top += 1
            else:continue
        for x in range(low[0], high[0]+1, width):
            for z in range(low[2], high[2]+1, width):
                yield [x, bottom, z], [min(x+width-1, high[0]), chunk_top, min(z+width-1, high[2])]


def _danger(row, rock):
    name = block_id(row)
    return (row.get('fluid') or row.get('block_entity') or name in
            {'minecraft:water', 'minecraft:lava', 'minecraft:fire', 'minecraft:soul_fire',
             'minecraft:cobweb', 'minecraft:powder_snow', 'minecraft:pointed_dripstone'}
            or rock and (name in FALLING or name.endswith('_concrete_powder')))


def _rock_observation(rows, low, high, item, *, allow_cleared=False):
    cells = {tuple(row['pos']): row for row in rows}
    inside = [row for p, row in cells.items() if in_box(p, low, high)]
    if any(block_id(row) not in NATURAL | LIGHTS | AIR for row in inside):return None
    if any(block_id(row) == 'minecraft:raw_iron_block'
           and not RAW_IRON_BLOCK_MIN_Y <= row['pos'][1] <= RAW_IRON_BLOCK_MAX_Y
           for row in inside):return None
    buffer = [row for p, row in cells.items() if all(low[i]-(2 if i == 1 else 3) <= p[i]
              <= high[i]+(2 if i == 1 else 3) for i in range(3))]
    if any(_danger(row, True) for row in buffer):return None
    remaining = sum(block_id(row) in NATURAL for row in inside)
    # Lower slices remove the old floor of a cleared upper slice. Fresh clear
    # air is traversable without that floor, but hazards and collision evidence
    # must still be checked before accepting it as an entrance.
    if allow_cleared and remaining == 0:
        if any(row.get('passable') is not True for row in inside):return None
        return {'available': 0, 'remaining': 0}
    if any(not cells.get((x, low[1]-1, z), {}).get('solid')
           for x in range(low[0], high[0]+1) for z in range(low[2], high[2]+1)):return None
    return {'available': sum(block_id(row) in ROCK_SOURCES[item] for row in inside),
            'remaining': remaining}


def rock_choice(rows, low, high, item, player, required_entry=None):
    """Conservative Python candidate filter; the native op rechecks every cell before mining."""
    best = None
    widths = sorted({min(6, high[0]-low[0]+1, high[2]-low[2]+1), 4, 2}, reverse=True)
    for width in widths:
        if width > min(high[0]-low[0]+1, high[2]-low[2]+1):continue
        for depth in sorted({min(18, high[1]-low[1]+1), 10, 6, 2}, reverse=True):
            if not 2 <= depth <= high[1]-low[1]+1:continue
            bottom = high[1]-depth+1
            for x in range(low[0], high[0]-width+2):
                for z in range(low[2], high[2]-width+2):
                    lo, hi = [x, bottom, z], [x+width-1, high[1], z+width-1]
                    if required_entry and not all(lo[i] <= required_entry['min'][i] <= required_entry['max'][i] <= hi[i] for i in (0, 2)):continue
                    observed = _rock_observation(rows, lo, hi, item)
                    if observed is None:continue
                    available = observed['available']
                    if not available:continue
                    remaining = observed['remaining']
                    score = (available, -math.hypot(x+width/2-player[0], z+width/2-player[2]))
                    if best is None or score > best[0]:
                        best = (score, {'min': lo, 'max': hi, 'available': available, 'remaining': remaining})
    return best[1] if best else None


def _key(item, low, high):
    return hashlib.sha256(json.dumps([item, low, high], separators=(',', ':')).encode()).hexdigest()[:24]


def _route_failure_path(c, profile, item):
    root=getattr(c,'root',None)
    server,dimension=profile.get('server'),profile.get('dimension')
    if root is None or not isinstance(server,str) or not isinstance(dimension,str):return None
    return _resource_ledger_scope_path(Path(root).parent/'material-resource-ledger',
                                       server,dimension,item)


def _route_region_key(region):
    return hashlib.sha256(json.dumps([region.get('min'),region.get('max'),
        region.get('access_shaft')],sort_keys=True,separators=(',', ':')).encode()).hexdigest()[:24]


def _validate_resource_ledger(ledger, item):
    if not isinstance(ledger,dict) or ledger.get('schema')!=1 or ledger.get('item')!=item:
        raise Unavailable('跨任务资源航线记录格式不符；停止并保留现场')
    if not isinstance(ledger.get('tiles'),dict):
        raise Unavailable('跨任务资源发现记录格式损坏；停止并保留现场')
    if any(not isinstance(key,str) or not isinstance(entry,dict)
           for key,entry in ledger['tiles'].items()):
        raise Unavailable('跨任务资源发现分区记录损坏；停止并保留现场')
    for key in ('history','extensions','extension_history','route_failure_history'):
        if key in ledger and not isinstance(ledger[key],dict):
            raise Unavailable('跨任务资源发现记录格式损坏；停止并保留现场')
    for key in ('history','extension_history','route_failure_history'):
        if any(not isinstance(entries,list) for entries in ledger.get(key,{}).values()):
            raise Unavailable('跨任务资源发现记录格式损坏；停止并保留现场')
    if 'route_failures' in ledger and not isinstance(ledger['route_failures'],dict):
        raise Unavailable('跨任务资源航线记录格式损坏；停止并保留现场')
    for key,record in ledger.get('route_failures',{}).items():
        observed=record.get('observed_at') if isinstance(record,dict) else None
        if (not isinstance(key,str) or not isinstance(record,dict)
                or record.get('code') not in ('guard_displaced','route_geometry_blocked','route_uncertain')
                or not isinstance(record.get('reason'),str)
                or type(observed) not in (int,float) or not math.isfinite(observed)):
            raise Unavailable('跨任务资源航线记录内容损坏；停止并保留现场')


def _resource_ledger(path, item, *, create=False):
    """Load a discovery ledger and durably add the route-failure namespace.

    Discovery ledgers predate route holds.  A missing namespace is therefore a
    schema-1 compatibility case, while an existing non-dict value is corruption
    and must never be replaced silently.
    """
    path=Path(path)
    existed=path.exists()
    if not existed:
        return ({'schema':1,'item':item,'tiles':{},'route_failures':{}}
                if create else None)
    if path.is_symlink() or path.stat().st_size>16*1024*1024:
        raise Unavailable('跨任务资源记录路径不安全或超出有界大小')
    ledger=json.loads(path.read_text())
    _validate_resource_ledger(ledger,item)
    if 'route_failures' not in ledger:
        ledger['route_failures']={}
        write_json(path,ledger)
    return ledger


def _resource_ledger_scope_path(directory, server, dimension, item):
    """Use normalized server identity and migrate only equivalent alias ledgers."""
    directory=Path(directory)
    canonical_server=server_key(server)
    canonical_scope=hashlib.sha256((canonical_server+'|'+dimension+'|'+item).encode()).hexdigest()[:20]
    canonical=directory/(canonical_scope+'.json')
    raw_server=str(server)
    aliases={raw_server,canonical_server}
    normalized_raw=raw_server.lower()
    if (normalized_raw.endswith(':25565') or ':' not in canonical_server
            or canonical_server.startswith('[') and canonical_server.endswith(']')):
        aliases.add(canonical_server+':25565')
    candidates=[]
    for alias in aliases:
        scope=hashlib.sha256((alias+'|'+dimension+'|'+item).encode()).hexdigest()[:20]
        path=directory/(scope+'.json')
        if path!=canonical and path.exists() and path not in candidates:candidates.append(path)
    if not candidates:return canonical
    loaded=[]
    if canonical.exists():loaded.append((canonical,json.loads(canonical.read_text())))
    loaded.extend((path,json.loads(path.read_text())) for path in candidates)
    for _,ledger in loaded:_validate_resource_ledger(ledger,item)
    normalized=[(path,{**ledger,'route_failures':ledger.get('route_failures',{})})
                for path,ledger in loaded]
    reference=normalized[0][1]
    if any(ledger!=reference for _,ledger in normalized[1:]):
        raise Unavailable('同一服务器存在冲突的资源发现记录；停止并保留全部现场')
    if canonical.exists():
        for path in candidates:path.unlink()
        return canonical
    directory.mkdir(parents=True,exist_ok=True)
    write_json(canonical,reference)
    for path in candidates:path.unlink()
    return canonical


def route_failure(c, profile, item, region):
    """A same-session route hold, not proof that the resource itself was depleted."""
    path=_route_failure_path(c,profile,item)
    if path is None or not path.exists():return None
    ledger=_resource_ledger(path,item)
    record=ledger['route_failures'].get(_route_region_key(region))
    return record if isinstance(record,dict) and record.get('world_session')==c.world \
        and record.get('region')=={key:region.get(key) for key in ('min','max','access_shaft')} else None


def _recover_parked_bobby_rejection(root,current,item,profile,out,path,ledger):
    """Use one exact prior control directory before the active-route gate."""
    if item not in ('minecraft:snow','minecraft:snow_block','minecraft:snowball'):
        return False
    from .bobby_snow_route import (LEDGER_KEY as BOBBY_LEDGER_KEY,
        UNLOADED_AIR_ONLY_REJECTION,recover_parked_rejection_files)
    bobby=ledger.get(BOBBY_LEDGER_KEY);route=(bobby.get('active_route')
        if isinstance(bobby,dict) else None)
    segment=route.get('current_segment') if isinstance(route,dict) else None
    if (not isinstance(route,dict) or route.get('state')!='outbound_uncertain'
            or not isinstance(segment,dict) or segment.get('index')!=1
            or segment.get('direction')!='outbound'
            or segment.get('state')!='uncertain'
            or route.get('outbound_confirmed')!=0 or route.get('return_confirmed')!=0
            or route.get('recent_segments')!=[]):return False
    job_root=Path(out).parent;jobs_root=Path(root)/'material-jobs'
    if (job_root.is_symlink() or not job_root.is_dir()
            or jobs_root.is_symlink() or not jobs_root.is_dir()):return False
    task=route.get('task_session')
    manifests=list(jobs_root.glob(
        'material-job-*/control-*/run-manifest-'+str(task)+'.json'))
    if len(manifests)>2:return False
    controls=[]
    for manifest in manifests:
        directory=manifest.parent;job=directory.parent
        if (manifest.is_symlink() or directory.is_symlink() or job.is_symlink()
                or not directory.is_dir() or not job.is_dir()
                or job.parent!=jobs_root):continue
        controls.append((directory,manifest))
    candidates=[]
    for directory,manifest in controls:
        events=directory/'events.jsonl';finish=directory/'stock-safety.json'
        try:
            if (manifest.is_symlink() or not manifest.is_file()
                    or manifest.stat().st_size>1024*1024):continue
            meta=json.loads(manifest.read_text())
            if (not isinstance(meta,dict) or meta.get('task_session')!=task
                    or meta.get('world_session')!=route.get('world_session')
                    or meta.get('dimension')!=profile.get('dimension')):continue
        except (OSError,ValueError,TypeError,json.JSONDecodeError):continue
        request_id=segment.get('request_id')
        files=([directory/('movement-failure-'+request_id+'.json')]
               if isinstance(request_id,str) and request_id else
               sorted(directory.glob('movement-failure-*.json')))
        if len(files)>64:return False
        for movement in files:
            try:
                if movement.is_symlink() or not movement.is_file() or movement.stat().st_size>2*1024*1024:
                    continue
                observed=json.loads(movement.read_text())
                params=observed.get('params') if isinstance(observed,dict) else None
                if (observed.get('op')!='navigate'
                        or observed.get('detail')!=UNLOADED_AIR_ONLY_REJECTION
                        or not isinstance(params,dict) or params.get('air_only') is not True
                        or params.get('target')!=segment.get('target')
                        or observed.get('terminal_pos')!=segment.get('from')):continue
            except (OSError,ValueError,TypeError,json.JSONDecodeError):continue
            if events.is_file() and finish.is_file() and not events.is_symlink() and not finish.is_symlink():
                candidates.append((movement,events,finish))
    if len(candidates)!=1:return False
    class ParkedScope:
        world=current.get('world_session')
        def status(self):return current
    try:
        receipt=recover_parked_rejection_files(
            ParkedScope(),path,*candidates[0])
        fresh=_resource_ledger(path,item)
        ledger.clear();ledger.update(fresh)
        write_json(job_root/'bobby-route-auto-recovery.json',{
            'schema':1,'world_session':current.get('world_session'),
            'route_id':receipt['route_id'],'request_id':receipt['request_id'],
            'state':receipt['state'],'moved':False})
        return True
    except (OSError,RuntimeError,ValueError,TypeError,KeyError,AttributeError,
            json.JSONDecodeError):
        return False


def held_resource_route(root, world, item, profile, out, current=None):
    """Read combat/unknown route holds before a backend opens any lease or box."""
    class Scope:
        pass
    scope=Scope();scope.root=Path(root);scope.world=world
    regions=[r for r in profile.get('resource_regions',[]) if r.get('item')==item]
    try:
        discovery_path=_route_failure_path(scope,profile,item)
        if discovery_path is not None and discovery_path.exists():
            discovered=_resource_ledger(discovery_path,item)
            if isinstance(current,dict):
                _recover_parked_bobby_rejection(
                    root,current,item,profile,out,discovery_path,discovered)
            remote_states=[]
            if item in ('minecraft:snow','minecraft:snow_block','minecraft:snowball'):
                from .seed_snow_search import ledger_state as seed_route_ledger
                from .bobby_snow_route import ledger_state as bobby_route_ledger
                remote_states=(seed_route_ledger(discovered),
                    bobby_route_ledger(discovered,profile['server'],profile['dimension']))
            for scoped in remote_states:
                active=scoped.get('active_route') if isinstance(scoped,dict) else None
                if isinstance(active,dict):
                    return {'code':'route_uncertain',
                            'reason':'远程雪地路线尚未闭环；不开启租约或整理装备'}
            tile_hold=discovered.get('guard_hold')
            if tile_hold is not None:
                if not isinstance(tile_hold,dict):
                    return {'code':'route_uncertain','reason':'资源发现路线暂停记录损坏'}
                if tile_hold.get('world_session')==world:
                    code=tile_hold.get('code')
                    return {'code':code if code in ('guard_displaced','route_uncertain')
                            else 'route_uncertain','reason':tile_hold.get('reason')}
    except (OSError,RuntimeError,ValueError,TypeError,AttributeError,Unavailable):
        return {'code':'route_uncertain','reason':'资源发现记录读取失败'}
    local=Path(out)/('acquisition-'+item.split(':')[-1]+'.json')
    if local.exists():
        try:
            ledger=json.loads(local.read_text())
            if (ledger.get('schema')!=1 or ledger.get('world_session')!=world
                    or ledger.get('item')!=item or not isinstance(ledger.get('visited'),dict)):
                return {'code':'route_uncertain','reason':'采集路线记录与当前世界不符'}
            keys={_route_region_key(region) for region in regions}
            for entry in ledger['visited'].values():
                if (isinstance(entry,dict) and entry.get('state')=='route_hold'
                        and entry.get('world_session')==world
                        and entry.get('region_key') in keys
                        and entry.get('route_code') in
                        ('guard_displaced','route_geometry_blocked','route_uncertain')):
                    return {'code':entry['route_code'],'reason':entry.get('reason')}
        except (OSError,ValueError,TypeError,AttributeError):
            return {'code':'route_uncertain','reason':'采集路线记录读取失败'}
    for region in regions:
        try:
            held=route_failure(scope,profile,item,region)
        except (Unavailable,OSError,ValueError,TypeError,AttributeError):
            return {'code':'route_uncertain','reason':'资源航线记录读取失败'}
        if held and held.get('code') in ('guard_displaced','route_geometry_blocked','route_uncertain'):
            return held
    return None


def record_route_failure(c, profile, item, region, code, detail, target,
                         evidence=None, state_hint=None):
    if code not in ('guard_displaced','route_geometry_blocked','route_uncertain'):return
    path=_route_failure_path(c,profile,item)
    if path is None:return
    ledger=_resource_ledger(path,item,create=True)
    state=state_hint if isinstance(state_hint,dict) else c.status()
    observed=state.get('time')
    if type(observed) not in (int,float) or not math.isfinite(observed):
        raise Unavailable('当前资源航线观察时间无效；停止且不写入暂停记录')
    record={'world_session':c.world,'region':{key:region.get(key) for key in ('min','max','access_shaft')},
            'code':code,'reason':detail,'target':list(target),'player_pos':list(state['pos']),
            'observed_at':observed,'guard_busy':state.get('guard_busy') is True,
            'route_evidence':evidence if isinstance(evidence,dict) else {}}
    failures=ledger.setdefault('route_failures',{})
    if not isinstance(failures,dict):raise Unavailable('跨任务资源航线记录格式损坏；停止并保留现场')
    key=_route_region_key(region)
    if key in failures:ledger.setdefault('route_failure_history',{}).setdefault(key,[]).append(failures[key])
    failures[key]=record;path.parent.mkdir(parents=True,exist_ok=True);write_json(path,ledger)


def _paused_guard_hold(c, ledger, path, region, low, high, target, trace,
                       detail, profile, item, previous=None, access=False,
                       checkpoint_paused=True, route_evidence=None):
    """Preserve a proved or uncertain combat stop before JobPaused escapes."""
    guard=next((row for row in reversed(trace)
                if row.get('route_code')=='guard_displaced'),None)
    if guard is None:return False
    evidence={'request_id':guard.get('request_id'),
              'terminal_verified':guard.get('terminal_verified') is True,
              'combat_confirmed':guard.get('combat_confirmed') is True,
              'world_session':c.world,'target':guard.get('target'),
              'checkpoint_paused':checkpoint_paused,
              **(route_evidence if isinstance(route_evidence,dict) else {})}
    entry={'state':'route_hold','min':low,'max':high,
           'region_key':_route_region_key(region),'route_code':'guard_displaced',
           'reason':detail,'entry_target':list(target),
           'player_pos':guard.get('actual'),'world_session':c.world,
           'observed_at':guard.get('observed_at'),'route':trace,
           'route_evidence':evidence}
    if previous:
        entry['previous_attempts']=[*previous.get('previous_attempts',[]),
            {name:value for name,value in previous.items() if name!='previous_attempts'}]
    key=('access-' if access else '')+_key(item,low,high)
    ledger['visited'][key]=entry
    write_json(path,ledger)
    if profile is not None:
        hint={'pos':guard.get('actual'),'time':guard.get('observed_at'),
              'guard_busy':guard.get('combat_confirmed') is True}
        record_route_failure(c,profile,item,region,'guard_displaced',detail,
                             target,evidence,state_hint=hint)
    return True


def _clear_receipt(c, item, low, high, reply, state):
    """A stopped clear is known failure, not an unknown transaction or success."""
    receipt = reply.get('rock_quarry') or {}
    request_id = getattr(c, 'last', None)
    if (not request_id or receipt.get('id') != request_id
            or receipt.get('world_session') != c.world
            or receipt.get('item') != item or receipt.get('min') != low or receipt.get('max') != high
            or receipt.get('completion') != 'clear' or receipt.get('active') is not False
            or reply.get('phase') not in ('done', 'waiting', 'stopped', 'error')
            or receipt.get('phase') != reply.get('phase') or receipt.get('pending_blocks') != 0
            or any(state.get(k) for k in ('borer_active', 'chopping', 'navigating', 'native_material_busy'))):
        return None
    return receipt


def _access_shaft(c, region, choice, item, target, ledger, path, checkpoint, profile=None):
    access = region.get('access_shaft')
    if not access:return None
    low, high = _bounds(access, shaft=True);region_low, region_high = _bounds(region)
    if (region.get('source') != 'natural_survey' or type(region.get('surface_y')) is not int
            or high[1] != region['surface_y'] or low[1] != region_high[1]+1
            or high[0]-low[0] != 1 or high[2]-low[2] != 1
            or not all(region_low[i] <= low[i] <= high[i] <= region_high[i] for i in (0, 2))):
        raise Unavailable('入口竖井缺少自然地形授权或与资源区不相连')
    bottom = choice['max'][1]+1
    top = high[1]
    centre = [(low[0]+high[0]+1)/2, (low[2]+high[2]+1)/2]
    while top >= bottom:
        segment_low = [low[0], max(bottom, top-17), low[2]]
        segment_high = [high[0], top, high[2]]
        if segment_low[1] == top:
            if top < high[1]:segment_high[1] += 1  # Overlap already cleared, authorized air.
            else:segment_low[1] -= 1  # One cap layer plus the authorized quarry's top layer.
        rows = _scan(c, [segment_low[0]-3, segment_low[1]-2, segment_low[2]-3],
                     [segment_high[0]+3, segment_high[1]+2, segment_high[2]+3], checkpoint)
        state = c.status();_safe(state)
        observed = _rock_observation(rows, segment_low, segment_high, item, allow_cleared=True)
        if observed is None:raise Unavailable('入口竖井出现液体、沙砾、建材或缺少底部支撑，已停止并保留地形',code='unsafe_region')
        key = 'access-' + _key(item, segment_low, segment_high)
        previous = ledger['visited'].get(key, {})
        if previous.get('state') == 'inflight':
            raise Unavailable('入口竖井前次回执仍不确定，保留记录且不自动重放', 'waiting')
        if previous.get('state') == 'clear_stopped':
            raise Unavailable('入口竖井前次已确认受阻，需修复入口路线；不会重复启动同一采坑',
                              code='native_clear_stopped')
        if not observed['remaining']:
            ledger['visited'][key] = {**previous, 'state': 'clear_verified', 'min': segment_low, 'max': segment_high,
                                      'observed_at': state.get('time')};write_json(path, ledger)
        else:
            tool = _tool(state, 'pickaxe', observed['remaining']+32, no_silk=True)
            trace = []
            entry_target=[centre[0],segment_high[1]+3.1,centre[1]]
            try:
                _travel(c, entry_target, checkpoint, trace,
                        route_scope=_resource_route_scope(profile, region))
            except JobPaused as error:
                _paused_guard_hold(c,ledger,path,region,segment_low,segment_high,
                                   entry_target,trace,str(error),profile,item,
                                   previous,access=True)
                raise
            except Unavailable as error:
                if error.code in ('guard_displaced','route_uncertain','route_geometry_blocked'):
                    current=c.status()
                    entry={'state':'route_hold','min':segment_low,'max':segment_high,
                           'region_key':_route_region_key(region),
                           'route_code':error.code,'reason':error.detail,'entry_target':entry_target,
                           'player_pos':list(current['pos']),'world_session':c.world,
                           'observed_at':current.get('time'),'route':trace,
                           'route_evidence':error.evidence}
                    if previous:
                        entry['previous_attempts']=[*previous.get('previous_attempts',[]),
                            {name:value for name,value in previous.items() if name!='previous_attempts'}]
                    ledger['visited'][key]=entry;write_json(path,ledger)
                    if profile is not None:
                        record_route_failure(c,profile,item,region,error.code,error.detail,
                                             entry_target,error.evidence)
                raise
            # Combat may have displaced the actor during the original route.
            # Re-observe the same authorized segment before its first mine.
            fresh_rows = _scan(c, [segment_low[0]-3, segment_low[1]-2, segment_low[2]-3],
                               [segment_high[0]+3, segment_high[1]+2, segment_high[2]+3],
                               checkpoint)
            fresh_observed = _rock_observation(fresh_rows, segment_low, segment_high,
                                               item, allow_cleared=True)
            if (fresh_observed is None
                    or fresh_observed['remaining'] != observed['remaining']):
                raise Unavailable('清怪后原入口方块已改变，停下并重新核对原区域', 'waiting')
            _choose_tool(c, tool, checkpoint)
            from .quarry_vegetation import clear_entrance
            clear_entrance(c, region, segment_low, segment_high, checkpoint)
            entry = {'state': 'inflight', 'completion': 'clear', 'min': segment_low, 'max': segment_high,
                     'before': carried(c.status(), item), 'route': trace}
            if previous:
                entry['previous_attempts'] = [*previous.get('previous_attempts', []),
                    {key:value for key,value in previous.items() if key != 'previous_attempts'}]
            ledger['visited'][key] = entry;write_json(path, ledger);checkpoint()
            reply = c.request('rock_quarry_batch', min=segment_low, max=segment_high, item=item,
                              target_count=0, completion='clear', seconds=min(600, max(90, observed['remaining']*3)))
            after = c.status();_safe(after)
            receipt = _clear_receipt(c, item, segment_low, segment_high, reply, after)
            if receipt is None:
                raise Unavailable('竖井本段尚未完整确认清空，保留在途回执，不自动重放', 'waiting')
            verified = _scan(c, segment_low, segment_high, checkpoint)
            remaining = sum(block_id(row) in NATURAL for row in verified)
            if receipt.get('remaining_blocks') != remaining:
                raise Unavailable('竖井回执与重新扫描的剩余数量不一致，保留在途记录')
            if any(_danger(row, True) or block_id(row) not in NATURAL | LIGHTS | AIR for row in verified):
                raise Unavailable('竖井停止后的实际方块出现异常，保留在途记录')
            if (reply.get('phase') == 'waiting' and receipt.get('area_cleared') is False
                    and reply.get('detail') == CLEAR_RESUPPLY_DETAIL):
                entry.update(state='clear_resupply', after=carried(after, item), native=receipt,
                             native_detail=reply['detail'], remaining=remaining, observed_at=after.get('time'))
                write_json(path, ledger)
                raise Unavailable('入口竖井背包预留空间不足，已核对停止回执；卸下副产物后重新核验本段',
                                  'waiting', code='quarry_backpack_reserve')
            if remaining or reply.get('phase') != 'done' or receipt.get('area_cleared') is not True:
                entry.update(state='clear_stopped', after=carried(after, item), native=receipt,
                             remaining=remaining, observed_at=after.get('time'))
                write_json(path, ledger)
                raise Unavailable(f'入口竖井已停止，实际还剩 {remaining} 格；保留进度并等待修复入口路线',
                                  code='native_clear_stopped')
            if any(block_id(row) not in LIGHTS | AIR for row in verified):
                raise Unavailable('竖井清空回执与实际方块不一致，停止继续下降')
            entry.update(state='clear_verified', after=carried(after, item), native=receipt,
                         observed_at=after.get('time'));write_json(path, ledger)
            if carried(after, item) >= target:return centre
        top = segment_low[1]-1
    return centre


def acquire(c, item, target_count, profile, out, checkpoint):
    """Perform at most one native collection batch; the owner calls again while waiting.

    profile.resource_regions = [{item, min: [x,y,z], max: [x,y,z]}].
    Out must be a stable acquisition directory for this job. No AI or login is used.
    """
    if type(target_count) is not int or not 1 <= target_count <= 2304:
        raise ValueError('Acquisition target must be an absolute inventory total from 1 to 2304')
    from .snow_harvest import PRODUCTS as SNOW_PRODUCTS
    checkpoint(); initial = c.status(); before = carried(initial, item)
    out = Path(out); path = out / ('acquisition-' + item.split(':')[-1] + '.json')
    early_ledger=json.loads(path.read_text()) if path.exists() else None
    if early_ledger is not None and (early_ledger.get('world_session')!=c.world
                                     or early_ledger.get('item')!=item):
        return {'phase':'blocked','detail':'采集记录属于另一世界或物品，不能沿用旧位置'}
    pending_return=(early_ledger or {}).get('seed_return')
    if (item in SNOW_PRODUCTS and isinstance(pending_return,dict)
            and pending_return.get('state') in ('required','inflight','uncertain')):
        return {'phase':'waiting','code':'seed_return_pending',
                'detail':'雪地物品已完成但返航仍待核；不会凭库存直接完成或重放令牌'}
    bobby_return=(early_ledger or {}).get('bobby_return')
    if (item in SNOW_PRODUCTS and isinstance(bobby_return,dict)
            and bobby_return.get('state') in ('required','inflight','uncertain')
            and not hasattr(c,'bobby_snow_route_id')):
        return {'phase':'waiting','code':'bobby_return_pending',
                'detail':'Bobby 雪地物品已完成但分段返航待核；不凭库存假完成'}
    seed_expedition=(early_ledger or {}).get('seed_expedition')
    configured_seed_route=any(region.get('item')==item
        and isinstance(region.get('seed_snow_route'),dict)
        for region in profile.get('resource_regions',[]))
    if (item in SNOW_PRODUCTS and isinstance(seed_expedition,dict)
            and seed_expedition.get('state') in
                ('active','return_required','return_inflight','return_uncertain')
            and not hasattr(c,'snow_expedition_token')):
        return {'phase':'waiting','code':'seed_route_recovery_required',
                'detail':'雪地长途路线仍在外站，但本进程没有可重放的明文令牌；停止等待人工核对'}
    if (item in SNOW_PRODUCTS and configured_seed_route
            and not hasattr(c,'snow_expedition_token')
            and (not isinstance(seed_expedition,dict)
                 or seed_expedition.get('state')!='home_arrived')):
        return {'phase':'waiting','code':'seed_route_recovery_required',
                'detail':'雪地资源区来自长途候选，但没有已确认返家的本地记录或当前令牌；不直接完成'}
    bobby_expedition=(early_ledger or {}).get('bobby_expedition')
    if (item in SNOW_PRODUCTS and isinstance(bobby_expedition,dict)
            and bobby_expedition.get('state') in
                ('active','return_required','return_inflight','return_uncertain')
            and not hasattr(c,'bobby_snow_route_id')):
        return {'phase':'waiting','code':'bobby_route_recovery_required',
                'detail':'Bobby 雪地分段路线在进程重启后失去临时控制权；停止等待核对'}
    if before >= target_count and not (item in SNOW_PRODUCTS
                                       and (hasattr(c,'snow_expedition_token')
                                            or hasattr(c,'bobby_snow_route_id'))):
        return {'phase': 'done', 'detail': '背包现物已经达到目标', 'before': before, 'after': before}
    if (item not in ROCK_SOURCES and item not in LOGS
            and item not in ('minecraft:sand', 'minecraft:dirt', 'minecraft:grass_block')
            and item not in SNOW_PRODUCTS):
        return {'phase': 'blocked', 'detail': '此原料尚无直接采集适配器：' + item}
    if item == 'minecraft:grass_block' and (type(initial.get('grass_block_tool_protocol')) is not int
                                             or initial['grass_block_tool_protocol'] < 1):
        return {'phase': 'blocked', 'detail': '当前 Kit 主包缺少草方块精准采集工具核验；请先更新主包'}
    out.mkdir(parents=True, exist_ok=True)
    ledger = early_ledger or {'schema': 1, 'world_session': c.world, 'item': item, 'visited': {}}
    if ledger.get('world_session') != c.world or ledger.get('item') != item:
        return {'phase': 'blocked', 'detail': '采集记录属于另一世界或物品，不能沿用旧位置'}
    if any(v.get('state') == 'inflight' for v in ledger['visited'].values()):
        return {'phase': 'blocked', 'detail': '前次采集回执不确定，需先核验原生任务与物品，不能重放'}
    seed_region=next((region for region in profile.get('resource_regions',[])
                      if region.get('item')==item
                      and isinstance(region.get('seed_snow_route'),dict)),None)
    if item in SNOW_PRODUCTS and seed_region is not None and hasattr(c,'snow_expedition_token'):
        route=seed_region['seed_snow_route']
        ledger['seed_expedition']={'state':'active','world_session':c.world,
            'route_id':route.get('route_id'),'candidate':route.get('candidate')}
        write_json(path,ledger)
    bobby_region=next((region for region in profile.get('resource_regions',[])
                       if region.get('item')==item
                       and isinstance(region.get('bobby_snow_route'),dict)
                       and region['bobby_snow_route'].get('route_id')==
                           getattr(c,'bobby_snow_route_id',None)),None)
    if item in SNOW_PRODUCTS and bobby_region is not None and hasattr(c,'bobby_snow_route_id'):
        route=bobby_region['bobby_snow_route']
        ledger['bobby_expedition']={'state':'active','world_session':c.world,
            'route_id':route.get('route_id'),'chunk':route.get('chunk'),
            'region_file':route.get('region_file'),
            'fingerprint':route.get('fingerprint')}
        write_json(path,ledger)
        from .bobby_snow_route import mark_harvesting
        mark_harvesting(c,Path(c.bobby_snow_resource_path),
                        json.loads(Path(c.bobby_snow_resource_path).read_text()))
    try:
        _safe(initial)
        if room_for_item(initial, item) < target_count-before:
            raise Unavailable('当前背包容纳不了本次总数，请先卸货或减少本批目标')
        regions = [r for r in profile.get('resource_regions', []) if r.get('item') == item]
        if item in SNOW_PRODUCTS:
            if hasattr(c,'bobby_snow_route_id'):
                regions=[r for r in regions if isinstance(r.get('bobby_snow_route'),dict)
                         and r['bobby_snow_route'].get('route_id')==c.bobby_snow_route_id]
            else:
                # A past far-cache region is evidence, not standing permission
                # for an arbitrary direct flight in a later process.
                regions=[r for r in regions if not isinstance(r.get('bobby_snow_route'),dict)]
        if not regions:
            return {'phase':'blocked','code':'no_safe_candidate',
                    'detail':'没有当前进程可用的已授权资源区域：'+item}
        for region in regions:_bounds(region)
        # A previous combat stop owns the original route for this session.
        # Check all regions before scanning/mining the first one, otherwise a
        # held second region could silently be replaced by the first region.
        for region in regions:
            region_key=_route_region_key(region)
            pending=next((entry for entry in ledger['visited'].values()
                          if entry.get('state')=='route_hold'
                          and entry.get('world_session')==c.world
                          and entry.get('region_key')==region_key
                          and entry.get('route_code') in
                          ('guard_displaced','route_geometry_blocked','route_uncertain')),None)
            if pending:
                return {'phase':'waiting','code':pending['route_code'],
                        'detail':'原资源区路线已暂停；不切换其他资源区'}
            held_route=route_failure(c,profile,item,region)
            if held_route is not None and held_route.get('code') in (
                    'guard_displaced','route_geometry_blocked','route_uncertain'):
                return {'phase':'waiting','code':held_route['code'],
                        'detail':'原资源区未确认路线待核；不自动重试或当作矿耗尽'}
        ledger['resource_regions']=[{key:region[key] for key in
                                    ('item','min','max','source','surface_y','access_shaft') if key in region}
                                   for region in regions]
        write_json(path,ledger)
        if item in ('minecraft:dirt', 'minecraft:grass_block'):
            from .dirt_harvest import acquire_surface_soil
            return acquire_surface_soil(c, item, target_count, profile, regions, path, ledger, checkpoint)
        if item in SNOW_PRODUCTS:
            from .snow_harvest import acquire_surface_snow, _return_remote_home
            try:
                return acquire_surface_snow(c,item,target_count,profile,regions,
                                            path,ledger,checkpoint)
            except Unavailable:
                stopped=c.status()
                can_return=((hasattr(c,'snow_expedition_token')
                             or hasattr(c,'bobby_snow_route_id'))
                    and stopped.get('health',0)>=18 and stopped.get('food',0)>=8
                    and stopped.get('guard_armed') and stopped.get('guard_pve_only')
                    and stopped.get('flight') and not stopped.get('under_water')
                    and not stopped.get('manual_movement')
                    and not (stopped.get('safety_hold') or {}).get('active'))
                if can_return:
                    try:_return_remote_home(c,checkpoint,path,ledger,
                                            reason='safe_collection_stop')
                    except Unavailable as return_error:
                        raise Unavailable(str(return_error),'waiting',
                                          code='route_uncertain') from return_error
                raise
        if item in LOGS:
            return _wood(c, item, target_count, regions, out, path, ledger, checkpoint, profile)
        sand = item == 'minecraft:sand'
        _tool(initial, 'shovel' if sand else 'pickaxe', 33, no_silk=not sand)
        if initial.get('quarry_protocol' if sand else 'rock_quarry_protocol', 0) < 1:
            raise Unavailable('当前 Kit 缺少所需原生采坑接口，请更新后再开始')
        scans = 0
        for region in regions:
            region_key=_route_region_key(region)
            local_holds=[entry for entry in ledger['visited'].values()
                         if entry.get('state')=='route_hold' and entry.get('world_session')==c.world
                         and entry.get('region_key')==region_key]
            pending=next((entry for entry in local_holds if entry.get('route_code')
                          in ('guard_displaced','route_geometry_blocked','route_uncertain')),None)
            if pending:
                return {'phase':'waiting','code':pending['route_code'],
                        'detail':'原资源区路线已暂停；没有切换其他资源区或重复未知请求'}
            if local_holds:
                continue
            held_route=route_failure(c,profile,item,region)
            if held_route is not None:
                if held_route['code'] in ('guard_displaced','route_geometry_blocked','route_uncertain'):
                    return {'phase':'waiting','code':held_route['code'],
                            'detail':'原资源区未确认路线待核；不自动重试或当作矿耗尽'}
                ledger.setdefault('route_holds',{})[region_key]={'state':'same_session_route_hold',
                    'code':held_route['code'],'reason':held_route['reason'],
                    'world_session':c.world,'observed_at':held_route['observed_at']}
                write_json(path,ledger)
                continue
            low, high = _bounds(region)
            for lo, hi in _windows(low, high, sand):
                key = _key(item, lo, hi)
                old = ledger['visited'].get(key, {})
                if old.get('state') in ('empty_or_unsafe', 'no_progress'):continue
                if scans >= MAX_SCANS:
                    return {'phase': 'waiting', 'detail': '本轮已核验 12 个小区域，下一轮从未扫描位置继续'}
                rows = _scan(c, [lo[0]-3, lo[1]-2, lo[2]-3], [hi[0]+3, hi[1]+2, hi[2]+3], checkpoint); scans += 1
                state = c.status(); _safe(state)
                choice = choose_quarry(rows, lo, hi, state['pos']) if sand else rock_choice(rows, lo, hi, item, state['pos'],region.get('access_shaft'))
                if choice is None:
                    ledger['visited'][key] = {'state': 'empty_or_unsafe', 'min': lo, 'max': hi, 'observed_at': state.get('time')}
                    write_json(path, ledger); continue
                amount = min(target_count-carried(state, item), choice['sand'] if sand else choice['available'], 1024 if sand else 648)
                tool = _tool(state, 'shovel' if sand else 'pickaxe', min(amount, 256)+32 if sand else choice['remaining']+32, no_silk=not sand)
                try:
                    entry_centre = _access_shaft(c,region,choice,item,target_count,ledger,path,checkpoint,profile) if not sand else None
                except Unavailable as error:
                    if error.code!='unsafe_region':raise
                    ledger['visited'][key]={'state':'empty_or_unsafe','min':lo,'max':hi,'reason':error.detail}
                    write_json(path,ledger);continue
                if entry_centre:
                    state=c.status();_safe(state)
                    if carried(state,item)>=target_count:
                        return {'phase':'done','detail':'开通已授权入口时，背包现物已达到采集目标',
                                'before':before,'after':carried(state,item),'gained':carried(state,item)-before}
                    # Access may have consumed one authorized cap layer or produced requested drops.
                    rows=_scan(c,[choice['min'][0]-3,choice['min'][1]-2,choice['min'][2]-3],
                               [choice['max'][0]+3,choice['max'][1]+2,choice['max'][2]+3],checkpoint)
                    fresh=_rock_observation(rows,choice['min'],choice['max'],item)
                    if fresh is None or not fresh['available']:raise Unavailable('入口完成后资源候选已变化，停止并重新规划')
                    amount=min(target_count-carried(state,item),fresh['available'],648)
                    tool=_tool(state,'pickaxe',fresh['remaining']+32,no_silk=True)
                trace = []
                target = [entry_centre[0] if entry_centre else (choice['min'][0]+choice['max'][0]+1)/2, choice['max'][1]+3.1,
                          entry_centre[1] if entry_centre else (choice['min'][2]+choice['max'][2]+1)/2]
                # Standing above an unmined cap is not an entrance to a lower
                # bounded area: AREA may not remove that outside-region roof.
                if any(math.floor(target[0]-.32) <= row['pos'][0] <= math.floor(target[0]+.32)
                       and math.floor(target[2]-.32) <= row['pos'][2] <= math.floor(target[2]+.32)
                       and choice['max'][1] < row['pos'][1] <= target[1]+1.8
                       and (row.get('fluid') or not row.get('passable', False)) for row in rows):
                    raise Unavailable('采坑入口仍有上覆地层，不能在授权采坑之外开挖入口')
                try:
                    _travel(c, target, checkpoint, trace,
                            route_scope=_resource_route_scope(profile, region))
                except JobPaused as error:
                    _paused_guard_hold(c,ledger,path,region,lo,hi,target,trace,
                                       str(error),profile,item,old)
                    raise
                except Unavailable as error:
                    if error.code in ('guard_displaced','route_uncertain','route_geometry_blocked'):
                        current=c.status()
                        ledger['visited'][key]={'state':'route_hold','min':lo,'max':hi,
                            'region_key':region_key,'route_code':error.code,'reason':error.detail,
                            'entry_target':target,'player_pos':list(current['pos']),
                            'world_session':c.world,'observed_at':current.get('time'),'route':trace,
                            'route_evidence':error.evidence}
                        write_json(path,ledger)
                        record_route_failure(c,profile,item,region,error.code,error.detail,
                                             target,error.evidence)
                    raise
                # A recovered route proves travel only. Verify the original
                # natural quarry window again before writing any mine intent.
                fresh_rows=_scan(c,[lo[0]-3,lo[1]-2,lo[2]-3],
                                 [hi[0]+3,hi[1]+2,hi[2]+3],checkpoint)
                fresh_choice=(choose_quarry(fresh_rows,lo,hi,c.status()['pos']) if sand
                              else rock_choice(fresh_rows,lo,hi,item,c.status()['pos'],
                                               region.get('access_shaft')))
                if (fresh_choice is None or fresh_choice['min']!=choice['min']
                        or fresh_choice['max']!=choice['max']):
                    raise Unavailable('清怪后原采坑候选改变，暂停并从原区域重扫', 'waiting')
                _choose_tool(c, tool, checkpoint)
                before = carried(c.status(), item)
                entry = {**choice, 'state': 'inflight', 'before': before, 'amount': amount, 'route': trace}
                if old.get('native_detail') == CLEAR_RESUPPLY_DETAIL and old.get('state') == 'progress':
                    entry['previous_attempts'] = [*old.get('previous_attempts', []),
                        {name:value for name,value in old.items() if name != 'previous_attempts'}]
                ledger['visited'][key] = entry; write_json(path, ledger)
                checkpoint()
                reply = c.request('quarry_batch' if sand else 'rock_quarry_batch',
                                  min=choice['min'], max=choice['max'], item=item, target_count=amount,
                                  **({} if sand else {'completion': 'collect'}), seconds=min(600, max(60, amount*3)))
                after = c.status(); _safe(after)
                return _receipt(c, item, target_count, before, after, reply, entry, ledger, path, checkpoint)
        return {'phase': 'blocked', 'detail': '已授权区域没有新的安全候选；空区和无进展位置已记录，不重复空跑', 'code': 'no_safe_candidate'}
    except Unavailable as error:
        if item in SNOW_PRODUCTS and hasattr(c,'snow_expedition_token'):
            stopped=c.status()
            can_return=(stopped.get('health',0)>=18 and stopped.get('food',0)>=8
                and stopped.get('guard_armed') and stopped.get('guard_pve_only')
                and stopped.get('flight') and not stopped.get('under_water')
                and not stopped.get('manual_movement')
                and not (stopped.get('safety_hold') or {}).get('active'))
            if can_return:
                try:
                    from .snow_harvest import _return_seed_home
                    _return_seed_home(c,checkpoint,path,ledger)
                except Unavailable as return_error:
                    return {'phase':'waiting','code':'route_uncertain',
                            'detail':str(return_error)}
        return {'phase': error.phase, 'detail': error.detail, **({'code':error.code} if error.code else {})}


def _receipt(c, item, target, before, state, reply, entry, ledger, path, checkpoint):
    after = carried(state, item)
    if any(state.get(key) for key in ('borer_active', 'chopping', 'navigating', 'native_material_busy')):
        return {'phase': 'blocked', 'detail': '原生采集仍在运行，保留在途记录，不能重复启动'}
    if reply.get('detail') == CLEAR_RESUPPLY_DETAIL and item in ROCK_SOURCES:
        receipt = reply.get('rock_quarry') or {}
        low, high = entry['min'], entry['max']
        uncertain = {'phase': 'blocked', 'detail': '采集补给停止回执尚未完整核实，保留在途记录且不重放'}
        if (not isinstance(receipt, dict) or not getattr(c, 'last', None)
                or receipt.get('id') != c.last or receipt.get('world_session') != c.world
                or state.get('world_session') != c.world or receipt.get('item') != item
                or receipt.get('min') != low or receipt.get('max') != high
                or receipt.get('completion') != 'collect' or receipt.get('active') is not False
                or reply.get('phase') != 'waiting' or receipt.get('phase') != 'waiting'
                or type(receipt.get('pending_blocks')) is not int or receipt['pending_blocks'] != 0
                or type(receipt.get('remaining_blocks')) is not int or receipt['remaining_blocks'] < 0):
            return uncertain
        # Save the complete known stop before another read can fail or hand off.
        # It remains inflight until fresh geometry independently agrees.
        entry.update(native=receipt, native_phase='waiting', native_detail=reply['detail'])
        write_json(path, ledger)
        rows = _scan(c, low, high, checkpoint)
        current = c.status(); _safe(current)
        if (current.get('world_session') != c.world
                or any(current.get(key) for key in ('borer_active', 'chopping', 'navigating', 'native_material_busy'))):
            return uncertain
        seen = set()
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get('pos'), list)
                    or len(row['pos']) != 3 or any(type(n) is not int for n in row['pos'])
                    or not in_box(row['pos'], low, high) or tuple(row['pos']) in seen
                    or not isinstance(row.get('state'), str)):
                return uncertain
            seen.add(tuple(row['pos']))
            if _danger(row, True) or block_id(row) not in NATURAL | LIGHTS | AIR:
                return uncertain
        remaining = sum(block_id(row) in NATURAL for row in rows)
        if remaining != receipt['remaining_blocks']:
            return uncertain
        after = carried(current, item)
        if after < before:
            return uncertain
        entry.update(state='progress', after=after, gained=after-before, remaining=remaining,
                     observed_at=current.get('time'))
        write_json(path, ledger)
        return {'phase': 'waiting', 'code': 'quarry_backpack_reserve',
                'detail': '采集因背包预留空间不足而停止，回执和剩余方块已核实；卸下副产物后可继续',
                'before': before, 'after': after, 'gained': after-before}
    entry.update(state='progress' if after > before else 'no_progress', after=after,
                 gained=after-before, native_phase=reply.get('phase'), native_detail=reply.get('detail'), observed_at=state.get('time'))
    write_json(path, ledger)
    if after >= target:
        return {'phase': 'done', 'detail': f'背包已核验 {after}/{target}', 'before': before, 'after': after, 'gained': after-before}
    if after > before:
        return {'phase': 'waiting', 'detail': f'本批净增 {after-before}，背包 {after}/{target}，下一轮继续核验采集', 'before': before, 'after': after, 'gained': after-before}
    return {'phase': 'blocked', 'detail': '原生作业没有实际背包增量，已记录本区域，不会照旧重放', 'code': 'no_inventory_progress'}


def _wood(c, item, target, regions, out, path, ledger, checkpoint, profile=None):
    if target > 512:raise Unavailable('原生砍树背包目标上限为 512，请分批存放再继续')
    state = c.status(); _safe(state)
    if state.get('tree_survey_protocol', 0) < 1:raise Unavailable('当前 Kit 缺少树种扫描接口')
    _tool(state, 'axe', target-carried(state, item)+32)
    checkpoint(); survey = c.request('scan_trees', item=item, radius=96).get('tree_survey')
    if not isinstance(survey, dict):raise Unavailable('树木扫描不可用', 'waiting')
    trees = [tree for tree in survey.get('trees', []) if tree.get('natural_leaves', 0) >= 4
             and any(in_box(tree.get('pos', []), *_bounds(region)) for region in regions)]
    pending=next((entry for entry in ledger['visited'].values()
                  if entry.get('state')=='route_hold'
                  and entry.get('route_code') in
                  ('guard_displaced','route_geometry_blocked','route_uncertain')
                  and entry.get('world_session')==c.world),None)
    if pending:
        raise Unavailable('原树木路线尚待核对，不换砍另一棵',
                          'waiting',code=pending['route_code'])
    for tree in trees:
        root = tree['pos']; key = _key(item, root, root)
        if ledger['visited'].get(key, {}).get('state') in ('empty_or_unsafe', 'no_progress', 'progress'):continue
        rows = _scan(c, [root[0]-11, root[1]-5, root[2]-11], [root[0]+11, root[1]+39, root[2]+11], checkpoint)
        logs = [row for row in rows if block_id(row) == item]
        valid_logs = all(any(in_box(row['pos'], *_bounds(region)) for region in regions) for row in logs)
        structures = any(row.get('block_entity') or any(token in block_id(row) for token in
                         ('_planks', '_bricks', 'glass', 'concrete', '_door', '_trapdoor')) for row in rows)
        spot = landing(rows, root) if valid_logs and not structures else None
        if spot is None:
            ledger['visited'][key] = {'state': 'empty_or_unsafe', 'root': root}; write_json(path, ledger); continue
        state = c.status(); _safe(state)
        tool = _tool(state, 'axe', max(target-carried(state, item), len(logs))+32)
        trace = []; guard_budget={'replans':0}
        region=next(r for r in regions if in_box(root,*_bounds(r)))
        high_target=[spot[0],max(tree['top']+3,spot[1]+3),spot[2]]
        try:
            route_scope=_resource_route_scope(profile,region)
            _travel(c, high_target, checkpoint, trace, guard_budget,
                    route_scope=route_scope)
            _travel(c, spot, checkpoint, trace, guard_budget,
                    route_scope=route_scope)
        except JobPaused as error:
            _paused_guard_hold(c,ledger,path,region,root,root,spot,trace,
                               str(error),profile,item)
            raise
        except Unavailable as error:
            if error.code=='guard_displaced':
                _paused_guard_hold(c,ledger,path,region,root,root,spot,trace,
                                   error.detail,profile,item,
                                   checkpoint_paused=False,route_evidence=error.evidence)
            elif error.code in ('route_geometry_blocked','route_uncertain'):
                row={'state':'route_hold','root':root,'region_key':_route_region_key(region),
                     'route_code':error.code,'reason':error.detail,
                     'world_session':c.world,'route':trace,
                     'route_evidence':error.evidence}
                ledger['visited'][key]=row;write_json(path,ledger)
                record_route_failure(c,profile,item,region,error.code,
                                     error.detail,spot,error.evidence)
            raise
        fresh_rows=_scan(c,[root[0]-11,root[1]-5,root[2]-11],
                         [root[0]+11,root[1]+39,root[2]+11],checkpoint)
        fresh_logs=[row for row in fresh_rows if block_id(row)==item]
        if ({(tuple(row['pos']),row['state']) for row in fresh_logs}
                != {(tuple(row['pos']),row['state']) for row in logs}
                or any(row.get('block_entity') or any(token in block_id(row) for token in
                       ('_planks','_bricks','glass','concrete','_door','_trapdoor'))
                       for row in fresh_rows)
                or landing(fresh_rows,root)!=spot):
            raise Unavailable('清怪后原树及安全落点变化，停下重扫，不改砍另一棵','waiting')
        # Native chop selects the nearest same-species natural tree, so reject
        # a landing whose nearer tree belongs outside the configured regions.
        checkpoint(); nearby = c.request('scan_trees', item=item, radius=12).get('tree_survey')
        if not isinstance(nearby, dict):raise Unavailable('落点附近树木尚未核验', 'waiting')
        fresh = c.status()
        nearest = min(nearby.get('trees', []), key=lambda t: math.dist([n+.5 for n in t['pos']], fresh['pos']), default=None)
        if nearest is None or nearest['pos'] != root:
            raise Unavailable('原生砍树的最近目标已变化，先重新核验，避免砍到区域外树木')
        _choose_tool(c, tool, checkpoint)
        before = carried(c.status(), item)
        sapling_item = item.removesuffix('_log') + '_sapling'
        seed_before = carried(c.status(), sapling_item)
        old_drops = {e.get('uuid'): e.get('stack', {}).get('count', 0)
                     for e in c.status().get('entities', []) if e.get('type') == 'minecraft:item'
                     and e.get('stack', {}).get('item') == sapling_item and e.get('uuid')}
        # Replant the verified lowest natural trunk cell, not a guessed nearby dirt block.
        trunk = min(logs, key=lambda row: (row['pos'][1],
                   (row['pos'][0]-root[0])**2+(row['pos'][2]-root[2])**2))
        plant_cell = [trunk['pos'][0], trunk['pos'][1], trunk['pos'][2]]
        support = next((row for row in rows if row['pos'] == [plant_cell[0], plant_cell[1]-1, plant_cell[2]]), None)
        if not support or support.get('state', '').split('[',1)[0].removeprefix('Block{').removesuffix('}') not in SAPLING_SOILS:
            plant_cell = [root[0], root[1], root[2]]
        entry = {'state': 'inflight', 'root': root, 'before': before, 'route': trace}
        ledger['visited'][key] = entry; write_json(path, ledger); checkpoint()
        reply = c.request('chop', item=item, target_count=target, tree_limit=1, seconds=240)
        after = c.status(); _safe(after)
        if after.get('chopper_remaining') or after.get('chopper_platforms'):
            return {'phase': 'blocked', 'detail': '整棵树或临时垫脚方块尚未收尾，保留在途记录待核验'}
        try:
            # Reuse a carried sapling; a new drop from this chop is not required.
            regrowth = _replant_tree_with_bonemeal(c, item, root, plant_cell, old_drops,
                                               0, carried(state, 'minecraft:bone_meal'),
                                               out, checkpoint)
        except NameError as error:
            # The optional regrowth tail must not discard already-confirmed
            # logs or force a safety logout. Keep the traceback location for repair.
            import traceback
            frames = traceback.extract_tb(error.__traceback__)
            where = {'function': frames[-1].name, 'line': frames[-1].lineno} if frames else {}
            regrowth = {'stage': 'regrowth_code_error', 'error': str(error), **where,
                        'tree_root': root, 'plant_cell': plant_cell,
                        'detail': 'Tree harvest is retained; regrowth stopped without retrying an unknown action'}
            try:
                with (Path(out)/'tree-regrowth-errors.jsonl').open('a') as stream:
                    stream.write(json.dumps(regrowth, ensure_ascii=False)+'\n')
            except OSError:
                pass
        entry['regrowth'] = regrowth
        ledger['visited'][key] = entry; write_json(path, ledger)
        return {**_receipt(c, item, target, before, c.status(), reply, entry, ledger, path, checkpoint),
                'regrowth': regrowth}
    if survey.get('unloaded_columns', 0):
        # The radius-96 survey may include unloaded columns unrelated to the
        # approved region. Check those X/Z chunks before asking discovery for a new region.
        for region in regions:
            lo, hi = _bounds(region);height=math.floor(c.status()['pos'][1])
            _scan(c,[lo[0],height,lo[2]],[hi[0],height,hi[2]],checkpoint)
    return {'phase': 'blocked', 'detail': '已观察的授权区域没有新的安全树木，需发现其他资源区', 'code': 'no_safe_candidate'}
