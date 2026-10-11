"""Observed projection exits and local parking; never fly upward through a roof."""
import math
import time
import json
from pathlib import Path
from collections import deque

from hull_escape import horizontal_exit
from kit_runtime.journal import write_json
from .protocol import JobBlocked


def _bounds(box):
    if not isinstance(box,dict):return None
    low,high=box.get('min'),box.get('max')
    if (not isinstance(low,list) or not isinstance(high,list) or len(low)!=3 or len(high)!=3
            or any(type(v) is not int for v in low+high) or any(a>b for a,b in zip(low,high))):return None
    return low,high


def quarry_exit_candidates(directory, world, position):
    """Coordinates identify an owned shaft; old clearance never authorizes movement."""
    directory=Path(directory)
    if not directory.is_dir():return []
    found=[]
    for path in sorted(directory.glob('acquisition-*.json'))[:32]:
        if path.stat().st_size>1_000_000:raise JobBlocked('采坑出口记录过大，请先检查账本')
        ledger=json.loads(path.read_text())
        if ledger.get('schema')!=1 or ledger.get('world_session')!=world:continue
        visited=ledger.get('visited') or {}
        if not isinstance(visited,dict):continue
        clear=[entry for key,entry in visited.items() if key.startswith('access-')
               and entry.get('state')=='clear_verified' and _bounds(entry)]
        for region in ledger.get('resource_regions',[]):
            opened=_bounds(region.get('open_entry'));box=_bounds(region)
            if box and opened and region.get('source')=='natural_survey' and not region.get('access_shaft'):
                low,high=box;sl,sh=opened;surface=high[1]
                if (sh[0]-sl[0]==1 and sh[2]-sl[2]==1 and sl[1]==surface+1 and sh[1]==surface+2
                        and all(low[i]<=sl[i]<=sh[i]<=high[i]for i in(0,2))
                        and all(low[i]-1<=position[i]<=high[i]+2 for i in(0,2))
                        and low[1]-2<=position[1]<surface+3
                        and any(_bounds(e)and e.get('state')in('inflight','progress','done','clear_verified')
                                and all(low[i]<=e['min'][i]<=e['max'][i]<=high[i]for i in range(3))
                                for e in visited.values())):
                    shaft={'min':[sl[0],low[1],sl[2]],'max':[sh[0],surface,sh[2]]}
                    found.append({'min':low,'max':high,'shaft':shaft,'surface_y':surface,
                                  'ledger':str(path),'original_open_entry':region['open_entry'],'clearance_credit':0})
            box,shaft=_bounds(region),_bounds(region.get('access_shaft'))
            surface=region.get('surface_y')
            if not box or not shaft or region.get('source')!='natural_survey' or type(surface) is not int:continue
            low,high=box;sl,sh=shaft
            if (sh[0]-sl[0]!=1 or sh[2]-sl[2]!=1 or sh[1]!=surface or surface+5>319
                    or not all(low[i]<=sl[i]<=sh[i]<=high[i] for i in (0,2))):continue
            if not (all(low[i]-1<=position[i]<=high[i]+2 for i in (0,2))
                    and low[1]-2<=position[1]<surface+3):continue
            if not any(all(entry['min'][i]==sl[i] and entry['max'][i]==sh[i] for i in (0,2))
                       and entry['max'][1]<=surface for entry in clear):continue
            candidate={'min':low,'max':high,'shaft':region['access_shaft'],'surface_y':surface,'ledger':str(path)}
            if candidate not in found:found.append(candidate)
    return sorted(found,key=lambda entry: math.hypot(position[0]-(entry['shaft']['min'][0]+1),position[2]-(entry['shaft']['min'][2]+1)))


def shaft_path(rows, position, shaft, low, high):
    """Small horizontal BFS through a fully acknowledged sparse air scan."""
    y=math.floor(position[1]);head=math.floor(position[1]+1.8-1e-7)
    blocked={tuple(row['pos']) for row in rows}
    start=(math.floor(position[0]),math.floor(position[2]))
    def clear(cell):
        x,z=cell
        return low[0]<=x<=high[0] and low[2]<=z<=high[2] and all((x,h,z) not in blocked for h in range(y,head+1))
    def goal(cell):return all(shaft['min'][axis]<=cell[index]<=shaft['max'][axis] for index,axis in enumerate((0,2)))
    if not clear(start):raise JobBlocked('当前位置的采坑出口空间不是已确认空气')
    queue=deque([start]);parents={start:None};end=None
    while queue:
        current=queue.popleft()
        if goal(current):end=current;break
        for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
            nxt=(current[0]+dx,current[1]+dz)
            if nxt not in parents and clear(nxt):parents[nxt]=current;queue.append(nxt)
    if end is None:raise JobBlocked('已挖空间没有连到原入口，不挖新通道')
    path=[]
    while end is not None:path.append(end);end=parents[end]
    return [[x+.5,position[1],z+.5] for x,z in reversed(path)]


