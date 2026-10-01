"""Lure one exact adult cow over freshly scanned flat ground while holding wheat."""
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import time
from animal_breed import _point, entity_rows
from kit_runtime.journal import write_json
from potato_farm import FarmWait
from potato_harvest import _counts, _lease

WHEAT = 'minecraft:wheat'


def ground_route(state, start, destination, scene, max_route=40):
    lo, hi = scene['min'], scene['max']; feet = destination[1]; by = {}
    if (not isinstance(state.get('blocks'), list) or state.get('unloaded_chunks', 0)
            or not _point(start) or not _point(destination) or type(feet) not in (int, float) or feet != int(feet)):
        raise FarmWait('WAIT_SCAN', 'Fresh complete ground scan and flat feet coordinates are required')
    for row in state['blocks']:
        p = row.get('pos')
        if (not isinstance(p, list) or len(p) != 3 or any(type(v) is not int for v in p)
                or not all(a <= b <= d for a,b,d in zip(lo,p,hi)) or tuple(p) in by
                or not isinstance(row.get('state'), str)
                or any(type(row.get(k)) is not bool for k in ('solid','passable','fluid','block_entity'))):
            raise FarmWait('WAIT_SCAN', 'Ground scan contains missing, duplicate or out-of-region metadata')
        by[tuple(p)] = row
    def safe(cell):
        x,z = cell; floor = by.get((x,int(feet)-1,z), {}); name = floor.get('state','').split('}',1)[0].removeprefix('Block{')
        return (lo[0] <= x <= hi[0] and lo[2] <= z <= hi[2]
                and lo[1] <= feet-1 and feet+1 <= hi[1]
                and (name in ('minecraft:grass_block','minecraft:dirt','minecraft:stone') or name.startswith('minecraft:') and name.endswith('_planks'))
                and floor.get('solid') is True and floor.get('fluid') is False and floor.get('block_entity') is False
                # Leave one body cell around walls so a following cow does not
                # cut the player's corner into trapdoors or fences.
                and all(lo[0] <= a <= hi[0] and lo[2] <= b <= hi[2]
                        and ((a,y,b) not in by or by[(a,y,b)]['passable'] is True
                             and by[(a,y,b)]['fluid'] is False and by[(a,y,b)]['block_entity'] is False)
                        for a in range(x-1,x+2) for b in range(z-1,z+2) for y in (int(feet),int(feet)+1)))
    origin = (math.floor(start[0]),math.floor(start[2])); goal = (math.floor(destination[0]),math.floor(destination[2]))
    if (abs(start[1]-feet) > .2 or any(abs(start[i]-(math.floor(start[i])+.5)) > .3 for i in (0,2))
            or not safe(origin) or not safe(goal)):
        raise FarmWait('WAIT_ROUTE', 'Start/destination must be centered above observed dry full-block ground')
    queue = deque([origin]); parents = {origin: None}; distance = {origin: 0}
    while queue:
        current = queue.popleft()
        if current == goal: break
        if distance[current] >= max_route: continue
        for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
            nxt = (current[0]+dx,current[1]+dz)
            if nxt not in parents and safe(nxt):
                parents[nxt] = current; distance[nxt] = distance[current]+1; queue.append(nxt)
    if goal not in parents: raise FarmWait('WAIT_ROUTE', 'No fully scanned cardinal ground route within the budget')
    path = []; cell = goal
    while cell is not None: path.append([cell[0]+.5,feet,cell[1]+.5]); cell = parents[cell]
    return list(reversed(path))


