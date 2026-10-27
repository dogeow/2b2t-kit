"""Observe an unmoved route rejection before any workbench interaction."""
DETAIL='No loaded collision-free route to this depot; no ceiling is broken'

def observable(command,error,event,state,world,task):
    try:
        menu=state['menu']
        return(command['action']=='open_workbench' and error['error']==DETAIL
            and error['native_inflight'] is None and error['unconfirmed_native_request'] is None
            and event['op']=='approach_block' and event['phase']=='waiting' and event['detail']==DETAIL
            and event['world_session']==world and event['params']['task_session']==task
            and event['params']['pos']==command['pos'] and event['params']['face']=='up'
            and event['params']['expected_state']=='Block{minecraft:crafting_table}'
            and event['request_id']==error['last_request']==state['last_request']
            and event['position_before']==event['position_after']==state['pos']
            and event['inventory_delta']=={} and event['revision_before']==event['revision_after']==state['control_revision']
            and event['health_before']==event['health_after']==state['health']==20
            and state['screen']=='' and menu['type']=='InventoryMenu' and menu['id']==0 and menu['cursor']['count']==0
            and state['manual_movement'] is False and not state.get('navigating')
            and not state.get('native_material_busy') and not state.get('pending_scan')
            and isinstance(state['movement_keys'],dict) and not any(state['movement_keys'].values()))
    except (KeyError,TypeError):return False
