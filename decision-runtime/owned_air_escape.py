"""A bounded side flight out of a canopy, using the existing owned Kit client."""
from copy import deepcopy
import json
import math
from pathlib import Path
import time


def blocks_segment(row,start,end):
    if row.get('passable') is True and row.get('fluid') is False:
        return False
    low=[min(start[0],end[0])-.35,min(start[1],end[1]),min(start[2],end[2])-.35]
    high=[max(start[0],end[0])+.35,max(start[1],end[1])+1.81,max(start[2],end[2])+.35]
    return all(row['pos'][i]+1>low[i] and row['pos'][i]<high[i] for i in range(3))


def side_candidates(rows,start,target_y,radius=8):
    if not 1<=radius<=8 or not start[1]<=target_y<=317:
        raise ValueError('Escape stays within eight side blocks and legal high air')
    candidates=[]
    for step in range(1,radius+1):
        for axis,direction in ((0,-1),(0,1),(2,-1),(2,1)):
            side=list(start);side[axis]=math.floor(start[axis])+.5+direction*step
            high=[side[0],target_y,side[2]]
            if not any(blocks_segment(row,start,side) or blocks_segment(row,side,high) for row in rows):
                candidates.append((math.dist(start,side),side,high))
    return sorted(candidates,key=lambda row:(row[0],row[1]))


def wait_known_idle(c,seconds=6,idle_predicate=None):
    if idle_predicate is None:
        from native_outcome_fence import exact_idle_terminal
        idle_predicate=exact_idle_terminal
    deadline=time.monotonic()+seconds
    while True:
        state=c.status();terminal=getattr(c,'last_terminal_evidence',None)or{}
        lease=state.get('supervision_lease')or{}
        if idle_predicate(c,state):return state
        known=(terminal.get('phase')=='done' or terminal.get('op')=='snapshot'and terminal.get('phase') is None)
        if (not known or terminal.get('request_id')!=c.last or terminal.get('task_session')!=c.task
                or terminal.get('world_session')!=c.world or terminal.get('revision_after')!=c.rev
                or getattr(c,'unconfirmed_native_request',None) is not None or c.native_inflight is not None
                or state.get('world_session')!=c.world or state.get('control_revision')!=c.rev
                or lease.get('id')!=c.heartbeat.id or lease.get('job_session')!=c.task
                or lease.get('kind')!='materials' or lease.get('revision')!=c.rev
                or time.monotonic()>=deadline):
            raise RuntimeError('Canopy escape requires the exact known idle owner')
        # A completed read reply can precede the status publisher clearing its
        # pending scan. Observe the same owner; never resend the completed read.
        time.sleep(.05)


def pickup_only_inventory(before, after, allowed):
    """Allow only positive plain64 pickup deltas explicitly named by the caller."""
    if not allowed:return after == before
    def split(rows):
        if (not isinstance(rows,list) or len(rows)!=43 or any(not isinstance(r,dict)for r in rows)
                or {r.get('slot') for r in rows}!=set(range(43))):
            raise ValueError('Complete inventory required for pickup-only comparison')
        protected=[];counts={item:0 for item in allowed}
        for row in rows:
            if not row.get('count'):continue
            if row.get('slot',43)<36 and row.get('item') in allowed:
                if (set(row)!={'slot','item','count','max_stack'} or row['max_stack']!=64
                        or type(row['count'])is not int or not 1<=row['count']<=64):
                    raise ValueError('Only ordinary plain64 pickups may grow during escape')
                counts[row['item']]+=row['count']
            else:
                protected.append(json.dumps({k:v for k,v in row.items()if k!='slot'},sort_keys=True))
        return sorted(protected),counts
    try:
        old,old_counts=split(before);new,new_counts=split(after)
    except (ValueError,TypeError,KeyError):return False
    return old==new and all(new_counts[item]>=old_counts[item]for item in allowed)


def escape_side(c,out,target_y=130,*,pickup_items=()):
    """No new owner or heartbeat; native navigation rechecks each physical sweep."""
    from lighting_cli import swept_entities
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    initial=wait_known_idle(c)
    inventory=deepcopy(initial['inventory'])
    allowed=frozenset(pickup_items)
    if any(not isinstance(item,str)or not item.startswith('minecraft:')for item in allowed):
        raise ValueError('Explicit Minecraft pickup item IDs required')
    def current():
        state=c.status()
        if (state['health']!=20 or state['food']<18 or state['screen'] or state['manual_movement']
                or not state['guard_armed'] or not state['guard_pve_only']
                or not pickup_only_inventory(inventory,state['inventory'],allowed)):
            raise RuntimeError('Canopy escape survival, input or inventory changed')
        return state
    def save(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2))
    def scan(low,high,name):
        current();reply=c.checked('scan',min=low,max=high,details=True,seconds=30)
        if reply['scan_cells_read']!=reply['scan_total_cells'] or reply['scan_total_cells']!=math.prod(high[i]-low[i]+1 for i in range(3)):
            raise RuntimeError('Canopy escape scan is incomplete')
        current();save(name,reply);return reply
    start=current()['pos'];target_y=max(target_y,start[1])
    # Native Flight can settle a fraction below its requested waypoint. Use
    # the actual AABB sweep below; rounding a valid AIR pose is unnecessary.
    low=[math.floor(start[0])-9,math.floor(start[1]),math.floor(start[2])-9]
    high=[math.floor(start[0])+9,math.ceil(target_y+1.81),math.floor(start[2])+9]
    reply=scan(low,high,'fresh-side-volume.json')
    if math.dist(current()['pos'],start)>.08:
        raise RuntimeError('Escape pose changed during planning')
    options=[option for option in side_candidates(reply['blocks'],start,target_y)
             if not swept_entities(reply,start,option[1],low,high,c.world,c.rev)
             and not swept_entities(reply,option[1],option[2],low,high,c.world,c.rev)]
    if not options:
        raise RuntimeError('No observed clear side flight and vertical column')
    _,side,high_target=options[0];save('plan.json',{'start':start,'side':side,'high':high_target})
    c.checked('navigate',target=side,arrival=.12,air_only=True,seconds=20)
    state=current()
    if math.dist(state['pos'],side)>.3 or not state['flight']:
        raise RuntimeError('Native side arrival is unproved')
    low=[math.floor(state['pos'][0]-.35),-64,math.floor(state['pos'][2]-.35)]
    high=[math.floor(state['pos'][0]+.35),319,math.floor(state['pos'][2]+.35)]
    column=scan(low,high,'actual-body-full-column.json')
    ground=max((row['pos'][1]+1 for row in column['blocks'] if row.get('fluid') or not row.get('passable')),default=None)
    if ground is None or high_target[1]-ground<20:
        raise RuntimeError('Actual side column cannot prove high parking clearance')
    source=current()['pos'];high_target=[source[0],target_y,source[2]]
    if any(blocks_segment(row,source,high_target)for row in column['blocks']) or swept_entities(column,source,high_target,low,high,c.world,c.rev):
        raise RuntimeError('Actual vertical body corridor changed')
    c.checked('navigate',target=high_target,arrival=.12,air_only=True,seconds=30)
    final=current()
    if math.dist(final['pos'],high_target)>.3 or not final['flight'] or final['pos'][1]-ground<20:
        raise RuntimeError('Native high arrival is unproved')
    proof={'world_session':c.world,'task_session':c.task,'lease_id':c.heartbeat.id,
           'ground_clearance':final['pos'][1]-ground,
           'inventory_unchanged':final['inventory']==inventory,
           'allowed_pickup_items':sorted(allowed),'current':final}
    save('verified.json',proof)
    return proof