def _air_scan(client, low, high):
    if math.prod(high[i]-low[i]+1 for i in range(3))>50000:raise JobBlocked('采坑出口扫描超出范围')
    reply=client.request('scan',min=low,max=high,details=True)
    # The native scan checks every covered chunk and omits only actual air.
    # An empty partial/error response must never become a navigable corridor.
    # Native read-only scan replies have id/world/blocks but no action phase.
    # Chunk failure instead has an explicit error phase and no complete blocks.
    if reply.get('phase') not in (None,'done') or reply.get('world_session')!=client.world or not isinstance(reply.get('blocks'),list):
        raise JobBlocked('采坑出口扫描尚未完整确认')
    # Retained lighting and safe, collision-free grass do not close a shaft.
    # A generic passable flag alone is insufficient: fire, fluids and other
    # dangerous non-full blocks must still obstruct this conservative route.
    from .acquisition import block_id
    safe_noncolliding = {'minecraft:'+name for name in
                        ('torch','wall_torch','short_grass','tall_grass','fern','large_fern')}
    return [row for row in reply['blocks'] if not (
        block_id(row) in safe_noncolliding and row.get('passable') is True
        and row.get('fluid') is False and row.get('block_entity') is False)]


def _air_move(client, target, seconds=20):
    reply=client.request('navigate',target=target,arrival=.25,seconds=seconds,air_only=True)
    state=settled_state(client,target,.45)
    if reply.get('phase')!='done' or math.dist(state['pos'],target)>.45:
        raise JobBlocked('出口实际位置未到达已确认空气点，停止继续上升')


def _body_sweep(start, end):
    low=[math.floor(min(start[0],end[0])-.31),math.floor(min(start[1],end[1])),
         math.floor(min(start[2],end[2])-.31)]
    high=[math.floor(max(start[0],end[0])+.31),math.floor(max(start[1],end[1])+1.8-1e-7),
          math.floor(max(start[2],end[2])+.31)]
    return low,high


def _inside_shaft(position, shaft):
    """The entire body footprint must fit the originally authorized 2x2."""
    low,high=_body_sweep(position,position)
    return all(shaft['min'][axis]<=low[axis]<=high[axis]<=shaft['max'][axis] for axis in (0,2))


def _shaft_column(position, surface):
    low,high=_body_sweep(position,position)
    high[1]=surface+5
    return low,high


