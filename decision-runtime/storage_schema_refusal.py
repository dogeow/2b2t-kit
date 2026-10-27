"""Exact top-face schema rejection occurs before container access calls status/native."""
import math
from material_plan import inventory_counts


def observable(command,error,baseline,event,state,world,task):
    try:
        pos,pose=command['pos'],command['pose']
        return bool(
            command['action']=='open_chest_from_pose' and command['face']=='up'
            and command.get('allow_top_face',False) is False
            and isinstance(pos,list) and len(pos)==3 and all(type(v)is int for v in pos)
            and isinstance(pose,list) and len(pose)==3
            and all(type(v)in(int,float)and math.isfinite(v)for v in pose)
            and error['type']=='ValueError'
            and error['error']=='Indoor chest needs an exact position, registered stand and permitted face'
            and error['native_inflight']is None and error['unconfirmed_native_request']is None
            and baseline['id']==error['last_request']==event['request_id']==state['last_request']
            and event['op']=='navigate' and event['phase']==baseline['phase']=='done'
            and event['world_session']==baseline['world_session']==state['world_session']==world
            and event['params']['task_session']==task
            and isinstance(event['params'].get('target'),list)and len(event['params']['target'])==3
            and all(type(v)in(int,float)and math.isfinite(v)for v in event['params']['target'])
            and math.dist(event['params']['target'],pose)<=.15 and event['inventory_delta']=={}
            and event['revision_after']==baseline['control_revision']==state['control_revision']
            and event['position_after']==baseline['pos']==state['pos']
            and inventory_counts(baseline)==inventory_counts(state)
            and state['connected']is True and state['health']==20 and state['manual_movement']is False
            and state['screen']=='' and state['menu']['type']=='InventoryMenu'
            and state['menu']['id']==0 and state['menu']['cursor']['count']==0
            and not any(state.get(k)for k in('navigating','native_material_busy','pending_scan'))
            and not any(state['movement_keys'].values()))
    except(KeyError,TypeError,ValueError):
        return False
