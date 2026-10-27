"""A rejected boat ray grants only observation, no placement or retry credit."""
DETAIL='Target interaction face is occluded or out of reach'
def observable(command,error,book,event,state,world,task,counts):
    return (command.get('action')=='boat_place' and error.get('error')==DETAIL
        and 'native_inflight'in error and error['native_inflight']is None
        and 'unconfirmed_native_request'in error and error['unconfirmed_native_request']is None
        and book.get('complete')is False and book.get('pending')=='place'
        and book.get('world_session')==world==state.get('world_session')==event.get('world_session')
        and book.get('support')==command.get('support')==event.get('params',{}).get('pos')
        and book.get('item')==command.get('item')==event.get('params',{}).get('expected_hand')
        and book.get('request_id')==error.get('last_request')==event.get('request_id')==state.get('last_request')
        and event.get('params',{}).get('task_session')==task and event.get('params',{}).get('face')=='up'
        and event.get('op')=='interact' and event.get('phase')=='error' and event.get('detail')==DETAIL
        and event.get('position_before')==event.get('position_after') and event.get('inventory_delta')=={}
        and event.get('revision_before')==event.get('revision_after')==state.get('control_revision')
        and book.get('before')==counts and state.get('connected')is True and state.get('health')==20
        and state.get('manual_movement')is False and not state.get('screen') and not state.get('guard_busy')
        and not state.get('navigating') and not state.get('native_material_busy') and not state.get('pending_scan')
        and not any((state.get('movement_keys')or{}).values()))
