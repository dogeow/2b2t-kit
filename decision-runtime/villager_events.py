"""Read incoming server receipts; missing ground food never creates a pickup."""
import json,math
from pathlib import Path

SCOPE='incoming_server_item_pickups_and_loaded_villager_entity_events'

def _identity(row):
    if not isinstance(row,dict):return False
    p=row.get('pos')
    return (type(row.get('entity_id'))is int and isinstance(row.get('uuid'),str)and 1<=len(row['uuid'])<=64
            and isinstance(row.get('type'),str)and row['type'].startswith('minecraft:')
            and isinstance(p,list)and len(p)==3 and all(type(v)in(int,float)and math.isfinite(v)for v in p))

def read(root,state):
    path=Path(root)/'loaded-villager-events.json'
    try:
        if path.stat().st_size>1048576:return None
        f=json.loads(path.read_text())
    except(OSError,ValueError,TypeError):return None
    if(not isinstance(f,dict)or f.get('protocol')!=1 or f.get('scope')!=SCOPE
            or f.get('connected')is not True or state.get('connected')is not True or f.get('subscriber_active')is not True
            or any(f.get(k)!=state.get(k)for k in('world_session','server','dimension','player_uuid','runtime_version','runtime_generation'))
            or type(f.get('runtime_generation'))is not int or type(f.get('time'))is not int or type(state.get('time'))is not int
            or not -1000<=state['time']-f['time']<=1000
            or type(f.get('world_entered_at'))is not int or not 0<=f['world_entered_at']<=f['time']
            or not isinstance(f.get('events'),list)or len(f['events'])>256
            or not isinstance(f.get('villagers'),list)or len(f['villagers'])>256):return None
    seen=set()
    for event in f['events']:
        if(not isinstance(event,dict)or type(event.get('sequence'))is not int or event['sequence']<=0 or event['sequence']in seen
                or type(event.get('received_at'))is not int or not f['world_entered_at']<=event['received_at']<=f['time']):return None
        seen.add(event['sequence']);kind=event.get('kind')
        if kind in('item_pickup','pickup_entities_unresolved'):
            if(type(event.get('amount'))is not int or not 1<=event['amount']<=64
                    or type(event.get('source_entity_id'))is not int or type(event.get('collector_entity_id'))is not int):return None
            if kind=='item_pickup'and(not _identity(event.get('source'))or not _identity(event.get('collector'))
                    or not isinstance(event.get('item'),str)or not event['item'].startswith('minecraft:')
                    or event['source']['entity_id']!=event['source_entity_id']or event['collector']['entity_id']!=event['collector_entity_id']):return None
            if kind=='pickup_entities_unresolved'and 'collector'in event and(not _identity(event['collector'])
                    or event['collector']['entity_id']!=event['collector_entity_id']):return None
        elif kind=='villager_entity_event':
            if(not _identity(event.get('villager'))or event['villager']['type']!='minecraft:villager'
                    or type(event.get('event_code'))is not int or not 0<=event['event_code']<=255):return None
        else:return None
    for v in f['villagers']:
        if not _identity(v)or v['type']!='minecraft:villager'or any(type(v.get(k))is not bool for k in('is_baby','sleeping','passenger','no_ai_client_flag')):return None
    return f

def pickups(frame,item,collectors,*,sources=(),after_time=0):
    if frame is None:raise ValueError('Pickup observations are unavailable, not empty')
    return [e for e in frame['events']if e['kind']=='item_pickup'and e['item']==item
            and e['collector']['uuid']in collectors and e['received_at']>=after_time
            and(not sources or e['source']['uuid']in sources)]

def entity_events(frame,villagers,*,after_time=0):
    if frame is None:raise ValueError('Villager event observations are unavailable, not empty')
    return [e for e in frame['events']if e['kind']=='villager_entity_event'
            and e['villager']['uuid']in villagers and e['received_at']>=after_time]

def joined_pickups(frame,item,collectors,seen_drop,*,after_time=0):
    """Join a fresh witnessed drop to a real pickup even after its entity vanished.

    A server collector is still required. Merely losing a world item, or a
    same-number source from another world/generation, never proves delivery.
    """
    if frame is None:raise ValueError('Pickup observations are unavailable, not empty')
    if not isinstance(seen_drop,dict):return []
    entity=seen_drop.get('entity')or{};stack=entity.get('stack')or{};observed=seen_drop.get('observed_at')
    if(any(seen_drop.get(k)!=frame.get(k)for k in('world_session','runtime_generation'))
            or type(observed)is not int or not frame['world_entered_at']<=observed<=frame['time']
            or observed<after_time or type(entity.get('id'))is not int
            or not isinstance(entity.get('uuid'),str)or not entity['uuid']
            or entity.get('type')!='minecraft:item'or stack.get('item')!=item
            or type(stack.get('count'))is not int or not 1<=stack['count']<=64):return []
    result=[]
    for e in frame['events']:
        collector=e.get('collector')
        if(e.get('kind')not in('item_pickup','pickup_entities_unresolved')or not _identity(collector)
                or collector['entity_id']!=e['collector_entity_id']or collector['uuid']not in collectors
                or e['source_entity_id']!=entity['id']or not observed<=e['received_at']<=observed+20000
                or not 1<=e['amount']<=stack['count']):continue
        if e['kind']=='item_pickup'and(e['item']!=item or e['source']['uuid']!=entity['uuid']):continue
        result.append({**e,'source_join':'fresh_same_world_generation_item_id_uuid',
                       'joined_source':entity,'source_observed_at':observed})
    return result


def wait_for_frame(root,get_state,*,seconds=3,clock=None,pause=None):
    """Read-only bounded retry for frames that fail the existing fresh evidence checks."""
    import time
    if type(seconds)not in(int,float)or not 0<seconds<=3:raise ValueError('Bounded villager evidence wait required')
    clock=clock or time.monotonic;pause=pause or time.sleep;end=clock()+seconds
    while True:
        state=get_state();frame=read(root,state)
        if frame is not None:return frame
        if clock()>=end:raise RuntimeError('Fresh villager evidence unavailable; no new world input')
        pause(min(.1,max(0,end-clock())))
