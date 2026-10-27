"""Plan flat corridor turns; every emitted segment still needs native collision checks."""
from collections import deque
import math

def flat_corridor_route(walkable, start, target):
    cells={tuple(p)for p in walkable}
    if not cells or any(len(p)!=2 or any(type(n)is not int for n in p)for p in cells):
        raise ValueError('Integer horizontal walk cells required')
    for point in(start,target):
        if len(point)!=3 or any(type(n)not in(int,float)or not math.isfinite(n)for n in point):
            raise ValueError('Finite XYZ poses required')
    if abs(start[1]-target[1])>.25:raise ValueError('Align height before planning a flat corridor')
    a=(math.floor(start[0]),math.floor(start[2]));b=(math.floor(target[0]),math.floor(target[2]))
    if a not in cells or b not in cells:raise ValueError('Both poses must belong to the corridor')
    queue=deque([a]);parents={a:None}
    while queue and b not in parents:
        x,z=queue.popleft()
        for dx,dz in((0,1),(0,-1),(1,0),(-1,0)):
            p=(x+dx,z+dz)
            if p in cells and p not in parents:parents[p]=(x,z);queue.append(p)
    if b not in parents:raise ValueError('No corridor route through declared walk cells')
    path=[];p=b
    while p is not None:path.append(p);p=parents[p]
    path.reverse();corners=[];direction=None
    for i in range(1,len(path)):
        step=(path[i][0]-path[i-1][0],path[i][1]-path[i-1][1])
        if direction is not None and step!=direction:corners.append(path[i-1])
        direction=step
    if a!=b:corners.append(b)
    return [[x+.5,target[1],z+.5]for x,z in corners]
