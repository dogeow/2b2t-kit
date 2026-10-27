"""Open a wooden door, walk through supported cells, then restore its original state."""
import json,math,time
from projection_completion import block_state
from survival_world import World,center
from work_access import approach_faces

WOOD_DOORS={f'minecraft:{wood}_door' for wood in ('oak','spruce','birch','jungle','acacia','dark_oak','mangrove','cherry','pale_oak','bamboo','crimson','warped')}
class DoorUseUnavailable(RuntimeError):pass

def crossing_hand(state):
    carried={row.get('item') for row in state.get('inventory',[]) if row.get('count',0)>0}
    for item in ('netherite_sword','diamond_sword','iron_sword','stone_sword','wooden_sword','golden_sword'):
        if 'minecraft:'+item in carried:return 'minecraft:'+item
    raise RuntimeError('Normal door crossing requires a carried sword; no interaction sent')

def crossing_destination(door,properties,player):
    axis=0 if properties['facing'] in ('east','west') else 2
    direction=1 if player[axis]<door[axis]+.5 else -1
    target=list(door);target[axis]+=direction
    return target,axis,direction

def read_block(client,pos):
    rows=client.request('scan',min=pos,max=pos,details=True)['blocks']
    if len(rows)!=1:raise RuntimeError('Door was removed or replaced')
    return rows[0]

def use_visible_door(client,pos,state,hand,preferred_face):
    """Recheck visibility from this side after crossing, without crossing back."""
    from projection_wood import PRE_USE_ERRORS
    for face in dict.fromkeys((preferred_face,'north','south','west','east','up','down')):
        if read_block(client,pos)['state']!=state:
            raise RuntimeError('Door changed before use; no repeated toggle')
        reply=client.request('interact',pos=pos,face=face,expected_state=state,expected_hand=hand)
        if reply.get('phase')=='done':return reply
        if reply.get('phase')=='error'and reply.get('detail')in PRE_USE_ERRORS:continue
        raise RuntimeError(reply.get('detail','Door interaction unconfirmed; no repeated toggle'))
    raise DoorUseUnavailable('No visible current-side door face; preserve the door')

def cross_door(client,pos):
    state=client.status();selection=state['projection_selection']
    if any(v<low or v>high for v,low,high in zip(pos,selection['min'],selection['max'])):
        raise RuntimeError('Door is outside the selected construction')
    row=read_block(client,pos);name,properties=block_state(row['state'])
    if name not in WOOD_DOORS or properties.get('half')!='lower' or properties.get('powered')!='false' or row.get('fluid'):
        raise RuntimeError('Expected a dry unpowered wooden door lower half')
    target,axis,direction=crossing_destination(pos,properties,state['pos']);was_open=properties['open']=='true'
    hand=crossing_hand(state)
    client.checked('select_item',item=hand)
    face=None
    if not was_open:
        near_face={(0,1):'west',(0,-1):'east',(2,1):'north',(2,-1):'south'}[(axis,direction)]
        face=near_face;used=False
        if math.dist(state['pos'],[v+.5 for v in pos])<=3:
            try:use_visible_door(client,pos,row['state'],hand,face);used=True
            except DoorUseUnavailable:pass # Every refusal occurred before any toggle.
        if not used:
            face=approach_faces(client,pos,row['state'],tuple(dict.fromkeys((near_face,'north','south','west','east','up','down'))))
            use_visible_door(client,pos,row['state'],hand,face)
        time.sleep(.3)
    opened=read_block(client,pos);opened_name,p=block_state(opened['state'])
    if opened_name!=name or p.get('open')!='true':raise RuntimeError('Door opening not observed; no duplicate toggle')
    state=client.status();feet=state['pos'];low=[min(math.floor(feet[i]),pos[i])-3 for i in range(3)];high=[max(math.ceil(feet[i]),pos[i])+3 for i in range(3)]
    rows=client.request('scan',min=low,max=high,details=True)['blocks'];world=World(rows,low,high)
    start=list(feet)
    rounded=round(start[1])
    # A native approach may hover .83 above a valid floor. Rounding that pose
    # upward invents a floor one block higher and loses the real door route.
    # Only normalize to a height whose full floor and body clearance exist.
    if abs(start[1]-rounded)<=.2 and world.stand((math.floor(start[0]),rounded,math.floor(start[2]))):
        start[1]=rounded
    # Reaching a visible face can itself walk through an already open door.
    # Do not require another supported route after that crossing is observed.
    crossed_during_approach=(feet[axis]-(pos[axis]+.5))*direction>=.55
    paths={} if crossed_during_approach else world.paths(start,limit=1000)
    choices=[tuple([target[0],target[1]+dy,target[2]]) for dy in (0,-1,1)]
    available=[p for p in choices if p in paths]
    if not available and not crossed_during_approach:raise RuntimeError('No supported walk through the opened door')
    route=[] if crossed_during_approach else world.route(paths,min(available,key=lambda p:len(world.route(paths,p))))
    if len(route)>12:raise RuntimeError('Door crossing route is unexpectedly long')
    for waypoint in route:
        client.checked('walk',target=center(waypoint),arrival=.08,seconds=10,restore_flight=True)
    after=client.status()
    if (after['pos'][axis]-(pos[axis]+.5))*direction<.55:raise RuntimeError('Crossing was not observed beyond the door')
    if not was_open:
        actual=read_block(client,pos)
        if actual['state']!=row['state']:
            if actual['state']!=opened['state']:raise RuntimeError('Door changed during crossing; preserve the new state')
            client.checked('select_item',item=hand)
            # Non-placement use accepts an actually visible face of the same block.
            use_visible_door(client,pos,actual['state'],hand,face)
            time.sleep(.3)
            if read_block(client,pos)['state']!=row['state']:raise RuntimeError('Original door state not restored')
    result={'door':pos,'before':row['state'],'destination':after['pos'],'restored':not was_open,
            'crossed_during_approach':crossed_during_approach}
    with (client.out/'door-crossings.jsonl').open('a') as stream:stream.write(json.dumps(result,ensure_ascii=False)+'\n')
    print('DOOR_CROSSED',pos,flush=True);return result

