"""Finite, observed boat transport through normal short native air waypoints.

The route proves only the pilot trip. Docking, disembarkation, breeding and
trades require their own physical evidence. Unknown movements are never replayed.
"""
from pathlib import Path
import hashlib,json,math,time
from material_plan import inventory_counts
from vehicle_observation import read_frame,villagers_aboard
from kit_runtime.journal import write_json

HAZARDS={'minecraft:fire','minecraft:soul_fire','minecraft:cobweb','minecraft:powder_snow',
         'minecraft:cactus','minecraft:sweet_berry_bush','minecraft:wither_rose','minecraft:magma_block','minecraft:bubble_column'}

TRANSPORT_GUARD_PROTOCOL=2
LATERAL_SLACK=.75

def measured_cargo_bounds(boat):
    boxes=[boat.get('bounds')]+[p.get('bounds')for p in boat.get('passengers',[])]
    for box in boxes:
        if(not isinstance(box,dict)or any(not isinstance(box.get(k),list)or len(box[k])!=3
                or any(type(v)not in(int,float)or not math.isfinite(v)for v in box[k])for k in ('min','max'))
                or any(box['min'][i]>=box['max'][i]for i in range(3))):
            raise RuntimeError('Actual current passenger bounding boxes required before transport')
    return {'min':[min(box['min'][i]for box in boxes)for i in range(3)],
            'max':[max(box['max'][i]for box in boxes)for i in range(3)]}

def clear_rows(rows,boat_y):
    for row in rows:
        name=row.get('state','').split('}',1)[0].removeprefix('Block{')
        if name in HAZARDS or row.get('block_entity')is not False:return False
        if row.get('fluid'):
            if name!='minecraft:water'or row['pos'][1]+1>boat_y+.3:return False
        elif name=='minecraft:dirt_path'and row['pos'][1]+.9375<=boat_y+.01:
            # The bottom of a boat on a village path is within this integer
            # cell, but remains above its actual 15/16-high collision shape.
            continue
        elif row.get('passable')is not True:return False
    return True

def next_pilot(here,target,boat_pos):
    slack=9.0-math.dist(here,boat_pos)
    if slack<.5:raise RuntimeError('Boat is too far behind; no next movement')
    distance=math.hypot(target[0]-here[0],target[2]-here[2])
    if abs(target[1]-here[1])>.25 and not(target[1]<here[1]and distance>.25):
        return [here[0],here[1]+math.copysign(min(1.5,slack,abs(target[1]-here[1])),target[1]-here[1]),here[2]]
    if distance<.01:return list(target)
    ratio=min(1,3.0/distance,slack/distance)
    return [here[0]+(target[0]-here[0])*ratio,here[1],here[2]+(target[2]-here[2])*ratio]

def known_air_preflight(book,receipt,state,retained_error):
    """Only the host's exact pre-dispatch clear-path refusal proves no movement."""
    pending=book.get('pending')or{}
    return (pending.get('op')=='navigate'and pending.get('request_id')is not None
            and receipt.get('id')==pending['request_id']==state.get('last_request')
            and receipt.get('world_session')==book.get('world_session')==state.get('world_session')
            and state.get('connected')is True and not state.get('manual_movement')and not state.get('screen')
            and receipt.get('phase')=='error'
            and receipt.get('detail')=='Air-only navigation requires the current material lease and a loaded clear dry path'
            and receipt.get('pos')==pending.get('from')==state.get('pos')
            and 'native_inflight'in retained_error and retained_error['native_inflight']is None
            and 'unconfirmed_native_request'in retained_error and retained_error['unconfirmed_native_request']is None
            and retained_error.get('last_request')==pending['request_id'])

