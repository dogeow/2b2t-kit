from material_plan import inventory_counts

def observable(command,error,baseline,event,state,world,task):
 try:
  return bool(command['action']=='open_brewing_stand'and error['type']=='RuntimeError'
   and error['error']=='Brewing stand pose or native owner changed; no input'
   and error['native_inflight']is None and error['unconfirmed_native_request']is None
   and baseline['id']==event['request_id']==error['last_request']==state['last_request']
   and event['op']=='navigate'and event['phase']==baseline['phase']=='done'
   and event['params']['task_session']==task and event['params']['target']==command['pose']
   and baseline['world_session']==event['world_session']==state['world_session']==world
   and event['revision_after']==baseline['control_revision']==state['control_revision']
   and event['position_after']==baseline['pos']==state['pos']and event['inventory_delta']=={}
   and inventory_counts(baseline)==inventory_counts(state)
   and state['connected']is True and state['health']==20 and state['screen']==''and state['manual_movement']is False
   and state['menu']['type']=='InventoryMenu'and state['menu']['id']==0 and state['menu']['cursor']['count']==0
   and not any(state['movement_keys'].values())and not any(state.get(k)for k in('navigating','native_material_busy','pending_scan')))
 except(KeyError,TypeError,ValueError):return False
