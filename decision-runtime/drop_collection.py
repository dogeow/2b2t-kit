"""Refresh drops after known pre-dispatch merges; never replay uncertain movement."""
import time,json
from material_plan import inventory_counts
from ground_pickup import collect_nearby_ground

REFRESH_ONLY={'Drop identity or stack changed','Drop is no longer loaded; observe again'}
NO_ACCESS={'No visible collision-free depot approach','No loaded collision-free route to this depot; no ceiling is broken'}
NO_ACCESS_AIR_ITEMS=frozenset('minecraft:'+n for n in ('dirt','cobblestone','stone','coal','sand','gravel'))

def collect_nearby_plant_shape(client,drop,before):
    """One tiny native collision-checked step for a plant drop by a thin stem."""
    item=drop.get('stack',{}).get('item');amount=drop.get('stack',{}).get('count')
    if item not in('minecraft:bamboo','minecraft:honeycomb')or type(amount)is not int or not 1<=amount<=64:return False
    if getattr(client,'native_inflight',None)is not None or getattr(client,'unconfirmed_native_request',None)is not None:return False
    q=client.status();live=next((e for e in q.get('entities',[])if e.get('uuid')==drop['uuid']and e.get('stack')==drop['stack']),None)
    if not live:return inventory_counts(q)[item]==before+amount
    import math
    dx,dz=live['pos'][0]-q['pos'][0],live['pos'][2]-q['pos'][2];distance=math.hypot(dx,dz)
    if(not .5<distance<=1.6 or abs(live['pos'][1]-q['pos'][1])>1.5
       or inventory_counts(q)[item]!=before or q.get('health')!=20 or q.get('guard_busy')or q.get('screen')
       or q.get('manual_movement')or q.get('under_water')or not q.get('flight')or not q.get('guard_armed')or not q.get('guard_pve_only')):return False
    target=[q['pos'][0]+.22*dx/distance,q['pos'][1],q['pos'][2]+.22*dz/distance]
    path=client.out/('plant-drop-real-shape-'+str(time.time_ns())+'.json')
    record={'world_session':client.world,'drop':live,'before':before,'from':q['pos'],'target':target,'pending':True,'bamboo_not_declared_air':True,'collect_item_replayed':False}
    from kit_runtime.journal import write_json
    write_json(path,record)
    try:r=client.request('navigate',target=target,arrival=.04,air_only=True,seconds=15)
    finally:record['request_id']=client.last;write_json(path,record)
    if r.get('phase')!='done':
        if(r.get('phase')=='error'and r.get('detail')=='Air-only navigation requires the current material lease and a loaded clear dry path'and r.get('pos')==q['pos']):return False
        raise RuntimeError('Plant pickup short native movement unconfirmed; no further attempt')
    end=time.monotonic()+4;stamps=[]
    while True:
        now=client.status()
        if inventory_counts(now)[item]==before+amount and not any(e.get('uuid')==drop['uuid']for e in now.get('entities',[])):
            if now.get('time')not in stamps:stamps.append(now.get('time'))
            if len(stamps)>=2:record.update(pending=False,confirmed=True,after=before+amount);write_json(path,record);return True
        if time.monotonic()>end:return False
        time.sleep(.15)


