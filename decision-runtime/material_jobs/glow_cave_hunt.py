"""Current dry cave-air routes and guarded normal attacks at actual glow squid."""
from collections import deque
from pathlib import Path
import math,time
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from .loaded_squid_survey import read_glow
from .squid_ink import observed_live
from .local_air_path import move
from .dry_hover_harvest import pickup

INK='minecraft:glow_ink_sac'
def supported_recenter(rows,start):
    """A normal tiny ground walk may settle a hover over a proved full floor."""
    x,y,z=map(math.floor,start);by={tuple(r['pos']):r for r in rows}
    floor=by.get((x,y-1,z),{});name=floor.get('state','').split('}')[0].removeprefix('Block{')
    natural={'minecraft:'+n for n in ('stone','granite','diorite','andesite','deepslate','tuff','calcite','cobblestone','dripstone_block')}
    if(not 0<=start[1]-y<=.2 or (x,y,z)in by or(x,y+1,z)in by
       or name not in natural or floor.get('solid')is not True
       or floor.get('fluid')is not False or floor.get('block_entity')is not False):
        return None
    return [x+.5,float(y),z+.5]

def component(rows,low,high,start):
    by={tuple(r['pos']):r for r in rows};blocked=set(by);first=tuple(math.floor(v)for v in start)
    unsafe=set()
    for row in rows:
        state=row.get('state','');name=state.split('}')[0].removeprefix('Block{')
        hot=(name in {'minecraft:lava','minecraft:fire','minecraft:soul_fire','minecraft:magma_block','minecraft:cactus','minecraft:sweet_berry_bush','minecraft:wither_rose'}
             or name in {'minecraft:campfire','minecraft:soul_campfire'}and 'lit=true'in state)
        if hot:
            x,y,z=row['pos']
            unsafe.update((x+dx,y+dy,z+dz)for dx in(-1,0,1)for dy in(-2,-1,0,1)for dz in(-1,0,1))
            if name=='minecraft:lava':
                # A clear body alone did not prevent a real fire injury while
                # descending above exposed lava. Keep the observed open column
                # out of the route until a solid dry barrier separates it.
                for dx in(-1,0,1):
                    for dz in(-1,0,1):
                        for h in range(y+1,high[1]+1):
                            barrier=by.get((x+dx,h,z+dz),{})
                            if (barrier.get('solid')is True and barrier.get('fluid')is False
                                    and barrier.get('block_entity')is False):break
                            unsafe.add((x+dx,h,z+dz))
    def clear(p):
        # Observe the surrounding heat buffer too. A two-cell air body above
        # lava is not a safe waypoint after Flight settings settle.
        return (low[0]<p[0]<high[0]and low[1]<p[1]<=high[1]-2
                and low[2]<p[2]<high[2]and p not in blocked
                and(p[0],p[1]+1,p[2])not in blocked and p not in unsafe)
    if not clear(first):raise RuntimeError('Current cave start is not fully observed two-cell AIR with hazard clearance')
    parents={first:None};queue=deque([first])
    while queue:
        p=queue.popleft()
        for d in((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
            q=tuple(p[i]+d[i]for i in range(3))
            if q not in parents and clear(q):parents[q]=p;queue.append(q)
    return parents

def points_for(parents,entity):
    p=entity['pos'];result=[]
    for x,y,z in parents:
        point=[x+.5,y+.1,z+.5]
        if math.dist([point[0],point[1]+1.62,point[2]],[p[0],p[1]+.4,p[2]])<=2.65:
            result.append(point)
    return result

def spawn_wait_poses(parents,waters,current):
    """Observed dry poses outside every pool cell's 24-block exclusion zone."""
    if not waters or any(not r.get('state','').startswith('Block{minecraft:water}')
                         or r['pos'][1]>30 for r in waters):
        raise ValueError('Actual low-water cells required')
    centres=[[v+.5 for v in r['pos']]for r in waters]
    poses=[]
    for cell in parents:
        point=[cell[0]+.5,cell[1]+.1,cell[2]+.5]
        distances=[math.dist(point,p)for p in centres]
        if min(distances)>=25 and max(distances)<=96:
            poses.append(point)
    return sorted(poses,key=lambda p:math.dist(p,current))

def spawn_viewpoints(parents,waters,current,*,grid=2,floor_rows=None):
    """Rank dry poses by dark surface water 25..32 blocks away, not all water."""
    if type(grid)is not int or not 1<=grid<=4:
        raise ValueError('Bounded dry viewpoint sampling required')
    if any(not r.get('state','').startswith('Block{minecraft:water}')
           or r['pos'][1]>30 or r.get('block_light')!=0 or r.get('sky_light')!=0 for r in waters):
        raise ValueError('Current dark low-water observations required')
    surface=[[v+.5 for v in r['pos']]for r in waters
             if(r['pos'][0],r['pos'][1]+1,r['pos'][2])in parents]
    floors=None if floor_rows is None else {tuple(r['pos']):r for r in floor_rows
            if r.get('solid')is True and r.get('fluid')is False and r.get('block_entity')is False}
    result=[]
    for x,y,z in parents:
        if x%grid or y%grid or z%grid:continue
        if floors is not None and(x,y-1,z)not in floors:continue
        point=[x+.5,y+.1,z+.5];count=local=0
        for water in surface:
            distance=sum((point[i]-water[i])**2 for i in range(3))
            if 625<=distance<=1024:
                count+=1
                local+=max(abs(math.floor(water[0])//16-x//16),abs(math.floor(water[2])//16-z//16))<=1
        if count:result.append({'point':point,'huntable_dark_spawn_cells_25_to_32':count,
                                'same_or_adjacent_chunk_eligible':local,
                                'solid_floor_verified':floors is not None,
                                'distance_from_current':math.dist(point,current)})
    return sorted(result,key=lambda r:(-r['huntable_dark_spawn_cells_25_to_32'],
                  -r['same_or_adjacent_chunk_eligible'],r['distance_from_current']))

def follow(c,parents,goal,out,checkpoint,*,max_straight=6):
    """Compress a proved component route, then refresh actual body air per leg."""
    if type(max_straight)is not int or not 1<=max_straight<=6:
        raise ValueError('Dry cave steps must be one to six blocks')
    cell=tuple(math.floor(v)for v in goal)
    if cell not in parents:raise RuntimeError('Dry cave goal is outside current observed component')
    path=[]
    while cell is not None:path.append(cell);cell=parents[cell]
    path.reverse();kept=[path[0]];direction=None
    for i in range(1,len(path)):
        d=tuple(path[i][a]-path[i-1][a]for a in range(3))
        if direction is not None and d!=direction and kept[-1]!=path[i-1]:kept.append(path[i-1])
        if math.dist(kept[-1],path[i])>=max_straight:kept.append(path[i])
        direction=d
    if kept[-1]!=path[-1]:kept.append(path[-1])
    out=Path(out);out.mkdir(parents=True,exist_ok=False);write_json(out/'component-route.json',{'world_session':c.world,'path':[list(p)for p in path],'waypoints':[list(p)for p in kept],'block_mutations':0})
    actual=[]
    for i,(x,y,z)in enumerate(kept[1:]):
        checkpoint();move(c,[x+.5,y+.1,z+.5],out/('actual-air-leg-%02d'%i),max_straight=max_straight,foot_offset=.1,max_horizontal=12,exact_target=True);actual.append(checkpoint()['pos'])
    return actual

def dry_attack_and_collect(c,candidate,out,checkpoint):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);path=out/'wild-glow-squid.json';q=checkpoint()
    if candidate.get('type')!='minecraft:glow_squid'or candidate.get('has_custom_name')is not False or q.get('under_water')or q.get('in_water'):raise RuntimeError('Actual wild glow squid and dry owned attack pose required')
    before=inventory_counts(q)[INK];old={e['uuid']for e in q.get('entities',[])if e['type']=='minecraft:item'};book={'world_session':c.world,'entity':candidate,'before':before,'pending':None,'attacks':[],'complete':False};write_json(path,book)
    c.checked('select_item',item='minecraft:netherite_sword')
    for i in range(3):
        q=checkpoint()
        if q.get('under_water')or q.get('in_water')or q.get('guard_busy')or q.get('health')!=20:raise RuntimeError('Dry guarded melee environment changed; no attack')
        e=observed_live(c,candidate['uuid'],'minecraft:glow_squid',q)
        if e is None:break
        distance=math.dist([q['pos'][0],q['pos'][1]+1.62,q['pos'][2]],[e['pos'][0],e['pos'][1]+.4,e['pos'][2]])
        if distance>2.75:book.update(pending=None,known_not_attacked=True,reason='Observed target moved outside dry melee reach');write_json(path,book);return book
        end=time.monotonic()+2
        while checkpoint().get('attack_strength',0)<.95:
            if time.monotonic()>end:raise RuntimeError('Actual sword cooldown not ready')
            time.sleep(.1)
        centre=[math.floor(v)for v in e['pos']];health=e['health'];book['pending']={'kind':'one_normal_wild_glow_attack','uuid':e['uuid'],'health_before':health};write_json(path,book)
        try:r=c.request('material_ink_attack',entity_id=e['id'],expected_uuid=e['uuid'],region_min=[v-4 for v in centre],region_max=[v+4 for v in centre])
        finally:book['pending']['request_id']=c.last;write_json(path,book)
        write_json(out/('attack-%d-native.json'%i),r);proof=r.get('ink_attack')or{}
        if proof.get('pre_dispatch_rejected')is True and proof.get('action_sent')is False:
            book.update(pending=None,known_not_attacked=True,rejection=proof);write_json(path,book);return book
        if r.get('phase')!='done'or proof.get('action_sent')is not True:raise RuntimeError('Native attack outcome unconfirmed; no repeat')
        end=time.monotonic()+3
        while True:
            current=observed_live(c,candidate['uuid'],'minecraft:glow_squid',checkpoint())
            if current is None or current['health']<health:break
            if time.monotonic()>end:raise RuntimeError('Original attack has no observed health change; no next attack')
            time.sleep(.1)
        book['attacks'].append({'proof':proof,'after':current});book['pending']=None;write_json(path,book)
        if current is None:break
    end=time.monotonic()+15
    while True:
        q=checkpoint();now=inventory_counts(q)[INK]
        if now>before:break
        drops=[e for e in q.get('entities',[])if e['type']=='minecraft:item'and e['uuid']not in old and e.get('stack',{}).get('item')==INK and math.dist(e['pos'],candidate['pos'])<10]
        if drops:
            # Wait for the current buoyant drop, then use only scanned dry AIR
            # body cells. This never dives, changes air, or repeats an attack.
            for index,drop in enumerate(drops):
                count=inventory_counts(checkpoint())[INK]
                pickup(c,drop,count,out/('current-ink-air-pickup-%d'%index),checkpoint,item=INK,expected_count=drop['stack']['count'])
            if inventory_counts(checkpoint())[INK]>before:break
        if time.monotonic()>end:raise RuntimeError('Wild glow squid drops not yet confirmed in inventory; no next kill')
        time.sleep(.2)
    after=inventory_counts(checkpoint())[INK];book.update(complete=True,pending=None,after=after,actual_gain=after-before);write_json(path,book);return book
