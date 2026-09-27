"""Plan a dry, two-block-high horizontal exit through observed air, without breaking blocks."""
from collections import deque
import math


def horizontal_exit(rows, position, minimum, maximum, scan_min, scan_max):
    y=math.floor(position[1])
    head=math.floor(position[1]+1.8-1e-7)
    occupied={tuple(row['pos']) for row in rows
              if row.get('fluid') or row.get('block_entity') or not row.get('passable',False)}
    start=(math.floor(position[0]),math.floor(position[2]))
    def clear(cell):
        x,z=cell
        return (scan_min[0]<=x<=scan_max[0] and scan_min[2]<=z<=scan_max[2]
                and all((x,h,z) not in occupied for h in range(y,head+1)))
    def outside(cell):
        x,z=cell
        return x<=minimum[0]-3 or x>=maximum[0]+3 or z<=minimum[2]-3 or z>=maximum[2]+3
    if not clear(start):raise RuntimeError('Observed player cell is not a clear escape cell')
    queue=deque([start]);parents={start:None};end=None
    while queue:
        at=queue.popleft()
        if outside(at):end=at;break
        for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
            nxt=(at[0]+dx,at[1]+dz)
            if nxt not in parents and clear(nxt):parents[nxt]=at;queue.append(nxt)
    if end is None:raise RuntimeError('No observed horizontal exit; preserve the hull')
    path=[]
    while end is not None:path.append(end);end=parents[end]
    path.reverse()
    turns=[]
    for i,cell in enumerate(path):
        if i==0 or i==len(path)-1 or (cell[0]-path[i-1][0],cell[1]-path[i-1][1])!=(path[i+1][0]-cell[0],path[i+1][1]-cell[1]):
            turns.append([cell[0]+.5,position[1],cell[1]+.5])
    return {'cells':[list(p) for p in path],'waypoints':turns,'feet_y':position[1]}
