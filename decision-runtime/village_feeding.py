"""Feed scoped founders through one owner; credit actual server collectors only."""
from pathlib import Path
import math,time,re
from material_plan import inventory_counts
from villager_events import read,joined_pickups,entity_events
from kit_runtime.journal import write_json

def feeding_containment(scan,low,high,people):
    """Prove containment after loading gates have been walled up.

    Farmland and full-width slab surfaces remain supporting floor blocks.
    Connected fences on full blocks under a low full roof also form a wall:
    their 1.5-high collision leaves only a half-block ceiling gap, too short
    for a baby villager. Other partial shapes count as possible open space.
    The prior six-closed-gate layout remains supported during loading.
    """
    if (len(low)!=3 or len(high)!=3 or any(type(v)is not int for v in (*low,*high))
            or any(high[i]<=low[i]for i in range(3))):
        raise ValueError('Exact bounded feeding enclosure required')
    bottom=[low[0],low[1]-1,low[2]]
    total=math.prod(high[i]-bottom[i]+1 for i in range(3))
    if (total>8192 or scan.get('scan_cells_read')!=total
            or scan.get('scan_total_cells')!=total):
        raise RuntimeError('Complete enclosure scan required')
    cells={}
    for row in scan.get('blocks',[]):
        p=tuple(row['pos'])
        if p in cells or not all(bottom[i]<=p[i]<=high[i]for i in range(3)):
            raise RuntimeError('Enclosure scan has conflicting or out-of-bounds cells')
        cells[p]=row
    gates=[v for v in cells.values()if'fence_gate}'in v['state']]
    if gates:
        if len(gates)!=6 or any('open=false'not in v['state']for v in gates):
            raise RuntimeError('All founder enclosure gates must be closed before feeding')
        return {'kind':'six_closed_loading_gates','scan_time':scan['time']}
    # Feet on farmland are at y+15/16. Start within the body above that floor,
    # rather than mistaking its support block for an entity inside a wall.
    seeds={(math.floor(actor['pos'][0]),math.floor(actor['pos'][1]+.5),math.floor(actor['pos'][2]))for actor in people}
    if not seeds:
        raise RuntimeError('Current founder positions required for sealed enclosure proof')
    def full(p):
        row=cells.get(p)or{}
        if row.get('solid')is True and row.get('fluid')is False:return True
        # These full-width horizontal collision surfaces support the entire
        # floor. A slab's remaining half-block gap cannot pass a baby villager.
        # Never promote partial blocks in walls or overhead to full barriers.
        if p[1]!=bottom[1]or row.get('block_entity')is not False:return False
        state=row.get('state','')
        cap=cells.get((p[0],p[1]+1,p[2]))or{}
        covered_composter=(row.get('fluid')is False and re.fullmatch(r'Block\{minecraft:composter\}\[level=[0-8]\]',state)is not None
            and cap.get('fluid')is False and cap.get('block_entity')is False
            and re.fullmatch(r'Block\{minecraft:[a-z0-9_]+_carpet\}',cap.get('state',''))is not None)
        return (row.get('fluid')is False and re.fullmatch(r'Block\{minecraft:farmland\}\[moisture=[0-7]\]',state)is not None
                or re.fullmatch(r'Block\{minecraft:[a-z0-9_]+_slab\}\[type=(?:top|bottom),waterlogged=(?:true|false)\]',state)is not None
                or covered_composter)
    partial_floors={p for p,row in cells.items()if p[1]==bottom[1]and row.get('solid')is not True and full(p)}
    directions={'north':(0,-1),'south':(0,1),'west':(-1,0),'east':(1,0)}
    opposite={'north':'south','south':'north','east':'west','west':'east'}
    fence_walls=set()
    for p,row in cells.items():
        state=row['state']
        if ('_fence}'not in state or row.get('fluid')is not False
                or 'waterlogged=false'not in state
                or not full((p[0],p[1]-1,p[2]))or not full((p[0],p[1]+2,p[2]))):continue
        connected=[name for name in directions if name+'=true'in state]
        if len(connected)<2:continue
        valid=0
        for name in connected:
            dx,dz=directions[name];q=(p[0]+dx,p[1],p[2]+dz);other=cells.get(q)or{}
            if full(q)or('_fence}'in other.get('state','')and other.get('fluid')is False
                    and opposite[name]+'=true'in other['state']):valid+=1
        if valid>=2:fence_walls.add(p)
    # Every linked partial block must itself have the base and low roof.
    # Otherwise a connected arm could end at a jumpable or unsealed segment.
    changed=True
    while changed:
        changed=False
        for p in list(fence_walls):
            valid=0
            for name,(dx,dz)in directions.items():
                if name+'=true'not in cells[p]['state']:continue
                q=(p[0]+dx,p[1],p[2]+dz)
                if full(q)or(q in fence_walls and opposite[name]+'=true'in cells[q]['state']):valid+=1
            if valid<2:fence_walls.remove(p);changed=True
    fence_barriers=fence_walls|{(x,y+1,z)for x,y,z in fence_walls}
    # A closed iron door is a full-width plane, not a full voxel. Only count
    # its pair when the observed floor, low lintel and both jambs close every
    # route around that plane. Villagers can open wooden doors themselves.
    iron_doors=set()
    door_pattern=r'Block\{minecraft:iron_door\}\[facing=(north|east|south|west),half=lower,hinge=(left|right),open=false,powered=false\]'
    for p,row in cells.items():
        match=re.fullmatch(door_pattern,row.get('state',''))
        if not match or row.get('fluid')is not False or row.get('block_entity')is not False:continue
        x,y,z=p;upper=cells.get((x,y+1,z))or{}
        if(upper.get('state')!=row['state'].replace('half=lower','half=upper')
                or upper.get('fluid')is not False or upper.get('block_entity')is not False
                or not full((x,y-1,z))or not full((x,y+2,z))):continue
        dx,dz=(0,1)if match[1]in('east','west')else(1,0)
        if not all(full((x+sign*dx,yy,z+sign*dz))for sign in(-1,1)for yy in(y,y+1)):continue
        iron_doors.update((p,(x,y+1,z)))
    def barrier(p):return full(p)or p in fence_barriers or p in iron_doors
    todo=list(seeds);seen=set()
    while todo:
        p=todo.pop()
        if p in seen or barrier(p):continue
        if any(p[i]<=bottom[i]or p[i]>=high[i]for i in range(3)):
            raise RuntimeError('Founder enclosure has a possible route to the outside')
        seen.add(p)
        for axis in range(3):
            for step in(-1,1):
                q=list(p);q[axis]+=step;todo.append(tuple(q))
    if not seeds<=seen:
        raise RuntimeError('Founder position overlaps a full enclosure block')
    return {'kind':'sealed_collision_shell'if fence_walls or partial_floors or iron_doors else'sealed_full_block_shell','scan_time':scan['time'],
            'low_roof_connected_fences':len(fence_walls),
            'closed_framed_iron_doors':len(iron_doors)//2,
            'partial_floor_collision_surfaces':len(partial_floors),
            'min':bottom,'max':list(high),'reachable_cells':len(seen),'seed_cells':[list(p)for p in sorted(seeds)]}

