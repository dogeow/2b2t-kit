"""Return an observed first input after a local preview-observation timeout.

Never repeats an input placement, supplies the second input or takes output.
Requires the two original input clicks to have exact successful native receipts.
"""
import json
from copy import deepcopy
from anvil_enchant_preview import stack_key, menu_slot, bag, _wait
from kit_runtime.journal import write_json


def returnable(command,error,book,events,state,certificate,world,task):
    try:
        menu=state['menu']; source=menu_slot(command['left_slot']); right=menu_slot(command['right_slot'])
        pickup,place=events[-2:]
        if not (command['action']=='anvil_enchant_preview'
                and error['error']=='Original preview/input observation unconfirmed; no click replay'
                and error['native_inflight'] is None and error['unconfirmed_native_request'] is None
                and book['complete'] is False and book['output_clicks']==0 and book['experience_spent']==0
                and book['pending']=={'stage':'place_input','source':source,'cell':0}
                and book['world_session']==world and book['task_session']==task
                and book['left']==command['expected_left'] and book['right']==command['expected_right']
                and book['input_source_slots']=={'left':command['left_slot'],'right':command['right_slot']}
                and state['connected'] is True and state['manual_movement'] is False
                and state['health']==20 and state['experience_level']==book['level_before']
                and state['world_session']==world and state['screen']=='AnvilScreen'
                and state['interface_paused'] is False and state['inventory_interface_paused'] is False
                and not any(state['movement_keys'].values())
                and menu['type']=='AnvilMenu' and menu['id']==book['menu_id'] and len(menu['slots'])==39
                and not menu['cursor']['count'] and not menu['slots'][1]['count'] and not menu['slots'][2]['count']
                and not menu['slots'][source]['count'] and menu['slots'][0]['count']==1
                and stack_key(menu['slots'][0])==stack_key(book['left'])
                and menu['slots'][right]['count']==1 and stack_key(menu['slots'][right])==stack_key(book['right'])
                and certificate['type']=='AnvilMenu' and certificate['id']==menu['id']
                and certificate['world_session']==world and certificate['task_session']==task
                and certificate['lease_id']==book['lease_id']==state['supervision_lease']['id']
                and certificate['control_revision']==book['control_revision']==state['control_revision']
                and place['request_id']==error['last_request']==state['last_request']):
            return False
        for event,slot,item,count,cursor,cursor_count in (
                (pickup,source,book['left']['item'],1,'minecraft:air',0),
                (place,0,'minecraft:air',0,book['left']['item'],1)):
            p=event['params']
            if not (event['op']=='slot_click' and event['phase']=='done' and event['world_session']==world
                    and event['position_before']==event['position_after']==state['pos']
                    and event['revision_before']==event['revision_after']==state['control_revision']
                    and event['health_before']==event['health_after']==20
                    and p['task_session']==task and p['menu_id']==menu['id'] and p['slot']==slot
                    and p['kind']=='pickup' and p['button']==0 and p['expected_item']==item
                    and p['expected_count']==count and p['expected_cursor']==cursor
                    and p['expected_cursor_count']==cursor_count):
                return False
        return True
    except (KeyError,ValueError,TypeError,AttributeError):
        return False


def restore_first_input(q):
    state=q.status(); command=json.loads((q.out/'command.json').read_text());d=q.out/command['id']
    if not (d/'error.json').exists() or (d/'result.json').exists() or (q.out/'control/unconfirmed-native-request.json').exists():
        raise RuntimeError('No settled partial preview to restore')
    error=json.loads((d/'error.json').read_text())
    path=d/'actual-zero-xp-anvil-preview/preview.json';book=json.loads(path.read_text())
    events=[json.loads(line) for line in (q.out/'control/events.jsonl').read_text().splitlines()]
    certificate=json.loads((q.out/'owned-material-menu.json').read_text())
    if not returnable(command,error,book,events,state,certificate,q.world,q.lease['job_session']):
        raise RuntimeError('Partial preview is not a proved successful first-input placement')
    proof=q.out/(q.prefix+'-input-restoration.json')
    record={'complete':False,'original_command':command,'pending':'return_left_input',
            'output_clicks':0,'placement_replayed':False,'level_before':state['experience_level']}
    write_json(proof,record)
    before=bag(state);before[stack_key(book['left'])]+=1
    params=dict(menu_id=state['menu']['id'],slot=0,kind='quick_move',button=0,
                expected_item=book['left']['item'],expected_count=1,
                expected_cursor='minecraft:air',expected_cursor_count=0)
    q._anvil_input_return=(command['id'],deepcopy(params))
    try:result=q.native('slot_click',**params)
    finally:q._anvil_input_return=None
    class Observer:
        def status(self):return q.status()
    after,times=_wait(Observer(),lambda s:s['menu']['id']==state['menu']['id']
                      and not s['menu']['cursor']['count'] and not any(r['count'] for r in s['menu']['slots'][:3])
                      and bag(s)==before and s['experience_level']==record['level_before'])
    record.update(pending='close_empty_owned_anvil',returned_request=result['id'],returned_times=times)
    write_json(proof,record)
    closed=q.native('close_menu')
    final,times=_wait(Observer(),lambda s:not s['screen'] and s['menu']['id']==0
                      and bag(s)==before and s['experience_level']==record['level_before'])
    (q.out/'owned-material-menu.json').unlink(missing_ok=True)
    record.update(complete=True,pending=None,closed_request=closed['id'],closed_times=times)
    write_json(proof,record)
    return record
