"""Observe a stopped approach before any food was thrown by this command."""
from material_plan import inventory_counts


def observable(command, error, book, event, state, world, task, expected_bread):
    try:
        pending = book['pending']
        params = pending['params']
        menu = state['menu']
        return (command['action'] == 'feed_village_founders' and book['world_session'] == world
                and book['required'] == command['quotas'] and book['complete'] is False
                and not book['receipts'] and not any(book['delivered'].values())
                and not book.get('recoveries') and book['pending_food'] is None
                and book.get('recovery_pending') is None and pending['op'] == 'walk'
                and error['error'] == 'time limit reached; inspect progress before resuming'
                and error['native_inflight'] is None and error['unconfirmed_native_request'] is None
                and event['op'] == 'walk' and event['phase'] == 'waiting'
                and event['detail'] == error['error'] and event['world_session'] == world
                and event['params']['task_session'] == task
                and all(event['params'].get(k) == v for k, v in params.items())
                and event['request_id'] == error['last_request'] == state['last_request']
                and event['inventory_delta'] == {}
                and event['health_before'] == event['health_after'] == state['health'] == 20
                and event['position_after'] == state['pos']
                and event['revision_after'] == state['control_revision']
                and type(expected_bread) is int and expected_bread > 0
                and inventory_counts(state)['minecraft:bread'] == expected_bread
                and state['screen'] == '' and menu['type'] == 'InventoryMenu'
                and menu['id'] == 0 and menu['cursor']['count'] == 0
                and state['manual_movement'] is False and not state.get('navigating')
                and not state.get('native_material_busy') and not state.get('pending_scan')
                and isinstance(state['movement_keys'], dict) and not any(state['movement_keys'].values()))
    except (KeyError, TypeError, ValueError):
        return False


def unmoved_air_refusal(command, error, book, event, state, world, task, expected_bread):
    """Permit a snapshot only after a zero-input pre-food air-route refusal."""
    try:
        detail='Air-only navigation requires the current material lease and a loaded clear dry path'
        pending=book['pending'];params=pending['params'];lease=state['supervision_lease']
        return (command['action']=='feed_village_founders' and book['world_session']==world
                and book['complete'] is False and book['required']==command['quotas']
                and book['receipts']==[] and book['delivered']=={u:0 for u in command['quotas']}
                and book['pending_food'] is None and not book.get('recoveries') and not book.get('recovery_pending')
                and pending['op']=='navigate' and params['air_only'] is True
                and error['type']=='RuntimeError' and error['error']==detail
                and error['native_inflight'] is None and error['unconfirmed_native_request'] is None
                and book['error']==repr(RuntimeError(detail))
                and event['op']=='navigate' and event['phase']==state['phase']=='error' and event['detail']==detail
                and event['world_session']==state['world_session']==world
                and event['request_id']==error['last_request']==state['last_request']
                and event['params']['task_session']==lease['job_session']==task
                and lease['world_session']==world and lease['kind']=='materials'
                and all(event['params'].get(k)==v for k,v in params.items())
                and event['position_before']==event['position_after']==state['pos']
                and event['revision_before']==event['revision_after']==state['control_revision']
                and event['inventory_delta']=={} and event['health_before']==event['health_after']==state['health']==20
                and type(expected_bread)is int and expected_bread>=sum(command['quotas'].values())
                and inventory_counts(state)['minecraft:bread']==expected_bread
                and state['connected'] is True and state['manual_movement'] is False and state['screen']==''
                and state['menu']['cursor']['count']==0 and not state.get('navigating')
                and not state.get('native_material_busy') and not state.get('pending_scan')
                and isinstance(state['movement_keys'],dict) and not any(state['movement_keys'].values()))
    except(KeyError,TypeError,ValueError):return False