def leave_quarry(client, directory):
    """Exit through a freshly verified body-sized column of the owned shaft."""
    state=client.status();position=state['pos']
    candidates=quarry_exit_candidates(directory,client.world,position)
    if not candidates:return False
    if state.get('air_only_navigation_protocol',0)<2:
        raise JobBlocked('当前 Kit 尚不支持采坑精确空气导航，请更新后继续')
    candidate=candidates[0];shaft=candidate['shaft'];surface=candidate['surface_y']
    path=[]
    # Native quarry work descends column by column. The current body column can
    # be clear while its unmined neighbor remains solid; never recenter across
    # that neighbor merely because the authorized shaft is two blocks wide.
    direct=_inside_shaft(position,shaft) and not _air_scan(client,*_shaft_column(position,surface))
    if not direct:
        low=[min(math.floor(position[0]),shaft['min'][0])-2,math.floor(position[1]),min(math.floor(position[2]),shaft['min'][2])-2]
        high=[max(math.floor(position[0]),shaft['max'][0])+2,math.floor(position[1]+1.8-1e-7),max(math.floor(position[2]),shaft['max'][2])+2]
        if high[0]-low[0]>18 or high[2]-low[2]>18:raise JobBlocked('当前位置离原入口过远，保留采坑出口记录')
        rows=_air_scan(client,low,high)
        columns=sorted(([x+.5,position[1],z+.5]
                        for x in range(shaft['min'][0],shaft['max'][0]+1)
                        for z in range(shaft['min'][2],shaft['max'][2]+1)),
                       key=lambda point:math.dist(point,position))
        route_error=None
        for column in columns:
            if _air_scan(client,*_shaft_column(column,surface)):continue
            x,z=math.floor(column[0]),math.floor(column[2])
            endpoint={'min':[x,shaft['min'][1],z],'max':[x,shaft['max'][1],z]}
            try:
                path=shaft_path(rows,position,endpoint,low,high)
            except JobBlocked as error:
                route_error=error
                continue
            break
        else:
            if route_error is not None:raise route_error
            raise JobBlocked('原入口现在有方块或水，没有可安全抵达的完整上升通道')
    waypoints=[]
    for planned in path:
        current=client.status()['pos']
        target=[planned[0],current[1],planned[2]]
        if math.dist(current,target)<.15:continue
        if _air_scan(client,*_body_sweep(current,target)):
            raise JobBlocked('采坑出口通道发生变化，不继续原路线')
        _air_move(client,target)
        waypoints.append(target)
    actual=client.status()['pos']
    if not _inside_shaft(actual,shaft):
        raise JobBlocked('角色身体尚未完全进入原竖井，不在授权入口外升空')
    column_low,column_high=_shaft_column(actual,surface)
    if _air_scan(client,column_low,column_high):
        raise JobBlocked('竖井上升空间发生变化，保持当前位置')
    fresh=client.status()['pos'];body_low,body_high=_body_sweep(fresh,fresh)
    if (not _inside_shaft(fresh,shaft) or any(body_low[i]<column_low[i] or body_high[i]>column_high[i]
                                            for i in range(3))):
        raise JobBlocked('核验期间角色离开已扫描的上升通道，保持当前位置')
    target=[fresh[0],surface+3.0,fresh[2]]
    _air_move(client,target,120)
    write_json(client.out/('quarry-exit-%d.json'%time.time_ns()),{'world_session':client.world,'source':candidate,'from':position,'waypoints':waypoints+[target],'actual':client.status()['pos'],'confirmed':True})
    return True


def move(client, target, seconds=120, arrival=1):
    reply = client.request('navigate', target=list(target), arrival=arrival, seconds=seconds,air_only=True)
    if reply.get('phase') != 'done':
        raise JobBlocked('路线没有走通：' + str(reply.get('detail', '未确认到达')))


def settled_state(client, target=None, tolerance=.6, seconds=4):
    """Read actual rest after a native acknowledgement; never broaden arrival."""
    deadline=time.monotonic()+seconds;stable_since=None;previous=None
    while True:
        state=client.status();now=time.monotonic()
        velocity=state.get('velocity',[0,0,0]);position=state['pos']
        # A grounded player still reports the downward gravity impulse before
        # collision resolution. Verify horizontal velocity and real position;
        # keep the vertical check for flying/swimming players.
        axes=(0,2) if state.get('on_ground') else (0,1,2)
        quiet=math.sqrt(sum(float(velocity[i])**2 for i in axes))<=.03
        quiet=quiet and (previous is None or math.dist(previous,position)<=.08)
        quiet=quiet and (target is None or math.dist(position,target)<=tolerance)
        stable_since=now if quiet and stable_since is None else stable_since if quiet else None
        if stable_since is not None and now-stable_since>=.4:
            return state
        if now>=deadline:
            raise JobBlocked('实际位置未到达或角色仍在漂移，停止衔接下一段路线')
        previous=list(position);time.sleep(.15)



def _below_vertical_start(row, position):
    """Known partial collision tops are below feet even when Flight reports airborne.

    Keep this deliberately limited to shapes whose collision height is fixed by
    the observed state. Dry farmland is 15/16 high; dry bottom slabs and chest
    tops have their known collision heights. Other shapes remain obstacles.
    """
    from .acquisition import block_id
    name,state=block_id(row),row.get('state','')
    if (row.get('solid') is not False or row.get('fluid') is not False
            or row['pos'][1]!=math.floor(position[1])):
        return False
    if (name in {'minecraft:chest','minecraft:trapped_chest','minecraft:ender_chest'}
            and row.get('block_entity') is True and 'waterlogged=true' not in state):
        return position[1]>=row['pos'][1]+.875-1e-7
    if (name=='minecraft:farmland' and row.get('block_entity') is False
            and state in {'Block{minecraft:farmland}[moisture=%d]'%n for n in range(8)}):
        return position[1]>=row['pos'][1]+.9375-1e-7
    return (name.endswith('_slab') and row.get('block_entity') is False
            and '[type=bottom,' in state and 'waterlogged=false]' in state
            and position[1]>=row['pos'][1]+.5)


