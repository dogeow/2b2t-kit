"""Small three-dimensional air routes from complete current-world scans; no mining."""
from collections import deque
import math
from pathlib import Path

from kit_runtime.journal import write_json
from .protocol import JobBlocked
from .navigation import _air_scan, _air_move, _body_sweep


def plan(rows, start, target, low, high):
    blocked={tuple(r['pos'])for r in rows}
    first=tuple(math.floor(v)for v in start);last=tuple(math.floor(v)for v in target)
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
        if math.dist(kept[-1],path[i])>=16:kept.append(path[i])
        previous=direction
    if kept[-1]!=path[-1]:kept.append(path[-1])
    return [[x+.5,y,z+.5]for x,y,z in kept]


def move(client,target,out):
    start=client.status()['pos']
    if (not isinstance(target,list)or len(target)!=3
            or any(type(v)not in(int,float)or not math.isfinite(v)for v in target)
            or math.hypot(target[0]-start[0],target[2]-start[2])>12
            or abs(target[1]-start[1])>64):raise JobBlocked('局部空气接近点超出有界范围')
    low=[math.floor(min(start[0],target[0]))-3,max(-64,math.floor(min(start[1],target[1]))-2),math.floor(min(start[2],target[2]))-3]
    high=[math.floor(max(start[0],target[0]))+3,min(319,math.floor(max(start[1],target[1]))+3),math.floor(max(start[2],target[2]))+3]
    if math.prod(high[i]-low[i]+1 for i in range(3))>30000:raise JobBlocked('局部空气扫描超出有界范围')
    path=plan(_air_scan(client,low,high),start,target,low,high)
    file=Path(out)/'local-air-path.json'
    if file.exists():raise JobBlocked('原空气路线回执必须保留，不重放')
    book={'world_session':client.world,'start':start,'target':target,'path':path,
          'pending':None,'moves':[],'complete':False,'mining_sent':False}
    write_json(file,book)
    for point in path:
        actual=client.status()['pos']
        if math.dist(actual,point)<.15:continue
        if _air_scan(client,*_body_sweep(actual,point)):raise JobBlocked('局部空气通道发生变化，未继续移动')
        book['pending']={'target':point};write_json(file,book)
        _air_move(client,point,45)
        book['moves'].append({'target':point,'actual':client.status()['pos'],'request_id':client.last})
        book['pending']=None;write_json(file,book)
    book.update(complete=True,actual=client.status()['pos']);write_json(file,book)
    return book
