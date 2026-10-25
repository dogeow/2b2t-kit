"""Read-only settlement of a known, idle workbench approach rejection.

Navigation may have occurred. No workbench interaction or craft is replayed.
The existing queue's workbench-read fence admits only the snapshot below.
"""
import json
import math

DETAIL='Depot approach occluded or out of reach'


def observable(command,error,event,state,world,task,bench):
    try:
        menu=state['menu'];lease=state['supervision_lease']
        return (command['action']=='manufacture' and isinstance(command['targets'],dict)
            and bool(command['targets'])
            and all(isinstance(k,str)and k.startswith('minecraft:')and type(v)is int and v>0 for k,v in command['targets'].items())
            and isinstance(bench,list)and len(bench)==3 and all(type(v)is int for v in bench)
            and error['error']==DETAIL and error['native_inflight']is None and error['unconfirmed_native_request']is None
            and event['op']=='approach_block'and event['phase']=='waiting'and event['detail']==DETAIL
            and event['world_session']==world==state['world_session']==lease['world_session']
            and event['params']['task_session']==task==lease['job_session']and lease['kind']=='materials'
            and event['params']['pos']==bench and event['params']['face']=='up'
            and event['params']['expected_state']=='Block{minecraft:crafting_table}'
            and event['request_id']==error['last_request']==state['last_request']
            and all(isinstance(event[k],list)and len(event[k])==3 and all(type(n)in(int,float)and math.isfinite(n)for n in event[k])for k in ['position_before','position_after'])
            and event['position_after']==state['pos']and event['inventory_delta']=={}
            and type(event['revision_before'])is int and event['revision_before']==event['revision_after']==state['control_revision']==lease['revision']
            and event['health_before']==event['health_after']==state['health']==20
            and state['connected']is True and state['screen']==''and menu['type']=='InventoryMenu'and menu['id']==0
            and menu['cursor']['count']==0 and all(not menu['slots'][i]['count']for i in range(1,5))
            and state['manual_movement']is False and not state.get('navigating')and not state.get('native_material_busy')and not state.get('pending_scan')
            and state.get('guard_armed')is True and state.get('guard_pve_only')is True and not state.get('guard_busy')
            and not state.get('health_recovery_hold')and not (state.get('safety_hold')or{}).get('active')
            and isinstance(state['movement_keys'],dict)and not any(state['movement_keys'].values()))
    except(KeyError,TypeError,ValueError,IndexError):return False


def observe(queue):
    state=queue.status();command=json.loads((queue.out/'command.json').read_text());directory=queue.out/command['id']
    if not(directory/'error.json').exists()or(directory/'result.json').exists()or(queue.out/'control/unconfirmed-native-request.json').exists():
        raise RuntimeError('Workbench rejection has no exact known idle terminal')
    error=json.loads((directory/'error.json').read_text());events=[json.loads(row)for row in(queue.out/'control/events.jsonl').read_text().splitlines()];event=next((row for row in reversed(events)if row.get('request_id')==error.get('last_request')),None)
    profile=json.loads(__import__('pathlib').Path(command['profile']).read_text());bench=(profile.get('outdoor_workbench')or{}).get('pos')or profile.get('workbench')
    if not observable(command,error,event,state,queue.world,queue.lease['job_session'],bench):raise RuntimeError('Workbench use, motion or ownership remains unproved')
    if getattr(queue,'_workbench_route_read',None)is not None:raise RuntimeError('Another workbench observation is active')
    queue._workbench_route_read=command['id']
    try:return queue.native('snapshot')
    finally:queue._workbench_route_read=None
