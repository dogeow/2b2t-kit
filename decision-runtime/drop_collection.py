"""Refresh drops after known pre-dispatch merges; never replay uncertain movement."""
import time,json
from material_plan import inventory_counts
from ground_pickup import collect_nearby_ground

REFRESH_ONLY={'Drop identity or stack changed','Drop is no longer loaded; observe again'}
NO_ACCESS={'No visible collision-free depot approach','No loaded collision-free route to this depot; no ceiling is broken'}

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
            ordinary=item in {'minecraft:dirt','minecraft:cobblestone','minecraft:stone','minecraft:coal'} or item.endswith(('_planks','_concrete'))
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
        return False
    return False
