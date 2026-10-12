"""Return through an existing shaft using coordinates as hints and fresh air proof."""
from collections import deque
import math
import time

from kit_runtime.journal import write_json
from .protocol import JobBlocked,server_key
from .navigation import (_bounds,_body_sweep,_air_scan,_air_move,_inside_shaft,
                         _shaft_column,settled_state)


def candidates(profile,state):
    if (state.get('dimension')!=profile.get('dimension')
            or server_key(state.get('server'))!=server_key(profile.get('server'))):return []
    hints=profile.get('quarry_exit_hints',[])
    if not isinstance(hints,list)or len(hints)>16:raise JobBlocked('登记采坑出口列表不完整')
    position=state['pos'];found=[]
    for hint in hints:
        if not isinstance(hint,dict)or hint.get('world_session')!=state.get('world_session'):continue
        shaft=_bounds(hint.get('shaft'));box=_bounds(hint)
        surface=hint.get('surface_y')
        if not shaft or not box or type(surface)is not int:continue
        low,high=box;sl,sh=shaft
        if (hint.get('source')!='natural_survey' or sh[0]-sl[0]!=1 or sh[2]-sl[2]!=1
                or not -64<=low[1]<=high[1]<sl[1]<=sh[1]==surface<=314
                or not all(low[i]<=sl[i]<=sh[i]<=high[i]for i in(0,2))):continue
        if (not low[1]-2<=position[1]<surface+2
                or max(abs(position[i]-(sl[i]+1))for i in(0,2))>32):continue
        found.append(hint)
    return sorted(found,key=lambda h:math.hypot(position[0]-h['shaft']['min'][0]-1,
                                               position[2]-h['shaft']['min'][2]-1))


def path_to_shaft(rows,column_rows,position,shaft,surface,low,high):
    """Bounded 3D air BFS; supports existing tunnel steps without removing blocks."""
    blocked={tuple(row['pos'])for row in rows};column={tuple(row['pos'])for row in column_rows}
    start=tuple(math.floor(v)for v in position);fraction=position[1]-start[1]
    def point(node):return[node[0]+.5,node[1]+fraction,node[2]+.5]
    def clear(a,b):
        lo,hi=_body_sweep(a,b)
        return(all(low[i]<=lo[i]<=hi[i]<=high[i]for i in range(3))
               and not any(tuple(p)in blocked for p in _cells(lo,hi)))
    def goal(node):
        if not all(shaft['min'][i]<=node[i]<=shaft['max'][i]for i in(0,2)):return False
        if point(node)[1]>surface+3 or _body_sweep(point(node),point(node))[1][1]>surface+5:return False
        lo,hi=_shaft_column(point(node),surface)
        return not any(tuple(p)in column for p in _cells(lo,hi))
    if not clear(position,point(start)):raise JobBlocked('当前位置到通道中心不是已核验空气')
    queue=deque([start]);parents={start:None};depth={start:0};end=None
    while queue:
        node=queue.popleft()
        if goal(node):end=node;break
        if depth[node]>=96:continue
        for axis,delta in ((0,1),(0,-1),(2,1),(2,-1),(1,1),(1,-1)):
            nxt=list(node);nxt[axis]+=delta;nxt=tuple(nxt)
            if nxt not in parents and clear(point(node),point(nxt)):
                parents[nxt]=node;depth[nxt]=depth[node]+1;queue.append(nxt)
    if end is None:raise JobBlocked('当前空气通道没有连到登记竖井，不挖新通道')
    route=[]
    while end is not None:route.append(point(end));end=parents[end]
    return _compact(list(reversed(route)))


def _cells(low,high):
    return((x,y,z)for x in range(low[0],high[0]+1)for y in range(low[1],high[1]+1)
           for z in range(low[2],high[2]+1))