def open_door_center(pos,properties):
    """Centre the .8125-wide opening left by vanilla's three-pixel door panel."""
    axis,offset={'north':(0,-3/32),'south':(0,3/32),'east':(2,-3/32),'west':(2,3/32)}[properties['facing']]
    if properties['hinge']=='left':offset=-offset
    point=[v+.5 for v in pos];point[axis]+=offset;return point

def fly_open_door(client,pos,original_state,checkpoint,out):
    """Cross a currently open owned door with actual native body collision checks.

    A carpet or partial floor can defeat the integer supported-walk planner.
    No door cell is relabelled air and no existing block is removed.
    """
    from pathlib import Path
    from kit_runtime.journal import write_json
    out=Path(out);out.mkdir(parents=True,exist_ok=False);row=read_block(client,pos)
    name,p=block_state(row['state']);old_name,old=block_state(original_state);q=checkpoint();lease=q.get('supervision_lease')or{}
    if(name not in WOOD_DOORS or name!=old_name or p.get('open')!='true'or p.get('half')!='lower'
       or p.get('powered')!='false'or row['state']!=original_state.replace('open=false','open=true')
       or not q.get('flight')or q.get('health')!=20 or q.get('guard_busy')or q.get('under_water')
       or not q.get('guard_armed')or not q.get('guard_pve_only')or lease.get('job_session')!=client.task
       or lease.get('world_session')!=client.world):raise RuntimeError('Current healthy owned open-door flight required')
    target,axis,direction=crossing_destination(pos,p,q['pos']);centre=open_door_center(pos,p);point=list(centre);point[axis]=target[axis]+.5;point[1]=pos[1]+.15
    if math.hypot(point[0]-q['pos'][0],point[2]-q['pos'][2])>4 or abs(q['pos'][1]-pos[1])>.2:raise RuntimeError('Open-door flight is not a short current doorway leg')
    book={'world_session':client.world,'door':pos,'original':original_state,'opened':row['state'],'start':q['pos'],'target':point,'pending':None,'legs':[],'complete':False};path=out/'crossing.json';write_json(path,book)
    # Raise first, so a carpet at the far side is below the whole horizontal
    # body sweep. Native air_only verifies the actual open door's thin shape.
    side_axis=2 if axis==0 else 0
    aligned=[q['pos'][0],point[1],q['pos'][2]];aligned[side_axis]=centre[side_axis]
    targets=[[q['pos'][0],point[1],q['pos'][2]],aligned]
    distance=abs(point[axis]-aligned[axis]);steps=max(1,math.ceil(distance/.4))
    targets.extend([[aligned[i]+(point[i]-aligned[i])*step/steps for i in range(3)]for step in range(1,steps+1)])
    for target in targets:
        checkpoint()
        if read_block(client,pos)['state']!=row['state']:raise RuntimeError('Open door changed before the next normal flight leg')
        book['pending']={'target':target};write_json(path,book)
        try:r=client.checked('navigate',target=target,arrival=.04,air_only=True,seconds=15)
        finally:book['pending']['request_id']=client.last;write_json(path,book)
        book['legs'].append({'target':target,'request_id':client.last,'reply_phase':r['phase'],'actual':checkpoint()['pos']});book['pending']=None;write_json(path,book)
    after=checkpoint()
    if(after['pos'][axis]-pos[axis]-.5)*direction<.55:raise RuntimeError('Native flight did not actually cross the open door')
    if old.get('open')=='false':
        hand=crossing_hand(after);client.checked('select_item',item=hand);near={(0,1):'east',(0,-1):'west',(2,1):'south',(2,-1):'north'}[(axis,direction)]
        use_visible_door(client,pos,row['state'],hand,near)
        end=time.monotonic()+5
        while read_block(client,pos)['state']!=original_state:
            checkpoint()
            if time.monotonic()>end:raise RuntimeError('Original door state not confirmed; no second toggle')
            time.sleep(.15)
    book.update(complete=True,actual=checkpoint()['pos'],original_state_restored=True);write_json(path,book);return book
