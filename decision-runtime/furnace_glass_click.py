"""One exact finished-glass output click after proving the original opener."""
import json
from material_plan import inventory_counts
from owned_furnace_origin import certificate


def signature(state,params,world):
    m=state.get('menu')or{};lease=state.get('supervision_lease')or{};rows=m.get('slots')or[]
    if (state.get('world_session')!=world or state.get('health')!=20 or state.get('manual_movement')is not False
            or state.get('screen')!='FurnaceScreen'or m.get('type')!='FurnaceMenu'or len(rows)!=39
            or m.get('cursor',{}).get('count')!=0 or rows[0].get('count')!=0
            or rows[2].get('item')!='minecraft:glass'or type(rows[2].get('count'))is not int or not 1<=rows[2]['count']<=64
            or state.get('interface_paused')is not False or state.get('inventory_interface_paused')is not False
            or state.get('guard_armed')is not True or state.get('guard_pve_only')is not True or state.get('guard_busy')
            or lease.get('kind')!='materials'or lease.get('world_session')!=world or lease.get('revision')!=state.get('control_revision')
            or params!={'menu_id':m.get('id'),'slot':2,'expected_item':'minecraft:glass','expected_count':rows[2]['count'],'expected_cursor':'minecraft:air','expected_cursor_count':0,'kind':'quick_move','button':0}):
        raise ValueError('Only one exact finished-glass output shift-click is allowed')
    return json.dumps({'world':world,'lease':lease['id'],'task':lease['job_session'],'revision':state['control_revision'],
                       'last_request':state['last_request'],'menu':m,'params':params},sort_keys=True)


def execute(queue,params,*,max_glass_total):
    state=queue.status();token=signature(state,params,queue.world)
    if type(max_glass_total)is not int or inventory_counts(state)['minecraft:glass']+params['expected_count']>max_glass_total:
        raise ValueError('Finished glass exceeds the explicitly requested inventory total')
    command=json.loads((queue.out/'command.json').read_text());directory=queue.out/command['id']
    if(directory/'error.json').exists()or not(directory/'result.json').exists()or(queue.out/'control/unconfirmed-native-request.json').exists():raise RuntimeError('Original furnace opening must be complete and known')
    reply=json.loads((directory/'result.json').read_text());events=[json.loads(x)for x in(queue.out/'control/events.jsonl').read_text().splitlines()];event=next((e for e in reversed(events)if e.get('request_id')==state['last_request']),None)
    if certificate(command,reply,event,state,world=queue.world,task=queue.lease['job_session'],lease_id=queue.lease['id'],pos=command.get('params',{}).get('pos'))is None:
        raise RuntimeError('Exact original furnace ownership is unproved; no inventory input')
    if getattr(queue,'_furnace_glass_click',None)is not None:raise RuntimeError('Another glass output click is active')
    queue._furnace_glass_click=token
    try:return queue.native('slot_click',**params)
    finally:queue._furnace_glass_click=None