def credit_collector(book,collector,amount):
    """Keep real child/other pickups without crediting an adult food quota."""
    if type(amount)is not int or amount!=1:
        raise RuntimeError('One normal bread drop needs an exact one-item collector receipt')
    if collector in book['delivered']:
        book['delivered'][collector]+=amount
    else:
        other=book.setdefault('other_villager_deliveries',{})
        other[collector]=other.get(collector,0)+amount

def settled_pose(state):
    v=state['velocity']
    if state['on_ground']and not state['flight']:return math.hypot(v[0],v[2])<.01
    return state['flight']and not state['navigating']and math.sqrt(sum(n*n for n in v))<.01

def stable_hover(samples):
    """Meteor can hold a position while reporting vanilla tick gravity."""
    if len(samples)<3 or samples[-1]['time']-samples[0]['time']<300:return False
    return (all(b['time']>a['time']for a,b in zip(samples,samples[1:]))
        and all(s['world_session']==samples[0]['world_session']and s['flight']and not s['navigating']
                and not s.get('manual_movement')and math.hypot(s['velocity'][0],s['velocity'][2])<.01
                and abs(s['velocity'][1])<=.08 and math.dist(s['pos'],samples[0]['pos'])<=.02 for s in samples))

def outside_food_pickup_box(position,points):
    return all(abs(position[0]-p[0])>2 or abs(position[2]-p[2])>2 for p in points)

