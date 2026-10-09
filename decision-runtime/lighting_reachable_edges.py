"""Light an occluded floor from an observed open adjacent column.

No tunnelling, block removal, inferred AIR, or changes to the lighting registry.
Native interaction still verifies the actual face, reach and ray immediately
before sending input. An interaction intent is never repeated.
"""
import math
import time
import heapq
from collections import deque
from lighting_cli import (LightingRun, LightingBlocked, TORCH, EVIDENCE, bounds,
    candidate_protected, safe_dark_support, safe_support, scan_cells, stock, later_torch_frame,
    risk_counts, validate_native_details, write_json, safe_noncolliding_plant,block_id,known_rejected_intent,verified_own_torch)

TRAVEL_FOOT_OFFSET=.195

def verified_native_guard_binding(state):
    return (isinstance(state,dict)
        and (state.get('kit_version'),state.get('runtime_version'))in
            (('2026.10.9.1','1.7.88'),('2026.10.9.2','1.7.88'),('2026.10.9.2','1.7.89'))
        and state.get('runtime_host_api')==3 and type(state.get('guard_busy'))is bool)


def ray_clear(cells, eye, support):
    aim = (support[0]+.5, support[1]+1-.001, support[2]+.5)
    distance = math.dist(eye, aim)
    if distance > 4.4:
        return False
    # Conservative full-voxel prediction; native uses the real collision shape.
    for i in range(math.ceil(distance/.04)+1):
        t = i / max(1, math.ceil(distance/.04))
        point = tuple(math.floor(eye[a]+(aim[a]-eye[a])*t) for a in range(3))
        replace_target=(support[0],support[1]+1,support[2])
        if point in cells and point != tuple(support) and not(point==replace_target and replaceable_short_grass(cells[point])):
            return False
    return True


def observed_exit_route(cells, station, low, high, budget=4000):
    """Axis steps with two full headroom cells, ending in an open exit column."""
    first=tuple(math.floor(v)for v in station)
    def clear(n):
        return (all(low[i]<=n[i]<=high[i] for i in range(3))
                and n[1]+1<=high[1] and all((n[0],y,n[2])not in cells or safe_noncolliding_plant(cells[(n[0],y,n[2])]) for y in (n[1],n[1]+1)))
    if not clear(first):return None
    queue=deque([first]);parents={first:None}
    while queue and len(parents)<=budget:
        n=queue.popleft()
        if all((n[0],y,n[2])not in cells or safe_noncolliding_plant(cells[(n[0],y,n[2])]) for y in range(n[1],high[1]+1)):
            route=[]
            while n is not None:
                route.append([n[0]+.5,n[1]+.1,n[2]+.5]);n=parents[n]
            # The returned order starts in open air and ends at the station.
            return route
        for delta in ((1,0,0),(-1,0,0),(0,0,1),(0,0,-1),(0,1,0),(0,-1,0)):
            nxt=tuple(n[i]+delta[i]for i in range(3))
            if nxt in parents or not clear(nxt):continue
            if delta[1]and any((n[0],y,n[2])in cells and not safe_noncolliding_plant(cells[(n[0],y,n[2])]) for y in range(min(n[1],nxt[1]),max(n[1],nxt[1])+2)):continue
            parents[nxt]=n;queue.append(nxt)
    return None


def exterior_surface_support(cells,pos):
    """Separate covered natural surface from a floor below dirt/stone terrain."""
    for p,row in cells.items():
        if p[0]!=pos[0]or p[2]!=pos[2]or p[1]<=pos[1]:continue
        if row.get('fluid')or row.get('block_entity'):return False
        if safe_noncolliding_plant(row):continue
        name=block_id(row)
        if name.endswith('_leaves') and 'persistent=false'in row.get('state',''):continue
        if name.endswith('_log'):continue
        if name=='minecraft:torch'and row.get('passable')is True:continue
        return False
    return True


def replaceable_short_grass(row):
    return bool(safe_noncolliding_plant(row)and row['state']=='Block{minecraft:short_grass}'and row.get('replaceable')is True)


def interaction_surface(cells,support,target):
    plant=cells.get(tuple(target))
    return (list(target),plant['state'])if replaceable_short_grass(plant)else(list(support),cells[tuple(support)]['state'])


def blocking_lighting_entities(rows):
    """Normal drops do not collide with a block use; preserve every other blocker."""
    if not isinstance(rows,list):
        raise LightingBlocked('Complete current entity observation required')
    return [row for row in rows if not(isinstance(row,dict)
            and row.get('type')in ('minecraft:item','minecraft:experience_orb')
            and row.get('hostile')is False and type(row.get('alive'))is bool)]


