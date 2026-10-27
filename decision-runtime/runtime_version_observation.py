"""Observe an acknowledged reload whose returned version differs; never repeat unknown input."""
from material_plan import inventory_counts

def observable(command,error,reply,event,state,world,task,before_generation):
    try:
        return bool(command['action']=='hot_runtime_update'
            and error['type']=='RuntimeError'and error['error']=='Runtime version was not confirmed; do not repeat reload blindly'
            and error['native_inflight']is None and error['unconfirmed_native_request']is None
            and event['op']=='runtime_reload'and event['phase']==reply['phase']=='done'
            and event['params']['task_session']==task
            and event['request_id']==error['last_request']==reply['id']==state['last_request']
            and event['world_session']==reply['world_session']==state['world_session']==world
            and type(before_generation)is int and reply['runtime_generation']==state['runtime_generation']==before_generation+1
            and reply['runtime_version']==state['runtime_version']
            and reply['navigation_runtime_version']==state['navigation_runtime_version']
            and reply['runtime_version']!=command['version']
            and event['revision_after']==reply['control_revision']==state['control_revision']
            and event['position_after']==reply['pos']==state['pos']
            and event['inventory_delta']=={}and inventory_counts(reply)==inventory_counts(state)
            and state['connected']is True and state['health']==20 and state['screen']==''and state['manual_movement']is False
            and state['menu']['cursor']['count']==0 and state['menu']['type']=='InventoryMenu'
            and not any(state.get(k)for k in('navigating','native_material_busy','pending_scan'))
            and not any(state['movement_keys'].values()))
    except(KeyError,TypeError,ValueError):return False