def collect_nearby_air(client,drop,before_count):
    """A new short normal flight after one exact reached-but-uncollected reply.

    Never calls collect_item again. Integer-grid pickup poses can stop just
    beyond pickup reach; a fractional pose uses the existing scanned air route.
    """
    terminal=getattr(client,'last_terminal_evidence',{})or{}
    params=terminal.get('params',{})
    reached=(terminal.get('phase')=='waiting' and terminal.get('detail')=='Drop pickup not confirmed at the reached position')
    no_route=(terminal.get('phase')=='error' and terminal.get('detail')in NO_ACCESS
              and drop.get('stack',{}).get('item')in NO_ACCESS_AIR_ITEMS)
    if (terminal.get('op')!='collect_item' or not(reached or no_route)
            or terminal.get('request_id')!=getattr(client,'last',None)
            or terminal.get('world_session')!=getattr(client,'world',None)
            or terminal.get('task_session')!=getattr(client,'task',None)
            or params.get('expected_uuid')!=drop.get('uuid')
            or params.get('expected_item')!=drop.get('stack',{}).get('item')
            or params.get('expected_count')!=drop.get('stack',{}).get('count')
            or getattr(client,'unconfirmed_native_request',None)is not None
            or getattr(client,'native_inflight',None)is not None):return False
    state=client.status();item=drop['stack']['item'];amount=drop['stack']['count']
    current=next((e for e in state.get('entities',[])if e.get('uuid')==drop['uuid']),None)
    if (not current or current.get('stack')!=drop['stack'] or type(amount)is not int or not 1<=amount<=64
            or terminal.get('revision_after')!=state.get('control_revision')
            or inventory_counts(state)[item]!=before_count
            or not state.get('flight')or state.get('guard_busy')or state.get('health')!=20
            or state.get('food',0)<18 or state.get('manual_movement')or state.get('screen')
            or not state.get('guard_armed')or not state.get('guard_pve_only')):return False
    point=[current['pos'][0]-.5,current['pos'][1]+.3,current['pos'][2]]
    beyond_short=sum((a-b)**2 for a,b in zip(point,state['pos']))>9
    falling_plant=(item in('minecraft:bamboo','minecraft:honeycomb')and amount<=64
        and abs(current['pos'][1]-state['pos'][1])<=10
        and sum((current['pos'][i]-state['pos'][i])**2 for i in(0,2))<=64)
    if beyond_short and not falling_plant:return False
    from material_jobs.local_air_path import move
    world=client.world;hurt=state.get('recent_hurt_at');trace=[]
    def checkpoint():
        q=client.status()
        if (q.get('world_session')!=world or q.get('health')!=20 or q.get('food',0)<18
                or q.get('recent_hurt_at')!=hurt or q.get('manual_movement')or q.get('screen')
                or q.get('guard_busy')or not q.get('guard_armed')or not q.get('guard_pve_only')):
            raise RuntimeError('Fractional pickup survival/control changed; no route replay')
        return q
    checkpoint()
    if no_route:
        # The integer pickup has a known terminal refusal. A different, fully
        # scanned air stance is a new movement, never another collect request.
        from material_jobs.dry_hover_harvest import pickup,pickup_count_supported
        if not pickup_count_supported(item,amount):return False
        return pickup(client,current,before_count,
            client.out/('no-grid-air-pickup-'+terminal['request_id']),checkpoint,item=item,expected_count=amount)
    if beyond_short:
        # An item can fall after the integer-grid native pickup selected its
        # goal. Follow the current same UUID through freshly scanned body air;
        # this is ordinary new movement, never another collect_item request.
        from material_jobs.dry_hover_harvest import pickup
        return pickup(client,current,before_count,client.out/('falling-plant-air-'+terminal['request_id']),checkpoint,item=item,expected_count=amount)
    # A hovered player can be only .02 above a full platform. The generic
    # resource-flight padding intersects that floor although the actual body
    # fits; use the bounded body scan and normal local air route instead.
    try:
        route=move(client,point,client.out/('fractional-air-pickup-'+terminal['request_id']),
                   max_straight=3,foot_offset=.2,exact_target=True)
    except RuntimeError as error:
        known_planning={
            '局部空气路线起点或终点未完整确认',
            '已存在空气空间没有连通，不挖掘新通道',
            '局部空气通道发生变化，未继续移动',
        }
        proof=getattr(client,'last_terminal_evidence',{})or{}
        from material_jobs.dry_hover_harvest import pickup_count_supported
        supported_amount=pickup_count_supported(item,amount)
        if (str(error)not in known_planning or not supported_amount
                or getattr(client,'native_inflight',None)is not None
                or getattr(client,'unconfirmed_native_request',None)is not None
                or proof.get('op')!='scan' or proof.get('phase')!='done'
                or proof.get('request_id')!=getattr(client,'last',None)
                or proof.get('world_session')!=world):raise
        # The correction failed on a completed body scan, before another move.
        # Use the same original UUID from an adjoining full air body cell;
        # never resend collect_item or retry an uncertain navigation.
        current=next((e for e in checkpoint().get('entities',[])if e.get('uuid')==drop['uuid']),None)
        if current is None or current.get('stack')!=drop['stack']:return False
        from material_jobs.dry_hover_harvest import pickup
        return pickup(client,current,before_count,
                      client.out/('adjoining-air-pickup-'+terminal['request_id']),checkpoint,item=item,expected_count=amount)
    trace.append(route)
    deadline=time.monotonic()+4
    while True:
        q=checkpoint();held=inventory_counts(q)[item]
        if held==before_count+amount and not any(e.get('uuid')==drop['uuid']for e in q.get('entities',[])):
            if getattr(client,'out',None):
                with (client.out/'fractional-air-pickup-confirmed.jsonl').open('a')as f:
                    f.write(json.dumps({'original_waiting_request':terminal,'drop':drop,'target':point,
                        'world_session':world,'inventory_before':before_count,'inventory_after':held,
                        'route':trace,'collect_item_replayed':False,'time':q.get('time')})+'\n')
            return True
        if held not in (before_count,before_count+amount)or time.monotonic()>=deadline:return False
        time.sleep(.15)

