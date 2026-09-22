"""Normal terrain planning: small local earthworks, vegetation and exploration."""
import math
from survival_world import World,cell,center,distance

VEGETATION={'short_grass','tall_grass','fern','large_fern','dandelion','poppy','azure_bluet','oxeye_daisy','cornflower','allium'}
EARTH={'dirt','grass_block','stone','andesite','diorite','granite','coarse_dirt','rooted_dirt','podzol'}

class NaturalWorld(World):
    def sight(self,feet,target):
        # Waypoint arrival has a small tolerance. A ray that merely grazes a leaf
        # corner at the ideal centre is not a reliable reachable mining face.
        end=[v+.5 for v in target]
        for dx,dz in ((0,0),(.2,.2),(.2,-.2),(-.2,.2),(-.2,-.2)):
            start=[feet[0]+.5+dx,feet[1]+1.62,feet[2]+.5+dz]
            steps=max(2,math.ceil(distance(start,end)*16))
            for i in range(1,steps):
                p=cell([a+(b-a)*i/steps for a,b in zip(start,end)])
                if p==tuple(target):break
                if not self.open(p):return False
        return True
    def removable_plant(self,p):return self.safe(p) and self.name(p) in VEGETATION and not self.row(p).get('block_entity')
    def build_space(self,p):return self.name(p)=='air' or self.removable_plant(p)
    def camp_plan(self,feet):
        parents=self.paths(feet);plans=[]
        for cx,y,cz in parents:
            if distance(feet,center((cx,y,cz)))>13:continue
            fill=[];clear=[];good=True
            for x in range(cx-2,cx+3):
                for z in range(cz-2,cz+3):
                    floor=(x,y-1,z)
                    if not self.full(floor):
                        if self.name(floor)=='air' and self.full((x,y-2,z)):fill.append(floor)
                        else:good=False;break
                    for by in range(y,y+3):
                        p=(x,by,z)
                        if self.name(p)=='air':continue
                        if self.removable_plant(p) or by==y and self.name(p) in EARTH and not self.row(p).get('block_entity'):clear.append(p)
                        else:good=False;break
                    if not good:break
                if not good:break
            if good and len(fill)+sum(self.name(p) not in VEGETATION for p in clear)<=12:
                cost=len(fill)*3+sum(1 if self.name(p) in VEGETATION else 3 for p in clear)+distance(feet,center((cx,y,cz)))
                plans.append((cost,{'center':[cx,y,cz],'fill':fill,'clear':sorted(clear,key=lambda p:-p[1])}))
        return min(plans,key=lambda p:p[0])[1] if plans else None
    def resource(self,feet,names,excluded=()):
        parents=self.paths(feet);candidates=[];approaches={}
        def approach(p):
            if p not in approaches:approaches[p]=self.approach(parents,p)
            return approaches[p]
        positions=[p for p in self.blocks if self.name(p) in names and p not in excluded and not self.row(p).get('block_entity')]
        positions.sort(key=lambda p:distance(feet,center(p)))
        for p in positions[:128]:
            above=(p[0],p[1]+1,p[2]);stance=approach(p)
            if stance is None:continue
            if above not in excluded and self.name(above) in names and approach(above) is not None:continue
            if p==(math.floor(feet[0]),math.floor(feet[1])-1,math.floor(feet[2])):continue
            if any(not self.safe((p[0]+dx,p[1]+dy,p[2]+dz)) for dx,dy,dz in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))):continue
            path=self.route(parents,stance);candidates.append((len(path)+distance(feet,center(p))*.1,p,path))
        if not candidates:return None
        _,p,path=min(candidates);return p,path
    def exploration(self,feet,visited,origin,radius=128):
        parents=self.paths(feet);buckets={}
        for p in parents:
            d=distance(feet,center(p))
            if not 6<=d<=13 or math.hypot(p[0]-origin[0],p[2]-origin[2])>radius:continue
            dx=p[0]-feet[0];dz=p[2]-feet[2];direction='east' if abs(dx)>abs(dz) and dx>0 else 'west' if abs(dx)>abs(dz) else 'south' if dz>0 else 'north'
            visits=visited.get((p[0]//4,p[2]//4),0);path=self.route(parents,p)
            score=visits*30+len(path)*.2-d
            if direction not in buckets or score<buckets[direction][0]:buckets[direction]=(score,p,path)
        return [(direction,p,path) for direction,(_,p,path) in sorted(buckets.items(),key=lambda pair:pair[1][0])[:3]]
