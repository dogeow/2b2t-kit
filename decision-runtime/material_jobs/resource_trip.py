"""Finite trips to explicit resource hints using normal native navigation.

Arrival does not prove a biome, a resource, or inventory. Each leg retains its
exact native receipt; a failed or unknown move cannot be replayed by this trip.
"""
import math,time
from pathlib import Path

from kit_runtime.journal import write_json
from .acquisition import _safe
from .navigation import settled_state


def travel(c,target,out,checkpoint,*,home,max_radius=9000,step=64,destination_name='陶瓦产地',long_transit=False):
    def point(p):return(isinstance(p,list)and len(p)==3
        and all(type(v)in(int,float)and math.isfinite(v)for v in p)and -64<=p[1]<317)
    if(type(long_transit)is not bool or not isinstance(destination_name,str)or not 1<=len(destination_name)<=48 or any(ord(v)<32 for v in destination_name)
            or not point(target)or not point(home)or type(max_radius)is not int or not 1<=max_radius<=16000
            or type(step)is not int or not 16<=step<=64
            or math.hypot(target[0]-home[0],target[2]-home[2])>max_radius):
        raise ValueError('Explicit target must be inside the finite resource trip')
    path=Path(out)/'resource-trip.json'
    if path.exists():raise RuntimeError('Original trip retained; never replay an uncertain or completed trip')
    path.parent.mkdir(parents=True,exist_ok=True)
    book={'world_session':c.world,'home':home,'target':target,'max_radius':max_radius,
          'legs':[],'pending':None,'complete':False,'source_verified':False,'inventory_credit':0}
    write_json(path,book)
    for index in range(min(512,math.ceil(2*max_radius/step)+8)):
        checkpoint();s=c.status();_safe(s)
        lease=s.get('supervision_lease')or{}
        if(s.get('world_session')!=c.world or s.get('connected')is not True
                or s.get('navigating')or getattr(c,'native_inflight',None)is not None
                or lease.get('kind')!='materials'or lease.get('job_session')!=c.task
                or lease.get('world_session')!=c.world or lease.get('revision')!=s.get('control_revision')):
            raise RuntimeError('Trip lost its healthy idle material owner; retain the original move')
        here=s['pos'];distance=math.hypot(target[0]-here[0],target[2]-here[2])
        if math.hypot(here[0]-home[0],here[2]-home[2])>max_radius:
            raise RuntimeError('Current position left the explicit resource trip')
        if math.dist(here,target)<=1.2:
            final=settled_state(c,target,1.5)
            book.update(complete=True,actual=final['pos']);write_json(path,book);return book
        ratio=min(1,step/distance)if distance else 1
        destination=([here[0],target[1],here[2]]if abs(here[1]-target[1])>.5 else
                     [here[0]+ratio*(target[0]-here[0]),target[1],here[2]+ratio*(target[2]-here[2])])
        if math.hypot(here[0]-c.anchor[0],here[2]-c.anchor[2])>480:
            raise RuntimeError('Unexplained displacement outside the last owned trip segment')
        # Same bounded reanchoring as the existing Kit wood expedition: only a
        # freshly observed physical pose can become the next native worksite.
        c.anchor=list(here);c.checked('guard',pve_only=True)
        if long_transit and abs(here[1]-target[1])<=.5:
            from .long_air_transit import choose
            longer,reads=choose(c,here,target,checkpoint)
            book.setdefault('long_leg_surveys',[]).extend(reads);write_json(path,book)
            if longer is not None:destination=longer
            else:
                from .long_air_transit import choose_short
                loading_until=time.monotonic()+20
                while True:
                    shorter,reads=choose_short(c,here,target,checkpoint)
                    book.setdefault('short_leg_surveys',[]).extend(reads);write_json(path,book)
                    if shorter is not None:destination=shorter;break
                    if any(v.get('obstacle_blocks')for v in reads):raise RuntimeError('Verified obstacle on short air segments; replan height without moving')
                    if time.monotonic()>=loading_until:raise RuntimeError('No currently loaded short air segment; no movement sent')
                    c.set_progress(phase='前方区块加载中，保持当前位置');checkpoint();time.sleep(1)
        book['pending']={'index':index,'from':here,'target':destination,'request_id':None}
        write_json(path,book);previous=c.last
        # The precise native air navigator confirms braking after restoring
        # Flight. A normal cruise DONE can still coast well beyond its target.
        # 64-block level diagonals stay within its bounded body-sweep volume.
        try:reply=c.request('navigate',target=destination,arrival=.35,air_only=True,seconds=90)
        finally:
            book['pending']['request_id']=c.last if c.last!=previous else None;write_json(path,book)
        if reply.get('phase')!='done':raise RuntimeError('Original native trip leg not completed; no replay')
        actual=settled_state(c,destination,1.5)
        book['legs'].append({**book['pending'],'actual':actual['pos'],'native_phase':reply['phase']})
        book['pending']=None;write_json(path,book)
        c.set_progress(phase=('前往'+destination_name+' · 剩余%d米')%round(math.hypot(
            target[0]-actual['pos'][0],target[2]-actual['pos'][2])))
    raise RuntimeError('Finite resource trip leg limit reached')
