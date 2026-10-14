"""Verified cactus planting from real carried seeds; never consumes the last seed for dye."""
from pathlib import Path
import json
import math
import time

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from .acquisition import block_id
from .colored_sources import _protected

SEED_RESERVE=6

def dye_budget(carried, reserve=SEED_RESERVE):
    if type(carried)is not int or carried<0 or type(reserve)is not int or reserve<1:
        raise ValueError('Actual carried cactus and positive seed reserve required')
    return max(0,carried-reserve)

def suitable(rows,pos):
    by={tuple(r['pos']):r for r in rows};x,y,z=pos
    floor=by.get((x,y-1,z))
    if (floor is None or block_id(floor)not in ('minecraft:sand','minecraft:red_sand')
            or floor.get('solid')is not True or floor.get('fluid')is not False
            or floor.get('block_entity')is not False):return False
    # A sparse row is air only after the caller's complete same-world scan.
    return all(p not in by for p in ((x,y,z),(x,y+1,z),(x,y+2,z),
                                   (x-1,y,z),(x+1,y,z),(x,y,z-1),(x,y,z+1)))


def side_pose_clear(rows, low, high, point, tolerance=.3):
    """A complete scan must cover the padded body, including damaging top faces.

    Cactus damage uses the block's space, beyond its smaller collision shape.
    Treat every cactus cell as dangerous even if its collision top is below feet.
    """
    from ground_pickup import hazard
    if (len(point) != 3 or any(not math.isfinite(n) for n in point)
            or not 0 <= tolerance <= .4):
        return False
    body_low = [math.floor(point[0]-.31-tolerance), math.floor(point[1]-tolerance),
                math.floor(point[2]-.31-tolerance)]
    body_high = [math.floor(point[0]+.31+tolerance), math.floor(point[1]+1.8+tolerance),
                 math.floor(point[2]+.31+tolerance)]
    if any(body_low[i] < low[i] or body_high[i] > high[i] for i in range(3)):
        return False
    return not any(all(body_low[i] <= r['pos'][i] <= body_high[i] for i in range(3))
                   and (r.get('passable') is not True or hazard(r)
                        or r.get('block_entity') is not False) for r in rows)


def side_poses(rows, low, high, pos, foot_offset=.25):
    x, y, z = pos
    options = [('east', [x+1.65, y+foot_offset, z+.5]),
               ('west', [x-.65, y+foot_offset, z+.5]),
               ('south', [x+.5, y+foot_offset, z+1.65]),
               ('north', [x+.5, y+foot_offset, z-.65])]
    return [(face, point) for face, point in options
            if side_pose_clear(rows, low, high, point)]


def harvestable_top(rows, pos):
    by = {tuple(r['pos']): r for r in rows}; x, y, z = pos
    target, base, above = by.get(tuple(pos)), by.get((x,y-1,z)), by.get((x,y+1,z))
    return bool(target and block_id(target) == 'minecraft:cactus'
                and base and block_id(base) == 'minecraft:cactus'
                and (above is None or block_id(above) == 'minecraft:cactus_flower'
                     and above.get('fluid') is False and above.get('block_entity') is False))


def authorized_planting_cell(profile, state, world, pos):
    """Only explicit farm cells in an already authorized sand area are exempt.

    The base's broad no-survey box remains unchanged. It does not authorize
    mining, other placements, map overlap, or planting beside a depot.
    """
    from .protocol import server_key
    plan = profile.get('cactus_planting_plan') or {}
    if (plan.get('authorized') is not True or plan.get('source') != 'user_requested_renewable_farm'
            or plan.get('world_session') != world or pos not in plan.get('positions', [])
            or server_key(plan.get('server')) != server_key(state.get('server'))
            or plan.get('dimension') != state.get('dimension')):
        return False
    selected = state.get('projection_selection') or {}
    if selected.get('min') and selected.get('max') and all(
            selected['min'][i]-16 <= pos[i] <= selected['max'][i]+16 for i in (0, 2)):
        return False
    depots = profile.get('depots', []) + profile.get('furnace_positions', [])
    depots += [profile[k] for k in ('workbench','ender_chest','shulker_pad') if k in profile]
    if any(math.hypot(pos[0]-p[0],pos[2]-p[2]) <= 48 for p in depots):
        return False
    for r in profile.get('resource_regions', []):
        box = r.get('original_authorized_bounds') or {}
        lo, hi = box.get('min'), box.get('max')
        if (r.get('item') == 'minecraft:sand' and r.get('source') == 'previous_authorized_sand_site'
                and isinstance(lo,list) and isinstance(hi,list) and len(lo)==len(hi)==3
                and all(lo[i] <= pos[i] <= hi[i] for i in range(3))):
            return True
    return False