def food_receipt_ready(matches,player_uuid,debit_times):
    # Own pickup can restore the stack before a second debit frame exists.
    # Its exact packet still needs two later restored-stock frames below.
    return len(matches)==1 and(matches[0]['collector']['uuid']==player_uuid or len(debit_times)>=2)

def choose_food_target(required,delivered,receipts):
    missing={u:max(0,n-delivered[u])for u,n in required.items()}
    candidates=[u for u in missing if missing[u]>0]
    intercepted={u:sum(r['target']==u and r['actual_collector']!=u for r in receipts)for u in candidates}
    return max(candidates,key=lambda u:(-intercepted[u],missing[u]))

def feeding_pose_bounds(low,high,bounds=None):
    """Keep food manoeuvres in one room while proving the whole linked enclosure."""
    if bounds is None:return list(low),list(high)
    if(not isinstance(bounds,dict)or set(bounds)!={'min','max'}
            or any(not isinstance(bounds[k],list)or len(bounds[k])!=3
                   or any(type(v)is not int for v in bounds[k])for k in bounds)):
        raise ValueError('Exact feeding pose bounds required')
    a,b=bounds['min'],bounds['max']
    if a[1]!=low[1]or any(not low[i]<=a[i]<b[i]<=high[i]for i in range(3)):
        raise ValueError('Feeding poses must stay within the enclosure on its verified floor')
    return list(a),list(b)

def food_retreat_pose(low,high,cells,points,people,state):
    # A villager can push the player onto a wall edge. Never descend through
    # that edge before moving toward an otherwise clear retreat cell.
    height=max(low[1]+.7,state['pos'][1]);choices=[]
    for x in range(low[0]+1,high[0]):
        for z in range(low[2]+1,high[2]):
            p=[x+.5,height,z+.5]
            if not outside_food_pickup_box(p,points):continue
            if 'minecraft:farmland}'in(cells.get((x,low[1]-1,z))or{}).get('state',''):continue
            # A full work block can occupy the feet even when the two cells
            # above it are empty. Beds remain below the usual 0.7-block hover.
            foot=cells.get((x,math.floor(height),z))or{}
            if foot.get('solid')is True or foot.get('fluid')is True:continue
            if any((x,y,z)in cells for y in range(low[1]+1,math.ceil(height+1.8-1e-6))):continue
            if any(math.dist(p,v['pos'])<1 for v in people):continue
            choices.append((math.dist(p,state['pos']),p))
    if not choices:raise RuntimeError('No clear retreat outside original food pickup box')
    return min(choices)[1]

def bed_level_pose(cells,target,*,sleeping=False):
    """Throw from the same bed surface instead of dropping food below its occupant."""
    p=target['pos'];cell=tuple(math.floor(v)for v in p);bed=cells.get(cell);height=cell[1]+9/16
    if not bed or not bed['state'].startswith('Block{minecraft:white_bed}')or abs(p[1]-height)>.08:return None
    state=bed['state'];directions={'north':(0,-1),'south':(0,1),'west':(-1,0),'east':(1,0)}
    direction=next((d for name,d in directions.items()if'facing='+name in state),None)
    if direction is None:return None
    sign=-1 if'part=head'in state else 1
    other=(cell[0]+sign*direction[0],cell[1],cell[2]+sign*direction[1]);partner=cells.get(other)
    if not partner or not partner['state'].startswith('Block{minecraft:white_bed}')or any((other[0],y,other[2])in cells for y in(cell[1]+1,cell[1]+2)):return None
    # A sleeping entity can lie off-centre on its head half. The midpoint can
    # become too close and alternate forever with the ground approach.
    if sleeping:return [other[0]+.5,height+.08,other[2]+.5]
    return [other[0]+.5,height,other[2]+.5]

