"""Player-only ground approach geometry; no entity positions are modified."""
import math,heapq

def inside(point,rect):
    return rect[0]<=point[0]<=rect[2]and rect[1]<=point[1]<=rect[3]

def intersects(a,b,rect):
    lo,hi=0.,1.
    for axis in range(2):
        d=b[axis]-a[axis]
        if abs(d)<1e-10:
            if not rect[axis]<=a[axis]<=rect[axis+2]:return False
        else:
            u,v=(rect[axis]-a[axis])/d,(rect[axis+2]-a[axis])/d
            lo=max(lo,min(u,v));hi=min(hi,max(u,v))
            if lo>hi:return False
    return True

def route(start,target,rects,bounds):
    if not inside(start,bounds)or not inside(target,bounds)or any(inside(p,r)for p in [start,target]for r in rects):
        raise ValueError('Player route endpoint is not clear')
    nodes=[list(start),list(target)]
    for x0,z0,x1,z1 in rects:
        for p in [[x0-.15,z0-.15],[x0-.15,z1+.15],[x1+.15,z0-.15],[x1+.15,z1+.15]]:
            if inside(p,bounds)and not any(inside(p,r)for r in rects)and p not in nodes:nodes.append(p)
    distance={0:0};parent={0:None};queue=[(0,0)]
    while queue:
        cost,i=heapq.heappop(queue)
        if cost!=distance[i]:continue
        if i==1:break
        for j,p in enumerate(nodes):
            if i==j or any(intersects(nodes[i],p,r)for r in rects):continue
            value=cost+math.dist(nodes[i],p)
            if value<distance.get(j,math.inf):distance[j]=value;parent[j]=i;heapq.heappush(queue,(value,j))
    if 1 not in parent:raise ValueError('No observed ground approach route')
    result=[];i=1
    while i is not None:result.append(nodes[i]);i=parent[i]
    return list(reversed(result))

def push_points(mob,boat,rects,bounds):
    dx,dz=mob[0]-boat[0],mob[1]-boat[1];length=math.hypot(dx,dz)
    if length<.1:return None
    away=[dx/length,dz/length];goal=[mob[i]-.25*away[i]for i in range(2)]
    # The player stays outside the boat's physical body plus a generous margin.
    boat_goal_rect=[rects[0][0]-.2,rects[0][1]-.2,rects[0][2]+.2,rects[0][3]+.2]
    for _ in range(30):
        if not inside(goal,boat_goal_rect):break
        goal=[goal[i]+.1*away[i]for i in range(2)]
    if not inside(goal,bounds)or any(inside(goal,r)for r in rects):return None
    for angle in [0,math.pi/4,-math.pi/4]:
        vector=[away[0]*math.cos(angle)-away[1]*math.sin(angle),away[0]*math.sin(angle)+away[1]*math.cos(angle)]
        behind=[max(bounds[i],min(bounds[i+2],mob[i]+.9*vector[i]))for i in range(2)]
        if not any(inside(behind,r)for r in rects)and math.dist(behind,goal)>.15:return behind,goal
    return None
