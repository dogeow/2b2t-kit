"""Exit a small three-dimensional projection through observed air only."""
from collections import deque
import copy
import json
import math
import time

from kit_runtime.journal import write_json
from .protocol import JobBlocked


def supported_door_leg(rows,start,target,low,high):
    """A short normal walk after a supported door crossing settles at an edge."""
    from survival_world import World,center,cell
    if (abs(start[1]-round(start[1]))>.08 or math.floor(target[1])!=round(start[1])
            or math.hypot(target[0]-start[0],target[2]-start[2])>2):return None
    world=World(rows,low,high);first=cell(start);end=cell(target)
    if not world.stand(first)or not world.stand(end):return None
    paths=world.paths(start,limit=128)
    if end not in paths:return None
    route=world.route(paths,end)
    if not route or len(route)>4:return None
    for x,y,z in [first]+route:
        floor=world.row((x,y-1,z))
        if (y!=first[1]or not floor.get('solid')or floor.get('fluid')is not False
                or floor.get('block_entity')is not False
                or any(world.name((x,h,z))not in('air','cave_air','void_air')for h in(y,y+1))):return None
    return [center(point)for point in route]


def plan_exit(rows, start, low, high, scan_low, scan_high):
    from .local_air_path import plan
    from .navigation import _below_vertical_start
    blocked = {tuple(row['pos']) for row in rows}
    from .acquisition import block_id
    for row in rows:
        if block_id(row).endswith(('_fence','_fence_gate','_wall')):
            x,y,z=row['pos'];blocked.add((x,y+1,z))
    first = tuple(math.floor(v) for v in start)
    if any(tuple(row['pos']) == first and _below_vertical_start(row, start) for row in rows):
        first = (first[0], first[1] + 1, first[2])
    def clear(q):
        return (all(scan_low[i] <= q[i] <= scan_high[i] for i in range(3))
                and q[1] < scan_high[1] and q not in blocked
                and (q[0], q[1]+1, q[2]) not in blocked)
    def outside(q):
        return q[1] > high[1]+2 or any(q[i] < low[i]-1 or q[i] > high[i]+1 for i in (0, 2))
    if not clear(first):
        raise JobBlocked('三维建筑出口起点不是已确认空气')
    queue = deque([first]); seen = {first}; end = None
    while queue:
        q = queue.popleft()
        if outside(q):
            end = q; break
        for delta in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
            nxt = tuple(a+b for a,b in zip(q, delta))
            if nxt not in seen and clear(nxt):
                seen.add(nxt); queue.append(nxt)
    if end is None:
        raise JobBlocked('建筑内没有已确认的三维空气出口，保留房屋结构')
    return plan(rows, start, [end[0]+.5,end[1]+.1,end[2]+.5], scan_low, scan_high,
                max_straight=8, foot_offset=.1)


