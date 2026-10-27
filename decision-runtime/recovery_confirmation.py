"""One native human-chat acknowledgement. Never call from unattended goal continuation.

The caller must have a direct human instruction for this incident and provide
its reference, quote and recorded timestamp. This module never edits health
locks or invokes the UI button on the human's behalf. The separate connect_once
entry point reserves one incident-bound native recovery connection.
"""
import time
import math
import uuid
from pathlib import Path
from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from safety_interlock import require_assistant_control_allowed,require_unlocked


def connection_request_for(state,address,expected_player,*,user_reference,user_text,hold_time,confirmation_recorded_at,now_ms):
    if (not isinstance(user_reference,str)or not user_reference.strip()or len(user_reference)>256
            or not isinstance(user_text,str)or not user_text.strip()or len(user_text)>512
            or type(hold_time)is not int or hold_time<=0
            or type(confirmation_recorded_at)is not int or not hold_time<=confirmation_recorded_at<=now_ms):
        raise ValueError('Direct human confirmation for this incident is required')
    if (type(state.get('explicit_recovery_connection_protocol'))is not int
            or state['explicit_recovery_connection_protocol']!=1
            or state.get('connected')is not False or state.get('screen')not in('TitleScreen','DisconnectedScreen')
            or state.get('account_name')!=expected_player or state.get('supervision_lease')
            or state.get('pending_scan')is not None or state.get('manual_movement')
            or not(state.get('safety_hold')or{}).get('active')
            or state['safety_hold'].get('time')!=hold_time):
        raise RuntimeError('Recovery connection requires this incident and idle title account')
    return {'id':'recovery-connect-'+uuid.uuid4().hex[:12],'op':'connect_server','address':address,
            'expected_player':expected_player,'world_session':state['world_session'],
            'expected_revision':state['control_revision'],'expires_at':now_ms+12000,'recovery_only':True,
            'authorization_channel':'human_chat','confirmed_by_user':True,'authorization_reference':user_reference,
            'authorization_text':user_text,'confirmed_hold_time':hold_time,'confirmation_recorded_at':confirmation_recorded_at}


def connect_once(root,out,address,expected_player,**grant):
    import json
    from game_connection_cli import pending_screen,connection_screen_seen
    root,out=Path(root),Path(out);require_assistant_control_allowed(root);state=read_fresh(root)
    request=connection_request_for(state,address,expected_player,now_ms=int(time.time()*1000),**grant)
    mailbox=root/'request.json'
    if mailbox.exists()and json.loads(mailbox.read_text()).get('id')!=state.get('last_request'):
        raise RuntimeError('Foreign request pending; no connection published')
    out.mkdir(parents=True,exist_ok=False);write_json(out/'intent.json',request);write_json(root/'request.json',request)
    reply=root/('reply-'+request['id']+'.json');deadline=time.monotonic()+60
    while not reply.exists():
        if time.monotonic()>deadline:raise RuntimeError('Connection receipt unknown; never replay')
        time.sleep(.1)
    receipt=json.loads(reply.read_text());write_json(out/'native-reply.json',receipt)
    if receipt.get('id')!=request['id']or receipt.get('phase')!='done':raise RuntimeError(receipt.get('detail','Recovery connection rejected'))
    started=time.monotonic();seen=False
    while time.monotonic()<deadline:
        current=read_fresh(root);write_json(out/'latest.json',current)
        if current.get('connected')is True:
            if current.get('player_name')!=expected_player or current.get('server','').lower().removesuffix(':25565')!=address.lower().removesuffix(':25565'):
                raise RuntimeError('Actual connected identity differs; no gameplay')
            write_json(out/'connected.json',current);return current
        if not pending_screen(current.get('screen'),seen,time.monotonic()-started):raise RuntimeError('Recovery connection failed; no retry')
        seen=connection_screen_seen(current.get('screen'),seen);time.sleep(.2)
    raise RuntimeError('Connection outcome unconfirmed; no retry')


def request_for(state,*,user_reference,user_text,hold_time,confirmation_recorded_at,now_ms):
    if (not isinstance(user_reference,str)or not user_reference.strip()or len(user_reference)>256
            or not isinstance(user_text,str)or not user_text.strip()or len(user_text)>512
            or type(hold_time)is not int or hold_time<=0
            or type(confirmation_recorded_at)is not int or not hold_time<=confirmation_recorded_at<=now_ms):
        raise ValueError('A direct human instruction recorded for this health incident is required')
    health=state.get('health')
    if (type(state.get('explicit_recovery_confirmation_protocol'))is not int or state.get('explicit_recovery_confirmation_protocol')!=1 or state.get('connected')is not True
            or type(health)not in(int,float)or not math.isfinite(health)or health<18 or state.get('food',0)<8 or state.get('manual_movement')
            or state.get('screen')not in('','PauseScreen','InventoryScreen')or state.get('supervision_lease')
            or state.get('pending_scan')is not None or not(state.get('safety_hold')or{}).get('active')):
        raise RuntimeError('Native recovery confirmation is unavailable or player has not recovered safely')
    menu=state.get('menu')or{};slots=menu.get('slots')or[]
    if(menu.get('type')!='InventoryMenu'or menu.get('cursor',{}).get('count')!=0
            or len(slots)<5 or any(slots[i].get('count')!=0 for i in range(5))):
        raise RuntimeError('Recovery confirmation preserves carried items and crafting drafts')
    return {'id':'human-recovery-'+uuid.uuid4().hex[:12],'op':'confirm_recovery',
            'server':state['server'],'dimension':state['dimension'],'site':state['pos'],
            'world_session':state['world_session'],'expected_revision':state['control_revision'],
            'expires_at':now_ms+12000,'authorization_channel':'human_chat','confirmed_by_user':True,
            'authorization_reference':user_reference,'authorization_text':user_text,
            'confirmed_hold_time':hold_time,'confirmation_recorded_at':confirmation_recorded_at}


def confirm(root,out,*,user_reference,user_text,hold_time,confirmation_recorded_at):
    root,out=Path(root),Path(out);require_assistant_control_allowed(root)
    state=read_fresh(root);request=request_for(state,user_reference=user_reference,user_text=user_text,
        hold_time=hold_time,confirmation_recorded_at=confirmation_recorded_at,now_ms=int(time.time()*1000))
    import json
    mailbox=root/'request.json'
    if mailbox.exists() and json.loads(mailbox.read_text()).get('id')!=state.get('last_request'):
        raise RuntimeError('Another native request remains pending; no confirmation published')
    out.mkdir(parents=True,exist_ok=False);write_json(out/'human-confirmation-intent.json',request)
    # No safety-file mutation; the native handler repeats all live checks and writes its own acknowledgement.
    write_json(root/'request.json',request);reply=root/('reply-'+request['id']+'.json');deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        if reply.exists():
            result=json.loads(reply.read_text());write_json(out/'native-reply.json',result)
            if result.get('id')!=request['id']or result.get('phase')!='done':
                raise RuntimeError(result.get('detail','Native confirmation rejected; no automatic retry'))
            after=result;require_unlocked(root,after)
            if after.get('world_session')!=state['world_session']or after.get('control_revision')!=state['control_revision']+1:
                raise RuntimeError('Native recovery scope changed; retain original receipt without replay')
            if not after.get('guard_armed')or not after.get('guard_pve_only'):
                raise RuntimeError('Native recovery defense unproved')
            write_json(out/'after.json',after);return after
        time.sleep(.1)
    raise RuntimeError('Original recovery request unconfirmed; no replay or backend unlock')
