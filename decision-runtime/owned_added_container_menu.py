"""Adopt only native-confirmed dispenser/hopper menus of this material owner."""
MENU_BY_SCREEN={'DispenserScreen':'DispenserMenu','HopperScreen':'HopperMenu'}

def allowed(state,world,task,revision):
    menu=state.get('menu')or{};lease=state.get('supervision_lease')or{}
    return (state.get('connected')is True and state.get('manual_movement')is False
        and isinstance(world,str)and bool(world)and state.get('world_session')==world
        and isinstance(task,str)and bool(task)and type(revision)is int
        and state.get('control_revision')==revision
        and state.get('screen')in MENU_BY_SCREEN
        and menu.get('type')==MENU_BY_SCREEN.get(state.get('screen'))
        and menu.get('material_owned')is True and type(menu.get('id'))is int and menu['id']>0
        and lease.get('kind')=='materials'and lease.get('job_session')==task
        and lease.get('world_session')==world and lease.get('revision')==revision)

SWORDS=frozenset('minecraft:'+v+'_sword'for v in('wooden','stone','copper','iron','golden','diamond','netherite'))
BLOCK_MENU={'minecraft:dispenser':('DispenserScreen','DispenserMenu'),'minecraft:hopper':('HopperScreen','HopperMenu')}

def opening_ticket(state,request,task):
    """Capture before our normal use. A late menu alone never grants ownership."""
    lease=state.get('supervision_lease')or{};interaction=state.get('game_interaction')or{};menu=state.get('menu')or{}
    block=request.get('expected_state','').split('}',1)[0].removeprefix('Block{');pair=BLOCK_MENU.get(block)
    if (request.get('op')!='interact'or pair is None or request.get('expected_hand')not in SWORDS
        or not isinstance(task,str)or not task or request.get('task_session')!=task
        or state.get('screen')!=''or menu.get('id')!=0 or(menu.get('cursor')or{}).get('count')!=0
        or state.get('connected')is not True or state.get('manual_movement')is not False
        or state.get('game_interaction_protocol')!=1 or type(interaction.get('interaction_serial'))is not int
        or not isinstance(lease.get('id'),str)or not lease['id']
        or lease.get('kind')!='materials'or lease.get('job_session')!=task
        or lease.get('world_session')!=state.get('world_session')
        or lease.get('revision')!=state.get('control_revision')
        or request.get('world_session')!=state.get('world_session')
        or request.get('expected_revision')!=state.get('control_revision')
        or not isinstance(request.get('id'),str)or not request['id']):return None
    return dict(request_id=request['id'],world=state['world_session'],task=task,revision=state['control_revision'],
        lease_id=lease.get('id'),serial=interaction['interaction_serial'],pos=request.get('pos'),
        hand=request['expected_hand'],block_state=request['expected_state'],screen=pair[0],menu_type=pair[1],acknowledged=False)

def published(client,ticket):
    if ticket is not None:
        client._owned_added_opening=ticket;client._owned_added_bound=None

def acknowledge(client,request,result,current):
    if request.get('op')=='close_menu'and result.get('phase')=='done':
        client._owned_added_opening=None;client._owned_added_bound=None;return
    t=getattr(client,'_owned_added_opening',None)
    if not t or t['request_id']!=request.get('id'):return
    native=result.get('last_block_interaction')or{};g=current.get('game_interaction')or{}
    if (request.get('op')=='interact'and result.get('id')==t['request_id']and result.get('phase')=='done'
        and result.get('world_session')==t['world']and current.get('world_session')==t['world']
        and current.get('control_revision')==t['revision']and current.get('manual_movement')is False
        and g.get('interaction_serial')==t['serial']and native.get('protocol')==1
        and native.get('request_id')==t['request_id']and native.get('world_session')==t['world']
        and native.get('pos')==t['pos']and native.get('state_before')==t['block_state']
        and native.get('hand')==t['hand']and native.get('method')=='useItemOn'
        and native.get('result_returned')is True and native.get('consumed_action')is True
        and type(current.get('time'))is int):
        t['acknowledged']=True;t['ack_time']=current['time']

def late_allowed(client,state):
    """Correlate a server GUI to our completed native use and unchanged human-input serial.

    Native material_owned is deliberately never rewritten. This closes the
    fixed-eight-tick opening race without accepting arbitrary user screens.
    """
    t=getattr(client,'_owned_added_opening',None);bound=getattr(client,'_owned_added_bound',None)
    if not t or not t.get('acknowledged'):return False
    menu=state.get('menu')or{};lease=state.get('supervision_lease')or{};g=state.get('game_interaction')or{}
    if (state.get('connected')is not True or state.get('manual_movement')is not False
        or state.get('world_session')!=t['world']or state.get('control_revision')!=t['revision']
        or state.get('screen')!=t['screen']or menu.get('type')!=t['menu_type']
        or type(menu.get('id'))is not int or menu['id']<=0
        or g.get('interaction_serial')!=t['serial']or lease.get('kind')!='materials'
        or lease.get('job_session')!=t['task']or lease.get('world_session')!=t['world']
        or lease.get('revision')!=t['revision']or lease.get('id')!=t['lease_id']):return False
    if bound is not None:return bound==menu['id']
    age=state.get('time',-1)-t['ack_time']
    native=state.get('last_block_interaction')or{}
    if not 0<=age<=20000 or native.get('request_id')!=t['request_id']or native.get('pos')!=t['pos']:return False
    client._owned_added_bound=menu['id']
    out=getattr(client,'out',None)
    if out is not None:
        from kit_runtime.journal import write_json
        write_json(out/('late-owned-menu-'+t['request_id']+'.json'),dict(t,menu_id=menu['id'],native_material_owned=menu.get('material_owned'),proof='exact_native_use_and_unchanged_human_input_serial'))
    return True
