"""Nearby source approaches through scanned air, keeping the current work height."""
import math
from pathlib import Path

from material_client import Handoff
from kit_runtime.journal import write_json
from .acquisition import _travel
from .local_air_path import move
from .navigation import settled_state
from .protocol import JobBlocked


def approach(c,target,out,checkpoint):
    checkpoint();here=c.status()['pos']
    if(not isinstance(target,list)or len(target)!=3
            or any(type(v)not in(int,float)or not math.isfinite(v)for v in target)
            or not -64<=target[1]<315 or math.hypot(target[0]-here[0],target[2]-here[2])>192):
        raise ValueError('Source approach must be nearby and inside legal world height')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'source-approach.json'
    if path.exists():raise RuntimeError('Original source approach retained; no replay')
    book={'world_session':c.world,'from':here,'target':target,'complete':False,'pending':None}
    write_json(path,book)
    local=out/'local';route=local/'local-air-path.json'
    if math.hypot(target[0]-here[0],target[2]-here[2])<=24 and abs(target[1]-here[1])<=64:
        try:
            move(c,target,local,max_horizontal=24,max_straight=8,foot_offset=.2)
            q=settled_state(c,target,.6)
            book.update(complete=True,mode='nearby_scanned_air',actual=q['pos']);write_json(path,book);return book
        except Handoff:raise
        except (JobBlocked,RuntimeError):
            if route.exists()or getattr(c,'native_inflight',None)is not None:raise
            # move() writes its route before the first navigation. Missing
            # route proof here means only observation/planning was attempted.
            book['local_planning_no_movement']=True;write_json(path,book)
    checkpoint();q=c.status();above=[target[0],max(q['pos'][1],target[1]+4),target[2]]
    book['pending']={'kind':'terrain_inspected_approach','target':above};write_json(path,book)
    _travel(c,above,checkpoint,[],keep_cruise=True)
    book['pending']={'kind':'normal_air_descent','target':target};write_json(path,book)
    c.checked('navigate',target=target,arrival=.2,air_only=True,seconds=90)
    q=settled_state(c,target,.6)
    book.update(pending=None,complete=True,mode='local_terrain_clearance',actual=q['pos']);write_json(path,book);return book