def run(c, follower_uuid, destination, scene, out, checkpoint=lambda:None, *, max_route=40,
        follower_wait_seconds=6, sleep=time.sleep, monotonic=time.monotonic):
    """Return observed cow/player proximity only; never feed, attack or claim breeding."""
    if (not isinstance(follower_uuid,str) or not follower_uuid or not _point(destination)
            or type(max_route) is not int or not 0 <= max_route <= 40
            or type(follower_wait_seconds) not in (int,float) or not 0 < follower_wait_seconds <= 6
            or not isinstance(scene,dict) or set(scene) != {'min','max'}
            or any(not isinstance(scene[k],list) or len(scene[k]) != 3 or any(type(v) is not int or abs(v)>30_000_000 for v in scene[k]) for k in scene)
            or any(a>b for a,b in zip(scene['min'],scene['max']))
            or math.prod(b-a+1 for a,b in zip(scene['min'],scene['max'])) > 50000
            or not -64 <= scene['min'][1] <= scene['max'][1] <= 319):
        raise ValueError('A named follower, bounded native scene and route<=40m are required')
    directory = Path(out); directory.mkdir(parents=True,exist_ok=True)
    scope = {'uuid':follower_uuid,'destination':destination,'scene':scene,'server':c.server}
    path = directory/('animal-lure-'+hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()[:16]+'.json')
    book = json.loads(path.read_text()) if path.exists() else {'scope':scope,'world_session':c.world,'steps':[],'pending':None}
    def save(): write_json(path,book)
    def result(code=None,detail=''):
        return {'phase':'done' if code is None else 'waiting','code':code,'detail':detail,'journal':str(path),
                'follower_uuid':follower_uuid,'steps':len(book['steps']),'breeding_claimed':False,'automatic_retry_allowed':False}
    if book.get('scope') != scope or book.get('world_session') != c.world: return result('WAIT_CONTROL','Old world/scope; no reconnect')
    if book.get('pending'): return result('WAIT_RECONCILE','Uncertain native movement remains pending; no replay')
    try:
        checkpoint(); initial = c.status(); hurt = book.setdefault('recent_hurt_at',initial.get('recent_hurt_at'))
        stock = book.setdefault('stock',dict(_counts(initial))); selected = book.setdefault('selected_slot',initial.get('selected_slot'))
        def safe(state):
            _lease(c,state,hurt)
            if (type(hurt) is not int or state.get('health') != 20 or state.get('flight') is not True
                    or dict(_counts(state)) != stock or state.get('selected_slot') != selected
                    or state.get('hand',{}).get('item') != WHEAT or state['hand'].get('count',0)<1):
                raise FarmWait('WAIT_SAFETY','HP20, owned flight, unchanged stock/held wheat and original injury marker are required')
        def survey(bounds):
            checkpoint(); before = c.status(); safe(before)
            state = c.request('scan',min=bounds['min'],max=bounds['max'],details=True); safe(state)
            if state['time'] <= before['time']: raise FarmWait('WAIT_SCAN','Native scan is not a later frame')
            cow = entity_rows(state,{'species':'minecraft:cow'}).get(follower_uuid,{})
            if (cow.get('type') != 'minecraft:cow' or cow.get('alive') is not True or cow.get('is_baby') is not False
                    or cow.get('visible') is not True or math.dist(cow['pos'],state['pos'])>7):
                raise FarmWait('WAIT_FOLLOWER','Exact live adult cow must remain visible within seven blocks')
            book['last_observation']={'time':state['time'],'player':state['pos'],'follower':cow}; save()
            return state,cow
        safe(initial); observed,cow = survey(scene); route = ground_route(observed,observed['pos'],destination,scene,max_route)
        if book.get('steps') and not book.get('complete'): raise FarmWait('WAIT_RECONCILE','Resolved earlier movement needs explicit caller reconciliation')
        if book.get('complete') and len(route)>1: raise FarmWait('WAIT_RECONCILE','Historical arrival is no longer current; no automatic movement')
        book['route'] = route; save(); index = 0
        while index < len(route)-1:
            end = index+1; direction = [route[end][i]-route[index][i] for i in (0,2)]
            while end+1 < len(route) and end-index < 3 and [route[end+1][i]-route[end][i] for i in (0,2)] == direction: end += 1
            target = route[end]; bounds = {'min':[max(scene['min'][0],math.floor(observed['pos'][0])-8),int(target[1])-1,max(scene['min'][2],math.floor(observed['pos'][2])-8)],
                                          'max':[min(scene['max'][0],math.floor(observed['pos'][0])+8),int(target[1])+1,min(scene['max'][2],math.floor(observed['pos'][2])+8)]}
            deadline = monotonic()+follower_wait_seconds
            for _ in range(32):
                observed,cow = survey(bounds)
                if math.dist(cow['pos'],observed['pos'])<=4: break
                if monotonic()>=deadline: raise FarmWait('WAIT_FOLLOWER','Follower did not close the gap; no additional movement')
                sleep(.2)
            if math.dist(cow['pos'],observed['pos'])>4: raise FarmWait('WAIT_FOLLOWER','Follower gap remained unproved')
            ground_route(observed,observed['pos'],target,bounds,3)
            book['pending'] = {'target':target,'follower':cow,'before_time':observed['time']}; save(); checkpoint(); safe(c.status())
            receipt = c.request('navigate',target=target,arrival=.15,seconds=10,air_only=True)
            book['pending']['receipt'] = {k:receipt.get(k) for k in ('id','phase','detail','time')}; save()
            if receipt.get('phase') != 'done': raise FarmWait('WAIT_RECONCILE','Native movement outcome is unknown; no retry')
            observed,cow = survey(bounds)
            if math.dist(observed['pos'],target)>.65: raise FarmWait('WAIT_RECONCILE','Actual player arrival was not proved')
            book['steps'].append({**book['pending'],'actual_player':observed['pos'],'actual_follower':cow['pos']}); book['pending']=None; save(); index=end
        deadline = monotonic()+follower_wait_seconds; times=[]
        for _ in range(32):
            observed,cow = survey(scene)
            if math.dist(observed['pos'],destination)<=.65 and math.dist(cow['pos'],destination)<=4:
                times.append(observed['time'])
                if len(times)==2:
                    book['complete']=True; save(); done=result(); done.update(player_pos=observed['pos'],follower_pos=cow['pos'],observed_times=times); return done
            else: times=[]
            if monotonic()>=deadline: break
            sleep(.2)
        raise FarmWait('WAIT_FOLLOWER','Player arrived but actual follower proximity needs confirmation')
    except Exception as error:
        code = error.code if isinstance(error,FarmWait) else 'WAIT_CONTROL'; book['last_wait']={'code':code,'detail':str(error)}; save()
        return result(code,str(error))