def owned_farm_top(profile, state, pos):
    """Actual planting receipts authorize grown tops, never the farm's bases."""
    from .protocol import server_key
    selected=state.get('projection_selection')or{}
    if selected.get('min')and selected.get('max')and all(
            selected['min'][i]-16<=pos[i]<=selected['max'][i]+16 for i in(0,2)):
        return False
    for box in profile.get('protected_regions',[]):
        if all(box['min'][i]-16<=pos[i]<=box['max'][i]+16 for i in(0,2)) \
                and box.get('note')!='base_courtyard_villa_projection_no_survey':
            return False
    for farm in profile.get('renewable_cactus_farms',[]):
        if (farm.get('complete')is not True or not farm.get('planting_receipt')
                or server_key(farm.get('server'))!=server_key(state.get('server'))
                or farm.get('dimension')!=state.get('dimension')):continue
        for base in farm.get('positions',[]):
            if pos[0]==base[0]and pos[2]==base[2]and base[1]+1<=pos[1]<=base[1]+2:
                return True
    return False


def planting_transit_height(position, planting_y):
    # Rise before crossing a planted row; the work pose is deliberately lower
    # only after the horizontal leg ends at the new verified side column.
    return max(position[1]+1, planting_y+20.)


def harvest_top(c, pos, profile, out, checkpoint):
    """One normal side harvest with the base retained; never stand on the cactus.

    Navigation, mining and pickup intent are durable. Pickup uses a proved side
    pose and normal movement; collect_item cannot choose a cactus-top pose here.
    """
    if (not isinstance(pos, list) or len(pos) != 3 or any(type(n) is not int for n in pos)
            or not any(r.get('authorized') is True and r.get('item') == 'minecraft:cactus'
                       and all(r['min'][i] <= pos[i] <= r['max'][i] for i in range(3))
                       for r in profile.get('colored_source_regions', []))):
        raise ValueError('A current explicitly authorized cactus patch is required')
    out = Path(out); out.mkdir(parents=True, exist_ok=True); path = out/'cactus-side-harvest.json'
    if path.exists():
        raise RuntimeError('Existing cactus harvest intent is not replayed')
    state = checkpoint()
    if _protected(pos, profile, state) and not owned_farm_top(profile,state,pos):
        raise RuntimeError('Cactus harvest overlaps a protected footprint')
    world = c.world; x, y, z = pos
    low, high = [x-3, y-2, z-3], [x+3, y+5, z+3]
    def observe():
        q = checkpoint()
        if (q.get('world_session') != world or q.get('health') != 20
                or q.get('guard_busy') or q.get('screen') or q.get('manual_movement')):
            raise RuntimeError('Cactus side harvest healthy control changed')
        r = c.request('scan', min=low, max=high, details=True)
        cells = math.prod(high[i]-low[i]+1 for i in range(3))
        if (r.get('id') != c.last or r.get('world_session') != world
                or r.get('phase') not in (None, 'done')
                or r.get('scan_cells_read') != cells or r.get('scan_total_cells') != cells
                or not isinstance(r.get('blocks'), list)):
            raise RuntimeError('Cactus side clearance scan is incomplete')
        return r['blocks']
    rows = observe(); by = {tuple(r['pos']): r for r in rows}
    target, base = by.get(tuple(pos)), by.get((x, y-1, z))
    if (not harvestable_top(rows, pos)
            or any(r.get('fluid') or r.get('block_entity') for r in rows)):
        raise RuntimeError('Harvest only an observed top with a retained dry base')
    choices = side_poses(rows, low, high, pos)
    if not choices:
        raise RuntimeError('No damaging-block-free cactus side pose')
    face, point = min(choices, key=lambda v: math.dist(v[1], state['pos']))
    book = {'world_session': world, 'task_session': c.task, 'pos': pos,
            'face': face, 'side_pose': point, 'pending': 'side_access', 'base_retained': False}
    write_json(path, book)
    from .acquisition import _travel
    from .navigation import lift_for_travel, settled_state
    lift_for_travel(c)
    high_point = [point[0], y+4., point[2]]
    trace = []; _travel(c, high_point, checkpoint, trace)
    rows = observe()
    if not side_pose_clear(rows, low, high, point):
        raise RuntimeError('Cactus side pose changed during access')
    c.checked('navigate', target=point, arrival=.2, air_only=True, seconds=30)
    actual = settled_state(c, point, .4)
    rows = observe()
    if not side_pose_clear(rows, low, high, actual['pos'], tolerance=.05):
        raise RuntimeError('Actual cactus work pose intersects a damaging block')
    # A far-side arrival can stop ~.15 short and miss randomly offset drops.
    # Approach a second checked side point before breaking, so the normal
    # pickup box reaches the drop immediately. Never enter the cactus cell.
    near = list(point)
    axis, delta = {'east': (0, -.2), 'west': (0, .2),
                   'south': (2, -.2), 'north': (2, .2)}[face]
    near[axis] += delta
    if not side_pose_clear(rows, low, high, near, tolerance=.1):
        raise RuntimeError('Closer cactus pickup pose lacks safe side clearance')
    c.checked('navigate', target=near, arrival=.2, air_only=True, seconds=15)
    actual = settled_state(c, near, .4); rows = observe()
    if not side_pose_clear(rows, low, high, actual['pos'], tolerance=.05):
        raise RuntimeError('Actual cactus pickup pose intersects a damaging block')
    book['actual_work_pose'] = actual['pos']
    target = next((r for r in rows if r['pos'] == pos), None)
    base = next((r for r in rows if r['pos'] == [x, y-1, z]), None)
    if not harvestable_top(rows, pos):
        raise RuntimeError('Cactus changed before mining; no mutation sent')
    from container_hand import select_container_hand
    select_container_hand(c)
    before = inventory_counts(checkpoint()).get('minecraft:cactus', 0)
    book.update(pending='mine', before=before, expected_state=target['state'], route=trace)
    write_json(path, book)
    reply = c.request('mine_block', pos=pos, face=face, expected_state=target['state'], seconds=20)
    book['mine_request_id'] = c.last; write_json(path, book)
    if reply.get('phase') != 'done':
        raise RuntimeError('Cactus mining receipt uncertain; no replay')
    book['pending'] = 'side_pickup'; write_json(path, book)
    deadline = time.monotonic()+4
    while True:
        q = checkpoint(); after = inventory_counts(q).get('minecraft:cactus', 0)
        if after == before+1:
            break
        if after != before or time.monotonic() >= deadline:
            raise RuntimeError('Cactus side pickup gain unconfirmed; no unsafe pickup route')
        time.sleep(.1)
    rows = observe(); by = {tuple(r['pos']): r for r in rows}
    if tuple(pos) in by or block_id(by.get((x, y-1, z), {})) != 'minecraft:cactus':
        raise RuntimeError('Cactus removal or base retention unconfirmed')
    book.update(pending=None, complete=True, after=after, actual_gain=1,
                base_retained=True, actual_side_pos=q['pos'])
    write_json(path, book); return book

