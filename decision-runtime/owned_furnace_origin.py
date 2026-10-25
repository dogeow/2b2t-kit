"""Certify observation/closure of the original server-opened furnace menu.

This is not permission to click inventory slots. Callers retain resident guards;
late windows still require the native host's ownership before any output click.
"""
from material_plan import inventory_counts


def certificate(command,reply,event,state,*,world,task,lease_id,pos):
    try:
        m=state['menu'];lease=state['supervision_lease'];old=reply['menu'];p=command['params']
        valid=(command['action']=='native'and command['op']=='interact'and p['pos']==pos
            and isinstance(pos,list)and len(pos)==3 and all(type(x)is int for x in pos)
            and p['face']=='up'and p['expected_state'].startswith('Block{minecraft:furnace}')
            and reply['phase']=='done'and bool(reply['id'])and reply['id']==event['request_id']==state['last_request']
            and event['op']=='interact'and event['phase']=='done'
            and event['params']['task_session']==task==lease['job_session']
            and all(event['params'][k]==p[k]for k in ['pos','face','expected_state','expected_hand'])
            and reply['world_session']==event['world_session']==state['world_session']==lease['world_session']==world
            and bool(world)and bool(task)and bool(lease_id)and lease['id']==lease_id and lease['kind']=='materials'
            and event['revision_before']==event['revision_after']==reply['control_revision']==state['control_revision']==lease['revision']
            and event['health_before']==event['health_after']==reply['health']==state['health']==20
            and event['inventory_delta']=={}and inventory_counts(reply)==inventory_counts(state)
            and event['position_before']==event['position_after']==reply['pos']==state['pos']
            and m['type']=='FurnaceMenu'and type(m['id'])is int and m['id']>0 and m['cursor']['count']==0
            and old['cursor']['count']==0 and ((old['type']=='InventoryMenu'and old['id']==0)or(old['type']=='FurnaceMenu'and old['id']==m['id']))
            and state['connected']is True and state['screen']=='FurnaceScreen'and state['manual_movement']is False
            and state['interface_paused']is False and state['inventory_interface_paused']is False
            and state['guard_armed']is True and state['guard_pve_only']is True and not state['guard_busy']
            and not state.get('health_recovery_hold')and not(state.get('safety_hold')or{}).get('active')
            and not state.get('navigating')and not state.get('native_material_busy')and not state.get('pending_scan')
            and isinstance(state['movement_keys'],dict)and not any(state['movement_keys'].values()))
        if not valid:return None
        return {'type':'FurnaceMenu','id':m['id'],'world_session':world,'task_session':task,
                'lease_id':lease_id,'control_revision':state['control_revision'],
                'purpose':'original_furnace_observation_and_close_only','source_request':reply['id'],'source_pos':pos}
    except(KeyError,TypeError,ValueError):return None


def pending_observation(queue,state):
    """Permit polling our exact pending opener, never an inventory input."""
    import json
    try:
        command=json.loads((queue.out/'command.json').read_text());directory=queue.out/command['id'];intent=json.loads((directory/'intent.json').read_text());request=json.loads((queue.root/'request.json').read_text());p=command['params'];m=state['menu'];lease=state['supervision_lease']
        if (intent!=command or (directory/'error.json').exists()or command['action']!='native'or command['op']!='interact'
                or request['op']!='interact'or not p['expected_state'].startswith('Block{minecraft:furnace}')
                or any(request[k]!=p[k]for k in ['pos','face','expected_state','expected_hand'])
                or request['id']!=state['last_request']or request['world_session']!=queue.world or state['world_session']!=queue.world
                or request['task_session']!=lease['job_session']or lease['job_session']!=queue.lease['job_session']
                or lease['id']!=queue.lease['id']or lease['kind']!='materials'or request['expected_revision']!=state['control_revision']
                or state['health']!=20 or state['manual_movement']is not False or state['screen']!='FurnaceScreen'
                or state.get('connected')is not True or state.get('guard_armed')is not True or state.get('guard_pve_only')is not True
                or state.get('guard_busy')or state.get('health_recovery_hold')or(state.get('safety_hold')or{}).get('active')
                or state.get('navigating')or any((state.get('movement_keys')or{}).values())
                or lease.get('world_session')!=queue.world or lease.get('revision')!=state.get('control_revision')
                or state['interface_paused']is not False or state['inventory_interface_paused']is not False
                or m['type']!='FurnaceMenu'or type(m['id'])is not int or m['id']<=0 or m['cursor']['count']!=0):return False
        result=directory/'result.json'
        if not result.exists():return True  # Polling only, while the actor journals the reply.
        reply=json.loads(result.read_text());events=[json.loads(x)for x in(queue.out/'control/events.jsonl').read_text().splitlines()];event=next((e for e in reversed(events)if e.get('request_id')==request['id']),None)
        return certificate(command,reply,event,state,world=queue.world,task=queue.lease['job_session'],lease_id=queue.lease['id'],pos=p['pos'])is not None
    except(OSError,ValueError,TypeError,KeyError):return False
