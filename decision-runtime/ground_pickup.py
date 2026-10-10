"""Short, supported ground adjustment when a drop lies beyond an integer-grid pickup pose."""
import math,time,json
from collections import deque
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


def farmland_route(player,drop,rows):
    """At most four ordinary steps over dry known farmland collision heights."""
    cells={tuple(r['pos']):r for r in rows};start=(math.floor(player[0]),math.floor(player[2]))
    heights={}
    for pos,row in cells.items():
        state=row.get('state','');farm=state.startswith('Block{minecraft:farmland}')
        if (not farm or row.get('fluid')is not False or row.get('block_entity')is not False
                or row.get('solid')is not False or abs(pos[1]+.9375-player[1])>1.05):continue
        height=pos[1]+.9375;point=[pos[0]+.5,height,pos[2]+.5]
        if math.hypot(point[0]-player[0],point[2]-player[2])>3:continue
        body=[cells.get((pos[0],y,pos[2]))for y in range(pos[1]+1,math.floor(height+1.8)+1)]
        if any(r and (r.get('passable')is not True or hazard(r) or r.get('block_entity')is not False)for r in body):continue
        if (pos[0],pos[2])in heights:return []
        heights[(pos[0],pos[2])]=height
    if start not in heights or abs(player[1]-heights[start])>.15:return []
    parents={start:None};depth={start:0};queue=deque([start]);end=None
    while queue:
        cell=queue.popleft();point=[cell[0]+.5,heights[cell],cell[1]+.5]
        if abs(point[1]-drop[1])<=.35 and math.hypot(point[0]-drop[0],point[2]-drop[2])<=.7:
            end=cell;break
        if depth[cell]>=4:continue
        for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
            nxt=(cell[0]+dx,cell[1]+dz)
            if nxt not in heights or nxt in parents or abs(heights[nxt]-heights[cell])>1.000001:continue
            # Extra jump headroom at the higher side remains checked; the
            # native walk handles actual .9375 farmland and its one-block step.
            ceiling=math.floor(max(heights[nxt],heights[cell])+2.8)
            if any((r:=cells.get((cx,y,cz))) and (r.get('passable')is not True or hazard(r))
                   for cx,cz in (cell,nxt)for y in range(math.floor(max(heights[nxt],heights[cell])+1.8),ceiling+1)):continue
            parents[nxt]=cell;depth[nxt]=depth[cell]+1;queue.append(nxt)
    if end is None:return []
    path=[]
    while end!=start:
        path.append([end[0]+.5,heights[end],end[1]+.5]);end=parents[end]
    return list(reversed(path))


def collect_nearby_ground(client,drop):
    state=client.status();current=next((e for e in state.get('entities',[]) if e.get('uuid')==drop['uuid']),None)
    if not current or current.get('stack')!=drop.get('stack'):return False
    origin=state['pos'];pos=current['pos'];item=drop['stack']['item'];before=inventory_counts(state)[item]
    low=[math.floor(min(a,b))-2 for a,b in zip(origin,pos)];high=[math.ceil(max(a,b))+2 for a,b in zip(origin,pos)]
    rows=client.request('scan',min=low,max=high,details=True)['blocks']
    choices=pickup_candidates(origin,pos,rows)
    route=[]
    if not choices and item in ('minecraft:wheat','minecraft:wheat_seeds'):
        route=farmland_route(origin,pos,rows)
    if not choices and not route:return False
    # One bounded normal walk; never replay an ambiguous inventory/arrival failure.
    for target in route or choices[:1]:
        fresh=client.status()
        if inventory_counts(fresh)[item]==before+drop['stack']['count'] and not any(e.get('uuid')==drop['uuid']for e in fresh.get('entities',[])):return True
        same=next((e for e in fresh.get('entities',[])if e.get('uuid')==drop['uuid']),None)
        if not same or same.get('stack')!=drop.get('stack')or inventory_counts(fresh)[item]!=before:return False
        result=client.request('walk',target=target,arrival=.08,seconds=8,restore_flight=True)
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
