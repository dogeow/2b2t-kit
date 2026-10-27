"""Observed dry Flight pursuit from an opened aquifer roof; no excavation."""
from collections import deque
from pathlib import Path
import math,time
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from .acquisition import _scan
from .aquifer_roof_access import water,DIRECTIONS
from .glow_cave_hunt import component,points_for,spawn_viewpoints,dry_attack_and_collect
from .loaded_squid_survey import read_glow
from .navigation import _body_sweep,_air_move

INK='minecraft:glow_ink_sac'

def wait_viewpoints(parents,waters,current,rows):
    """An unattended wait needs a freshly observed floor below its dry body.

    Spawn coverage alone can favor a deep unsupported hover over the pool's
    lower lava chamber. Preserve those cells for observations, not waiting.
    """
    return spawn_viewpoints(parents,waters,current,grid=1,floor_rows=rows)

def route_waypoints(parents,goal,rows):
    """Keep narrow-cave precision; avoid stopping every2m in tall open air."""
    cell=tuple(math.floor(v)for v in goal);path=[]
    while cell is not None:path.append(cell);cell=parents[cell]
    path.reverse();blocked={tuple(r['pos'])for r in rows};kept=[path[0]];direction=None
    for i in range(1,len(path)):
        d=tuple(path[i][j]-path[i-1][j]for j in range(3))
        if direction is not None and d!=direction and kept[-1]!=path[i-1]:kept.append(path[i-1])
        # Cruise's obstacle probe needs more headroom than the player body.
        # Check the entire straight stretch, not only its endpoint.
        start=path.index(kept[-1]);tall=all(
            (x+dx,y,z+dz)in parents and (x+dx,y+2,z+dz)not in blocked
            for x,y,z in path[start:i+1]for dx in(-1,0,1)for dz in(-1,0,1))
        if not tall and math.dist(kept[-1],path[i])>2 and kept[-1]!=path[i-1]:kept.append(path[i-1])
        limit=8 if tall else 2
        if math.dist(kept[-1],path[i])>=limit:kept.append(path[i])
        direction=d
    if kept[-1]!=path[-1]:kept.append(path[-1])
    return path,kept