def plant(c,positions,profile,out,checkpoint):
    if (not isinstance(positions,list) or not 1<=len(positions)<=16
            or any(not isinstance(p,list)or len(p)!=3 or any(type(n)is not int for n in p)for p in positions)
            or len({tuple(p)for p in positions})!=len(positions)):
        raise ValueError('Explicit distinct bounded cactus positions required')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'cactus-planting.json'
    if path.exists():raise RuntimeError('Existing planting intent is not replayed')
    before=inventory_counts(checkpoint()).get('minecraft:cactus',0)
    if before<len(positions):raise RuntimeError('Planting needs real carried cactus seeds')
    book={'world_session':c.world,'before':before,'positions':positions,'planted':[],'pending':None}
    write_json(path,book)
    def scan(low,high):
        checkpoint();reply=c.checked('scan',min=low,max=high,details=True)
        cells=1
        for i in range(3):cells*=high[i]-low[i]+1
        if (reply.get('world_session')!=c.world or reply.get('scan_cells_read')!=cells
                or reply.get('scan_total_cells')!=cells):raise RuntimeError('Planting scan is incomplete')
        return reply['blocks']
    for pos in positions:
        state=checkpoint()
        if _protected(pos,profile,state) and not authorized_planting_cell(profile,state,c.world,pos):
            raise RuntimeError('Cactus planting overlaps a protected footprint or depot')
        x,y,z=pos;low=[x-3,y-2,z-3];high=[x+3,y+5,z+3];rows=scan(low,high)
        if not suitable(rows,pos):raise RuntimeError('Cactus site needs dry sand and empty growth clearance')
        floor=[x,y-1,z];ground=next(r for r in rows if r['pos']==floor)
        choices=side_poses(rows,low,high,pos,foot_offset=.65)
        if not choices:raise RuntimeError('No cactus planting side pose clear of damaging blocks')
        _,point=min(choices,key=lambda p:math.dist(p[1],state['pos']))
        from .acquisition import _travel
        from .navigation import settled_state
        transit=planting_transit_height(state['pos'],y)
        up=[state['pos'][0],transit,state['pos'][2]]
        c.checked('navigate',target=up,arrival=.2,air_only=True,seconds=90)
        settled_state(c,up,.4)
        trace=[];_travel(c,[point[0],transit,point[2]],checkpoint,trace)
        rows=scan(low,high)
        if not side_pose_clear(rows,low,high,point):raise RuntimeError('Cactus planting side clearance changed')
        c.checked('navigate',target=point,arrival=.2,air_only=True,seconds=30)
        state=settled_state(c,point,.4);rows=scan(low,high)
        if not side_pose_clear(rows,low,high,state['pos'],tolerance=.05):raise RuntimeError('Actual planting pose touches a damaging block')
        if not suitable(rows,pos):raise RuntimeError('Cactus planting site changed during approach')
        c.checked('select_item',item='minecraft:cactus')
        count=inventory_counts(checkpoint()).get('minecraft:cactus',0)
        book['pending']={'pos':pos,'before':count};write_json(path,book)
        c.checked('interact',pos=floor,face='up',expected_state=ground['state'],expected_hand='minecraft:cactus')
        deadline=time.monotonic()+6
        while True:
            actual=scan(pos,pos);state=checkpoint()
            if (len(actual)==1 and block_id(actual[0])=='minecraft:cactus'
                    and inventory_counts(state).get('minecraft:cactus',0)==count-1):break
            if time.monotonic()>=deadline:raise RuntimeError('Plant and seed consumption unconfirmed; no repeat')
            time.sleep(.15)
        current=scan(low,high);state=checkpoint()
        if not side_pose_clear(current,low,high,state['pos'],tolerance=.05):
            raise RuntimeError('Actual pose intersects the planted cactus; no further placement')
        book['planted'].append({'pos':pos,'state':actual[0]['state'],'after':count-1,
                                'actual_side_pos':state['pos'],'health':state['health'],'route':trace})
        book['pending']=None;write_json(path,book)
    book.update(complete=True,remaining=inventory_counts(checkpoint()).get('minecraft:cactus',0))
    write_json(path,book);return book