def envelope(q,b,destination):
    bounds=measured_cargo_bounds(b)
    low=[math.floor(min(bounds['min'][i]-(LATERAL_SLACK if i!=1 else 0),q['pos'][i]-(.31 if i!=1 else 0),destination[i]-(.31 if i!=1 else 0))-.01)for i in range(3)]
    low[1]=math.floor(min(b['pos'][1],q['pos'][1],destination[1])+1e-6)
    high=[math.floor(max(bounds['max'][i]+(LATERAL_SLACK if i!=1 else 0),q['pos'][i]+(.31 if i!=1 else 1.8),destination[i]+(.31 if i!=1 else 1.8))+.01)for i in range(3)]
    # Real passenger boxes include their riding offset. A zombie rides lower
    # than a villager; a fixed villager-height column incorrectly seals a
    # physically clear two-block-high zombie entrance. Keep headroom above
    # the tallest observed passenger, including tall or paired villagers.
    high[1]=math.floor(max(bounds['max'][1]+.25,b['pos'][1]+.8,q['pos'][1]+1.8,destination[1]+1.8)-1e-6)
    return low,high

def resumable(book,world,uuid,passengers,route,home):
    return (book.get('world_session')==world and book.get('uuid')==uuid and book.get('passengers')==passengers
            and book.get('route')==route and book.get('home')==home and book.get('complete')is False
            and book.get('pending')is None and isinstance(book.get('legs'),list)
            and type(book.get('waypoint'))is int and 0<=book['waypoint']<len(route)
            and set(book.get('baseline_health',{}))==set(passengers)and not book.get('safety_returns')and not book.get('aborted'))

def finish_known_leg(c,observe,book,reply,destination,path):
    """Check every fresh cargo frame, before waiting for the leash to settle."""
    from boat_safety import return_after_known_move
    try:
        after,current=observe();until=time.monotonic()+8
        while True:
            if any(p['health']<book['baseline_health'][p['uuid']]for p in current['passengers']):
                raise RuntimeError('Founder health changed after the original towing leg')
            if math.dist(after['pos'],destination)>.6:raise RuntimeError('Native pilot arrival differs from the exact towing leg')
            if math.dist(after['pos'],current['pos'])<=6.75:return after,current
            if time.monotonic()>until:raise RuntimeError('Boat did not catch up; retain original completed pilot leg')
            time.sleep(.1);after,current=observe()
    except RuntimeError:
        return_after_known_move(c,book,book['pending'],reply,path)
        raise