def leave(client, state, *, max_straight=8):
    if type(max_straight)is not int or not 1<=max_straight<=8:
        raise ValueError('Building exit legs must be one to eight blocks')
    from .navigation import _air_scan, settled_state
    from .local_air_path import move,ObservedAirPathBlocked
    selection = state['projection_selection']; low = selection['min']; high = selection['max']
    if high[1] <= low[1]:
        return False
    scan_low = [low[0]-4,max(-64,low[1]-2),low[2]-4]
    scan_high = [high[0]+4,min(319,high[1]+6),high[2]+4]
    if math.prod(b-a+1 for a,b in zip(scan_low,scan_high)) > 50000:
        return False
    scope = (state.get('world_session'),copy.deepcopy(selection))
    def current():
        fresh = settled_state(client)
        if ((fresh.get('world_session'),fresh.get('projection_selection')) != scope
                or fresh.get('control_revision') != getattr(client,'rev',state.get('control_revision'))):
            raise JobBlocked('三维建筑退出期间世界、控制或投影改变')
        return fresh
    current()
    out = client.out / ('exit-3d-%d' % time.time_ns())
    out.mkdir(exist_ok=False)
    book = {'world_session':client.world,'start':state['pos'],'paths':[],
            'complete':False,'mining_sent':False,'pending':None,'doors':[],
            'max_straight':max_straight}
    write_json(out/'route.json',book)
    visited = set()
    for turn in range(5):
        current()
        rows = _air_scan(client, scan_low, scan_high)
        fresh = current()
        # A supported walk can coast slightly after restoring Flight. This is
        # a complete room scan, not a narrow column anchored to the old pose.
        # Plan from the current body only while it remains inside that scan.
        from .navigation import _body_sweep
        body_low,body_high=_body_sweep(fresh['pos'],fresh['pos'])
        if not all(scan_low[i]<=body_low[i]<=body_high[i]<=scan_high[i] for i in range(3)):
            raise JobBlocked('三维建筑退出当前位置已离开完整扫描范围')
        door = None
        try:
            path = plan_exit(rows,fresh['pos'],low,high,scan_low,scan_high)
        except JobBlocked as error:
            if '三维空气出口' not in str(error):raise
            path,door = door_prefix(rows,fresh['pos'],low,high,scan_low,scan_high)
            if turn==4 or tuple(door) in visited:raise JobBlocked('建筑穿门退出超出有界范围')
        book['paths'].append(path);write_json(out/'route.json',book)
        for index, point in enumerate(path):
            actual = current()['pos']
            if math.dist(actual,point) <= .3:continue
            book['pending'] = {'target':point,'turn':turn,'index':index}; write_json(out/'route.json',book)
            # Every air leg is scanned again. A door voxel is never dispatched
            # as air; the existing normal supported crossing owns that step.
            try:
                move(client,point,out/('turn-%02d-leg-%03d'%(turn,index)),max_straight=max_straight,foot_offset=.1)
            except ObservedAirPathBlocked as error:
                if (not book['doors']or getattr(client,'native_inflight',None)is not None
                        or getattr(client,'unconfirmed_native_request',None)is not None):raise
                rejected=json.loads(error.journal.read_text())
                if (rejected.get('world_session')!=client.world or rejected.get('pending')is not None
                        or not rejected.get('blocked_before_next_move')):raise
                # The door walk can settle .2 back from its reported centre.
                # Keep the strict air sweep. A new, supported ground walk may
                # centre the body away from that step/door edge instead.
                fresh=current();ground_rows=_air_scan(client,scan_low,scan_high);fresh=current()
                route=supported_door_leg(ground_rows,fresh['pos'],point,scan_low,scan_high)
                if route is None:raise
                book.setdefault('known_air_rejections',[]).append({'journal':str(error.journal),
                    'actual':fresh['pos'],'target':point,'native_air_movement_sent':False})
                for step in route:
                    current();book['pending']={'supported_door_walk':step};write_json(out/'route.json',book)
                    try:client.checked('walk',target=step,arrival=.08,seconds=10,restore_flight=True)
                    finally:
                        book['pending']['request_id']=getattr(client,'last',None);write_json(out/'route.json',book)
                    actual=current()['pos']
                    if math.dist(actual,step)>.35:raise JobBlocked('穿门后的有地板步行未到达原空气出口路线')
            book['pending'] = None; write_json(out/'route.json',book)
        if door is None:break
        from door_access import cross_door
        current();book['pending']={'door':door};write_json(out/'route.json',book)
        result=cross_door(client,door)
        book['doors'].append(result);book['pending']=None;write_json(out/'route.json',book)
        visited.add(tuple(door))
    actual = current()['pos']
    if not (actual[1]>high[1]+2 or any(actual[i]<low[i]-1 or actual[i]>high[i]+1 for i in (0,2))):
        raise JobBlocked('三维建筑出口实际位置仍在投影内')
    book.update(complete=True,actual=actual); write_json(out/'route.json',book)
    return True


def door_prefix(rows,start,low,high,scan_low,scan_high):
    """Plan only up to a paired wooden door; normal interaction crosses it."""
    from door_access import WOOD_DOORS
    from projection_completion import block_state
    from .local_air_path import plan
    cells={tuple(row['pos']):row for row in rows};doors={}
    for pos,row in cells.items():
        name,props=block_state(row.get('state',''))
        if (name not in WOOD_DOORS or props.get('half')!='lower' or props.get('powered')!='false'
                or row.get('fluid') is not False or not all(low[i]<=pos[i]<=high[i] for i in range(3))):continue
        upper=(pos[0],pos[1]+1,pos[2]);other=cells.get(upper,{})
        upper_name,upper_props=block_state(other.get('state',''))
        if (upper_name!=name or upper_props!={**props,'half':'upper'} or other.get('fluid') is not False):continue
        doors[pos]=pos;doors[upper]=pos
    virtual=[row for row in rows if tuple(row['pos']) not in doors]
    path=plan_exit(virtual,start,low,high,scan_low,scan_high)
    expanded=[tuple(math.floor(v) for v in path[0])]
    for point in path[1:]:
        end=tuple(math.floor(v) for v in point)
        while expanded[-1]!=end:
            q=expanded[-1];axis=next(i for i in range(3) if q[i]!=end[i])
            nxt=list(q);nxt[axis]+=1 if end[axis]>q[axis] else -1;expanded.append(tuple(nxt))
    for index,q in enumerate(expanded):
        hit=doors.get(q) or doors.get((q[0],q[1]+1,q[2]))
        if hit:
            if not index or q[1]!=hit[1]:raise JobBlocked('木门前没有已确认的正常穿行姿态')
            previous=expanded[index-1]
            prefix=plan(rows,start,[previous[0]+.5,previous[1]+.1,previous[2]+.5],
                        scan_low,scan_high,max_straight=8,foot_offset=.1)
            return prefix,list(hit)
    raise JobBlocked('建筑没有已确认的木门出口，保留房屋结构')