def run(c,root,low,high,seed,out,checkpoint,*,target=8,seconds=600,radius=8):
    if not 1<=target<=64 or not 10<=seconds<=900:raise ValueError('Bounded actual ink hunt required')
    out=Path(out);out.mkdir(parents=True,exist_ok=False);file=out/'hunt.json'
    book={'world_session':c.world,'target':target,'initial':inventory_counts(checkpoint())[INK],
          'pending':None,'moves':[],'observations':[],'hunts':[],'mining_dispatched':False,'complete':False}
    write_json(file,book);until=time.monotonic()+seconds;deferred={};last_report=0;scene_index=0;wait_pose=None
    def state():
        q=checkpoint()
        if (q.get('world_session')!=c.world or q.get('under_water')or q.get('air_supply')!=300
                or not q.get('flight')):raise RuntimeError('Actual dry owned Flight pose required')
        return q
    def scene():
        nonlocal scene_index
        q=state();r=c.checked('scan',min=low,max=high,details=True)
        write_json(out/('scene-%03d.json'%scene_index),r);scene_index+=1
        if r.get('scan_cells_read')!=r.get('scan_total_cells')or r.get('scan_total_cells')!=math.prod(high[i]-low[i]+1 for i in range(3)):
            raise RuntimeError('Complete actual cave scene required')
        parents=component(r['blocks'],low,high,state()['pos'])
        waters={tuple(b['pos']):b for b in r['blocks']if water(b)};first=tuple(seed)
        if first not in waters:raise RuntimeError('Original actual aquifer source changed')
        pool={first};queue=deque([first])
        while queue:
            p=queue.popleft()
            for d in DIRECTIONS:
                v=tuple(p[i]+d[i]for i in range(3))
                if v in waters and v not in pool:pool.add(v);queue.append(v)
        selected=[waters[p]for p in pool if p[1]>=seed[1]and math.dist(p,seed)<=radius]
        return parents,selected,r['blocks']
    def route(parents,goal,rows,label,max_legs=4):
        path,kept=route_waypoints(parents,goal,rows)
        write_json(out/(label+'-path.json'),{'world_session':c.world,'cells':path,'waypoints':kept})
        for x,y,z in kept[1:1+max_legs]:
            q=state()
            if q['health']!=20 or q.get('guard_busy'):return False
            point=[x+.5,y+.1,z+.5]
            if _scan(c,*_body_sweep(q['pos'],point),state):raise RuntimeError('Actual dry hunt body route changed')
            book['pending']={'kind':'one_dry_air_leg','target':point};write_json(file,book)
            try:_air_move(c,point,15,arrival=.08)
            finally:book['pending']['request_id']=c.last;write_json(file,book)
            book['moves'].append({**book['pending'],'actual':state()['pos']});book['pending']=None;write_json(file,book)
        return len(kept)-1<=max_legs
    attempt=0
    while time.monotonic()<until and inventory_counts(state())[INK]<target:
        q=state()
        if q['health']!=20 or q.get('guard_busy'):time.sleep(.2);continue
        observed=read_glow(root,q)
        if time.monotonic()-last_report>=30:
            record={'time':q['time'],'pos':q['pos'],'health':q['health'],'ink':inventory_counts(q)[INK],'glows':observed}
            book['observations'].append(record);write_json(file,book);print('ACTUAL_AQUIFER_GLOW',record,flush=True);last_report=time.monotonic()
        candidates=[e for e in observed if all(low[i]<e['pos'][i]<high[i]-1 for i in range(3))
                    and(e['uuid']not in deferred or math.dist(e['pos'],deferred[e['uuid']][0])>1.5
                        or time.monotonic()-deferred[e['uuid']][1]>12)]
        parents=waters=rows=None
        if candidates:
            parents,waters,rows=scene();options=[]
            for e in candidates:
                poses=points_for(parents,e)
                if poses:options.append((e,min(poses,key=lambda p:math.dist(p,q['pos']))))
                else:deferred[e['uuid']]=(e['pos'],time.monotonic())
            if options:
                e,point=min(options,key=lambda pair:math.dist(pair[1],q['pos']))
                arrived=route(parents,point,rows,'chase-%03d'%attempt);attempt+=1
                if not arrived:continue
                fresh=next((v for v in read_glow(root,state())if v['uuid']==e['uuid']),None)
                if fresh is None:continue
                q=state()
                if q.get('on_ground'):raise RuntimeError('Actual dry airborne melee pose required')
                result=dry_attack_and_collect(c,fresh,out/('actual-wild-kill-%03d'%len(book['hunts'])),state)
                book['hunts'].append(result);write_json(file,book)
                c.set_progress(done=min(target,inventory_counts(state())[INK]),phase='荧光墨囊实际入包 %d／%d'%(inventory_counts(state())[INK],target))
                if result.get('known_not_attacked')and result.get('reason')=='Observed target moved outside dry melee reach':
                    # The animal is still a live target. Replan from our actual
                    # nearby pose rather than travelling back to the AFK point.
                    continue
                if not result.get('complete'):deferred[e['uuid']]=(fresh['pos'],time.monotonic())
                wait_pose=None;continue
        if wait_pose is None:
            if parents is None:parents,waters,rows=scene()
            offers=wait_viewpoints(parents,[r for r in waters if r.get('block_light')==r.get('sky_light')==0],q['pos'],rows)
            if not offers:raise RuntimeError('No currently observed dry spawn-wait viewpoint for the opened pool')
            wait_pose=offers[0]['point'];write_json(out/'actual-spawn-wait-pose.json',offers[0])
        if math.dist(state()['pos'],wait_pose)>.3:
            if parents is None:parents,waters,rows=scene()
            route(parents,wait_pose,rows,'wait-%03d'%attempt,max_legs=8);attempt+=1
        else:time.sleep(.2)
    q=state();book.update(complete=inventory_counts(q)[INK]>=target,actual_ink=inventory_counts(q)[INK],final_pose=q['pos'],health=q['health'])
    write_json(file,book);return book
