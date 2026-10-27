"""A wrong-kind container scan is observable only with the exact original reply."""
from material_plan import inventory_counts

def observable(command,error,baseline,reply,event,state,world,task):
    try:
        pos=command['pos'];rows=reply['blocks'];expected=command.get('block_id','minecraft:chest')
        return bool(command['action']=='open_chest_from_pose'
            and error['type']=='OutdoorChestChanged'and error['error']=='Expected outdoor chest changed'
            and error['native_inflight']is None and error['unconfirmed_native_request']is None
            and event['request_id']==reply['id']==error['last_request']==state['last_request']
            and event['op']=='scan'and event['params']['min']==event['params']['max']==pos
            and event['params']['task_session']==task and event['inventory_delta']=={}
            and event['phase']==reply['phase']=='done'
            and reply['scan_cells_read']==reply['scan_total_cells']==len(rows)==1
            and rows[0]['pos']==pos and not rows[0]['state'].startswith('Block{'+expected+'}')
            and reply['world_session']==event['world_session']==baseline['world_session']==state['world_session']==world
            and reply['control_revision']==reply['scan_start_revision']==reply['scan_end_revision']==event['revision_before']==event['revision_after']==baseline['control_revision']==state['control_revision']
            and reply['pos']==event['position_before']==event['position_after']==baseline['pos']==state['pos']
            and inventory_counts(reply)==inventory_counts(baseline)==inventory_counts(state)
            and state['connected']is True and state['health']==20 and state['manual_movement']is False
            and state['screen']==''and state['menu']['type']=='InventoryMenu'and state['menu']['id']==0
            and state['menu']['cursor']['count']==0 and not any(state['movement_keys'].values())
            and not any(state.get(k)for k in('navigating','native_material_busy','pending_scan')))
    except(KeyError,TypeError,ValueError):return False
