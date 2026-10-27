"""Read-only admission after a trade capacity check, before any selection or purchase."""
DETAIL='Reserve output and existing payment return slots before trade selection'
def observable(command,error,state,event,world,task,*,journal_exists,unknown_exists):
 try:
  menu=state['menu'];info=menu['merchant'];lease=state['supervision_lease']
  return(command['action']=='merchant_buy_one'and type(command['index'])is int
   and 0<=command['index']<len(info['offers'])and error['error']==DETAIL and error['type']=='RuntimeError'
   and error['native_inflight']is None and error['unconfirmed_native_request']is None
   and not journal_exists and not unknown_exists
   and event['request_id']==error['last_request']==state['last_request']and event['phase']=='done'
   and (event['op']=='snapshot' or event['op']=='interact_entity'
        and event['request_id']==info['opening_request_id']and event['params'].get('expected_uuid')==info['villager_uuid']
        and event['params'].get('expected_hand')=='minecraft:netherite_sword')
   and event['world_session']==state['world_session']==world and event['params']['task_session']==task
   and event['position_before']==event['position_after']==state['pos']and event['inventory_delta']=={}
   and event['revision_before']==event['revision_after']==state['control_revision']
   and state['connected']is True and state['health']==20 and state['manual_movement']is False
   and state['screen']=='MerchantScreen'and menu['type']=='MerchantMenu'and menu['id']>0 and menu['cursor']['count']==0
   and info['owned']is True and info['owner_task']==task and info['villager_uuid']and info['opening_request_id']
   and lease['kind']=='materials'and lease['job_session']==task and lease['world_session']==world
   and not state.get('navigating')and not state.get('native_material_busy')and not state.get('pending_scan'))
 except(KeyError,TypeError,ValueError):return False
