"""Recognize a conserved, known partial deposit stopped by a full container."""
from collections import Counter
from material_plan import inventory_counts

def unstarted_full_deposit(command,error,prior,receipt,state,event,world,task):
    """A full destination refused before the first click, following another item transfer."""
    item=command.get('item');menu=state.get('menu')or{};scope=receipt.get('owned_menu')or{}
    slots=menu.get('slots')or[];lease=state.get('supervision_lease')or{};params=event.get('params')or{}
    if (command.get('action')!='transfer' or command.get('deposit')is not True
        or type(command.get('target'))is not int or command['target']<0
        or not isinstance(item,str) or error.get('error')!='Destination has no space for '+item
        or error.get('type')!='RuntimeError' or error.get('native_inflight')is not None
        or error.get('unconfirmed_native_request')is not None
        or prior.get('action')!='transfer' or prior.get('deposit')is not True
        or not isinstance(prior.get('item'),str) or prior['item']==item
        or receipt.get('actual_held')!=prior.get('target')
        or inventory_counts(state)[prior['item']]!=prior.get('target')
        or inventory_counts(state)[item]<=command['target']
        or state.get('world_session')!=world or state.get('health')!=20
        or state.get('manual_movement')is not False or state.get('phase')!='done'
        or state.get('screen')!='ContainerScreen' or menu.get('type')!='ChestMenu'
        or len(slots)not in(63,90) or menu.get('cursor',{}).get('count')!=0
        or any(not r.get('count') or r.get('item')==item and r['count']<r.get('max_stack',64) for r in slots[:-36])
        or scope.get('type')!='ChestMenu' or scope.get('id')!=menu.get('id')
        or scope.get('world_session')!=world or scope.get('task_session')!=task
        or scope.get('lease_id')!=lease.get('id') or scope.get('control_revision')!=state.get('control_revision')
        or lease.get('kind')!='materials' or lease.get('job_session')!=task or lease.get('world_session')!=world
        or error.get('last_request')!=state.get('last_request') or event.get('request_id')!=state.get('last_request')
        or event.get('world_session')!=world or event.get('phase')!='done' or event.get('op')!='slot_click'
        or params.get('task_session')!=task or params.get('expected_item')!=prior['item']
        or params.get('kind')!='quick_move' or event.get('revision_after')!=state.get('control_revision')
        or event.get('position_after')!=state.get('pos')
        or state.get('navigating') or state.get('native_material_busy') or state.get('pending_scan')):
        return None
    return dict(item=item,confirmed_moved=0,actual_held=inventory_counts(state)[item],
                reason='destination_full_before_first_click',original_transfer_not_replayed=True)

def full_deposit(command,error,before,state,events,world,task):
    item=command.get('item');menu=state.get('menu')or{};old=before.get('menu')or{}
    if(command.get('action')!='transfer'or command.get('deposit')is not True
       or type(command.get('target'))is not int or command['target']<0
       or not isinstance(item,str)or error.get('error')!='Destination has no space for '+item
       or error.get('type')!='RuntimeError'or error.get('native_inflight')is not None
       or error.get('unconfirmed_native_request')is not None
       or error.get('last_request')!=state.get('last_request')
       or state.get('world_session')!=world or before.get('world_session')!=world
       or state.get('health')!=20 or state.get('manual_movement')is not False
       or state.get('phase')!='done'or state.get('screen')not in('ContainerScreen','ShulkerBoxScreen')
       or menu.get('type')not in('ChestMenu','ShulkerBoxMenu')or old.get('type')!=menu['type']
       or menu.get('id')!=old.get('id')or menu.get('cursor',{}).get('count')!=0
       or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')):return None
    a,b=inventory_counts(before),inventory_counts(state);moved=a[item]-b[item]
    if moved<=0 or b[item]<=command['target']:return None
    def box(m):return sum((Counter({r['item']:r['count']})for r in m['slots'][:-36]if r.get('count')),Counter())
    expected=a.copy();expected[item]-=moved
    expected_box=box(old);expected_box[item]+=moved
    if +expected!=b or +expected_box!=box(menu):return None
    start=next((i for i,e in enumerate(events)if e.get('request_id')==before.get('id')),None)
    tail=events[start+1:]if start is not None else[]
    if not tail:return None
    delta=Counter()
    for e in tail:
        if(e.get('world_session')!=world or e.get('params',{}).get('task_session')!=task
           or e.get('phase')!='done'or e.get('op')not in('slot_click','snapshot','scan')
           or e.get('op')in('snapshot','scan')and bool(e.get('inventory_delta'))
           or e.get('op')=='slot_click'and(e.get('params',{}).get('kind')!='quick_move' or e.get('params',{}).get('expected_item')!=item)):return None
        delta.update(e.get('inventory_delta')or{})
    last=tail[-1]
    if({k:v for k,v in delta.items()if v}!={item:-moved}
       or last.get('request_id')!=state.get('last_request')
       or last.get('revision_after')!=state.get('control_revision')
       or last.get('position_after')!=state.get('pos')):return None
    return dict(item=item,confirmed_moved=moved,actual_held=b[item],reason='destination_full',original_transfer_not_replayed=True)