def entity_free_box(entities,lower,upper):
    for entity in blocking_lighting_entities(entities):
        box=entity.get('bounds')if isinstance(entity,dict)else None
        if not isinstance(box,dict)or any(not isinstance(box.get(k),list)or len(box[k])!=3
            or any(type(v)not in (int,float)or not math.isfinite(v)for v in box[k])for k in ('min','max')):
            return False
        if any(box['min'][i]>=box['max'][i]for i in range(3)):return False
        if all(box['max'][i]>lower[i]and box['min'][i]<upper[i]for i in range(3)):return False
    return True


def compress_axis_route(route):
    """Keep turns/endpoints; a straight corridor needs one native waypoint."""
    if len(route)<3:return [list(p)for p in route]
    result=[list(route[0])]
    def direction(a,b):return tuple(0 if x==y else (1 if y>x else -1)for x,y in zip(a,b))
    for i in range(1,len(route)-1):
        if direction(route[i-1],route[i])!=direction(route[i],route[i+1]):result.append(list(route[i]))
    result.append(list(route[-1]));return result


def shortcut_observed_route(cells,route,low,high,entities):
    """Remove a turn only when its entire conservative body box was observed clear."""
    boxes=[]
    for entity in blocking_lighting_entities(entities):
        box=entity.get('bounds')if isinstance(entity,dict)else None
        if not isinstance(box,dict):return route
        boxes.append(box)
    def clear(a,b):
        lower=[min(a[0],b[0])-.6,min(a[1],b[1]),min(a[2],b[2])-.6]
        upper=[max(a[0],b[0])+.6,max(a[1],b[1])+1.8,max(a[2],b[2])+.6]
        if any(lower[i]<low[i]or upper[i]>high[i]+1 for i in range(3)):return False
        if any(all(box['max'][i]>lower[i]and box['min'][i]<upper[i]for i in range(3))for box in boxes):return False
        return not any(not safe_noncolliding_plant(row)
            and all(p[i]+1>lower[i]and p[i]<upper[i]for i in range(3))for p,row in cells.items())
    if len(route)<3:return route
    result=[list(route[0])];index=0
    while index<len(route)-1:
        following=next((j for j in range(len(route)-1,index,-1)if clear(route[index],route[j])),index+1)
        result.append(list(route[following]));index=following
    return result


def observed_station_route(cells,start,station,low,high,entities=None,budget=4000):
    """A short six-axis route through this complete observed volume, not inferred AIR."""
    validate_native_details(cells)
    obstacles=blocking_lighting_entities([] if entities is None else entities)
    boxes=[]
    for entity in obstacles:
        box=entity.get('bounds')if isinstance(entity,dict)else None
        if not isinstance(box,dict)or any(not isinstance(box.get(k),list)or len(box[k])!=3
            or any(type(v)not in (int,float)or not math.isfinite(v)for v in box[k])for k in ('min','max')):
            return None
        if any(box['min'][i]>=box['max'][i]for i in range(3)):return None
        boxes.append(box)
    def body(n):return ([n[0]+.15,n[1]+TRAVEL_FOOT_OFFSET,n[2]+.15],
                        [n[0]+.85,n[1]+TRAVEL_FOOT_OFFSET+1.8,n[2]+.85])
    def entities_clear(a,b):
        al,ah=body(a);bl,bh=body(b)
        lower=[min(al[i],bl[i])for i in range(3)];upper=[max(ah[i],bh[i])for i in range(3)]
        return not any(all(box['max'][i]>lower[i]and box['min'][i]<upper[i]for i in range(3))for box in boxes)
    def clear_volume(lower,upper):
        return (all(low[i]<=lower[i]and upper[i]<=high[i]+1 for i in range(3))
            and not any(not safe_noncolliding_plant(row)
                and all(p[i]+1>lower[i]and p[i]<upper[i]for i in range(3))for p,row in cells.items())
            and not any(all(box['max'][i]>lower[i]and box['min'][i]<upper[i]for i in range(3))for box in boxes))
    def clear(n):return clear_volume(*body(n))
    goal=tuple(math.floor(v)for v in station)
    if not clear(goal):return None
    starts=[(math.floor(start[0]),y,math.floor(start[2]))for y in {math.floor(start[1]),math.ceil(start[1])}]
    starts=[n for n in starts if clear(n)and math.dist(start,[n[0]+.5,n[1]+TRAVEL_FOOT_OFFSET,n[2]+.5])<=1]
    if not starts:return None
    first=min(starts,key=lambda n:math.dist(start,[n[0]+.5,n[1]+TRAVEL_FOOT_OFFSET,n[2]+.5]))
    # The actual pose can be off the grid centre after native braking. Keep the
    # connection to that centre unless its complete observed body sweep is clear.
    centre=[first[0]+.5,first[1]+TRAVEL_FOOT_OFFSET,first[2]+.5]
    lower=[min(start[i],centre[i])-(.35 if i!=1 else 0)for i in range(3)]
    upper=[max(start[i],centre[i])+(.35 if i!=1 else 1.8)for i in range(3)]
    if not clear_volume(lower,upper):return None
    def distance(n):return sum(abs(n[i]-goal[i])for i in range(3))
    queue=[(distance(first),distance(first),first)];parents={first:None};costs={first:0}
    while queue and len(parents)<=budget:
        priority,_,n=heapq.heappop(queue)
        if priority!=costs[n]+distance(n):continue
        if n==goal:
            route=[]
            while n is not None:
                route.append([n[0]+.5,n[1]+TRAVEL_FOOT_OFFSET,n[2]+.5]);n=parents[n]
            route.reverse();return compress_axis_route(route)
        neighbours=[tuple(n[i]+d[i]for i in range(3))for d in ((1,0,0),(-1,0,0),(0,0,1),(0,0,-1),(0,1,0),(0,-1,0))]
        neighbours.sort(key=distance)
        for nxt in neighbours:
            cost=costs[n]+1
            if cost<costs.get(nxt,math.inf)and clear(nxt)and entities_clear(n,nxt):
                parents[nxt]=n;costs[nxt]=cost;heapq.heappush(queue,(cost+distance(nxt),distance(nxt),nxt))
    return None


