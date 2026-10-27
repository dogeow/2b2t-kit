"""Observe a pre-click quick-move refusal with exact retained carried property.

An earlier accepted move may settle during the refusal frame. Its partial gain
is reconciled against the opened-container baseline, never credited to a retry.
"""
from collections import Counter
from anvil_enchant_preview import bag,stack_key
from material_plan import inventory_counts


def observable(command,error,before,event,reply,state,world,task):
    try:
        menu=state['menu'];p=event['params'];item=command['item'];gain=inventory_counts(state)[item]-inventory_counts(before)[item]
        expected=bag(before);expected[stack_key({'item':item,'count':1,'max_stack':64})]+=gain
        return (command['action']=='transfer'and not command.get('deposit')
                and item=='minecraft:iron_ingot'and type(command['target'])is int
                and 0<gain and inventory_counts(state)[item]<=command['target']
                and error['error']in('Slot item changed','Slot count changed')
                and error['native_inflight']is None and error['unconfirmed_native_request']is None
                and state['connected']is True and state['health']==20 and state['manual_movement']is False
                and state['screen']=='ContainerScreen'and menu['type']=='ChestMenu'
                and menu['id']==before['menu']['id']and not menu['cursor']['count']
                and bag(state)==expected and bag(reply)==expected
                and not state.get('navigating')and not state.get('native_material_busy')and not state.get('pending_scan')
                and not any(state['movement_keys'].values())
                and event['op']=='slot_click'and p['kind']=='quick_move'and p['button']==0
                and p['expected_item']==item and p['expected_count']>0
                and p['expected_cursor']=='minecraft:air'and p['expected_cursor_count']==0
                and p['menu_id']==menu['id']and 0<=p['slot']<len(menu['slots'])-36
                and p['task_session']==task
                and event['phase']==reply['phase']=='error'and event['detail']==reply['detail']==error['error']
                and event['request_id']==reply['id']==error['last_request']==state['last_request']
                and event['world_session']==reply['world_session']==state['world_session']==before['world_session']==world
                and event['position_before']==event['position_after']==reply['pos']==state['pos']
                and event['revision_before']==event['revision_after']==reply['control_revision']==state['control_revision']
                and event['health_before']==event['health_after']==20 and not reply.get('outcome_pending'))
    except(KeyError,TypeError,AttributeError,ValueError):return False
