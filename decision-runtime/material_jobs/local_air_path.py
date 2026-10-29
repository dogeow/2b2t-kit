"""Small three-dimensional air routes from complete current-world scans; no mining."""
from collections import deque
import math
from pathlib import Path

from kit_runtime.journal import write_json
from .protocol import JobBlocked
from .navigation import _air_scan, _air_move, _body_sweep, _below_vertical_start


class ObservedAirPathBlocked(JobBlocked):
    """A complete body scan blocked the next leg before movement was sent."""
    def __init__(self,journal):
        super().__init__('局部空气通道发生变化，未继续移动')
        self.journal=Path(journal)


def native_cone_edge_candidate(rows,start,target):
    """Only admit a tiny dry-cone edge to the native real-shape collision gate."""
    from .acquisition import block_id
    from projection_completion import block_state
    return (bool(rows) and math.hypot(target[0]-start[0],target[2]-start[2])<=.5
            and abs(target[1]-start[1])<=.25
            and math.floor(start[1])==math.floor(target[1])
            and all(abs(target[i]-(math.floor(target[i])+.5))<=.300001 for i in (0,2))
            and all(block_id(row)=='minecraft:pointed_dripstone' and row.get('fluid')is False
                    and row.get('block_entity')is False
                    and block_state(row['state'])[1].get('waterlogged')=='false' for row in rows))


def plan(rows, start, target, low, high, *, max_straight=16, foot_offset=0):
    if type(max_straight)is not int or not 1<=max_straight<=16:
        raise JobBlocked('局部空气路线步长必须在1至16格之间')
    if type(foot_offset)not in(int,float) or not math.isfinite(foot_offset) or not 0<=foot_offset<=.2:
        raise JobBlocked('局部空气路线脚部余量必须在0至0.2格之间')
    blocked={tuple(r['pos'])for r in rows}
    # Fences and walls have a 1.5-block collision shape. Their upper half is
    # inside the voxel above the stored block; sparse air there is not clear.
    from .acquisition import block_id
    for row in rows:
        if block_id(row).endswith(('_fence','_fence_gate','_wall')):
            x,y,z=row['pos'];blocked.add((x,y+1,z))
    first=tuple(math.floor(v)for v in start);last=tuple(math.floor(v)for v in target)
    # Standing on a verified partial collision surface is not standing inside
    # its full voxel. Start above that surface; do not lower feet to grid+.2.
    if any(tuple(r['pos'])==first and _below_vertical_start(r,start)for r in rows):
        first=(first[0],first[1]+1,first[2])
    elif(start[1]-(first[1]+foot_offset)>.2 and any(
            tuple(r['pos'])==(first[0],first[1]-1,first[2])and r.get('fluid')is True for r in rows)):
        # Do not normalize a high hover down to grid+.1 above water. Flight
        # settling can dip that waypoint into the fluid before the real route.
        first=(first[0],first[1]+1,first[2])
    def clear(q):
        x,y,z=q
        return (low[0]<=x<=high[0]and low[1]<=y<high[1]and low[2]<=z<=high[2]
                and q not in blocked and(x,y+1,z)not in blocked)
    if not clear(first)or not clear(last):raise JobBlocked('局部空气路线起点或终点未完整确认')
    parents={first:None};queue=deque([first])
    while queue:
        q=queue.popleft()
        if q==last:break
        for d in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
            nxt=tuple(a+b for a,b in zip(q,d))
            if nxt not in parents and clear(nxt):parents[nxt]=q;queue.append(nxt)
    if last not in parents:raise JobBlocked('已存在空气空间没有连通，不挖掘新通道')
    path=[];q=last
    while q is not None:path.append(q);q=parents[q]
    path.reverse()
    if len(path)>128:raise JobBlocked('局部空气路线过长，保留现场')
    # Keep turns, and divide long straight stretches into ordinary short moves.
    kept=[path[0]];previous=None
    for i in range(1,len(path)):
        direction=tuple(path[i][a]-path[i-1][a]for a in range(3))
        if previous is not None and direction!=previous and kept[-1]!=path[i-1]:kept.append(path[i-1])
        if math.dist(kept[-1],path[i])>=max_straight:kept.append(path[i])
        previous=direction
    if kept[-1]!=path[-1]:kept.append(path[-1])
    # At most .2 fits a 1.8-block player inside the same two proved air cells.
    # A supported route uses this margin because Flight restoration can settle
    # below an integer target and make the next sweep intersect the floor.
    return [[x+.5,y+foot_offset,z+.5]for x,y,z in kept]