def lowest_transit_height(cells,start,entry,ceiling):
    """Lowest observed clear horizontal corridor; native checks every complete leg."""
    floor_y=max(start[1],entry[1]);heights={floor_y}
    occupied=[row for row in cells.values()if not safe_noncolliding_plant(row)]
    heights.update(row['pos'][1]+1.1 for row in occupied if floor_y<=row['pos'][1]+1.1<=ceiling)
    legs=[(start[0],start[2],entry[0],start[2]),(entry[0],start[2],entry[0],entry[2])]
    for height in sorted(h for h in heights if h<=ceiling):
        if not any(row['pos'][1]+1>height and row['pos'][1]<height+1.81
            and any(row['pos'][0]+1>min(x1,x2)-.35 and row['pos'][0]<max(x1,x2)+.35
                    and row['pos'][2]+1>min(z1,z2)-.35 and row['pos'][2]<max(z1,z2)+.35
                    for x1,z1,x2,z2 in legs)for row in occupied):return height
    return None


def edge_candidates(cells, low, high, start, protected=None,*,surface_only=False,entities=None,station_height=1.1,target_bounds=None,hostile_clearance=0):
    if type(station_height)not in (int,float)or not math.isfinite(station_height)or not 1.1<=station_height<=3.3:
        raise ValueError('Station height must remain within verified normal block reach')
    low, high = bounds(low, high)
    if type(hostile_clearance)not in (int,float)or not math.isfinite(hostile_clearance)or not 0<=hostile_clearance<=40:
        raise ValueError('Hostile station clearance must be explicit and bounded')
    target_low,target_high=(bounds(target_bounds['min'],target_bounds['max'])if target_bounds is not None else (low,high))
    if any(target_low[i]<low[i]or target_high[i]>high[i]for i in range(3)):
        raise ValueError('Target lighting bounds must be contained in the complete scan')
    validate_native_details(cells)
    dark = [p for p,r in cells.items() if r.get('zombie_block_light_risk')is True
            and not candidate_protected(p,(p[0],p[1]+1,p[2]),protected)
            and all(target_low[i]<=p[i]<=target_high[i]for i in range(3))
            and(not surface_only or exterior_surface_support(cells,p))]
    supports=[p for p in dark if safe_dark_support(cells[p])]
    lit_neighbour=(not supports or hostile_clearance>0)and bool(dark)
    if lit_neighbour:
        supports=[p for p,r in cells.items()if safe_support(r,require_dark=False)
                  and not candidate_protected(p,(p[0],p[1]+1,p[2]),protected)
                  and any(sum(abs(a-b)for a,b in zip(p,q))<=11 for q in dark)]
    result=[]
    route_cache={}
    for support in supports:
        x,y,z=support;target=(x,y+1,z)
        if (target in cells and not replaceable_short_grass(cells[target]))or y+1<low[1] or y+3>high[1]:
            continue
        stations=[]
        for dx,dz in [(a,b) for a in range(-3,4) for b in range(-3,4)
                      if 1<=a*a+b*b<=9]:
            sx,sz=x+dx,z+dz
            if not low[0]<=sx<=high[0] or not low[2]<=sz<=high[2]:
                continue
            station=[sx+.5,y+station_height,sz+.5]
            if hostile_clearance>0:
                threats=[e for e in (entities or [])if not isinstance(e,dict)or e.get('hostile')is True]
                if any(not isinstance(e,dict)or not isinstance(e.get('pos'),list)or len(e['pos'])!=3
                    or any(type(v)not in (int,float)or not math.isfinite(v)for v in e['pos'])
                    or math.hypot(station[0]-e['pos'][0],station[2]-e['pos'][2])<hostile_clearance for e in threats):continue
            if entities is not None:
                pre_low=[min(support[i],math.floor(station[i]-(.35 if i!=1 else 0)))for i in range(3)]
                pre_high=[max(target[i],math.floor(station[i]+(.35 if i!=1 else 1.81+1.62)))+1 for i in range(3)]
                if not entity_free_box(entities,pre_low,pre_high):continue
            # Native arrival can settle up to .2 below a requested waypoint.
            # A face must remain visible at that lower actual eye position.
            if not all(ray_clear(cells,[station[0]+ox,station[1]+1.62-.2,station[2]+oz],support)
                       for ox,oz in ((0,0),(-.2,-.2),(-.2,.2),(.2,-.2),(.2,.2))):
                continue
            key=tuple(station)
            if key not in route_cache:route_cache[key]=observed_exit_route(cells,station,low,high)
            route=route_cache[key]
            if route and entities is not None:
                first=route[0]
                if not entity_free_box(entities,[first[0]-.35,first[1],first[2]-.35],
                    [first[0]+.35,high[1]+1,first[2]+.35]):continue
                if any(not entity_free_box(entities,[min(a[0],b[0])-.35,min(a[1],b[1]),min(a[2],b[2])-.35],
                    [max(a[0],b[0])+.35,max(a[1],b[1])+1.8,max(a[2],b[2])+.35])for a,b in zip(route,route[1:])):continue
            if route:stations.append((station,route))
        if stations:
            station,route=min(stations,key=lambda p:(math.dist(p[0],[x+.5,y+1,z+.5]),len(p[1])+math.dist(start,p[1][0])))
            score=sum(sum(abs(a-b)for a,b in zip(support,p))<=11 for p in dark)
            result.append({'support':list(support),'target':list(target),
                'support_state':cells[support]['state'],'station':station,
                'entry_route':route,
                'lit_neighbour':lit_neighbour,
                'prediction_dark_neighbours':score})
    return sorted(result,key=lambda r:(-r['prediction_dark_neighbours'],math.dist(start,r['station'])))


