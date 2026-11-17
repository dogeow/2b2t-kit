"""A single quick move from a precisely witnessed storage slot."""
import json

def _source(state, params, world, task, item):
    menu=state.get('menu') or {}; rows=menu.get('slots') or []; lease=state.get('supervision_lease') or {}
    if (state.get('connected') is not True or state.get('world_session')!=world or state.get('health')!=20
        or state.get('manual_movement') is not False or state.get('guard_busy') or state.get('native_material_busy')
        or state.get('pending_scan') or state.get('safety_hold',{}).get('active') or state.get('health_recovery_hold')
        or lease.get('kind')!='materials' or lease.get('job_session')!=task or lease.get('world_session')!=world
        or lease.get('revision')!=state.get('control_revision') or menu.get('type')!='ChestMenu'
        or state.get('screen')!='ContainerScreen' or len(rows) not in (63,90)
        or type(menu.get('id')) is not int or menu['id']<=0 or params.get('menu_id')!=menu['id']
        or params.get('kind')!='quick_move' or params.get('expected_item')!=item
        or params.get('expected_count')!=1 or params.get('expected_cursor')!='minecraft:air' or params.get('expected_cursor_count')!=0
        or set(params)!={'menu_id','slot','kind','expected_item','expected_count','expected_cursor','expected_cursor_count'}
        or type(params.get('slot')) is not int or not 0<=params['slot']<len(rows)-36
        or (menu.get('cursor') or {}).get('count')!=0
        or not any(not row.get('count') for row in rows[len(rows)-36:])):return None
    row=rows[params['slot']]
    if row.get('item')!=item or row.get('count')!=1:return None
    return row,(world,state['control_revision'],menu['id'],state.get('last_request'),json.dumps(params,sort_keys=True))

def signature(state, params, world, task, expected):
    source=_source(state,params,world,task,'minecraft:enchanted_book')
    if source is None or not isinstance(expected,dict) or not expected:return None
    row,stamp=source;ench=row.get('stored_enchantments')
    if not isinstance(ench,list):return None
    actual={v.get('id'):v.get('level') for v in ench}
    if len(actual)!=len(ench) or actual!=expected:return None
    return (*stamp,json.dumps(expected,sort_keys=True))

def equipment_signature(state, params, world, task, expected):
    from anvil_enchant_preview import stack_key
    if not isinstance(expected,dict) or expected.get('count')!=1:return None
    item=expected.get('item')
    if item not in ('minecraft:bow','minecraft:diamond_chestplate','minecraft:diamond_pickaxe'):return None
    durability=expected.get('max_durability')
    if type(durability)is not int or durability<=0 or expected.get('durability')!=durability:return None
    source=_source(state,params,world,task,item)
    if source is None:return None
    row,stamp=source
    if stack_key(row)!=stack_key(expected):return None
    return (*stamp,stack_key(expected))

def equipment_deposit_signature(state, params, world, task, expected):
    """Move one exact finished item into an owned, fingerprinted shulker."""
    from collections import Counter
    from anvil_enchant_preview import stack_key
    if not isinstance(expected,dict) or set(expected)!={'item','contents'}:return None
    item=expected['item']; contents=expected['contents']
    if not isinstance(item,dict) or item.get('item') not in ('minecraft:bow','minecraft:diamond_axe') or item.get('count')!=1:return None
    maximum=item.get('max_durability')
    if type(maximum)is not int or maximum<=0 or item.get('durability')!=maximum or not isinstance(contents,list):return None
    menu=state.get('menu')or{}; rows=menu.get('slots')or[]; lease=state.get('supervision_lease')or{}
    if (state.get('connected') is not True or state.get('world_session')!=world or state.get('health')!=20
        or state.get('manual_movement') is not False or state.get('guard_busy') or state.get('native_material_busy')
        or state.get('pending_scan') or state.get('safety_hold',{}).get('active') or state.get('health_recovery_hold')
        or lease.get('kind')!='materials' or lease.get('job_session')!=task or lease.get('world_session')!=world
        or lease.get('revision')!=state.get('control_revision') or menu.get('type')!='ShulkerBoxMenu'
        or state.get('screen')!='ShulkerBoxScreen' or len(rows)!=63 or type(menu.get('id')) is not int or menu['id']<=0
        or set(params)!={'menu_id','slot','kind','expected_item','expected_count','expected_cursor','expected_cursor_count'}
        or params.get('menu_id')!=menu['id'] or type(params.get('slot')) is not int or not 27<=params['slot']<63
        or params.get('kind')!='quick_move' or params.get('expected_item')!=item['item'] or params.get('expected_count')!=1
        or params.get('expected_cursor')!='minecraft:air' or params.get('expected_cursor_count')!=0
        or (menu.get('cursor')or{}).get('count')!=0 or not any(not v.get('count') for v in rows[:27])):return None
    row=rows[params['slot']]
    if row.get('count')!=1 or stack_key(row)!=stack_key(item):return None
    def fingerprint(values):return Counter((stack_key(v),v['count']) for v in values if v.get('count'))
    if fingerprint(rows[:27])!=fingerprint(contents):return None
    return (world,state['control_revision'],menu['id'],state.get('last_request'),json.dumps(params,sort_keys=True),stack_key(item),json.dumps(sorted(fingerprint(contents).items()),sort_keys=True))
