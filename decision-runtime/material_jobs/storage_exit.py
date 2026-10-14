"""Precisely centre a settled warehouse exit using the current native body check."""
import math
import time
from kit_runtime.journal import write_json
from material_plan import inventory_counts


def center_target(state):
    pos=state.get('pos')
    if (not isinstance(pos,list)or len(pos)!=3
            or any(type(v)not in(int,float)or not math.isfinite(v)for v in pos)
            or state.get('air_only_navigation_protocol',0)<2
            or state.get('on_ground')is not True or state.get('flight')is not False
            or state.get('health')!=20 or state.get('food',0)<8
            or state.get('manual_movement')or state.get('screen')
            or state.get('guard_busy')or state.get('under_water')
            or state.get('guard_armed')is not True or state.get('guard_pve_only')is not True):
        return None
    fx,fz=pos[0]-math.floor(pos[0]),pos[2]-math.floor(pos[2])
    if .35<=fx<=.65 and .35<=fz<=.65:return None
    return [math.floor(pos[0])+.5,pos[1],math.floor(pos[2])+.5]


def center(c):
    from .navigation import settled_state
    state=c.status()
    if center_target(state)is None:return False
    # A normal ground walk may coast after its native done receipt. Choose
    # the final cell from the actual stopped position, not the arrival frame.
    state=settled_state(c,seconds=5);target=center_target(state)
    if target is None:return False
    before=dict(inventory_counts(state));world=c.world
    reply=c.checked('navigate',target=target,arrival=.15,air_only=True,seconds=25)
    actual=settled_state(c,target,.55)
    if (actual.get('world_session')!=world or actual.get('health')!=20
            or math.hypot(actual['pos'][0]-target[0],actual['pos'][2]-target[2])>.18
            or dict(inventory_counts(actual))!=before):
        raise RuntimeError('Precise warehouse exit pose or inventory is unconfirmed')
    write_json(c.out/('warehouse-exit-center-%d.json'%time.time_ns()),
               {'world_session':world,'target':target,'actual':actual['pos'],
                'native_reply':reply,'inventory_unchanged':True,'ground_walk_replayed':False})
    return True