class ReachableEdgeLightingRun(LightingRun):
    def __init__(self,*args,surface_only=False,native_guard_only=False,station_height=1.1,target_bounds=None,hostile_clearance=0,**kwargs):
        if type(station_height)not in (int,float)or not math.isfinite(station_height)or not 1.1<=station_height<=3.3:
            raise ValueError('Station height must remain within verified normal block reach')
        if type(native_guard_only)is not bool:raise ValueError('Native guard mode must be explicit boolean')
        if native_guard_only:
            initial=args[5]if len(args)>5 else kwargs['initial']
            if not verified_native_guard_binding(initial):
                raise LightingBlocked('Native guard mode requires the verified current Kit/runtime binding')
        super().__init__(*args,**kwargs);self.surface_only=surface_only
        self.report['surface_only']=surface_only
        self.native_guard_only=native_guard_only;self.report['native_guard_only']=native_guard_only
        self.station_height=station_height;self.report['station_height']=station_height
        self.target_bounds=target_bounds;self.hostile_clearance=hostile_clearance
        if type(hostile_clearance)not in (int,float)or not math.isfinite(hostile_clearance)or not 0<=hostile_clearance<=40:
            raise ValueError('Hostile station clearance must be explicit and bounded')
        if target_bounds is not None:
            lo,hi=bounds(target_bounds['min'],target_bounds['max'])
            if any(lo[i]<self.low[i]or hi[i]>self.high[i]for i in range(3)):raise ValueError('Target bounds exceed scan')
        self.report['target_bounds']=target_bounds;self.report['hostile_clearance']=hostile_clearance
        self.last_entry_route=None
        self.keep_low_between_placements=False
    def counts(self,cells):
        complete_cells=cells
        target=getattr(self,'target_bounds',None)
        if target is not None:cells={p:r for p,r in cells.items()if all(target['min'][i]<=p[i]<=target['max'][i]for i in range(3))}
        if not self.surface_only:return risk_counts(cells,self.protected)
        selected={p:r for p,r in cells.items()if r.get('zombie_spawn_floor')and exterior_surface_support(complete_cells,p)}
        return risk_counts(selected,self.protected)
    def follow_route(self,route,state):
        for waypoint in compress_axis_route(route):
            if math.dist(state['pos'],waypoint)>.4:self.move(waypoint);state=self.c.status()
        return state
    def local_station_route(self,state,station):
        start=state['pos']
        if abs(start[1]-station[1])>12 or math.dist(start,station)>32:return None
        low=[max(self.move_low[i],math.floor(min(start[i],station[i]))-(1 if i==1 else 2))for i in range(3)]
        high=[min(self.move_high[i],math.ceil(max(start[i],station[i]))+(5 if i==1 else 2))for i in range(3)]
        if math.prod(high[i]-low[i]+1 for i in range(3))>50000:return None
        reply=self.scan(low,high);cells=scan_cells(reply,low,high,self.c.world)
        cells={p:r for p,r in cells.items()if not verified_own_torch(r,self.report['placed'],self.c.world,self.c.task,state['time'])}
        route=observed_station_route(cells,start,station,low,high,reply['scan_entities'])
        return shortcut_observed_route(cells,route,low,high,reply['scan_entities'])if route else None
    def approach_edge_station(self,candidate,state,index):
        station=candidate['station'];route=candidate['entry_route'];entry=route[0]
        local=self.local_station_route(state,station)
        if local is not None:
            self.report.setdefault('routes',[]).append({'kind':'observed_local_station_route','index':index,'waypoints':local})
            self.follow_route(local,state);return
        if self.last_entry_route and math.dist(state['pos'],self.last_entry_route[-1])<=.6:
            state=self.follow_route(list(reversed(self.last_entry_route[:-1])),state)
        high_y=max(state['pos'][1],self.high[1]-2)
        low=[max(self.move_low[i],math.floor(min(state['pos'][i],entry[i]))-(0 if i==1 else 1))for i in range(3)]
        high=[min(self.move_high[i],math.ceil(max(state['pos'][i],entry[i]))+(2 if i==1 else 1))for i in range(3)]
        high[1]=min(self.move_high[1],max(high[1],self.high[1]))
        if math.prod(high[i]-low[i]+1 for i in range(3))<=50000:
            reply=self.scan(low,high);cells=scan_cells(reply,low,high,self.c.world)
            observed=lowest_transit_height(cells,state['pos'],entry,high[1]-1.81)
            if observed is not None:high_y=observed
        self.report.setdefault('routes',[]).append({'kind':'observed_entry_transit','index':index,'height':high_y})
        self.follow_route([[state['pos'][0],high_y,state['pos'][2]],
                           [entry[0],high_y,state['pos'][2]],[entry[0],high_y,entry[2]]]+route,state)
    def place_edge(self,candidate,index):
        support=tuple(candidate['support']);target=candidate['target'];station=candidate['station'];route=candidate['entry_route'];entry=route[0]
        state=self.wait_for_guard(stage='before_edge_station')
        return_high=max(state['pos'][1],self.high[1]-2)
        self.approach_edge_station(candidate,state,index)
        state=self.wait_for_guard(stage='before_edge_selection')
        if math.dist(state['pos'],station)>.6:
            raise LightingBlocked('Actual adjacent station changed')
        self.c.checked('select_item',item=TORCH)
        state=self.wait_for_guard(stage='before_edge_interaction')
        if math.dist(state['pos'],station)>.6 or stock(state)<1:
            raise LightingBlocked('Adjacent station or exact torch stock changed')
        lo=[min(support[i],math.floor(station[i]-(.35 if i!=1 else 0)))for i in range(3)]
        hi=[max(target[i],math.floor(station[i]+(.35 if i!=1 else 1.81+1.62)))for i in range(3)]
        current=self.scan(lo,hi,f'edge-pre-{index}.json');cells=scan_cells(current,lo,hi,self.c.world)
        row=cells.get(support)
        if (not row or row['state']!=candidate['support_state']or not safe_support(row,require_dark=not candidate.get('lit_neighbour',False))
                or tuple(target)in cells and not replaceable_short_grass(cells[tuple(target)]) or candidate_protected(support,target,self.protected)
                or blocking_lighting_entities(current['scan_entities'])):
            raise LightingBlocked('Current adjacent support/target/entity proof changed')
        latest=self.fresh()
        if (math.dist(latest['pos'],station)>.6 or self.guard_blocking(latest)
                or latest['hand']['item']!=TORCH):
            raise LightingBlocked('Current guard or adjacent station changed')
        before=stock(latest)
        intent={'world_session':self.c.world,'task_session':self.c.task,
                'support':list(support),'target':target,'state':'interaction_intent',
                'before_stock':before,'before_time':latest['time'],
                'access':'observed_air_route_and_native_face_checked'}
        path=self.intent_path(target)
        if path.exists():
            import json
            prior=json.loads(path.read_text())
            if not known_rejected_intent(prior,self.c.root):
                raise LightingBlocked('Existing torch intent is never repeated')
            archived=self.out/f'prior-proved-no-send-{index}.json'
            write_json(archived,prior)
            intent['prior_proved_no_send']=str(archived)
        write_json(path,intent);write_json(self.out/f'edge-before-{index}.json',latest)
        interaction_pos,interaction_state=interaction_surface(cells,support,target)
        ack=self.c.checked('interact',pos=interaction_pos,face='up',expected_state=interaction_state,expected_hand=TORCH)
        write_json(self.out/f'edge-interaction-{index}.json',ack)
        deadline=time.monotonic()+8;frames=[];last=latest['time']
        while time.monotonic()<deadline:
            actual=self.scan(target,target);state=self.fresh()
            if later_torch_frame(actual,state,target,self.c.world,before,last):
                frames.append({'actual':actual,'inventory':state});last=state['time']
                if len(frames)>=2:break
            time.sleep(.2)
        if len(frames)<2:raise LightingBlocked('Adjacent torch unknown; preserve intent without repeat')
        write_json(self.out/f'edge-confirmed-{index}.json',frames)
        intent.update(state='verified',after_stock=stock(state),after_time=state['time'],
                      later_verified_frames=2,interaction_request=ack['id'],evidence_scope=EVIDENCE,
                      observed_block_state=actual['blocks'][0]['state'])
        write_json(path,intent);self.report['placed'].append(intent);self.save()
        self.last_entry_route=[list(p)for p in route]
        # Direct one-point recovery callers keep their existing high-return
        # contract. Continuous work stays low until the next station or park.
        if not getattr(self,'keep_low_between_placements',False):
            state=self.follow_route(list(reversed(route[:-1])),self.c.status())
            self.follow_route([[entry[0],return_high,entry[2]]],state)

    def work(self):
        self.reject_unknown_intents()
        self.keep_low_between_placements=True
        for i in range(self.limit):
            reply=self.scan(self.low,self.high,f'edge-survey-{i}.json')
            cells=scan_cells(reply,self.low,self.high,self.c.world)
            counts=self.counts(cells)
            self.report['all_scanned_counts']=risk_counts(cells,self.protected)
            if i==0:self.report['before']=counts
            self.report['after']=counts;self.save()
            if not counts['unprotected_dark_floor']:break
            candidates=edge_candidates(cells,self.low,self.high,self.fresh()['pos'],self.protected,
                surface_only=self.surface_only,entities=reply['scan_entities'],station_height=getattr(self,'station_height',1.1),
                target_bounds=getattr(self,'target_bounds',None),hostile_clearance=getattr(self,'hostile_clearance',0))
            if not candidates:break
            self.place_edge(candidates[0],i)
        if counts['unprotected_dark_floor']==0:
            write_json(self.out/'edge-final-survey.json',reply)
        else:reply=self.scan(self.low,self.high,'edge-final-survey.json')
        self.report['after']=self.counts(scan_cells(reply,self.low,self.high,self.c.world))
        self.report.update(state='bounded_run_finished',remaining_unprotected_risk=self.report['after']['unprotected_dark_floor'])
        self.save()
        self.keep_low_between_placements=False
    def park(self):
        state=self.fresh(work=False)
        if self.last_entry_route and math.dist(state['pos'],self.last_entry_route[-1])<=.6:
            self.follow_route(list(reversed(self.last_entry_route[:-1])),state)
        super().park()
