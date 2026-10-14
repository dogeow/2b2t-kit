"""Refresh drops after known pre-dispatch merges; never replay uncertain movement."""
import time,json
from material_plan import inventory_counts
from ground_pickup import collect_nearby_ground

REFRESH_ONLY={'Drop identity or stack changed','Drop is no longer loaded; observe again'}
NO_ACCESS={'No visible collision-free depot approach','No loaded collision-free route to this depot; no ceiling is broken'}


def collect_nearby_air(client,drop,before_count):
    """A new short normal flight after one exact reached-but-uncollected reply.

    Never calls collect_item again. Integer-grid pickup poses can stop just
    beyond pickup reach; a fractional pose uses the existing scanned air route.
    """
    terminal=getattr(client,'last_terminal_evidence',{})or{}
    params=terminal.get('params',{})
    if (terminal.get('op')!='collect_item' or terminal.get('phase')!='waiting'
            or terminal.get('detail')!='Drop pickup not confirmed at the reached position'
            or terminal.get('request_id')!=getattr(client,'last',None)
            or terminal.get('world_session')!=getattr(client,'world',None)
            or terminal.get('task_session')!=getattr(client,'task',None)
            or params.get('expected_uuid')!=drop.get('uuid')
            or params.get('expected_item')!=drop.get('stack',{}).get('item')
            or params.get('expected_count')!=1
            or getattr(client,'unconfirmed_native_request',None)is not None):return False
    state=client.status();item=drop['stack']['item'];amount=drop['stack']['count']
    current=next((e for e in state.get('entities',[])if e.get('uuid')==drop['uuid']),None)
    if (not current or current.get('stack')!=drop['stack'] or amount!=1
            or terminal.get('revision_after')!=state.get('control_revision')
            or inventory_counts(state)[item]!=before_count
            or not state.get('flight')or state.get('guard_busy')or state.get('health')!=20
            or state.get('food',0)<18 or state.get('manual_movement')or state.get('screen')
            or not state.get('guard_armed')or not state.get('guard_pve_only')):return False
    point=[current['pos'][0]-.5,current['pos'][1]+.3,current['pos'][2]]
    if sum((a-b)**2 for a,b in zip(point,state['pos']))>9:return False
    from material_jobs.acquisition import _travel
    world=client.world;hurt=state.get('recent_hurt_at');trace=[]
    def checkpoint():
        q=client.status()
        if (q.get('world_session')!=world or q.get('health')!=20 or q.get('food',0)<18
                or q.get('recent_hurt_at')!=hurt or q.get('manual_movement')or q.get('screen')
                or q.get('guard_busy')or not q.get('guard_armed')or not q.get('guard_pve_only')):
            raise RuntimeError('Fractional pickup survival/control changed; no route replay')
        return q
    _travel(client,point,checkpoint,trace)
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
            ordinary=item in {'minecraft:dirt','minecraft:cobblestone','minecraft:stone','minecraft:coal','minecraft:sand','minecraft:gravel'} or item.endswith(('_planks','_concrete'))
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
        reply=client.request('collect_item',expected_uuid=current['uuid'],expected_item=item,
                             expected_count=current['stack']['count'],seconds=seconds)
        if reply.get('phase')=='done':return True # Native pickup checks gain and disappearance.
        if reply.get('phase')=='error' and reply.get('detail') in REFRESH_ONLY:
            time.sleep(.2);continue
        if reply.get('detail') in NO_ACCESS:return collect_nearby_ground(client,current)
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
