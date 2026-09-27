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
        soil = actual.get((x, y-1, z)); target = actual.get((x, y, z))
        head = actual.get((x, y+1, z))
        if (not soil or not target or block_id(target) not in
            ('Block{minecraft:air}', 'Block{minecraft:cave_air}', 'Block{minecraft:void_air}')
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
            soil = actual.get((x, y-1, z)); target = actual.get((x, y, z))
            if (not soil or block_id(soil) not in SAPLING_SOILS
                    or not target or block_id(target) not in
                    ('Block{minecraft:air}', 'Block{minecraft:cave_air}', 'Block{minecraft:void_air}')
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
    'minecraft:raw_copper': {'minecraft:copper_ore', 'minecraft:deepslate_copper_ore'},
    'minecraft:coal': {'minecraft:coal_ore', 'minecraft:deepslate_coal_ore'},
    **{'minecraft:'+name: {'minecraft:'+name} for name in ('andesite', 'diorite', 'granite', 'tuff', 'calcite')},
}
NATURAL = {'minecraft:' + name for name in (
    'stone', 'deepslate', 'granite', 'diorite', 'andesite', 'tuff', 'calcite', 'dripstone_block',
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


class Unavailable(Exception):
    def __init__(self, detail, phase='blocked', code=None):
        self.phase, self.detail, self.code = phase, detail, code
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


def _travel(c, target, checkpoint, trace):
    """Use inspected axis-aligned clear segments; never fly down through an unmined cap."""
    here = list(c.status()['pos'])
    if c.status().get('air_only_navigation_protocol',0)<2:
        raise Unavailable('当前 Kit 缺少仅走空气的材料导航接口，请更新后再开始')
    if math.hypot(target[0]-here[0], target[2]-here[2]) > 384:
        raise Unavailable('资源区离当前控制点太远，需由发现路线分段接近', 'waiting')
    cruise = max(here[1], target[1])
    # Read the complete two-leg flight corridor before picking its height.
    # A ground-level depot must not make the next quarry route cross a roof.
    bend=[target[0],here[1],here[2]]
    for start,end in ((here,bend),(bend,target)):
        axis=0 if abs(start[0]-end[0])>=abs(start[2]-end[2]) else 2
        low=math.floor(min(start[axis],end[axis])-.32)
        high=math.floor(max(start[axis],end[axis])+.32)
        for base in range(low,high+1,32):
            lo=[math.floor(min(start[0],end[0])-.32),math.floor(min(here[1],target[1])),math.floor(min(start[2],end[2])-.32)]
            hi=[math.floor(max(start[0],end[0])+.32),319,math.floor(max(start[2],end[2])+.32)]
            lo[axis]=base;hi[axis]=min(high,base+31)
            observed=_scan(c,lo,hi,checkpoint)
            cruise=max(cruise,max((r['pos'][1]+3.1 for r in observed if r.get('fluid') or not r.get('passable',False)),default=cruise))
    if cruise>=317:
        raise Unavailable('已观察航线上方没有足够净空，不穿过障碍')
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
            raise Unavailable('资源区入口或航线仍有障碍；不会穿越地层或挖开区域外建筑')
        checkpoint()
        reply = c.request('navigate', target=point, arrival=.25, air_only=True, seconds=90)
        from .navigation import settled_state
        actual = settled_state(c,point,.55); _safe(actual)
        trace.append({'target': point, 'actual': actual['pos'], 'phase': reply.get('phase')})
        if reply.get('phase') != 'done' or math.dist(actual['pos'], point) > .55:
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


def _access_shaft(c, region, choice, item, target, ledger, path, checkpoint):
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
            _travel(c, [centre[0], segment_high[1]+3.1, centre[1]], checkpoint, trace)
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
    checkpoint(); initial = c.status(); before = carried(initial, item)
    if before >= target_count:return {'phase': 'done', 'detail': '背包现物已经达到目标', 'before': before, 'after': before}
    if item not in ROCK_SOURCES and item not in LOGS and item not in ('minecraft:sand', 'minecraft:dirt', 'minecraft:grass_block'):
        return {'phase': 'blocked', 'detail': '此原料尚无直接采集适配器：' + item}
    if item == 'minecraft:grass_block' and (type(initial.get('grass_block_tool_protocol')) is not int
                                             or initial['grass_block_tool_protocol'] < 1):
        return {'phase': 'blocked', 'detail': '当前 Kit 主包缺少草方块精准采集工具核验；请先更新主包'}
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    path = out / ('acquisition-' + item.split(':')[-1] + '.json')
    ledger = json.loads(path.read_text()) if path.exists() else {'schema': 1, 'world_session': c.world, 'item': item, 'visited': {}}
    if ledger.get('world_session') != c.world or ledger.get('item') != item:
        return {'phase': 'blocked', 'detail': '采集记录属于另一世界或物品，不能沿用旧位置'}
    if any(v.get('state') == 'inflight' for v in ledger['visited'].values()):
        return {'phase': 'blocked', 'detail': '前次采集回执不确定，需先核验原生任务与物品，不能重放'}
    try:
        _safe(initial)
        if room_for_item(initial, item) < target_count-before:
            raise Unavailable('当前背包容纳不了本次总数，请先卸货或减少本批目标')
        regions = [r for r in profile.get('resource_regions', []) if r.get('item') == item]
        if not regions:raise Unavailable('没有已授权的资源区域：' + item)
        for region in regions:_bounds(region)
        ledger['resource_regions']=[{key:region[key] for key in
                                    ('item','min','max','source','surface_y','access_shaft') if key in region}
                                   for region in regions]
        write_json(path,ledger)
        if item in ('minecraft:dirt', 'minecraft:grass_block'):
            from .dirt_harvest import acquire_surface_soil
            return acquire_surface_soil(c, item, target_count, profile, regions, path, ledger, checkpoint)
        if item in LOGS:
            return _wood(c, item, target_count, regions, out, path, ledger, checkpoint)
        sand = item == 'minecraft:sand'
        _tool(initial, 'shovel' if sand else 'pickaxe', 33, no_silk=not sand)
        if initial.get('quarry_protocol' if sand else 'rock_quarry_protocol', 0) < 1:
            raise Unavailable('当前 Kit 缺少所需原生采坑接口，请更新后再开始')
        scans = 0
        for region in regions:
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
                    entry_centre = _access_shaft(c,region,choice,item,target_count,ledger,path,checkpoint) if not sand else None
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
                _travel(c, target, checkpoint, trace)
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


def _wood(c, item, target, regions, out, path, ledger, checkpoint):
    if target > 512:raise Unavailable('原生砍树背包目标上限为 512，请分批存放再继续')
    state = c.status(); _safe(state)
    if state.get('tree_survey_protocol', 0) < 1:raise Unavailable('当前 Kit 缺少树种扫描接口')
    _tool(state, 'axe', target-carried(state, item)+32)
    checkpoint(); survey = c.request('scan_trees', item=item, radius=96).get('tree_survey')
    if not isinstance(survey, dict):raise Unavailable('树木扫描不可用', 'waiting')
    trees = [tree for tree in survey.get('trees', []) if tree.get('natural_leaves', 0) >= 4
             and any(in_box(tree.get('pos', []), *_bounds(region)) for region in regions)]
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
        trace = []; _travel(c, [spot[0], max(tree['top']+3, spot[1]+3), spot[2]], checkpoint, trace)
        _travel(c, spot, checkpoint, trace)
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
