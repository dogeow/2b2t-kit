"""Choose longer straight legs only through freshly confirmed loaded body air."""
import math
from .navigation import _body_sweep


def candidates(here,target):
    """Axis legs keep the native 8192-cell swept-box limit unchanged."""
    axes=sorted((0,2),key=lambda i:abs(target[i]-here[i]),reverse=True)
    seen=set()
    for axis in axes:
        distance=abs(target[axis]-here[axis])
        if distance<=64:continue
        for length in (256,192,128,96):
            actual=min(length,distance)
            if actual<=64:continue
            point=[here[0],target[1],here[2]]
            point[axis]+=math.copysign(actual,target[axis]-here[axis])
            key=tuple(point)
            if key not in seen:
                seen.add(key);yield point


def choose(c,here,target,checkpoint):
    attempts=[]
    for point in candidates(here,target):
        checkpoint()
        low,high=_body_sweep(here,point)
        reply=c.request('scan',min=low,max=high,details=True)
        total=math.prod(b-a+1 for a,b in zip(low,high))
        known=(reply.get('id')==c.last and reply.get('world_session')==c.world)
        if not known:raise RuntimeError('Long-leg read belongs to another world/request; no movement')
        clear=(reply.get('phase')=='done'and reply.get('scan_cells_read')==total
               and reply.get('scan_total_cells')==total and reply.get('blocks')==[])
        attempts.append({'target':point,'scan_request_id':c.last,'phase':reply.get('phase'),
                         'clear_loaded_body_air':clear,'movement_dispatched':False})
        if clear:return point,attempts
    return None,attempts


def choose_short(c,here,target,checkpoint):
    """At a loading boundary, verify a shorter segment before any move is sent."""
    axis=max((0,2),key=lambda i:abs(target[i]-here[i]));distance=abs(target[axis]-here[axis]);attempts=[];seen=set()
    for length in(64,32,16):
        point=list(here);point[1]=target[1];point[axis]+=math.copysign(min(length,distance),target[axis]-here[axis])
        if tuple(point)in seen:continue
        seen.add(tuple(point));checkpoint();low,high=_body_sweep(here,point);reply=c.request('scan',min=low,max=high,details=True)
        if reply.get('id')!=c.last or reply.get('world_session')!=c.world:raise RuntimeError('Short-leg read belongs to another world/request; no movement')
        total=math.prod(b-a+1 for a,b in zip(low,high));clear=(reply.get('phase')=='done'and reply.get('scan_cells_read')==total and reply.get('scan_total_cells')==total and reply.get('blocks')==[])
        attempts.append({'target':point,'scan_request_id':c.last,'phase':reply.get('phase'),'clear_loaded_body_air':clear,'obstacle_blocks':reply.get('blocks',[])if reply.get('phase')=='done'else None,'movement_dispatched':False})
        if clear:return point,attempts
    return None,attempts