def close_hover_food_pose(low,high,cells,target,people,state):
    """A dry upper-room approach; never land on crops or overlap a villager."""
    if bed_level_pose(cells,target) is not None:return None
    height=low[1]+1.1
    def valid(point):
        if not(low[0]+1<=point[0]<=high[0]-.3 and low[2]+1<=point[2]<=high[2]-.3):return False
        horizontal=math.hypot(point[0]-target['pos'][0],point[2]-target['pos'][2])
        if horizontal<.65 or not .6<=math.dist(point,target['pos'])<=1.5:return False
        if any(v['uuid']!=target['uuid']and math.hypot(point[0]-v['pos'][0],point[2]-v['pos'][2])<.65 for v in people):return False
        for x in range(math.floor(point[0]-.3+1e-6),math.floor(point[0]+.3-1e-6)+1):
            for z in range(math.floor(point[2]-.3+1e-6),math.floor(point[2]+.3-1e-6)+1):
                for y in range(math.floor(height),math.ceil(height+1.8-1e-6)):
                    row=cells.get((x,y,z))
                    if row is not None and(row.get('passable')is not True or row.get('fluid')is not False or row.get('block_entity')is not False):return False
        return True
    current=[state['pos'][0],height,state['pos'][2]]
    if valid(current):return current
    choices=[]
    for radius in(.75,1.0,1.2):
        for i in range(8):
            angle=i*math.pi/4;point=[target['pos'][0]+radius*math.cos(angle),height,target['pos'][2]+radius*math.sin(angle)]
            if not valid(point):continue
            other=min((math.dist(point,v['pos'])for v in people if v['uuid']!=target['uuid']),default=10)
            choices.append((max(0,2.3-other),math.dist(point,state['pos']),point))
    return min(choices)[-1]if choices else None

def ground_food_pose(low,high,cells,target,people,state,*,standoff=False):
    """Use a supported aisle throw when the native three-block guard permits it."""
    choices=[]
    for x in range(low[0]+1,high[0]):
        for z in range(low[2]+1,high[2]):
            floor=cells.get((x,low[1]-1,z),{})
            if not floor.get('solid')or floor.get('fluid'):continue
            if any((v:=cells.get((x,y,z)))is not None and(not v['passable']or v['fluid']or v['block_entity'])for y in(low[1],low[1]+1)):continue
            p=[x+.5,low[1],z+.5];d=math.dist(p,target['pos'])
            if not(1.8 if standoff else .65)<=d<=(2.7 if standoff else 1.25):continue
            other=min((math.dist(p,v['pos'])for v in people if v['uuid']!=target['uuid']),default=10)
            travel=math.dist(p,state['pos'])
            choices.append((max(0,2.3-other),travel if standoff else d,d if standoff else travel,p))
    return min(choices)[-1]if choices else None

def fresh_food_pose(state,target):
    """Recheck the moving recipient immediately before creating a Q intent."""
    return (math.dist(state['pos'],target['pos'])<=2.7 and target.get('visible')is True
            and state.get('hand',{}).get('item')=='minecraft:bread'and state['hand'].get('count',0)>0)