def move(client,target,out,*,max_straight=16,foot_offset=0,max_horizontal=12,exact_target=False,scan_bounds=None,
         allow_dry_cone_edge=False,allow_surface_lift=True):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    start=client.status()['pos']
    if (type(exact_target)is not bool or type(allow_dry_cone_edge)is not bool
            or type(allow_surface_lift)is not bool or allow_dry_cone_edge and not exact_target
            or type(max_horizontal)not in(int,float)or not math.isfinite(max_horizontal)or not 1<=max_horizontal<=24
            or not isinstance(target,list)or len(target)!=3
            or any(type(v)not in(int,float)or not math.isfinite(v)for v in target)
            or math.hypot(target[0]-start[0],target[2]-start[2])>max_horizontal
            or abs(target[1]-start[1])>64):raise JobBlocked('局部空气接近点超出有界范围')
    low=[math.floor(min(start[0],target[0]))-3,max(-64,math.floor(min(start[1],target[1]))-2),math.floor(min(start[2],target[2]))-3]
    high=[math.floor(max(start[0],target[0]))+3,min(319,math.floor(max(start[1],target[1]))+3),math.floor(max(start[2],target[2]))+3]
    if scan_bounds is not None:
        if (not isinstance(scan_bounds,dict) or set(scan_bounds)!={'min','max'}
                or any(not isinstance(scan_bounds[k],list) or len(scan_bounds[k])!=3
                       or any(type(v)is not int for v in scan_bounds[k])for k in ('min','max'))):
            raise JobBlocked('显式空气扫描范围必须是完整整数边界')
        low,high=list(scan_bounds['min']),list(scan_bounds['max'])
        body_low,body_high=_body_sweep(start,target)
        if (low[1]<-64 or high[1]>319 or any(low[i]>high[i]for i in range(3))
                or not all(low[i]<=body_low[i]<=body_high[i]<=high[i]for i in range(3))):
            raise JobBlocked('显式空气扫描范围没有覆盖实际起终点身体')
    if math.prod(high[i]-low[i]+1 for i in range(3))>30000:raise JobBlocked('局部空气扫描超出有界范围')
    path=plan(_air_scan(client,low,high),start,target,low,high,max_straight=max_straight,foot_offset=foot_offset)
    if exact_target and path[-1]!=target:path.append(list(target))
    file=Path(out)/'local-air-path.json'
    if file.exists():raise JobBlocked('原空气路线回执必须保留，不重放')
    book={'world_session':client.world,'start':start,'target':target,'path':path,
          'pending':None,'moves':[],'complete':False,'mining_sent':False,'foot_offset':foot_offset,'exact_target':exact_target,
          'scan_bounds':{'min':low,'max':high},'allow_dry_cone_edge':allow_dry_cone_edge}
    write_json(file,book)
    for index,point in enumerate(path):
        precise=exact_target and index==len(path)-1
        actual=client.status()['pos']
        # A .2 feet margin has no room for native navigation's .05 vertical
        # settling error below a two-block ceiling. Recenter a high starting
        # hover before its first horizontal leg when the caller reserves .1.
        if (index==0 and 0<foot_offset<.2 and math.floor(actual[1])==math.floor(point[1])
                and math.hypot(actual[0]-point[0],actual[2]-point[2])<=.15
                and actual[1]-point[1]>.08):precise=True
        if not precise and math.dist(actual,point)<.15:continue
        # Restoring Flight can settle a supported .2-margin waypoint by .15
        # blocks. It is still inside the same proved body cells; centering the
        # start again adds a full movement without improving the next sweep.
        if (not precise and foot_offset and math.dist(actual,point)<=.3
                and abs(actual[0]-point[0])<=.18 and abs(actual[2]-point[2])<=.18
                and all(math.floor(actual[i])==math.floor(point[i])for i in range(3))):continue
        occupied=_air_scan(client,*_body_sweep(actual,point))
        if point[1]>=actual[1]:occupied=[r for r in occupied if not _below_vertical_start(r,actual)]
        cone_probe=precise and allow_dry_cone_edge and native_cone_edge_candidate(occupied,actual,point)
        if occupied and not cone_probe:
            book['blocked_before_next_move']={'target':point,'actual':actual,'blocks':occupied}
            write_json(file,book)
            # A known pre-send foot-water blockage is different from an
            # uncertain movement. Recover through the separately checked
            # water-capable primitive, then scan a new dry route once. Never
            # relabel the observed water as AIR or relax collision checks.
            water={'Block{minecraft:water}[level='+str(n)+']'for n in range(16)}
            dry_floor=math.floor(actual[1])+1
            if (allow_surface_lift and target[1]>=dry_floor+.5
                    and math.hypot(target[0]-actual[0],target[2]-actual[2])<=.15
                    and point[1]>actual[1]
                    and all(r.get('state')in water and r.get('fluid')is True
                            and r.get('block_entity')is False
                            and r['pos'][1]==math.floor(actual[1])for r in occupied)
                    and getattr(client,'native_inflight',None)is None
                    and getattr(client,'unconfirmed_native_request',None)is None):
                from .construction_breathing import lift_surface_feet
                lift_surface_feet(client,client.status())
                child=Path(out)/'after-surface-lift'
                result=move(client,target,child,max_straight=max_straight,foot_offset=foot_offset,
                            max_horizontal=max_horizontal,exact_target=exact_target,scan_bounds=scan_bounds,
                            allow_dry_cone_edge=allow_dry_cone_edge,allow_surface_lift=False)
                book.update(complete=result['complete'],actual=result['actual'],
                            replaced_after_verified_surface_lift=True,replacement_route=str(child/'local-air-path.json'))
                write_json(file,book)
                return book
            raise ObservedAirPathBlocked(file)
        book['pending']={'target':point};write_json(file,book)
        if cone_probe:
            # Do not call an occupied voxel air. The unchanged native air_only
            # admission and every-tick noCollision check must prove real shapes.
            book['pending']['native_real_shape_gate_required']=True;write_json(file,book)
        if precise:
            _air_move(client,point,45,arrival=.08)
        elif foot_offset:
            _air_move(client,point,45,arrival=.2)
        else:
            _air_move(client,point,45)
        book['moves'].append({'target':point,'actual':client.status()['pos'],'request_id':client.last,
                              'native_real_shape_gate_required':bool(cone_probe)})
        book['pending']=None;write_json(file,book)
    book.update(complete=True,actual=client.status()['pos']);write_json(file,book)
    return book


def move_replanning_once(client,target,out,**kwargs):
    """One new route from actual rest after an exact known pre-move blockage."""
    import json
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    try:return move(client,target,out/'attempt-0',**kwargs)
    except ObservedAirPathBlocked as blocked:
        if (getattr(client,'native_inflight',None)is not None
                or getattr(client,'unconfirmed_native_request',None)is not None):raise
        current=client.status();prior=json.loads(blocked.journal.read_text())
        if (current.get('world_session')!=client.world or current.get('manual_movement')
                or prior.get('world_session')!=client.world or prior.get('pending')is not None
                or not prior.get('blocked_before_next_move')):raise
        write_json(out/'replan.json',{'world_session':client.world,'from_actual':current['pos'],
            'target':target,'prior_journal':str(blocked.journal),'blocked_scan_request':client.last,
            'prior_actions_replayed':False,'remaining_replans':0})
        return move(client,target,out/'attempt-1',**kwargs)
