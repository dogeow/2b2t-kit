"""Narrow box-click shapes; callers separately verify the exact SDK-owned window certificate."""
import json

def permitted(state,params,world,task):
    menu=state.get('menu')or{};rows=menu.get('slots')or[];cursor=menu.get('cursor')or{};lease=state.get('supervision_lease')or{}
    keys={'menu_id','slot','expected_item','expected_count','expected_cursor','expected_cursor_count','kind','button'}
    if (not isinstance(world,str)or not world or not isinstance(task,str)or not task
        or set(params)-keys or state.get('connected')is not True or state.get('health')!=20
        or state.get('world_session')!=world or state.get('manual_movement')is not False
        or state.get('safety_hold',{}).get('active')or state.get('health_recovery_hold')
        or state.get('interface_paused')is not False or state.get('inventory_interface_paused')is not False
        or state.get('guard_busy')or state.get('native_material_busy')or state.get('pending_scan')
        or lease.get('kind')!='materials'or lease.get('job_session')!=task or lease.get('world_session')!=world
        or lease.get('revision')!=state.get('control_revision')
        or(state.get('screen'),menu.get('type'))not in(('ContainerScreen','ChestMenu'),('ShulkerBoxScreen','ShulkerBoxMenu'))
        or len(rows)not in(63,90)or menu.get('type')=='ShulkerBoxMenu'and len(rows)!=63
        or type(menu.get('id'))is not int or menu['id']<=0 or type(params.get('menu_id'))is not int or params['menu_id']!=menu['id']
        or type(params.get('slot'))is not int or not 0<=params['slot']<len(rows)
        or type(params.get('button',0))is not int or params.get('button',0)!=0
        or type(params.get('expected_count'))is not int or type(params.get('expected_cursor_count'))is not int
        or not isinstance(params.get('expected_item'),str)or not params['expected_item'].startswith('minecraft:')
        or not isinstance(params.get('expected_cursor'),str)or not params['expected_cursor'].startswith('minecraft:')
        or params.get('kind')not in('pickup','quick_move')):return False
    row=rows[params['slot']];boundary=len(rows)-36
    if (params.get('expected_item')!=row.get('item')or params.get('expected_count')!=row.get('count')
        or params.get('expected_cursor')!=cursor.get('item')or params.get('expected_cursor_count')!=cursor.get('count')):return False
    def box(v):return isinstance(v.get('item'),str)and v['item'].startswith('minecraft:')and v['item'].endswith('shulker_box')and v.get('count')==1
    if not cursor.get('count')and box(row):
        if params['kind']=='quick_move':
            inventory=[v for v in state.get('inventory',[])if 0<=v.get('slot',99)<36]
            return(params['slot']<boundary and len(inventory)==36 and sum(not v.get('count')for v in inventory)>=3
                   and not any(v.get('count')and str(v.get('item','')).endswith('shulker_box')for v in inventory))
        return params['slot']>=boundary
    return(params['kind']=='pickup'and box(cursor)and params['slot']<boundary and row.get('count')==0)

def signature(state,params,world):
    return(world,state['control_revision'],state['menu']['id'],state.get('last_request'),json.dumps(params,sort_keys=True))