def collect_drop(client,drop,observation=None,seconds=90):
    original=observation or client.status();item=drop['stack']['item'];before=inventory_counts(original)[item]
    reselected=False
    for attempt in range(3):
        state=client.status()
        current=next((e for e in state.get('entities',[]) if e.get('uuid')==drop['uuid']),None)
        if current is None:
            if inventory_counts(state)[item]>=before+drop['stack']['count']:return True
            # Stack merges can also retire the source UUID. For ordinary building
            # materials, select a fresh nearby stack as a new pickup, never pretend
            # that the vanished identity itself was confirmed collected.
            ordinary=item in {'minecraft:dirt','minecraft:cobblestone','minecraft:stone','minecraft:coal','minecraft:sand','minecraft:gravel','minecraft:bamboo','minecraft:honeycomb'} or item.endswith(('_planks','_concrete'))
            recent=original.get('time') is not None and 0<=state.get('time',0)-original['time']<=2500
            nearby=[e for e in state.get('entities',[]) if e.get('type')=='minecraft:item'
                    and e.get('stack',{}).get('item')==item and e['stack'].get('count',0)>=drop['stack']['count']
                    and sum((a-b)**2 for a,b in zip(e.get('pos',[]),drop['pos']))<=4
                    and len(e.get('pos',[]))==3]
            if ordinary and recent and not reselected and nearby:
                replacement=min(nearby,key=lambda e:sum((a-b)**2 for a,b in zip(e['pos'],drop['pos'])))
                if getattr(client,'out',None):
                    with (client.out/'drop-refresh.jsonl').open('a') as f:f.write(json.dumps({'old':drop,'new':replacement,'reason':'fresh nearby material stack after source UUID vanished; no identity equivalence claimed'})+'\n')
                drop=replacement;reselected=True;continue
            # Allow a packet to catch up, but do not substitute an unproven new entity.
            time.sleep(.2);continue
        if current.get('type')!='minecraft:item' or current.get('stack',{}).get('item')!=item or current['stack'].get('count',0)<=0:return False
        if inventory_counts(state)[item]>=before+current['stack']['count']:
            # Inventory packets can arrive before the source entity-removal
            # packet. Observe the original pickup instead of navigating again.
            time.sleep(.2);continue
        reply=client.request('collect_item',expected_uuid=current['uuid'],expected_item=item,
                             expected_count=current['stack']['count'],seconds=seconds)
        if reply.get('phase')=='done':return True # Native pickup checks gain and disappearance.
        if reply.get('phase')=='error' and reply.get('detail') in REFRESH_ONLY:
            time.sleep(.2);continue
        if reply.get('detail') in NO_ACCESS:
            if collect_nearby_air(client,current,before):return True
            if collect_nearby_ground(client,current):return True
            return collect_nearby_plant_shape(client,current,before)
        if reply.get('phase')=='waiting' and reply.get('detail')=='Drop pickup not confirmed at the reached position':
            latest=client.status()
            if inventory_counts(latest)[item]>=before+current['stack']['count'] \
                    and not any(e.get('uuid')==current['uuid'] for e in latest.get('entities',[])):
                return True
            same=next((e for e in latest.get('entities',[]) if e.get('uuid')==current['uuid']
                       and e.get('stack')==current.get('stack')),None)
            if same is not None:
                # An airborne approach can stop just outside pickup reach.
                # Reuse the existing exactly scoped fractional air correction
                # before the ground fallback; never send collect_item twice.
                if collect_nearby_air(client,same,before):return True
                return collect_nearby_ground(client,same)
        return False
    return False