def feed(owner,root,quotas,path,low,high,*,pose_bounds=None,hover_approach=False,ground_standoff=False):
    if type(hover_approach)is not bool:raise ValueError('Hover approach flag must be boolean')
    if type(ground_standoff)is not bool or ground_standoff and hover_approach:raise ValueError('Choose one bounded feeding approach')
    path=Path(path)
    pose_low,pose_high=feeding_pose_bounds(low,high,pose_bounds)
    required=dict(quotas)
    if not required or any(type(n)is not int or not 1<=n<=64 for n in required.values())or sum(required.values())>64:
        raise ValueError('A bounded positive founder food quota is required')
    if path.exists():
        import json
        book=json.loads(path.read_text())
        if(book['complete']or book['pending']is not None or book['pending_food']is not None
                or book.get('recovery_pending')is not None or book['required']!=required
                or book['world_session']!=owner.world or book.get('pose_bounds')!=pose_bounds
                or not(book.get('recoveries')or book.get('preflight_rejections')or book.get('pose_recoveries'))
                or any(r['outcome']!='recovered_to_player_not_fed'or not r['collector_packet']for r in book.get('recoveries',[]))
                or any(r.get('classification')!='pinned_food_guard_rejected_before_normal_Q'or r.get('world_session')!=owner.world
                       or r.get('host_jar_sha256')!='d51d980dd68ea9f76e0d00c531d2b903657e3879d5ac5b91ff3a47d39ad9653a'
                       or r.get('original_request_replayed')is not False for r in book.get('preflight_rejections',[]))
                or any(r.get('classification')!='pose_refused_before_any_bread_drop' or r.get('world_session')!=owner.world
                       or r.get('no_bread_drop_intents')is not True or r.get('original_request_replayed')is not False
                       or type(r.get('bread_before'))is not int or type(r.get('bread_after'))is not int
                       or r.get('bread_before')!=sum(required.values()) or r.get('bread_after')!=r.get('bread_before')
                       for r in book.get('pose_recoveries',[]))
                or book.get('pose_recoveries')and(book['receipts']or any(book['delivered'].values()))):
            raise RuntimeError('Original feeding journal is unresolved; no repeated bread drops')
        if book.get('pose_recoveries')and inventory_counts(owner.status())['minecraft:bread']!=book['pose_recoveries'][-1]['bread_after']:
            raise RuntimeError('Original pre-drop bread stock changed; no resumed feeding')
        if 'error'in book:book.setdefault('prior_errors',[]).append(book.pop('error'))
    else:book={'complete':False,'pending':None,'pending_food':None,'required':required,
        'delivered':{uid:0 for uid in quotas},'receipts':[],'world_session':owner.world,'pose_bounds':pose_bounds}
    mode='standoff_ground'if ground_standoff else'hover'if hover_approach else'ground'
    if book.get('approach_mode','ground')!=mode:
        book.setdefault('approach_history',[]).append({'from':book.get('approach_mode','ground'),'to':mode,'after_acknowledged_receipts':len(book['receipts'])})
    book['approach_mode']=mode
    def save():write_json(path,book)
    def native(op,**params):
        book['pending']={'op':op,'params':params};save();r=owner.native(op,**params);book['pending']=None;save();return r
    def observe():
        end=time.monotonic()+4
        while True:
            s=owner.status();f=read(root,s)
            if f is not None:return s,f
            if time.monotonic()>end:raise RuntimeError('Current-world pickup observer unavailable')
            time.sleep(.1)
    def parents(s):
        rows={v['uuid']:v for v in s['loaded_villagers']['villagers']if v['uuid']in required}
        if len(rows)!=len(required)or any(v['health']<20 or v['is_baby']or not(low[0]<v['pos'][0]<high[0]+1 and low[2]<v['pos'][2]<high[2]+1)for v in rows.values()):
            raise RuntimeError('Exact healthy adult founders must remain loaded inside their enclosure')
        return rows
    def settle():
        end=time.monotonic()+4;seen=[];hover=[]
        while True:
            s=owner.status()
            if settled_pose(s):
                if not seen or s['time']>seen[-1]:seen.append(s['time'])
                if len(seen)>=2:return s
            else:seen=[]
            if not hover or s['time']>hover[-1]['time']:hover=(hover+[s])[-5:]
            if stable_hover(hover):return s
            if time.monotonic()>end:raise RuntimeError('Founder feeding pose is not settled')
            time.sleep(.1)
    try:
        a=native('scan',min=[low[0],low[1]-1,low[2]],max=high,details=True)
        book['containment']=feeding_containment(a,low,high,parents(owner.status()).values());save()
        cells={tuple(v['pos']):v for v in a['blocks']}
        for attempt in range(max(0,sum(required.values())-sum(r['server_receipt']['amount']for r in book['receipts']))+2):
            s,f=observe();rows=parents(s);missing={uid:max(0,n-book['delivered'][uid])for uid,n in required.items()}
            if not any(missing.values()):break
            if sum(r['server_receipt']['amount']for r in book['receipts'])>=sum(required.values()):break
            if inventory_counts(s)['minecraft:bread']==0:break
            uid=choose_food_target(required,book['delivered'],book['receipts'])
            native('select_item',item='minecraft:bread')
            for _ in range(12):
                s,f=observe();rows=parents(s);target=rows[uid];distance=math.dist(s['pos'],target['pos'])
                flag=next(v for v in f['villagers']if v['uuid']==uid);sleeping=flag['sleeping'];raised=bed_level_pose(cells,target,sleeping=sleeping)
                if ground_standoff and sleeping:
                    # A ground throw can slide below the bed's raised pickup
                    # box. Keep the food until the adult is awake instead.
                    book.update(waiting_for_awake_founder=uid,pending=None,
                                remaining={u:max(0,n-book['delivered'][u])for u,n in required.items()},
                                bread_actual=inventory_counts(s)['minecraft:bread'])
                    save();return book
                if ground_standoff:
                    raised=None
                    if(s.get('on_ground')and 1.8<=distance<=2.7 and target['visible']
                            and s['hand']['item']=='minecraft:bread'):break
                if hover_approach and raised is None:
                    point=close_hover_food_pose(pose_low,pose_high,cells,target,s['loaded_villagers']['villagers'],s)
                    if point is None:raise RuntimeError('No clear upper-room hover feeding pose; no Q sent')
                    if s['flight']and math.dist(s['pos'],point)<=.13 and .6<=distance<=1.5 and target['visible']and s['hand']['item']=='minecraft:bread':break
                    native('navigate',target=point,arrival=.1,air_only=True,seconds=20);settle();continue
                if raised and(abs(s['pos'][1]-raised[1])>.1 or sleeping and math.dist(s['pos'],raised)>.13):
                    if not all(math.dist(raised,v['pos'])>=.8 for key,v in rows.items()if key!=uid):
                        raise RuntimeError('Same-height bed feeding surface is occupied; no Q sent')
                    if sleeping:
                        if abs(s['pos'][1]-raised[1])>.1:native('navigate',target=[s['pos'][0],raised[1],s['pos'][2]],arrival=.1,air_only=True,seconds=20)
                        native('navigate',target=raised,arrival=.1,air_only=True,seconds=20)
                    else:native('walk',target=raised,arrival=.1,restore_flight=False,seconds=20)
                    settle();continue
                if not ground_standoff and (.4 if sleeping and raised else .6)<=distance<=1.25 and target['visible']and s['hand']['item']=='minecraft:bread':break
                point=ground_food_pose(pose_low,pose_high,cells,target,list(rows.values()),s,standoff=ground_standoff)
                if point is None:raise RuntimeError('No clear close founder feeding pose')
                if s['hand']['item']!='minecraft:bread':native('select_item',item='minecraft:bread')
                native('walk',target=point,arrival=.1,restore_flight=False,seconds=20);settle()
            else:raise RuntimeError('Moving founder never reached bounded close feeding range; no Q sent')
            s,f=observe();target=parents(s)[uid]
            if not fresh_food_pose(s,target):
                book.setdefault('pose_revalidations',[]).append({'time':s['time'],'target':uid,'pos':s['pos'],'target_pos':target['pos'],'no_Q_sent':True});save();continue
            before=inventory_counts(s)['minecraft:bread'];initial={e['uuid']for e in s['entities']if e.get('stack',{}).get('item')=='minecraft:bread'}
            if book.get('pose_recoveries'):book.setdefault('pose_history',[]).extend(book.pop('pose_recoveries'))
            started=s['time'];book['pending_food']={'target':uid,'before_bread':before,'started_at':started};save()
            r=native('villager_bread_drop',entity_id=target['id'],expected_uuid=uid,expected_count=s['hand']['count']);book['pending_food']['native_request']=r['id'];save()
            # A villager may need to walk to the drop. Do not expire before
            # the already bounded 20-second source/collector join window.
            seen=None;debit_times=[];pickup_grace=time.monotonic()+3;end=time.monotonic()+22;matches=[];retreated=False
            while True:
                s,f=observe();current_parents=parents(s)
                if inventory_counts(s)['minecraft:bread']==before-1 and(not debit_times or s['time']>debit_times[-1]):debit_times.append(s['time'])
                candidates=[e for e in s['entities']if e.get('type')=='minecraft:item'and e.get('stack',{}).get('item')=='minecraft:bread'and e['uuid']not in initial and e['stack']['count']==1]
                if seen is None and len(candidates)==1:
                    seen={'world_session':s['world_session'],'runtime_generation':s['runtime_generation'],'observed_at':s['time'],'entity':candidates[0]};book['pending_food']['seen_drop']=seen;save()
                if seen:
                    collectors={v['uuid']for v in s['loaded_villagers']['villagers']}|{s['player_uuid']}
                    matches=joined_pickups(f,'minecraft:bread',collectors,seen,after_time=started)
                book['pending_food']['last_observer_frame']=f;save()
                # A confirmed pickup needs no retreat. Give a nearby villager
                # time to receive the item before starting another movement.
                if food_receipt_ready(matches,s['player_uuid'],debit_times):break
                if seen and not retreated and time.monotonic()>=pickup_grace:
                    food=seen['entity']['pos']
                    retreat=food_retreat_pose(pose_low,pose_high,cells,[food,target['pos'],current_parents[uid]['pos']],list(current_parents.values()),s)
                    height=retreat[1]
                    if abs(s['pos'][1]-height)>.1:native('navigate',target=[s['pos'][0],height,s['pos'][2]],arrival=.1,air_only=True,seconds=15)
                    native('navigate',target=retreat,arrival=.1,air_only=True,seconds=15);retreated=True
                    continue
                if time.monotonic()>end:raise RuntimeError('Original bread drop lacks its exact server collector receipt; do not repeat')
                time.sleep(.1)
            match=matches[0];collector=match['collector']['uuid']
            if collector==s['player_uuid']:
                book['recovery_pending']={'collector_packet':matches,'expected_bread':before};save()
                end=time.monotonic()+4;restored=[]
                while len(restored)<2:
                    s,f=observe()
                    if inventory_counts(s)['minecraft:bread']==before:
                        if not restored or s['time']>restored[-1]:restored.append(s['time'])
                    else:restored=[]
                    if time.monotonic()>end:raise RuntimeError('Original own pickup packet lacks its restored inventory')
                    time.sleep(.1)
                book.setdefault('recoveries',[]).append({'original_pending_food':book['pending_food'],'collector_packet':matches,'outcome':'recovered_to_player_not_fed','restored_inventory_times':restored});book['pending_food']=None;book['recovery_pending']=None;save();continue
            credit_collector(book,collector,match['amount'])
            book['receipts'].append({'target':uid,'actual_collector':collector,'debit_times':debit_times,'server_receipt':match,'native_request':r['id']});book['pending_food']=None;save()
        s,f=observe();parents(s);book.update(complete=all(book['delivered'][uid]>=n for uid,n in required.items()),pending=None,
            remaining={uid:max(0,n-book['delivered'][uid])for uid,n in required.items()},bread_actual=inventory_counts(s)['minecraft:bread'],
            raw_villager_events=entity_events(f,set(required)),health=s['health'],scope='actual_incoming_pickup_receipts_not_food_inventory_parentage_or_birth');save();return book
    except Exception as e:book['error']=repr(e);save();raise