def leave_projection(client):
    # A completed ground walk can still be coasting or falling. Anchor the
    # clearance scan to an actual rest, not just the walk acknowledgement.
    state = settled_state(client)
    selection = state.get('projection_selection', {})
    low, high, p = selection.get('min'), selection.get('max'), state['pos']
    if not low or not high or not all(low[i]-1 <= p[i] <= high[i]+1 for i in (0, 2)) or p[1] > high[1]+2:
        return
    low,high=list(low),list(high)
    scope=(state.get('world_session'),state.get('control_revision'),selection.get('key'))
    if state.get('air_only_navigation_protocol',0)<2:
        raise JobBlocked('当前 Kit 尚不支持精确空气导航，不能核验投影退出')
    # A union/AABB of courtyard subregions also contains outdoor protection
    # holes. Prove open sky before treating those positions as an interior.
    if high[1]+3<=317:
        for attempt in range(2):
            column_low,column_high=_body_sweep(p,p);column_high[1]=319
            column=_air_scan(client,column_low,column_high)
            fresh=settled_state(client);actual=fresh['pos']
            current_selection=fresh.get('projection_selection',{})
            if ((fresh.get('world_session'),fresh.get('control_revision'),current_selection.get('key'))!=scope
                    or current_selection.get('min')!=low or current_selection.get('max')!=high):
                raise JobBlocked('露天退出核验期间位置或投影改变，保持当前位置')
            actual_low,actual_high=_body_sweep(actual,actual)
            moved=(math.dist(actual,p)>.15 or actual_low[1]<column_low[1]
                   or any(actual_low[i]<column_low[i] or actual_high[i]>column_high[i] for i in (0,2)))
            if moved:
                if attempt:
                    raise JobBlocked('露天退出核验期间位置或投影改变，保持当前位置')
                # Never use the old column after crossing its body footprint.
                p=actual
                if (not all(low[i]-1<=p[i]<=high[i]+1 for i in (0,2)) or p[1]>high[1]+2):
                    raise JobBlocked('露天退出核验期间位置或投影改变，保持当前位置')
                continue
            p=actual
            if not any(not _below_vertical_start(row,p) for row in column):
                target=[actual[0],max(actual[1]+1,high[1]+3.0),actual[2]]
                _air_move(client,target,90)
                final=client.status()['pos']
                if final[1]<=high[1]+2:
                    raise JobBlocked('实际位置尚未升出投影高度，不继续移动')
                write_json(client.out/('exit-%d.json'%time.time_ns()),{'mode':'verified_open_sky_column',
                           'world_session':client.world,'from':p,'waypoints':[target],'actual':final,'confirmed':True})
                return
    floor, head = math.floor(p[1]), math.floor(p[1]+1.8-1e-7)
    lo, hi = [low[0]-4, floor, low[2]-4], [high[0]+4, head, high[2]+4]
    if math.prod(hi[i]-lo[i]+1 for i in range(3)) > 50000:
        raise JobBlocked('建筑出口扫描范围过大，需要已有通道')
    rows = [{**row,'passable':False} for row in _air_scan(client,lo,hi)]
    route = horizontal_exit(rows, p, low, high, lo, hi)
    write_json(client.out / ('exit-%d.json' % time.time_ns()), route)
    for waypoint in route['waypoints']:
        if math.dist(client.status()['pos'], waypoint) < .35:
            continue
        _air_move(client, waypoint, 20)
        actual = client.status()['pos']
        if abs(actual[1]-p[1]) > .4 or math.dist(actual, waypoint) > .9:
            raise JobBlocked('建筑出口实际位置与已扫描路径不符')


