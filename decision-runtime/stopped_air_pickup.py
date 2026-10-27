"""Observe a conserved item gain during a known stopped air route; never replay it."""
import math
from material_plan import inventory_counts
from villager_events import joined_pickups


def observable(command,reply,previous,prior,event,state,frame,world,task,uid):
    try:
        if (command['action']!='native'or command['op']!='navigate'or command['params']['air_only']is not True
                or previous['action']!='native'or previous['op']!='snapshot'or prior.get('phase')not in(None,'done')
                or prior.get('phase')is None and (prior.get('connected')is not True or not isinstance(prior.get('id'),str))
                or prior['world_session']!=world or reply['world_session']!=world or state['world_session']!=world
                or reply['phase']!='waiting'or reply['detail']!='air-only path changed; no blocks were excavated'
                or reply['id']!=state['last_request']or event['request_id']!=reply['id']
                or event['op']!='navigate'or event['phase']!='waiting'or event['detail']!=reply['detail']
                or event['world_session']!=world or event['params']['task_session']!=task
                or event['params']['target']!=command['params']['target']
                or prior['control_revision']!=event['revision_before']
                or reply['control_revision']!=state['control_revision']or event['revision_after']!=state['control_revision']
                or event['position_after']!=reply['pos']or event['position_before']!=prior['pos']
                or event['health_before']!=20 or event['health_after']!=20 or state['health']!=20
                or state['connected']is not True or state['manual_movement']is not False or state['screen']
                or state['flight']is not True or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')
                or not isinstance(state['movement_keys'],dict)or any(state['movement_keys'].values())):return False
        a,b=reply['pos'],state['pos']
        if (any(not isinstance(p,list)or len(p)!=3 or any(type(v)not in(int,float)or not math.isfinite(v)for v in p)for p in(a,b))
                or math.hypot(a[0]-b[0],a[2]-b[2])>.05 or not 0<=a[1]-b[1]<=.1):return False
        sources=[v for v in prior['entities']if v.get('uuid')==uid]
        if len(sources)!=1:return False
        source=sources[0];stack=source['stack'];item=stack['item'];amount=stack['count']
        if source['type']!='minecraft:item'or type(amount)is not int or amount!=1:return False
        same_item=[v for v in prior['entities']if v.get('type')=='minecraft:item'and v.get('stack',{}).get('item')==item]
        if len(same_item)!=1 or any(v.get('uuid')==uid for v in state['entities']):return False
        before,after=inventory_counts(prior),inventory_counts(state)
        delta={k:after[k]-before[k]for k in before.keys()|after.keys()if after[k]!=before[k]}
        if delta!={item:amount}or event['inventory_delta']!=delta or inventory_counts(reply)!=after:return False
        # The short-lived entity-event publisher may already have pruned the
        # pickup. Inventory, the immutable native delta and disappearance still
        # prove conservation, as in the existing stopped-walk pickup observer.
        # If a source receipt remains available, it must agree with that proof.
        if frame is not None:
            if frame['world_session']!=world or frame['runtime_generation']!=prior['runtime_generation']:return False
            source_events=[e for e in frame['events']if e.get('source_entity_id')==source['id']]
            if source_events:
                seen={'world_session':world,'runtime_generation':prior['runtime_generation'],'observed_at':prior['time'],'entity':source}
                pickups=joined_pickups(frame,item,{state['player_uuid']},seen,after_time=prior['time'])
                return len(pickups)==1 and pickups[0]['amount']==amount
        return True
    except(KeyError,TypeError,ValueError):return False
