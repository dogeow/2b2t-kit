"""Short, supported ground adjustment when a drop lies beyond an integer-grid pickup pose."""
import math,time,json
from material_plan import inventory_counts

def hazard(cell):
    state=cell.get('state','')
    return bool(cell.get('fluid')) or any(state.startswith('Block{minecraft:'+name+'}') for name in (
        'fire','soul_fire','cobweb','powder_snow','sweet_berry_bush','wither_rose','cactus','magma_block','campfire','soul_campfire'))

def clear_body(point,cells):
    for x in range(math.floor(point[0]-.31),math.floor(point[0]+.31)+1):
        for z in range(math.floor(point[2]-.31),math.floor(point[2]+.31)+1):
            for y in range(math.floor(point[1]+.01),math.floor(point[1]+1.8)+1):
                cell=cells.get((x,y,z))
                if cell and (cell.get('passable') is not True or hazard(cell)):return False
    return True

def clear_segment(start,end,rows):
    cells={tuple(r['pos']):r for r in rows}
    for step in range(21):
        p=[a+(b-a)*step/20 for a,b in zip(start,end)]
        for x in range(math.floor(p[0]-.31),math.floor(p[0]+.31)+1):
            for z in range(math.floor(p[2]-.31),math.floor(p[2]+.31)+1):
                support=cells.get((x,math.floor(p[1]-.01),z))
                if not support or not support.get('solid') or hazard(support):return False
                for y in range(math.floor(p[1]+.01),math.floor(p[1]+1.8)+1):
                    cell=cells.get((x,y,z))
                    if cell and (cell.get('passable') is not True or hazard(cell)):return False
    return True


def pickup_candidates(player,drop,rows):
    cells={tuple(r['pos']):r for r in rows};candidates=[]
    for y in {round(player[1]),math.floor(player[1]),math.floor(player[1])-1}:
        if not -.05<=player[1]-y<=1.05 or not y-.2<=drop[1]<=y+2.1:continue
        # Only a short, clear descent onto supported ground; no teleport or long fall.
        if not all(clear_body([player[0],player[1]+(y-player[1])*t/10,player[2]],cells) for t in range(11)):continue
        for x in range(math.floor(drop[0])-1,math.floor(drop[0])+2):
            for z in range(math.floor(drop[2])-1,math.floor(drop[2])+2):
                for ox in (.35,.5,.65):
                    for oz in (.35,.5,.65):
                        p=[x+ox,y,z+oz]
                        if abs(p[0]-drop[0])>1.25 or abs(p[2]-drop[2])>1.25 or sum((a-b)**2 for a,b in zip(player,p))>9:continue
                        if clear_segment([player[0],y,player[2]],p,rows):candidates.append(p)
    return sorted(candidates,key=lambda p:sum((a-b)**2 for a,b in zip(player,p)))


def collect_nearby_ground(client,drop):
    state=client.status();current=next((e for e in state.get('entities',[]) if e.get('uuid')==drop['uuid']),None)
    if not current or current.get('stack')!=drop.get('stack'):return False
    origin=state['pos'];pos=current['pos'];item=drop['stack']['item'];before=inventory_counts(state)[item]
    low=[math.floor(min(a,b))-2 for a,b in zip(origin,pos)];high=[math.ceil(max(a,b))+2 for a,b in zip(origin,pos)]
    rows=client.request('scan',min=low,max=high,details=True)['blocks']
    choices=pickup_candidates(origin,pos,rows)
    if not choices:return False
    # One bounded normal walk; never replay an ambiguous inventory/arrival failure.
    result=client.request('walk',target=choices[0],arrival=.08,seconds=8,restore_flight=True)
    if result.get('phase')!='done':return False
    until=time.monotonic()+3
    while time.monotonic()<until:
        state=client.status()
        if inventory_counts(state)[item]>=before+drop['stack']['count'] and not any(e.get('uuid')==drop['uuid'] for e in state.get('entities',[])):
            if getattr(client,'out',None):
                with (client.out/'ground-pickup-confirmed.jsonl').open('a') as stream:
                    stream.write(json.dumps({'time':state.get('time'),'world_session':state.get('world_session'),'item':item,'observed_drop_uuid':drop['uuid'],'expected_count':drop['stack']['count'],'inventory_before':before,'inventory_after':inventory_counts(state)[item],'position':state['pos'],'source_absent':True})+'\n')
            return True
        time.sleep(.2)
    return False
