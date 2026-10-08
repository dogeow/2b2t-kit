"""Light an occluded floor from an observed open adjacent column.

No tunnelling, block removal, inferred AIR, or changes to the lighting registry.
Native interaction still verifies the actual face, reach and ray immediately
before sending input. An interaction intent is never repeated.
"""
import math
import time
from collections import deque
from lighting_cli import (LightingRun, LightingBlocked, TORCH, EVIDENCE, bounds,
    candidate_protected, safe_dark_support, scan_cells, stock, later_torch_frame,
    risk_counts, validate_native_details, write_json, safe_noncolliding_plant,block_id,known_rejected_intent)


def ray_clear(cells, eye, support):
    aim = (support[0]+.5, support[1]+1-.001, support[2]+.5)
    distance = math.dist(eye, aim)
    if distance > 4.4:
        return False
    # Conservative full-voxel prediction; native uses the real collision shape.
    for i in range(math.ceil(distance/.04)+1):
        t = i / max(1, math.ceil(distance/.04))
        point = tuple(math.floor(eye[a]+(aim[a]-eye[a])*t) for a in range(3))
        if point in cells and point != tuple(support):
            return False
    return True


def observed_exit_route(cells, station, low, high, budget=4000):
    """Axis steps with two full headroom cells, ending in an open exit column."""
    first=tuple(math.floor(v)for v in station)
    def clear(n):
        return (all(low[i]<=n[i]<=high[i] for i in range(3))
                and n[1]+1<=high[1] and all((n[0],y,n[2])not in cells for y in (n[1],n[1]+1)))
    if not clear(first):return None
    queue=deque([first]);parents={first:None}
    while queue and len(parents)<=budget:
        n=queue.popleft()
        if all((n[0],y,n[2])not in cells for y in range(n[1],high[1]+1)):
            route=[]
            while n is not None:
                route.append([n[0]+.5,n[1]+.1,n[2]+.5]);n=parents[n]
            # The returned order starts in open air and ends at the station.
            return route
        for delta in ((1,0,0),(-1,0,0),(0,0,1),(0,0,-1),(0,1,0),(0,-1,0)):
            nxt=tuple(n[i]+delta[i]for i in range(3))
            if nxt in parents or not clear(nxt):continue
            if delta[1]and any((n[0],y,n[2])in cells for y in range(min(n[1],nxt[1]),max(n[1],nxt[1])+2)):continue
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


def edge_candidates(cells, low, high, start, protected=None,*,surface_only=False):
    low, high = bounds(low, high)
    validate_native_details(cells)
    dark = [p for p,r in cells.items() if safe_dark_support(r)
            and not candidate_protected(p,(p[0],p[1]+1,p[2]),protected)
            and(not surface_only or exterior_surface_support(cells,p))]
    result=[]
    route_cache={}
    for support in dark:
        x,y,z=support;target=(x,y+1,z)
        if (target in cells and not replaceable_short_grass(cells[target]))or y+1<low[1] or y+3>high[1]:
            continue
        stations=[]
        for dx,dz in [(a,b) for a in range(-3,4) for b in range(-3,4)
                      if 1<=a*a+b*b<=9]:
            sx,sz=x+dx,z+dz
            if not low[0]<=sx<=high[0] or not low[2]<=sz<=high[2]:
                continue
            station=[sx+.5,y+1.1,sz+.5]
            # Native arrival can settle up to .2 below a requested waypoint.
            # A face must remain visible at that lower actual eye position.
            if not ray_clear(cells,[station[0],station[1]+1.62-.2,station[2]],support):
                continue
            key=tuple(station)
            if key not in route_cache:route_cache[key]=observed_exit_route(cells,station,low,high)
            route=route_cache[key]
            if route:stations.append((station,route))
        if stations:
            station,route=min(stations,key=lambda p:len(p[1])+math.dist(start,p[1][0]))
            score=sum(sum(abs(a-b)for a,b in zip(support,p))<=11 for p in dark)
            result.append({'support':list(support),'target':list(target),
                'support_state':cells[support]['state'],'station':station,
                'entry_route':route,
                'prediction_dark_neighbours':score})
    return sorted(result,key=lambda r:(-r['prediction_dark_neighbours'],math.dist(start,r['station'])))


class ReachableEdgeLightingRun(LightingRun):
    def __init__(self,*args,surface_only=False,**kwargs):
        super().__init__(*args,**kwargs);self.surface_only=surface_only
        self.report['surface_only']=surface_only
    def counts(self,cells):
        if not self.surface_only:return risk_counts(cells,self.protected)
        selected={p:r for p,r in cells.items()if r.get('zombie_spawn_floor')and exterior_surface_support(cells,p)}
        return risk_counts(selected,self.protected)
    def place_edge(self,candidate,index):
        support=tuple(candidate['support']);target=candidate['target'];station=candidate['station'];route=candidate['entry_route'];entry=route[0]
        state=self.wait_for_guard(stage='before_edge_station')
        high_y=max(state['pos'][1],self.high[1]-2)
        if state['pos'][1]<high_y-.1:self.move([state['pos'][0],high_y,state['pos'][2]])
        state=self.fresh()
        self.move([entry[0],high_y,state['pos'][2]])
        self.move([entry[0],high_y,entry[2]])
        for waypoint in route:self.move(waypoint)
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
        if (not row or row['state']!=candidate['support_state']or not safe_dark_support(row)
                or tuple(target)in cells and not replaceable_short_grass(cells[tuple(target)]) or candidate_protected(support,target,self.protected)
                or current['scan_entities']):
            raise LightingBlocked('Current adjacent support/target/entity proof changed')
        latest=self.fresh()
        if (math.dist(latest['pos'],station)>.6 or latest['guard_busy']
                or self.active_hostiles(latest)or latest['hand']['item']!=TORCH):
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
        ack=self.c.checked('interact',pos=list(support),face='up',expected_state=row['state'],expected_hand=TORCH)
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
                      later_verified_frames=2,interaction_request=ack['id'],evidence_scope=EVIDENCE)
        write_json(path,intent);self.report['placed'].append(intent);self.save()
        for waypoint in reversed(route[:-1]):self.move(waypoint)
        self.move([entry[0],high_y,entry[2]])

    def work(self):
        self.reject_unknown_intents()
        for i in range(self.limit):
            reply=self.scan(self.low,self.high,f'edge-survey-{i}.json')
            cells=scan_cells(reply,self.low,self.high,self.c.world)
            counts=self.counts(cells)
            self.report['all_scanned_counts']=risk_counts(cells,self.protected)
            if i==0:self.report['before']=counts
            self.report['after']=counts;self.save()
            if not counts['unprotected_dark_floor']:break
            candidates=edge_candidates(cells,self.low,self.high,self.fresh()['pos'],self.protected,surface_only=self.surface_only)
            if not candidates:break
            self.place_edge(candidates[0],i)
        reply=self.scan(self.low,self.high,'edge-final-survey.json')
        self.report['after']=self.counts(scan_cells(reply,self.low,self.high,self.c.world))
        self.report.update(state='bounded_run_finished',remaining_unprotected_risk=self.report['after']['unprotected_dark_floor'])
        self.save()
