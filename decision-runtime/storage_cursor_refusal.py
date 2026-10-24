"""Return a known storage pickup after a later pre-input remainder rejection."""
def return_plan(command,error,state,events,world,task):
    menu=state.get('menu')or{};slots=menu.get('slots')or[];cursor=menu.get('cursor')or{}
    if(command.get('action')!='transfer'or command.get('deposit')is True
       or error.get('error')not in ('Slot item changed','Slot count changed')
       or error.get('type')!='RuntimeError'or 'native_inflight'not in error or 'unconfirmed_native_request'not in error or error.get('native_inflight')is not None
       or error.get('unconfirmed_native_request')is not None
       or state.get('world_session')!=world or state.get('health')!=20
       or state.get('manual_movement')is not False or state.get('navigating')
       or state.get('native_material_busy')or state.get('pending_scan')
       or menu.get('type')not in ('ChestMenu','ShulkerBoxMenu')or len(slots)<37
       or cursor.get('item')!=command.get('item')or not 0<cursor.get('count',0)<=cursor.get('max_stack',64)
       or len(events)<2):return None
    pickup,rejected=events[-2:];a=pickup.get('params')or{};b=rejected.get('params')or{};boundary=len(slots)-36
    for event in (pickup,rejected):
        if(event.get('world_session')!=world or event.get('op')!='slot_click'
           or event.get('params',{}).get('task_session')!=task
           or event.get('revision_after')!=state.get('control_revision')
           or event.get('position_after')!=state.get('pos')or event.get('inventory_delta')):return None
    if(pickup.get('phase')!='done'or rejected.get('phase')!='error'
       or rejected.get('detail')!=error['error']
       or rejected.get('request_id')!=error.get('last_request')or error.get('last_request')!=state.get('last_request')
       or a.get('menu_id')!=menu.get('id')or b.get('menu_id')!=menu.get('id')
       or a.get('kind')!='pickup'or a.get('button')!=0
       or type(a.get('slot'))is not int or not 0<=a['slot']<boundary or b.get('slot')!=a['slot']
       or a.get('expected_cursor')!='minecraft:air'or a.get('expected_cursor_count')!=0 or a.get('expected_item')!=cursor['item']
       or a.get('expected_count')!=cursor['count']
       or b.get('kind')!='pickup'or b.get('button')!=1
       or b.get('expected_cursor')!=cursor['item']or b.get('expected_cursor_count')!=cursor['count']
       or b.get('expected_count')!=0 or b.get('expected_item')!='minecraft:air'):return None
    empty=next((r for r in slots[boundary:]if r.get('count')==0 and type(r.get('slot'))is int),None)
    if empty is None:return None
    return dict(menu_id=menu['id'],slot=empty['slot'],kind='pickup',button=0,
                expected_item='minecraft:air',expected_count=0,
                expected_cursor=cursor['item'],expected_cursor_count=cursor['count'])
