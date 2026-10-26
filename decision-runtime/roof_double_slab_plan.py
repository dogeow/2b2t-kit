"""Plan additive normal interactions for exact model double slabs; no game input."""
import math
from roof_slab_window_plan import SLAB
DOUBLE='Block{minecraft:cobblestone_slab}[type=double,waterlogged=false]'
SIDES=((1,0,'east'),(-1,0,'west'),(0,1,'south'),(0,-1,'north'))

def choices(expected,observed,player,*,low,high,protected=(),y=72):
    if(len(low)!=3 or len(high)!=3 or any(type(v)is not int for v in [*low,*high])
            or any(a>b for a,b in zip(low,high))):raise ValueError('Inclusive witnessed bounds required')
    blocked=set(map(tuple,protected));result=[]
    def inside(p):return all(a<=v<=b for a,v,b in zip(low,p,high))
    def dry(p,state):
        row=observed.get(p,{})
        return (inside(p) and row.get('state')==state and row.get('fluid')is False and row.get('block_entity')is False)
    def clear_pose(pose):
        x,z=math.floor(pose[0]),math.floor(pose[2])
        a=(x-1,y+1,z-1);b=(x+1,y+11,z+1)
        return inside(a)and inside(b)and not any(x-1<=p[0]<=x+1 and y+1<=p[1]<=y+11 and z-1<=p[2]<=z+1 for p in observed)
    for target,state in expected.items():
        if target[1]!=y or state!=DOUBLE or target in blocked or not inside(target):continue
        unlock=sum(expected.get((target[0]+dx,y,target[2]+dz))==SLAB and (target[0]+dx,y,target[2]+dz)not in observed for dx,dz,_ in SIDES)
        cases=[]
        if dry(target,SLAB):cases.append((target,None,[target[0]+.5,y+2.1,target[2]+.5]))
        elif target not in observed:
            for dx,dz,face in SIDES:
                anchor=(target[0]-dx,y,target[2]-dz)
                if anchor in blocked or expected.get(anchor)!=SLAB or not dry(anchor,SLAB):continue
                cases.append((anchor,face,[target[0]+.5+dx,y+2.1,target[2]+.5+dz]))
        for anchor,face,pose in cases:
            if not clear_pose(pose):continue
            stages=[]
            if face is not None:stages.append({'support':list(anchor),'face':face,'expected_support':SLAB,'expected_before':'Block{minecraft:air}','expected_after':SLAB})
            stages.append({'support':list(target),'face':'up','expected_support':SLAB,'expected_before':SLAB,'expected_after':DOUBLE})
            result.append({'target':list(target),'hover':pose,'stages':stages,'item_cost':len(stages),'unlock_score':unlock,'distance':math.dist(player,pose)})
    return sorted(result,key=lambda p:(-p['unlock_score'],p['distance'],p['target'],p['hover']))


def clear_route(source,target,observed,*,low,high):
    """A direct hover route needs witnessed air for the entire player body."""
    if any(len(p)!=3 or any(type(v)not in(int,float)or not math.isfinite(v)for v in p)for p in(source,target)):return False
    steps=max(1,math.ceil(math.dist(source,target)/.15))
    for step in range(steps+1):
        t=step/steps;p=[a+(b-a)*t for a,b in zip(source,target)]
        for x in range(math.floor(p[0]-.32),math.floor(p[0]+.32-1e-7)+1):
            for y in range(math.floor(p[1]),math.floor(p[1]+1.82-1e-7)+1):
                for z in range(math.floor(p[2]-.32),math.floor(p[2]+.32-1e-7)+1):
                    cell=(x,y,z)
                    if not all(a<=v<=b for a,v,b in zip(low,cell,high))or cell in observed:return False
    return True
