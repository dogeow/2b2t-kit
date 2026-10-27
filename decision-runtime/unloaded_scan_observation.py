"""A stopped unloaded read permits another observation, never a clearance claim."""
import math,re

def observable(command,reply,event,state,world,task):
    params=command.get('params')or{}
    try:
        low,high=params['min'],params['max']
        if len(low)!=3 or len(high)!=3 or any(type(n)is not int for n in low+high):return False
        volume=math.prod(high[i]-low[i]+1 for i in range(3))
        if any(high[i]<low[i]for i in range(3))or not 0<volume<=30000:return False
    except(KeyError,TypeError):return False
    detail=reply.get('detail','')
    return (command.get('action')=='native' and command.get('op')=='scan'
        and reply.get('op')=='scan' and reply.get('phase')=='waiting'
        and re.fullmatch(r'scan stopped; partial records retained: Server chunk is not loaded: -?\d+ -?\d+',detail)is not None
        and reply.get('scan_coherent')is False and reply.get('scan_total_cells')==volume
        and type(reply.get('scan_cells_read'))is int and 0<=reply['scan_cells_read']<volume
        and reply.get('id')==event.get('request_id')==state.get('last_request')
        and world==reply.get('world_session')==event.get('world_session')==state.get('world_session')
        and state.get('connected')is True and state.get('manual_movement')is False
        and state.get('screen')=='' and state.get('health')==20
        and not any(state.get(k)for k in ('navigating','native_material_busy','pending_scan'))
        and not any((state.get('movement_keys')or{}).values())
        and event.get('op')=='scan' and event.get('phase')=='waiting' and event.get('detail')==detail
        and event.get('params',{}).get('task_session')==task
        and all(event.get('params',{}).get(k)==v for k,v in params.items())
        and event.get('inventory_delta')=={} and event.get('health_before')==event.get('health_after')==20
        and event.get('position_before')==event.get('position_after')==reply.get('pos')==state.get('pos')
        and event.get('revision_before')==event.get('revision_after')==reply.get('scan_start_revision')==reply.get('scan_end_revision')==state.get('control_revision'))
