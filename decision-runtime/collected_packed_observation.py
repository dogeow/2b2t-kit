"""Read-only reconciliation of a known box picked up during its owned approach."""
from collections import Counter
from anvil_enchant_preview import stack_key
from material_plan import inventory_counts
from packed_supplies import contents


DETAIL='Owned portable box still needs recovery after one short normal step; no collection replay'


def observable(command,error,record,event,reply,state,world,task):
    try:
        expected=Counter()
        for row in record['ownership_preflight']['inventory']:
            if row['slot']<36 and row['count']:expected[row['item']]+=row['count']
        expected.update(record['taken']);expected[record['item']]+=1
        boxes=[v for v in state['inventory']if v['count']and v['item'].endswith('shulker_box')]
        taken=record['taken'];item=command['expected_stack']['item']
        return (command['action']=='take_packed_equipment' and error['error']==DETAIL
                and error['native_inflight'] is None and error['unconfirmed_native_request'] is None
                and record['stage']=='broken' and record['world_session']==world
                and record['slot']==command['box_slot']==record['source']['slot']
                and record['source']['item']==record['item'] and record['source']['count']==1
                and record['source']['counts']==record['initial_counts']
                and record['ownership_preflight']['world_session']==world
                and record['ownership_preflight']['cursor_clean'] is True
                and taken=={item:1} and record['exact_stacks']=={item:command['expected_stack']}
                and all(record['initial_counts'][k]-record['remaining_counts'].get(k,0)==taken.get(k,0)
                        for k in record['initial_counts'])
                and set(record['remaining_counts'])<=set(record['initial_counts'])
                and len(boxes)==1 and boxes[0]['item']==record['item'] and boxes[0]['count']==1
                and contents(boxes[0]['contains'])==record['remaining_counts']
                and inventory_counts(state)==expected
                and any(v['count']==1 and stack_key(v)==stack_key(command['expected_stack'])for v in state['inventory'])
                and not any(v.get('uuid')==record['drop_uuid']for v in state['entities'])
                and state['connected'] is True and state['world_session']==world
                and state['health']==20 and state['manual_movement'] is False
                and not state['screen'] and state['menu']['type']=='InventoryMenu'
                and state['menu']['id']==0 and not state['menu']['cursor']['count']
                and not state.get('navigating') and not state.get('native_material_busy') and not state.get('pending_scan')
                and not any(state['movement_keys'].values())
                and event['op']=='scan' and event['phase']==reply['phase']=='done'
                and event['world_session']==reply['world_session']==world
                and event['params']['task_session']==task
                and event['request_id']==reply['id']==error['last_request']==state['last_request']
                and event['position_before']==event['position_after']==reply['pos']==state['pos']
                and event['revision_before']==event['revision_after']==reply['control_revision']==state['control_revision']
                and event['inventory_delta']=={} and event['health_before']==event['health_after']==20)
    except (KeyError,TypeError,AttributeError,ValueError):return False