def _compact(route):
    """Retain every bend, grouping only collinear air points within 30 blocks."""
    result=[]
    for point in route:
        if len(result)>=2:
            a,b=result[-2:];old=tuple(b[i]-a[i]for i in range(3));new=tuple(point[i]-b[i]for i in range(3))
            if (sum(v!=0 for v in old)==1 and sum(v!=0 for v in new)==1
                    and all((u==0)==(v==0)and u*v>=0 for u,v in zip(old,new))
                    and math.dist(a,point)<=30):result[-1]=point;continue
        result.append(point)
    return result


def _fresh_air(client,low,high):
    rows=_air_scan(client,low,high);seen=set()
    for row in rows:
        pos=row.get('pos')if isinstance(row,dict)else None
        if (not isinstance(pos,list)or len(pos)!=3 or any(type(v)is not int for v in pos)
                or tuple(pos)in seen or any(not low[i]<=pos[i]<=high[i]for i in range(3))):
            raise JobBlocked('采坑出口方块坐标不完整，保留当前位置')
        seen.add(tuple(pos))
    return rows


def leave(client,profile):
    state=client.status();hints=candidates(profile,state)
    if not hints:return False
    if (state.get('air_only_navigation_protocol',0)<2 or state.get('health',0)<19
            or state.get('under_water')or state.get('manual_movement')or not state.get('guard_armed')
            or not state.get('flight')):raise JobBlocked('登记采坑退出需要当前健康防护和空气导航')
    from .acquisition import _safe
    _safe(state)
    start=list(state['pos']);hint=hints[0];shaft=hint['shaft'];surface=hint['surface_y'];y=math.floor(start[1])
    low=[min(math.floor(start[0]),shaft['min'][0])-2,max(-64,y-4),min(math.floor(start[2]),shaft['min'][2])-2]
    high=[max(math.floor(start[0]),shaft['max'][0])+2,min(319,y+6),max(math.floor(start[2]),shaft['max'][2])+2]
    column_low=[shaft['min'][0],low[1],shaft['min'][2]]
    column_high=[shaft['max'][0],surface+5,shaft['max'][2]]
    rows=_fresh_air(client,low,high);columns=_fresh_air(client,column_low,column_high)
    fresh=client.status()
    _safe(fresh)
    if math.dist(fresh['pos'],start)>.25:raise JobBlocked('采坑出口扫描期间角色位置改变')
    route=path_to_shaft(rows,columns,start,shaft,surface,low,high)
    journal=client.out/('registered-quarry-exit-%d.json'%time.time_ns())
    book={'schema':1,'world_session':client.world,'hint':hint,'clearance_credit':0,
          'from':start,'route':route,'confirmed_steps':[],'pending':None,'complete':False}
    write_json(journal,book)
    for point in route:
        current=client.status();_safe(current);actual=current['pos']
        if math.dist(actual,point)<.15:continue
        if _fresh_air(client,*_body_sweep(actual,point)):raise JobBlocked('登记采坑通道发生变化，不继续原路线')
        book['pending']={'target':point};write_json(journal,book)
        _air_move(client,point,45)
        book['confirmed_steps'].append({'target':point,'actual':client.status()['pos']})
        book['pending']=None;write_json(journal,book)
    current=client.status();_safe(current);actual=current['pos']
    if not _inside_shaft(actual,shaft):raise JobBlocked('身体尚未完全进入登记竖井，不在外侧升空')
    lo,hi=_shaft_column(actual,surface)
    if _fresh_air(client,lo,hi):raise JobBlocked('登记竖井上升空间发生变化')
    current=client.status();_safe(current);fresh=current['pos']
    if math.dist(fresh,actual)>.25 or not _inside_shaft(fresh,shaft):raise JobBlocked('扫描后角色离开已核验竖井')
    target=[fresh[0],surface+3.,fresh[2]];book['pending']={'target':target};write_json(journal,book)
    _air_move(client,target,120)
    book.update(pending=None,complete=True,actual=client.status()['pos']);write_json(journal,book)
    return True