def _escape_local_canopy(client):
    """Follow a scanned local ground corridor to an open sky column when a tree blocks ascent."""
    from wood_expedition import sky_path
    state=settled_state(client)
    x,y,z=map(math.floor,state['pos'])
    reply=client.request('scan',min=[x-12,y-4,z-12],max=[x+12,y+39,z+12],details=True)
    if (reply.get('phase') not in (None,'done') or reply.get('world_session')!=client.world
            or not isinstance(reply.get('blocks'),list)):
        raise JobBlocked('树冠退出扫描尚未完整确认')
    # Reuse the surveyed ground planner, without constructing a wood job or
    # borrowing its inventory target/route journal. Unknown or wet supports
    # cannot become walking ground.
    rows=[{**row,'solid':row.get('solid') is True and row.get('fluid') is False
                         and row.get('block_entity') is False,
           'passable':row.get('passable') is True and row.get('fluid') is False}
          for row in reply['blocks']]
    path=sky_path(rows,state['pos'])
    if not path:raise JobBlocked('树冠附近没有已核验的地面出口')
    for point in path:
        current=settled_state(client)
        if math.dist(current['pos'],point)<.25:continue
        client.checked('walk',target=point,arrival=.2,seconds=12)
        settled_state(client,point,.4)
    actual=settled_state(client)
    write_json(client.out/('canopy-exit-%d.json'%time.time_ns()),
               {'world_session':client.world,'from':state['pos'],'waypoints':path,
                'actual':actual['pos'],'parking_confirmed':False})
    # local_park performs the full-height column proof at this actual exit,
    # then chooses the normal local height instead of a fixed Y=140 flight.
    return actual


def _escape_open_trapdoor(client, state, column):
    """One normal ground step beside an open trapdoor; never toggle or mine it."""
    from .acquisition import block_id
    start=list(state['pos']);x,y,z=map(math.floor,start)
    obstacles=[r for r in column if r['pos'][1]>=y and not r.get('passable',True)]
    if (not obstacles or any(not block_id(r).endswith('_trapdoor')
            or 'open=true' not in r.get('state','') or 'waterlogged=false' not in r.get('state','')
            or r.get('fluid') is not False or r.get('block_entity') is not False for r in obstacles)):
        return None
    if (state.get('world_session')!=client.world or state.get('manual_movement')
            or state.get('health',0)<19 or state.get('under_water') or state.get('guard_busy')
            or not state.get('guard_armed') or not state.get('guard_pve_only')):
        raise JobBlocked('活板门旁绕行的角色或防护状态未确认')
    low,high=[x-1,y-1,z-1],[x+1,319,z+1]
    reply=client.request('scan',min=low,max=high,details=True)
    if (reply.get('phase') not in (None,'done') or reply.get('world_session')!=client.world
            or not isinstance(reply.get('blocks'),list)):
        raise JobBlocked('活板门附近落脚与完整升空列尚未确认')
    cells={}
    for row in reply['blocks']:
        p=row.get('pos')
        if (not isinstance(p,list) or len(p)!=3 or any(type(v)is not int for v in p)
                or any(not low[i]<=p[i]<=high[i]for i in range(3)) or tuple(p)in cells):
            raise JobBlocked('活板门旁绕行扫描含未知、重复或越界格')
        cells[tuple(p)]=row
    if any(cells.get(tuple(r['pos']),{}).get('state')!=r['state']for r in obstacles):
        raise JobBlocked('活板门在出口扫描期间变化；保留现场')
    target=None
    for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
        cx,cz=x+dx,z+dz;floor=cells.get((cx,y-1,cz),{})
        if (floor.get('solid')is True and floor.get('fluid')is False
                and floor.get('block_entity')is False
                and not any(p[0]==cx and p[2]==cz and p[1]>=y for p in cells)):
            target=[cx+.5,float(y),cz+.5];break
    if target is None:
        raise JobBlocked('打开的活板门旁没有一格干燥落脚和完整露天列')
    fresh=settled_state(client)
    if (fresh.get('world_session')!=client.world or math.dist(fresh['pos'],start)>.2
            or fresh.get('manual_movement') or fresh.get('health',0)<19
            or not fresh.get('guard_armed') or not fresh.get('guard_pve_only')):
        raise JobBlocked('活板门旁一步绕行前位置或防护已变化')
    # Normal walking checks the actual partial collision shape. The destination
    # has a full dry floor; this does not pretend the trapdoor voxel is air.
    client.checked('walk',target=target,arrival=.25,seconds=12,restore_flight=False)
    actual=settled_state(client,target,.55)
    if actual.get('health',0)<19 or actual.get('world_session')!=client.world:
        raise JobBlocked('活板门旁绕行后的角色状态变化，不继续上升')
    write_json(client.out/('open-trapdoor-exit-%d.json'%time.time_ns()),{
        'world_session':client.world,'from':start,'target':target,'actual':actual['pos'],
        'door_states_preserved':True,'normal_walk_confirmed':True,'parking_confirmed':False})
    return actual


