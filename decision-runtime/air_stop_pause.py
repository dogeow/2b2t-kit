"""Permit ending a lease after its exact acknowledged stopped navigation, never retry movement."""
from material_plan import inventory_counts

def allowed(action,command,reply,state,event,world,task,unknown=False):
 try:
  return (action=='pause'and not unknown and command['action']=='native'and command['op']=='navigate'
   and command['params']['air_only']is True and reply['phase']==state['phase']==event['phase']=='waiting'
   and reply['detail']==event['detail']=='air-only path changed; no blocks were excavated'
   and reply['id']==state['last_request']==event['request_id']
   and reply['world_session']==state['world_session']==event['world_session']==world
   and reply['control_revision']==state['control_revision']==event['revision_after']
   and event['op']=='navigate'and event['params']['task_session']==task
   and event['params']['target']==command['params']['target']and event['inventory_delta']=={}
   and inventory_counts(reply)==inventory_counts(state)and state['health']==20
   and state['connected']is True and state['manual_movement']is False and state['screen']==''
   and not state.get('navigating')and not state.get('native_material_busy')and not state.get('pending_scan')
   and isinstance(state['movement_keys'],dict)and not any(state['movement_keys'].values())
   and abs(state['velocity'][0])<=.03 and abs(state['velocity'][2])<=.03 and abs(state['velocity'][1])<=.12)
 except(KeyError,TypeError,ValueError):return False
