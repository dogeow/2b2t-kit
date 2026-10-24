"""Derive an isolated librarian room's reads from its verified work block."""
from dataclasses import dataclass

@dataclass(frozen=True)
class LibrarianRoom:
    uid:str
    work:tuple
    inward:int
    interior_floor_y:int|None=None
    front_bed:bool=False
    public_counter:tuple|None=None
    interior_depth:int=3
    interior_x_offsets:tuple=(0,)

    def __post_init__(self):
        if (not isinstance(self.interior_x_offsets,tuple)
                or any(type(v)is not int for v in self.interior_x_offsets)
                or self.interior_x_offsets not in ((0,),(-1,0),(0,1))):
            raise ValueError('One or two contiguous interior columns must include the workpoint')

    @property
    def floor_y(self):
        return self.work[1] if self.interior_floor_y is None else self.interior_floor_y

    @classmethod
    def from_slot(cls,slot):
        p=slot.get('actual_work_block')or slot.get('work_block');name=slot.get('id','');uid=slot.get('occupant_uuid')
        if(not isinstance(p,list)or len(p)!=3 or any(type(n)is not int for n in p)
                or not isinstance(uid,str)or not uid or len(name)<3 or name[0]not in 'WE'or name[1]not in 'NS'):
            raise ValueError('Verified librarian slot, UUID and integer work block required')
        inward=1 if name[1]=='S'else-1
        floor=slot.get('interior_floor_y',p[1])
        if type(floor)is not int or not 0<=p[1]-floor<=1:
            raise ValueError('Workpoint must be at the floor or one block above it')
        front_bed=slot.get('bed_head')==[p[0],floor,p[2]+inward]
        counter=slot.get('work_block',p)
        if (not isinstance(counter,list) or len(counter)!=3 or any(type(n)is not int for n in counter)
                or counter[0]!=p[0] or not 0<=(p[2]-counter[2])*inward<=4):
            raise ValueError('Public counter must precede the private workpoint on the same column')
        depth=slot.get('interior_depth',3)
        if type(depth)is not int or depth not in (2,3):raise ValueError('Explicit two or three cell interior required')
        offsets=slot.get('interior_x_offsets',[0])
        if not isinstance(offsets,list) or any(type(v)is not int for v in offsets):
            raise ValueError('Explicit integer interior columns required')
        return cls(uid,tuple(p),inward,floor,front_bed,tuple(counter),depth,tuple(offsets))

    def bounds(self):
        x,y,z=self.work;end=z+(self.interior_depth+1)*self.inward
        counter_z=(self.public_counter or self.work)[2]
        return [x+min(self.interior_x_offsets)-1,self.floor_y-1,min(z,end,counter_z)],[x+max(self.interior_x_offsets)+1,max(self.floor_y+3,y+2),max(z,end,counter_z)]

    def public_pose(self):
        """Feet below the original half-slab trade opening, outside the resident cell."""
        x,_,z=self.public_counter or self.work;y=self.work[1]
        if self.interior_depth==2 and (self.work[2]-z)*self.inward==1:
            return [self.work[0]+.5,float(self.floor_y),self.work[2]+.5-self.inward]
        return [x+.5,min(y+.1,self.floor_y+1.1),z+.5-self.inward]

    def public_mining_face(self):
        return 'north'if self.inward==1 else'south'

    def public_trade_pose(self):
        """Approach the trade window, retaining 5 mm beyond a .6-wide body."""
        p = self.public_pose()
        p[2] += self.inward * .195
        return p

    def public_print_pose(self):
        """Farther public pose verified for the server-confirmed WN02 print."""
        x, _, z = self.public_counter or self.work;y=self.work[1]
        if self.interior_depth==2 and (self.work[2]-z)*self.inward==1:x,_,z=self.work
        return [x + .5, min(y + .3, self.floor_y + 1.1), z + .5 - 2 * self.inward]

    def private_center(self,height):
        x,y,z=self.work
        return [x+.5,self.floor_y+height,z+.5+self.inward]

    def operator_pose(self):
        p=self.private_center(1.1 if self.front_bed else .1);p[2]-=self.inward*.19
        return p

    def private_roof(self):
        x,y,z=self.work
        return [x,self.floor_y+3,z+self.inward]

    def barrier(self):
        x,y,z=self.work
        return [x,self.floor_y+1,z+2*self.inward]

    def lectern_state(self):
        return 'Block{minecraft:lectern}[facing='+('north'if self.inward==1 else'south')+',has_book=false,powered=false]'

    def actor(self,scene):
        matches=[v for v in scene.get('scan_entities',[])if v.get('uuid')==self.uid]
        if(len(matches)!=1 or matches[0].get('type')!='minecraft:villager'
                or matches[0].get('health')!=20 or matches[0].get('is_baby')is not False):
            raise ValueError('Exact healthy adult resident missing from its current room scan')
        return matches[0]

    def require_caps(self,rows):
        x,y,z=self.work;cap=rows.get((x,y+1,z),{}).get('state','')
        valid=cap=='Block{minecraft:dark_oak_slab}[type=bottom,waterlogged=false]'
        if not valid:
            from projection_completion import block_state
            try:kind,props=block_state(cap)
            except ValueError:kind,props='',{}
            valid=(kind.endswith('_trapdoor')and props.get('half')=='top'and props.get('waterlogged')=='false'
                   and(props.get('open')=='false'or props.get('open')=='true'
                       and props.get('facing')in('north','south')
                       and rows.get((x,y,z),{}).get('state','').startswith('Block{minecraft:lectern}')))
        if not valid or rows.get((x,y+2,z),{}).get('solid')is not True:
            raise ValueError('Original closed counter cap is not intact')


def walk_public(c,destination):
    route=getattr(c,'walk_librarian_public',None)
    if route is not None and route(destination):return
    p=c.check()['pos'];floor=destination.floor_y
    c.n('walk',target=[p[0],64.0 if p[0]<761015 else 65.0,797811.5],arrival=.1,restore_flight=False,seconds=20)
    p=c.check()['pos']
    if (p[0]<761015)!=(floor==64):
        c.n('walk',target=[761015.5,64.5,797811.5],arrival=.1,restore_flight=False,seconds=20)
        c.n('walk',target=[761014.5 if floor==64 else 761016.5,float(floor),797811.5],arrival=.1,restore_flight=False,seconds=20)
    c.n('walk',target=[destination.work[0]+.5,float(floor),797811.5],arrival=.1,restore_flight=False,seconds=30)
    target=destination.public_pose();target[1]=float(floor);c.n('walk',target=target,arrival=.1,restore_flight=False,seconds=15)