def _park_column(client,state):
    """Scan every column touched by the real player body, including cell edges."""
    p=state['pos']
    low=[math.floor(p[0]-.31),-64,math.floor(p[2]-.31)]
    high=[math.floor(p[0]+.31),319,math.floor(p[2]+.31)]
    reply=client.request('scan',min=low,max=high,details=True)
    if (reply.get('phase')not in (None,'done')or reply.get('world_session')!=client.world
            or not isinstance(reply.get('blocks'),list)):
        raise JobBlocked('实际身体覆盖的升空列尚未确认')
    return reply['blocks']


def local_park(client):
    """Pick the current column after exiting the hull; no fixed return flight."""
    leave_projection(client)
    state = settled_state(client)
    x, z = math.floor(state['pos'][0]), math.floor(state['pos'][2])
    rows = _park_column(client,state)
    escaped=_escape_open_trapdoor(client,state,rows)
    if escaped is not None:
        state=escaped;x,z=math.floor(state['pos'][0]),math.floor(state['pos'][2])
        rows=_park_column(client,state)
    top = max((r['pos'][1]+1 for r in rows if r.get('fluid') or not r.get('passable', True)), default=None)
    if top is None or top+24 >= 319:
        raise JobBlocked('没有可核验的安全停靠高度')
    if state['pos'][1] < top and any(r['pos'][1] >= math.floor(state['pos'][1])
                                    and (r.get('fluid')or not r.get('passable',True))
                                    and not _below_vertical_start(r,state['pos'])for r in rows):
        # A canopy may cover the exact trunk column even though a nearby
        # surveyed ground route and open sky are available. Don't log out there.
        state=_escape_local_canopy(client)
        x,z=math.floor(state['pos'][0]),math.floor(state['pos'][2])
        rows=_park_column(client,state)
        top=max((r['pos'][1]+1 for r in rows if r.get('fluid') or not r.get('passable',True)),default=None)
        if top is None or top+24>=319 or state['pos'][1]<top:
            raise JobBlocked('绕出树冠后仍没有已验证的本地高空停靠路线')
    fresh=settled_state(client)
    if math.dist(fresh['pos'],state['pos'])>.3:
        raise JobBlocked('停靠扫描期间位置发生变化，不能沿旧坐标升空')
    # Keep a one-block upward reserve for the next client tick. The host still
    # verifies the actual clear path and safe altitude, without relaxing scope.
    return [fresh['pos'][0], max(fresh['pos'][1]+1, top+24), fresh['pos'][2]]


def lift_for_travel(client):
    """Take off through the same verified column used by healthy cleanup.

    A chest's real .875-high collision surface is safe to stand on, while the
    padded voxel corridor deliberately treats the chest block as an obstacle.
    Do the native collision-aware vertical takeoff before that corridor check.
    """
    point = local_park(client)
    state = settled_state(client)
    if (state.get('flight') is True and not state.get('on_ground')
            and math.dist(state['pos'],point)<=1.000001):
        return state
    client.checked('navigate',target=point,arrival=.25,air_only=True,seconds=90)
    return settled_state(client,point,.6)


def outside_station(client, selection):
    low, high = selection['min'], selection['max']
    p = client.status()['pos']
    y = max(low[1]+2, min(high[1]+2, p[1]))
    centers = [[high[0]+3.5, y, (low[2]+high[2]+1)/2],
               [low[0]-2.5, y, (low[2]+high[2]+1)/2],
               [(low[0]+high[0]+1)/2, y, high[2]+3.5],
               [(low[0]+high[0]+1)/2, y, low[2]-2.5]]
    for candidate in sorted(centers, key=lambda v: math.dist(v, p)):
        lo = [math.floor(candidate[0])-1, math.floor(candidate[1])-1, math.floor(candidate[2])-1]
        hi = [lo[0]+2, lo[1]+4, lo[2]+2]
        rows = client.request('scan', min=lo, max=hi, details=True)['blocks']
        if any(r.get('fluid') or not r.get('passable', False) for r in rows):
            continue
        _air_move(client, candidate, 90)
        return candidate
    raise JobBlocked('投影外侧没有可用施工站位')