def run(c,uuid,passengers,route,home,out,checkpoint,max_radius=4096,resume=None,passenger_kind='minecraft:villager',waypoint_arrival=.6):
    if type(waypoint_arrival)not in(int,float)or not math.isfinite(waypoint_arrival)or not .12<=waypoint_arrival<=.6:
        raise ValueError('Pilot waypoint arrival must be .12.. .6 blocks')
    from capture_target import BAIT_TYPES
    protected_bait=passenger_kind in BAIT_TYPES
    if passenger_kind!='minecraft:villager' and not protected_bait:
        raise ValueError('Only villagers or the exact actively protected named farm zombie may be transported')
    def point(p):return isinstance(p,list)and len(p)==3 and all(type(v)in(int,float)and math.isfinite(v)for v in p)and -62<=p[1]<317
    if(not point(home)or not isinstance(route,list)or not 1<=len(route)<=32
            or any(not point(p)or any(abs(p[i])>=799968 for i in (0,2))or math.hypot(p[0]-home[0],p[2]-home[2])>max_radius for p in route)
            or not isinstance(passengers,list)or not 1<=len(passengers)<=2 or len(set(passengers))!=len(passengers)):
        raise ValueError('Exact finite in-border route and one or two adult villager UUIDs required')
    def observe():
        checkpoint();q=c.status();lease=q.get('supervision_lease')or{}
        if(q.get('connected')is not True or q.get('world_session')!=c.world or q.get('manual_movement')or q.get('screen')
                or q.get('health',0)<19 or q.get('food',0)<18 or not q.get('guard_armed')or not q.get('guard_pve_only')
                or lease.get('kind')!='materials'or lease.get('job_session')!=c.task or lease.get('world_session')!=c.world):
            raise RuntimeError('Boat trip lost its current healthy sole material controller')
        frame=read_frame(c.root,q)
        if frame is None:raise RuntimeError('Current complete loaded vehicle frame required')
        b=next((v for v in frame['vehicles']if v['uuid']==uuid),None)
        if protected_bait:
            from protected_zombie_transport import observed_aboard
            valid=b is not None and all(p.get('type')==passenger_kind for p in b.get('passengers',[])) and observed_aboard(c.root,b,passengers,q)
        else:valid=b is not None and villagers_aboard(b,passengers,player_uuid=q['player_uuid'])
        if not valid:
            raise RuntimeError('Original boat, adult passengers or resolved player leash changed')
        measured_cargo_bounds(b)
        if any(v.get('leash_holder',{}).get('uuid')==q['player_uuid']for v in frame.get('leashables',[])):
            raise RuntimeError('An unrelated creature is tied to the pilot; no transport movement')
        if math.hypot(q['pos'][0]-home[0],q['pos'][2]-home[2])>max_radius:
            raise RuntimeError('Current pilot is outside the finite village trip')
        return q,b
    q,b=observe();baseline={p['uuid']:p['health']for p in b['passengers']}
    if any(h<20 for h in baseline.values()):raise RuntimeError('Transport starts with full-health founders only')
    scope=hashlib.sha256((c.server.lower().removesuffix(':25565')+'|'+q['dimension']+'|'+uuid).encode()).hexdigest()[:24]
    directory=Path(c.root)/'village-boats'/scope;directory.mkdir(parents=True,exist_ok=True);pointer=directory/'tow-active.json'
    if resume is not None:
        path=Path(resume).resolve()
        if(not pointer.exists()or Path(json.loads(pointer.read_text())['journal']).resolve()!=path
                or getattr(c,'native_inflight',None)is not None or getattr(c,'unconfirmed_native_request',None)is not None):
            raise RuntimeError('Only the original idle towing journal may resume; unresolved input is protected')
        book=json.loads(path.read_text())
        if book.get('lease_id')!=q['supervision_lease']['id']or book.get('task_session')!=c.task:
            raise RuntimeError('Legacy or changed-owner towing journal requires reconciliation, not automatic resume')
        if not resumable(book,c.world,uuid,passengers,route,home)or book.get('passenger_kind','minecraft:villager')!=passenger_kind or book.get('waypoint_arrival',.6)!=waypoint_arrival:
            raise RuntimeError('Original towing identity, finite route, world or input-free checkpoint differs')
        baseline=book['baseline_health']
        book.setdefault('resumptions',[]).append({'time':q['time'],'task_session':c.task,'actual_pilot':q['pos'],
            'actual_boat':b,'completed_legs':len(book['legs']),'no_pending_input':True})
    elif pointer.exists():
        from boat_failure_closeout import closed_failed_trip
        prior_path=Path(json.loads(pointer.read_text())['journal']);prior=json.loads(prior_path.read_text())
        if prior.get('pending')or not(prior.get('complete')or closed_failed_trip(prior,c.world,uuid,prior_path)):
            raise RuntimeError('Original boat trip is unresolved; no alternate-directory replay')
    if resume is None:
        out=Path(out);out.mkdir(exist_ok=False);path=out/'tow.json'
        book={'world_session':c.world,'uuid':uuid,'passengers':passengers,'passenger_kind':passenger_kind,'route':route,'home':home,'baseline_health':baseline,'waypoint_arrival':waypoint_arrival,
              'lease_id':q['supervision_lease']['id'],'task_session':c.task,
              'pending':None,'complete':False,'legs':[],'waypoint':0,'before_inventory':dict(inventory_counts(q))}
    def save():write_json(path,book)
    save();write_json(pointer,{'journal':str(path.resolve()),'world_session':c.world})
    def guarded_observe():
        try:
            state,boat=observe()
            if any(p['health']<baseline[p['uuid']]for p in boat['passengers']):
                raise RuntimeError('Founder health decreased; stop further towing inputs')
            return state,boat
        except RuntimeError:
            last=book.get('last_completed_move')
            if last:
                from boat_safety import return_after_known_move
                return_after_known_move(c,book,last['pending'],last['reply'],path)
            raise
    for index,target in enumerate(route):
        if index<book['waypoint']:continue
        rescans=0
        for _ in range(4096):
            q,b=guarded_observe()
            if math.dist(q['pos'],target)<=waypoint_arrival and abs(q['pos'][1]-target[1])<=min(.25,waypoint_arrival):break
            if q.get('guard_busy'):time.sleep(.2);continue
            destination=next_pilot(q['pos'],target,b['pos'])
            low,high=envelope(q,b,destination)
            if math.prod(high[i]-low[i]+1 for i in range(3))>12000:raise RuntimeError('Cargo body sweep exceeds the bounded transport envelope')
            scene=c.checked('scan',min=low,max=high,details=True)
            if(scene.get('scan_cells_read')!=scene.get('scan_total_cells')or not clear_rows(scene['blocks'],b['pos'][1])):
                book['obstacle']={'min':low,'max':high,'blocks':scene.get('blocks')};save();raise RuntimeError('Actual cargo/player corridor is obstructed; no movement sent')
            book['last_read_only']={k:scene.get(k)for k in ['id','phase','world_session','control_revision']};save()
            fresh,boat_now=guarded_observe()
            fresh_low,fresh_high=envelope(fresh,boat_now,destination)
            if math.dist(fresh['pos'],q['pos'])>.2 or any(fresh_low[i]<low[i]or fresh_high[i]>high[i]for i in range(3)):
                # Leash physics may move the boat while a read-only scan is in
                # flight. Re-observe before input instead of replaying a move.
                rescans+=1;book['read_only_rescans']=book.get('read_only_rescans',0)+1;save()
                if rescans>=32:raise RuntimeError('Cargo did not settle inside a freshly verified sweep; no movement sent')
                time.sleep(.1);continue
            rescans=0
            if math.hypot(fresh['pos'][0]-c.anchor[0],fresh['pos'][2]-c.anchor[2])>128:
                c.anchor=list(fresh['pos']);c.checked('guard',pve_only=True)
            book['pending']={'op':'navigate','from':fresh['pos'],'boat_before':boat_now,'target':destination,'request_id':None};save();previous=c.last
            try:reply=c.request('navigate',target=destination,arrival=min(.2,waypoint_arrival*.6),air_only=True,seconds=45)
            finally:book['pending']['request_id']=c.last if c.last!=previous else None;save()
            if reply.get('phase')!='done':raise RuntimeError('Original towing leg did not complete; retain it without replay')
            book['last_completed_move']={'pending':dict(book['pending']),'reply':{k:reply.get(k)for k in ['id','phase','world_session','control_revision','pos']}};save()
            after,current=finish_known_leg(c,guarded_observe,book,reply,destination,path)
            book['legs'].append({**book['pending'],'actual':after['pos'],'boat_after':current,'native_phase':reply['phase']});book['pending']=None;save()
            remaining=math.dist(after['pos'],target)+sum(math.dist(a,b)for a,b in zip(route[index:],route[index+1:]))
            c.set_progress(phase=('运送刷铁机诱饵'if protected_bait else'运送村民')+' · 剩余%d格 · 预计约%d秒'%(round(remaining),max(1,round(remaining/2.5))))
        else:raise RuntimeError('Finite cargo waypoint leg bound reached')
        book['waypoint']=index+1;save()
    q,b=guarded_observe();book.update(complete=True,pending=None,actual_pilot=q['pos'],actual_boat=b,
        proof_scope='finite_normal_pilot_route_with_same_live_villagers_and_player_leash_not_disembarkation_or_trade_completion');save()
    return {'complete':True,'uuid':uuid,'boat':b,'legs':len(book['legs']),'pilot_route_only':True,'proof':str(path.resolve())}
