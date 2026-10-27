"""Permit a fresh route after manual cancellation; never resolve or replay the old trip."""
import math

def admit(unknown,command,last_event,state):
    params=unknown.get('params')or{};point=params.get('target')
    return (unknown.get('op')=='navigate' and params.get('air_only')is True
        and isinstance(point,list)and len(point)==3 and all(type(v)in(int,float)and math.isfinite(v)for v in point)
        and command.get('action')=='native'and command.get('op')=='navigate'and command.get('params')==params
        and unknown.get('original_request_replayed')is False
        and unknown.get('world_session')==state.get('world_session')==last_event.get('world_session')
        and last_event.get('params',{}).get('task_session')==unknown.get('task_session')
        and last_event.get('op')in('scan','snapshot','navigate')and last_event.get('phase')in(None,'done')
        and last_event.get('inventory_delta')=={}
        and type(last_event.get('revision_after'))is int and state.get('control_revision',-1)>last_event['revision_after']
        and state.get('last_request')==unknown.get('request_id')
        and state.get('connected')is True and state.get('health')==20 and state.get('manual_movement')is False
        and state.get('screen')==''and state.get('phase')=='stopped'and state.get('detail')=='手动移动接管'
        and not state.get('supervision_lease')and not state.get('health_recovery_hold')and not state.get('safety_hold',{}).get('active')
        and not any(state.get(k)for k in ('navigating','native_material_busy','pending_scan'))
        and not any((state.get('movement_keys')or{}).values()))
