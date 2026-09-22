"""Open a wooden door, walk through supported cells, then restore its original state."""
import json,math,time
from projection_completion import block_state
from survival_world import World,center
from work_access import approach_faces

WOOD_DOORS={f'minecraft:{wood}_door' for wood in ('oak','spruce','birch','jungle','acacia','dark_oak','mangrove','cherry','pale_oak','bamboo','crimson','warped')}

def crossing_destination(door,properties,player):
    axis=0 if properties['facing'] in ('east','west') else 2
    direction=1 if player[axis]<door[axis]+.5 else -1
    target=list(door);target[axis]+=direction
    return target,axis,direction

def read_block(client,pos):
    rows=client.request('scan',min=pos,max=pos,details=True)['blocks']
    if len(rows)!=1:raise RuntimeError('Door was removed or replaced')
    return rows[0]

def cross_door(client,pos):
    state=client.status();selection=state['projection_selection']
    if any(v<low or v>high for v,low,high in zip(pos,selection['min'],selection['max'])):
        raise RuntimeError('Door is outside the selected construction')
    row=read_block(client,pos);name,properties=block_state(row['state'])
    if name not in WOOD_DOORS or properties.get('half')!='lower' or properties.get('powered')!='false' or row.get('fluid'):
        raise RuntimeError('Expected a dry unpowered wooden door lower half')
    target,axis,direction=crossing_destination(pos,properties,state['pos']);was_open=properties['open']=='true'
    client.checked('select_item',item='minecraft:diamond_sword')
    face=approach_faces(client,pos,row['state'],('north','south','west','east','up','down'))
    if not was_open:
        client.checked('interact',pos=pos,face=face,expected_state=row['state'],expected_hand='minecraft:diamond_sword')
        time.sleep(.3)
    opened=read_block(client,pos);opened_name,p=block_state(opened['state'])
    if opened_name!=name or p.get('open')!='true':raise RuntimeError('Door opening not observed; no duplicate toggle')
    state=client.status();feet=state['pos'];low=[min(math.floor(feet[i]),pos[i])-3 for i in range(3)];high=[max(math.ceil(feet[i]),pos[i])+3 for i in range(3)]
    rows=client.request('scan',min=low,max=high,details=True)['blocks'];world=World(rows,low,high)
    start=list(feet)
    if abs(start[1]-round(start[1]))<=.2:start[1]=round(start[1])
    paths=world.paths(start,limit=1000)
    choices=[tuple([target[0],target[1]+dy,target[2]]) for dy in (0,-1,1)]
    available=[p for p in choices if p in paths]
    if not available:raise RuntimeError('No supported walk through the opened door')
    destination=min(available,key=lambda p:len(world.route(paths,p)));route=world.route(paths,destination)
    if len(route)>12:raise RuntimeError('Door crossing route is unexpectedly long')
    for waypoint in route:
        client.checked('walk',target=center(waypoint),arrival=.08,seconds=10,restore_flight=True)
    after=client.status()
    if (after['pos'][axis]-(pos[axis]+.5))*direction<.55:raise RuntimeError('Crossing was not observed beyond the door')
    if not was_open:
        actual=read_block(client,pos)
        if actual['state']!=row['state']:
            if actual['state']!=opened['state']:raise RuntimeError('Door changed during crossing; preserve the new state')
            client.checked('select_item',item='minecraft:diamond_sword')
            # Non-placement use accepts an actually visible face of the same block.
            client.checked('interact',pos=pos,face=face,expected_state=actual['state'],expected_hand='minecraft:diamond_sword')
            time.sleep(.3)
            if read_block(client,pos)['state']!=row['state']:raise RuntimeError('Original door state not restored')
    result={'door':pos,'before':row['state'],'destination':after['pos'],'restored':not was_open}
    with (client.out/'door-crossings.jsonl').open('a') as stream:stream.write(json.dumps(result,ensure_ascii=False)+'\n')
    print('DOOR_CROSSED',pos,flush=True);return result
