"""Worker-owned evidence for the host's local settled item selection.

select_item becomes op=settle on .6/.7 and has no durable host reply. These
records copy actual SDK/native frames; they are not block mutation ACKs.
"""
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

from decisions import status
from singleplayer_trial_bridge import validate_registry, validate_scope

CONTRACT = 'host_settle_select_item_v1'
SOURCE = 'sdk_native_selector_frame_and_fresh_current_witness'
HOSTS = {'2026.10.7.6', '2026.10.7.7'}
SCOPE = ('world_id', 'trial_id', 'run_id', 'world_session', 'dimension')


def request_fingerprint(request):
    return hashlib.sha256(json.dumps(request,sort_keys=True,separators=(',',':'),
        ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _held_fingerprint(frame):
    selected=frame.get('selected_slot');menu=frame.get('menu',{})
    if type(selected) is not int or not 0<=selected<9:
        return None
    rows=frame.get('inventory',[]);slots=menu.get('slots',[])
    if not isinstance(rows,list) or not isinstance(slots,list):
        return None
    inventory={row.get('slot'):row for row in rows if isinstance(row,dict)}
    menu_slots={row.get('slot'):row for row in slots if isinstance(row,dict)}
    if not set(range(36))<=inventory.keys() or not set(range(46))<=menu_slots.keys():
        return None
    held=frame.get('hand')
    if (not isinstance(held,dict) or type(held.get('count')) is not int or held['count']<=0
            or held.get('item') in (None,'minecraft:air')):
        return None
    without_slot=lambda row:{key:value for key,value in row.items() if key!='slot'}
    if held!=without_slot(inventory[selected]) or held!=without_slot(menu_slots[36+selected]):
        return None
    if any(menu_slots[slot].get('item')!='minecraft:air' or menu_slots[slot].get('count')!=0
           for slot in range(5)):
        return None
    return {'selected_slot':selected,'hand':held}


def _selection_frame(frame,request,*,within_expiry=False):
    try:
        identity=frame.get('trial_identity',{});keys=frame.get('movement_keys',{})
        menu=frame.get('menu',{});cursor=menu.get('cursor',{})
        if (request.get('op')!='select_item' or request.get('local_trial') is not True
                or request.get('local_survival') is not True or request.get('server')!='singleplayer'
                or not isinstance(request.get('id'),str) or not re.fullmatch(r'trial-[A-Za-z0-9_-]{1,74}',request['id'])
                or not isinstance(request.get('item'),str) or not request['item'].startswith('minecraft:')
                or type(request.get('expected_revision')) is not int or type(request.get('expires_at')) is not int
                or frame.get('kit_version') not in HOSTS or frame.get('game_version')!='26.1.2'
                or frame.get('singleplayer_trial_protocol')!=1
                or frame.get('connected') is not True or frame.get('server')!='singleplayer'
                or frame.get('game_mode')!='survival' or frame.get('player_dead') is True or frame.get('health',0)<=0
                or frame.get('manual_movement') is not False or frame.get('screen','')!=''
                or identity.get('registered') is not True or identity.get('process_alive') is not True
                or any((identity if key in ('trial_id','run_id') else frame).get(key)!=request.get(key) for key in SCOPE)
                or identity.get('world_id')!=request.get('world_id')
                or frame.get('id')!=request['id'] or frame.get('last_request')!=request['id']
                or frame.get('op')!='settle' or frame.get('phase')!='done'
                or frame.get('detail')!='server state available' or frame.get('outcome_pending') is True
                or frame.get('control_revision')!=request['expected_revision']
                or type(frame.get('time')) is not int
                or menu.get('id')!=0 or menu.get('type')!='InventoryMenu'
                or cursor.get('item')!='minecraft:air' or cursor.get('count')!=0
                or not {'forward','back','jump','sneak'}<=keys.keys() or any(value is not False for value in keys.values())
                or any(frame.get(key) is not False for key in ('chopping','navigating','printing','borer_active'))
                or frame.get('guard_busy') is not False):
            return False
        if within_expiry and not request['expires_at']-10_000<=frame['time']<=request['expires_at']:
            return False
        held=_held_fingerprint(frame)
        if not held or held['hand']['item']!=request['item']:
            return False
        if 'slot' in request and (type(request['slot']) is not int or not 0<=request['slot']<36
                or held['selected_slot']!=(request['slot'] if request['slot']<9 else 5)):
            return False
        return True
    except (KeyError,TypeError,ValueError,AttributeError):
        return False


def _valid(value):
    try:
        request,result,witness=(value.get(key) for key in ('request','native_result','current_witness'))
        return (value.get('schema')==1 and value.get('source')==SOURCE and value.get('contract')==CONTRACT
            and value.get('confirmation_scope')=='local_settled_selection_not_server_block_ack'
            and value.get('server_block_acknowledged') is False
            and isinstance(value.get('source_proof_sha256'),str)
            and re.fullmatch(r'[0-9a-f]{64}',value['source_proof_sha256']) is not None
            and request_fingerprint(request)==value.get('request_sha256')
            and _selection_frame(result,request,within_expiry=True)
            and _selection_frame(witness,request)
            and witness['time']>=result['time']
            and _held_fingerprint(witness)==_held_fingerprint(result))
    except (KeyError,TypeError,ValueError,AttributeError):
        return False


def capture_select_item_receipt(game,source_proof,*,reader=status,wall_time=time.time):
    """Copy exact observed SDK success and current selector; never send input."""
    game=Path(game).resolve();automation=game/'config/twob2tkit/automation'
    registry=validate_registry(json.loads((automation.parent/'singleplayer-trial/registry.json').read_text()),game)
    mailbox=automation/'request.json';proof=Path(source_proof)
    if mailbox.is_symlink() or not mailbox.is_file() or mailbox.stat().st_size>131072:
        raise RuntimeError('Exact original selection mailbox is unavailable')
    raw_request=mailbox.read_bytes();request=json.loads(raw_request)
    if proof.is_symlink() or not proof.is_file() or proof.stat().st_size>32_000_000:
        raise RuntimeError('Original SDK selector proof is unavailable')
    source_bytes=proof.read_bytes();source=json.loads(source_bytes)
    matches=[row for row in source.get('receipts',[]) if isinstance(row,dict)
             and row.get('id')==request.get('id') and row.get('request_id')==request.get('id')
             and row.get('native') is True]
    if len(matches)!=1 or not _selection_frame(matches[0],request,within_expiry=True):
        raise RuntimeError('No exact native selector frame in its original valid window; keep unknown')
    current=reader(automation)
    validate_scope(current,registry,request.get('world_session'),registry.get('run_id'))
    if (request.get('run_id')!=registry.get('run_id')
            or not 0<=wall_time()-current.get('time',0)/1000<=3
            or not _selection_frame(current,request)
            or _held_fingerprint(current)!=_held_fingerprint(matches[0])
            or mailbox.read_bytes()!=raw_request):
        raise RuntimeError('Fresh current selection no longer matches the original native result')
    value={'schema':1,'source':SOURCE,'contract':CONTRACT,'request':request,
           'request_sha256':request_fingerprint(request),'original_envelope_sha256':hashlib.sha256(raw_request).hexdigest(),
           'native_result':matches[0],'current_witness':current,
           'source_proof':str(proof.resolve()),'source_proof_sha256':hashlib.sha256(source_bytes).hexdigest(),
           'confirmation_scope':'local_settled_selection_not_server_block_ack','server_block_acknowledged':False}
    if not _valid(value):
        raise RuntimeError('Local selector evidence is inconsistent; keep unknown')
    root=automation.parent/'singleplayer-trial/worker/native-selection-receipts'
    if any(path.is_symlink() for path in (root,*root.parents)):
        raise RuntimeError('Selection ledger must not contain symlinks')
    root.mkdir(parents=True,exist_ok=True);path=root/(request['id']+'.json')
    if path.exists():
        prior=json.loads(path.read_text())
        if (path.is_symlink() or not _valid(prior) or prior['request_sha256']!=value['request_sha256']
                or prior['native_result']!=value['native_result'] or prior['source_proof_sha256']!=value['source_proof_sha256']):
            raise RuntimeError('Different selector evidence exists; preserve it')
        return prior
    temporary=path.with_suffix('.'+uuid.uuid4().hex[:8]+'.tmp')
    temporary.write_text(json.dumps(value,allow_nan=False,ensure_ascii=False)+'\n');temporary.replace(path)
    return value


def known_select_item_receipt(game,registry,unresolved,state):
    rid=unresolved.get('id')
    if unresolved.get('op')!='select_item' or not isinstance(rid,str) or not re.fullmatch(r'trial-[A-Za-z0-9_-]{1,74}',rid):
        return None
    path=Path(game).resolve()/'config/twob2tkit/singleplayer-trial/worker/native-selection-receipts'/(rid+'.json')
    try:
        if any(part.is_symlink() for part in (path,*path.parents)) or not path.is_file() or path.stat().st_size>2_000_000:
            return None
        value=json.loads(path.read_text())
        if not _valid(value):return None
        request=value['request']
        if (any(unresolved.get(key)!=request.get(key) for key in SCOPE)
                or unresolved.get('request_sha256')!=value['request_sha256']
                or request['world_id']!=registry['world_id'] or request['trial_id']!=registry['trial_id']):
            return None
        validate_scope(state,registry,request['world_session'],registry['run_id'])
        if (state.get('dimension')!=request['dimension'] or state.get('kit_version')!=value['native_result']['kit_version']
                or state['time']<value['current_witness']['time']
                or state.get('control_revision',-1)<request['expected_revision']):
            return None
        if registry['run_id']==request['run_id'] and (not _selection_frame(state,request)
                or _held_fingerprint(state)!=_held_fingerprint(value['current_witness'])):
            return None
        return value
    except (OSError,KeyError,TypeError,ValueError,RuntimeError):
        return None
