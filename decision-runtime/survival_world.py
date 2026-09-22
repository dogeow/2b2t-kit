"""Small observed-world graph. Unknown cells are never treated as open terrain."""
from collections import deque
import math
import re

DANGERS={'lava','water','fire','soul_fire','magma_block','cactus','sweet_berry_bush',
         'powder_snow','campfire','soul_campfire','pointed_dripstone','wither_rose'}

def block_id(state):
    match=re.search(r'Block\{minecraft:([^}]+)\}',state)
    return match.group(1) if match else 'unknown'

def distance(a,b): return math.dist(a,b)
def center(p): return [p[0]+.5,p[1],p[2]+.5]
def cell(p): return tuple(math.floor(v) for v in p)

class Paths(dict):
    centering=None

class World:
    def __init__(self,rows,low,high):
        self.blocks={tuple(r['pos']):r for r in rows}
        self.low=tuple(low);self.high=tuple(high)
    def known(self,p): return all(a<=b<=c for a,b,c in zip(self.low,p,self.high))
    def row(self,p): return self.blocks.get(tuple(p),{})
    def name(self,p): return block_id(self.row(p).get('state','Block{minecraft:air}')) if self.known(p) else 'unknown'
    def safe(self,p):
        r=self.row(p)
        return self.known(p) and self.name(p) not in DANGERS and not r.get('fluid',False)
    def open(self,p):
        opened_door=self.name(p).endswith('_door') and 'open=true' in self.row(p).get('state','')
        return self.safe(p) and (p not in self.blocks or self.row(p).get('passable',False) or opened_door)
    def full(self,p): return self.safe(p) and self.row(p).get('solid',False)
    def earth(self,p):return self.full(p) and self.name(p) in ('dirt','grass_block')
    def stand(self,p):
        x,y,z=p
        return self.full((x,y-1,z)) and self.open(p) and self.open((x,y+1,z))
    def paths(self,start,limit=2500):
        actual=list(start);start=cell(start)
        if not self.stand(start):
            x,y,z=start
            nearby=[(x+dx,y,z+dz) for dx in (-1,0,1) for dz in (-1,0,1)
                    if self.stand((x+dx,y,z+dz)) and distance(actual,center((x+dx,y,z+dz)))<=.85]
            if not nearby:return {}
            start=min(nearby,key=lambda p:distance(actual,center(p)))
        parent=Paths({start:None});queue=deque([start])
        parent.centering=start if distance(actual,center(start))>.2 else None
        while queue and len(parent)<limit:
            x,y,z=queue.popleft()
            for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
                for dy in (0,1,-1):
                    p=(x+dx,y+dy,z+dz)
                    # A rising step also needs clearance over the starting head.
                    if p not in parent and self.stand(p) and (dy!=1 or self.open((x,y+2,z))) and (dy!=-1 or self.open((x+dx,y+1,z+dz))):
                        parent[p]=(x,y,z);queue.append(p);break
        return parent
    @staticmethod
    def route(parent,target):
        out=[]
        while parent.get(target) is not None:out.append(target);target=parent[target]
        prefix=[parent.centering] if getattr(parent,'centering',None) is not None else []
        return prefix+list(reversed(out))
    def sight(self,feet,target):
        start=[feet[0]+.5,feet[1]+1.62,feet[2]+.5]
        end=[v+.5 for v in target];length=distance(start,end)
        for i in range(1,max(2,math.ceil(length*10))):
            ratio=i/max(2,math.ceil(length*10));p=cell([a+(b-a)*ratio for a,b in zip(start,end)])
            if p==tuple(target):return True
            if not self.open(p):return False
        return True
    def approach(self,parent,target,reach=3.6):
        choices=[p for p in parent if distance([p[0]+.5,p[1]+1.62,p[2]+.5],[v+.5 for v in target])<=reach and self.sight(p,target)]
        return min(choices,key=lambda p:len(self.route(parent,p)),default=None)
    def resource(self,feet,names,excluded=()):
        parent=self.paths(feet);found=[]
        candidates=[(p,r) for p,r in self.blocks.items() if self.name(p) in names and p not in excluded]
        candidates.sort(key=lambda pair:distance(feet,center(pair[0])))
        for p,r in candidates[:128]:
            if p in excluded or self.name(p) not in names or r.get('block_entity'):continue
            # Remove the exposed top of a column first, leaving steps rather than an overhang.
            if self.name((p[0],p[1]+1,p[2])) in names:continue
            if p==tuple([math.floor(feet[0]),math.floor(feet[1])-1,math.floor(feet[2])]):continue
            if any(not self.safe((p[0]+dx,p[1]+dy,p[2]+dz)) for dx,dy,dz in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))):continue
            stance=self.approach(parent,p)
            if stance is not None:found.append((len(self.route(parent,stance))+distance(feet,center(p))*.1,p,stance))
        if not found:return None
        _,p,stance=min(found);return p,self.route(parent,stance)
    def camp(self,feet):
        parent=self.paths(feet);candidates=[]
        for cx,y,cz in parent:
            if distance(feet,center((cx,y,cz)))>9:continue
            cells=[(x,y,z) for x in range(cx-2,cx+3) for z in range(cz-2,cz+3)]
            if all(self.stand(p) and self.name(p)=='air' and self.name((p[0],y+1,p[2]))=='air' and self.name((p[0],y+2,p[2]))=='air' for p in cells):
                candidates.append((distance(feet,center((cx,y,cz))),[cx,y,cz]))
        return min(candidates,default=(None,None))[1]

def shelter(camp):
    x,y,z=camp;door=(x,y,z+2)
    walls=[(bx,by,bz) for by in (y,y+1) for bx in range(x-2,x+3) for bz in range(z-2,z+3)
           if (abs(bx-x)==2 or abs(bz-z)==2) and (bx,bz)!=(x,z+2)]
    roof=[(bx,y+2,bz) for bx in range(x-2,x+3) for bz in range(z-2,z+3)]
    roof.sort(key=lambda p:-max(abs(p[0]-x),abs(p[2]-z)))
    return walls+roof,door
