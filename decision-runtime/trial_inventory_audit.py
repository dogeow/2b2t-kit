"""Independent physical review of one retired, unconfirmed inventory pickup.

A new server/client probe proves current stock only. It cannot add a missing
historical ACK, classify the old click as no-send, or authorize its replay.
"""
import hashlib
import json
import os
import copy
from types import SimpleNamespace
from pathlib import Path
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from singleplayer_trial_bridge import Paused

SCOPE=('world_id','trial_id','run_id','world_session','dimension')
SHA=re.compile(r'[0-9a-f]{64}\Z')
MAX_INVENTORY_HISTORY=4


def verified_retirement(exit_state,quit_reply,disconnected,original,old_jvm_pid):
    """Accept observed normal exit, or saved native quit plus actual process stop.

    The second contract deliberately retains an unobserved exit code. Neither
    contract proves the historical inventory click was applied or rejected.
    """
    if type(exit_state.get('exit_code')) is int and exit_state['exit_code']==0 and exit_state.get('exit_type')=='NORMAL':
        return True
    if (exit_state.get('source')!='verified_native_saved_quit_and_terminated_process'
            or 'exit_code' not in exit_state or exit_state['exit_code'] is not None
            or exit_state.get('exit_type')!='unobserved'):
        return False
    request=record(exit_state.get('quit_request'),131072)
    stopped=record(exit_state.get('launcher_stopped'),131072)
    ref=stopped.get('log_excerpt',{})
    if file_hash(ref.get('path',''))!=ref.get('sha256'):return False
    text=Path(ref['path']).read_text()
    if (request.get('protocol')!=1 or request.get('command')!='quit_game'
            or request.get('id')!=quit_reply.get('id') or quit_reply.get('protocol')!=1
            or quit_reply.get('phase')!='done' or type(request.get('expires_at')) is not int
            or stopped.get('source')!='hmcl_process_stopped_event_excerpt'
            or stopped.get('event')!='ProcessStoppedEvent' or 'ProcessStoppedEvent' not in text
            or stopped.get('old_jvm_pid')!=old_jvm_pid
            or any(stopped.get(key)!=original.get(key) for key in ('world_id','world_session','run_id'))
            or type(stopped.get('stopped_at')) is not int or type(disconnected.get('time')) is not int
            or not disconnected['time']<=request['expires_at']
            # HMCL disk stamps have second precision, so their represented
            # second may contain the later millisecond-native quit receipt.
            or not max(disconnected['time'],request['expires_at']-15000)<=stopped['stopped_at']+999
            or not stopped['stopped_at']<=request['expires_at']+30000):
        return False
    clock=datetime.fromtimestamp(stopped['stopped_at']/1000,ZoneInfo('Asia/Taipei')).strftime('%H:%M:%S')
    return clock in text


def file_hash(path):
    path=Path(path)
    if (not path.is_absolute() or any(part.is_symlink() for part in (path,*path.parents))
            or not path.is_file()):
        raise Paused('Inventory review evidence must be an absolute unlinked file')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda:stream.read(131072),b''):digest.update(part)
    return digest.hexdigest()


def record(reference,limit=8_000_000):
    if (not isinstance(reference,dict) or not isinstance(reference.get('path'),str)
            or not isinstance(reference.get('sha256'),str) or not SHA.fullmatch(reference['sha256'])
            or file_hash(reference['path'])!=reference['sha256']):
        raise Paused('Inventory review evidence hash changed')
    path=Path(reference['path'])
    if path.stat().st_size>limit:raise Paused('Inventory review evidence is oversized')
    value=json.loads(path.read_text())
    if not isinstance(value,dict):raise Paused('Invalid inventory review record')
    return value


def quantities(rows):
    if not isinstance(rows,list) or len(rows)!=43:
        raise Paused('Historical inventory review requires all 43 player slots')
    slots={};totals={}
    for row in rows:
        if (not isinstance(row,dict) or type(row.get('slot')) is not int or not 0<=row['slot']<43
                or row['slot'] in slots or not isinstance(row.get('item'),str)
                or not row['item'].startswith('minecraft:') or type(row.get('count')) is not int
                or not 0<=row['count']<=999 or (row['item']=='minecraft:air')!=(row['count']==0)):
            raise Paused('Inventory stock observation is partial or malformed')
        slots[row['slot']]=row
        if row['count']:totals[row['item']]=totals.get(row['item'],0)+row['count']
    if set(slots)!=set(range(43)):raise Paused('Inventory slot coverage is incomplete')
    return slots,totals


def empty_menu(menu):
    if (not isinstance(menu,dict) or menu.get('id')!=0 or menu.get('type')!='InventoryMenu'
            or menu.get('cursor',{}).get('item')!='minecraft:air'
            or type(menu.get('cursor',{}).get('count')) is not int or menu['cursor']['count']!=0):
        return False
    slots=menu.get('slots')
    if not isinstance(slots,list) or len(slots)<5:return False
    return all(isinstance(slots[i],dict) and slots[i].get('slot')==i
        and slots[i].get('item')=='minecraft:air' and type(slots[i].get('count')) is int
        and slots[i]['count']==0 for i in range(5))


def exact_side(side):
    menu=side.get('menu',side)
    quantities(side.get('inventory'))
    def stack(row):
        if (not isinstance(row,dict) or not all(key in row for key in ('item','count','max_stack','stack_data'))
                or type(row['count']) is not int or type(row['max_stack']) is not int):
            raise Paused('Current probe lacks full stack codec observations')
        return {key:row[key] for key in ('item','count','max_stack','stack_data')}
    slots=menu.get('slots',[])
    if (not isinstance(slots,list) or len(slots)!=46
            or any(not isinstance(row,dict) or row.get('slot')!=i for i,row in enumerate(slots))):
        raise Paused('Current probe menu slot coverage is incomplete')
    if type(menu.get('state_id')) is not int or menu['state_id']<0:
        raise Paused('Current probe menu state identifier is invalid')
    return {'inventory':[(row['slot'],stack(row)) for row in sorted(side['inventory'],key=lambda row:row['slot'])],
            'cursor':stack(menu.get('cursor')),'slots':[(i,stack(row)) for i,row in enumerate(slots)],
            'menu_id':menu.get('id'),'menu_type':menu.get('type'),
            'quickcraft_status':menu.get('quickcraft_status')}


def historical_manifest(value):
    """Only the actual menu-0 one-log pickup case has an admission contract."""
    if (not isinstance(value,dict) or value.get('schema')!=1
            or value.get('kind')!='retired_inventory_pickup_unknown'
            or value.get('historical_effects_unresolved') is not True
            or value.get('old_action_replayed') is not False or value.get('old_action_completed') is not False):
        raise Paused('Historical inventory intent has no supported review contract')
    original=record(value.get('original_intent'),131072)
    failed=record(value.get('failed_client'))
    if (original.get('op')!='slot_click' or original.get('menu_id')!=0 or original.get('slot')!=11
            or original.get('kind')!='pickup' or original.get('button')!=0
            or original.get('expected_item')!='minecraft:dark_oak_log' or original.get('expected_count')!=1
            or original.get('expected_cursor')!='minecraft:air' or original.get('expected_cursor_count')!=0
            or original.get('server')!='singleplayer' or original.get('local_trial') is not True
            or original.get('local_survival') is not True or type(original.get('expected_revision')) is not int
            or not isinstance(original.get('id'),str) or not re.fullmatch(r'trial-[A-Za-z0-9_-]{1,74}',original['id'])
            or failed.get('id')!=original['id']
            or (failed.get('last_request') not in (None,original['id']) if original.get('inventory_confirm') is True
                else failed.get('last_request')!=original['id'])
            or failed.get('control_revision')!=original['expected_revision']
            or any((failed.get('trial_identity',{}) if key in ('trial_id','run_id') else failed).get(key)
                   !=original.get(key) for key in SCOPE) or not empty_menu(failed.get('menu'))):
        raise Paused('Unsupported or mismatched historical pickup; do not replay it')
    if original.get('inventory_confirm') is True:
        pending=record(value.get('sdk_pending'))
        native=record(value.get('native_unknown_reply'))
        receipt=native.get('inventory_click_receipt',{})
        if (pending.get('protocol')!=1 or pending.get('request_id')!=original['id']
                or pending.get('envelope')!=original
                or pending.get('outcome')!='sent_or_unknown_until_native_and_sdk_confirmation'
                or any(pending.get('arguments',{}).get(key)!=original.get(key) for key in
                    ('menu_id','slot','kind','button','expected_item','expected_count','expected_cursor','expected_cursor_count','inventory_confirm'))
                or native.get('id')!=original['id'] or native.get('op')!='slot_click'
                or native.get('phase')!='waiting' or native.get('outcome_pending') is not True
                or native.get('kit_version')!='2026.10.7.8'
                or native.get('control_revision')!=original['expected_revision']
                or any((native.get('trial_identity',{}) if key in ('trial_id','run_id') else native).get(key)
                    !=original.get(key) for key in SCOPE)
                or receipt.get('protocol')!=1 or receipt.get('request_id')!=original['id']
                or receipt.get('classification')!='unknown' or receipt.get('server_processed') is not True
                or type(receipt.get('native_sequence')) is not int or receipt['native_sequence']!=1
                or receipt.get('correlation_ambiguous') is not True or receipt.get('scope_current') is not True
                or receipt.get('world_session')!=original['world_session']
                or receipt.get('control_revision')!=original['expected_revision']
                or receipt.get('slot')!=11 or receipt.get('button')!=0 or receipt.get('kind')!='pickup'
                or failed.get('op')!='slot_click' or failed.get('phase')!='waiting'
                or failed.get('outcome_pending') is not True):
            raise Paused('Confirmed-protocol historical click must retain its exact ambiguous native outcome')
        if exact_side(receipt.get('server',{}))!=exact_side(receipt.get('client',{})):
            raise Paused('Retired ambiguous click final server/client stock disagrees')
        if quantities(pending.get('before',{}).get('inventory'))[1]!=quantities(failed.get('inventory'))[1]:
            raise Paused('Retired SDK stage stock changed; separate audit required')
    elif (failed.get('op')!='settle' or failed.get('phase')!='done'
            or failed.get('detail')!='server state available'):
        raise Paused('Legacy timer-only inventory observation contract differs')
    inventory,totals=quantities(failed.get('inventory'))
    if (inventory[11]['item']!=original['expected_item'] or inventory[11]['count']!=1
            or len(failed['menu']['slots'])<=11 or failed['menu']['slots'][11].get('slot')!=11
            or failed['menu']['slots'][11].get('item')!=original['expected_item']
            or failed['menu']['slots'][11].get('count')!=1
            or totals.get('minecraft:dirt')!=23):
        raise Paused('Failed pickup stock lacks the actual retained log and 23 dirt')
    return original,failed


def historical_pending(output,registry,state):
    """Discover preserved inventory intents after a genuinely new trial Start."""
    rows=[];frozen={}
    root=Path(output)/'legacy-inventory-intents'
    if root.is_symlink():raise Paused('Historical inventory archive is linked')
    for path in sorted(root.glob('*/manifest.json')):
        manifest=record({'path':str(path.resolve()),'sha256':file_hash(path.resolve())})
        original,failed=historical_manifest(manifest)
        if original.get('world_id')!=registry['world_id'] or original.get('trial_id')!=registry['trial_id']:
            continue
        if original['run_id']==registry['run_id'] or original['world_session']==state['world_session']:
            raise Paused('Current connection inventory unknown cannot become historical review')
        rows.append({'id':original['id'],'op':'slot_click',**{key:original[key] for key in SCOPE},
            'arguments':{key:original[key] for key in ('menu_id','slot','kind','button','expected_item',
                'expected_count','expected_cursor','expected_cursor_count')},
            'inventory_manifest':str(path.resolve())})
        for reference in (manifest['original_intent'],manifest['failed_client']):
            frozen[Path(reference['path'])]=reference['sha256']
        for name in ('sdk_pending','native_unknown_reply'):
            if name in manifest:
                reference=manifest[name];record(reference)
                frozen[Path(reference['path'])]=reference['sha256']
        frozen[path.resolve()]=file_hash(path.resolve())
    if len(rows)>MAX_INVENTORY_HISTORY:raise Paused('Inventory history review limit exceeded')
    return rows,frozen


def archive_failed_pickup(game,failed_client,*,old_worker_pid,old_jvm_pid,
                          sdk_pending_path=None,native_unknown_reply_path=None):
    """Copy the original envelope and failed client frame without gameplay."""
    game=Path(game).resolve();output=game/'config/twob2tkit/singleplayer-trial/worker'
    mailbox=output.parent.parent/'automation/request.json'
    content=mailbox.read_bytes();original=json.loads(content)
    rid=original.get('id')
    if not isinstance(rid,str) or not re.fullmatch(r'trial-[A-Za-z0-9_-]{1,74}',rid):
        raise Paused('Original inventory request identity is invalid')
    folder=output/'legacy-inventory-intents'/rid
    archive=output/'legacy-material-intents'/(rid+'.request.json')
    if any(path.is_symlink() for path in (folder,*folder.parents,archive,archive.parent)):
        raise Paused('Inventory archive must not contain symlinks')
    folder.mkdir(parents=True,exist_ok=True);archive.parent.mkdir(parents=True,exist_ok=True)
    if archive.exists() and archive.read_bytes()!=content:
        raise Paused('Different original inventory envelope exists; preserve it')
    if not archive.exists():archive.write_bytes(content)
    failure=folder/'failed-client.json'
    encoded=(json.dumps(failed_client,ensure_ascii=False,allow_nan=False)+'\n').encode()
    if failure.exists() and failure.read_bytes()!=encoded:
        raise Paused('Different failed client frame exists; preserve it')
    if not failure.exists():failure.write_bytes(encoded)
    value={'schema':1,'kind':'retired_inventory_pickup_unknown','historical_effects_unresolved':True,
        'old_action_completed':False,'old_action_replayed':False,'old_worker_pid':old_worker_pid,
        'old_jvm_pid':old_jvm_pid,'original_intent':{'path':str(archive),'sha256':file_hash(archive)},
        'failed_client':{'path':str(failure),'sha256':file_hash(failure)}}
    if original.get('inventory_confirm') is True:
        if sdk_pending_path is None or native_unknown_reply_path is None:
            raise Paused('Confirmed-protocol unknown requires its immutable SDK intent and native reply')
        for name,path in (('sdk_pending',sdk_pending_path),('native_unknown_reply',native_unknown_reply_path)):
            path=Path(path).resolve()
            value[name]={'path':str(path),'sha256':file_hash(path)}
    historical_manifest(value)
    target=folder/'manifest.json'
    if target.exists() and json.loads(target.read_text())!=value:
        raise Paused('Different inventory manifest exists; preserve it')
    if not target.exists():target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return {'path':str(target),'sha256':file_hash(target)}


def _validate_inventory_review(worker,reference,state,pid_alive,*,require_probe=True):
    review=record(reference)
    if (review.get('schema')!=1 or review.get('kind')!='operator_retired_inventory_review'
            or review.get('decision')!='fresh_inventory_replan_allowed'
            or review.get('historical_effects_unresolved') is not True
            or review.get('old_action_completed') is not False or review.get('old_action_replayed') is not False):
        raise Paused('Inventory review cannot claim historical completion or no-send')
    manifest=record(review.get('manifest'))
    original,failed=historical_manifest(manifest)
    matches=[row for row in worker.legacy_pending if row.get('id')==original['id'] and row.get('op')=='slot_click']
    if (len(matches)!=1 or original['world_id']!=worker.registry['world_id']
            or original['trial_id']!=worker.registry['trial_id'] or original['run_id']==worker.run_id
            or original['world_session']==state['world_session']):
        raise Paused('Inventory review does not bind the separately retired controller')
    refs=review.get('artifacts',{})
    if set(refs)!={'before_save','after_save','normal_quit','normal_exit'}:
        raise Paused('Inventory review lacks actual save, quit and new authoritative probe')
    values={key:record(ref) for key,ref in refs.items()}
    saved,disconnected,quit_reply,exit_state=(values[key] for key in
        ('before_save','after_save','normal_quit','normal_exit'))
    if (saved.get('world_id')!=original['world_id'] or saved.get('world_session')!=original['world_session']
            or any(saved.get(key) is not False for key in ('chopping','navigating','borer_active','printing'))
            or saved.get('trial_identity',{}).get('process_alive') is not False
            or disconnected.get('connected') is not False or quit_reply.get('phase')!='done'
            or disconnected.get('trial_identity',{}).get('world_id')!=original['world_id']
            or quit_reply.get('trial_identity',{}).get('world_id')!=original['world_id']
            or saved.get('trial_identity',{}).get('trial_id')!=original['trial_id']
            or not verified_retirement(exit_state,quit_reply,disconnected,original,review.get('old_jvm_pid'))
            or exit_state.get('old_jvm_alive_now') is not False
            or type(review.get('old_worker_pid')) is not int or type(review.get('old_jvm_pid')) is not int
            or review['old_worker_pid']<=1 or review['old_jvm_pid']<=1
            or review['old_worker_pid']==os.getpid() or review['old_jvm_pid']==worker.parent_pid
            or review['old_worker_pid']!=manifest.get('old_worker_pid')
            or review['old_jvm_pid']!=manifest.get('old_jvm_pid')
            or exit_state.get('old_jvm_pid')!=review['old_jvm_pid']
            or exit_state.get('world_id')!=original['world_id']
            or exit_state.get('world_session')!=original['world_session']
            or exit_state.get('run_id')!=original['run_id']
            or pid_alive(review['old_worker_pid']) or pid_alive(review['old_jvm_pid'])):
        raise Paused('Historical inventory controller did not normally save and end')
    log_ref=exit_state.get('save_log',{})
    if (file_hash(log_ref.get('path',''))!=log_ref.get('sha256')
            or not all(phrase in Path(log_ref['path']).read_text() for phrase in
                ('Saving players','Saving worlds','(world): All chunks are saved','(DIM-1): All chunks are saved',
                 '(DIM1): All chunks are saved','All dimensions are saved'))):
        raise Paused('Inventory retirement lacks complete real saved-world evidence')
    if quantities(saved.get('inventory'))[1]!=quantities(failed['inventory'])[1]:
        raise Paused('Stock changed before normal retirement; preserve inventory unknown')
    if not require_probe:
        return {'request_id':original['id'],'request':original,'manifest':manifest,'review':review,
                'historical_effects_unresolved':True,'old_action_completed':False,'old_action_replayed':False}
    probe_result=getattr(worker,'inventory_review_probe',None)
    probe_request=getattr(worker,'inventory_review_probe_request',None)
    if not isinstance(probe_result,dict) or not isinstance(probe_request,dict):
        raise Paused('A new worker-owned inventory probe is required')
    probe=probe_result.get('inventory_probe',{})
    if (probe_result.get('phase')!='done' or probe_result.get('op')!='inventory_probe'
            or probe_result.get('outcome_pending') is not False or probe.get('protocol')!=1
            or probe.get('scope_current') is not True or probe.get('server_observed') is not True
            or probe.get('audit_scope')!='current_state_only_not_historical_dispatch'
            or probe.get('world_session')!=state['world_session']
            or probe_result.get('id')!=probe_request.get('id') or probe.get('request_id')!=probe_request.get('id')
            or probe_request.get('op')!='inventory_probe'
            or type(probe_request.get('expires_at')) is not int
            or not probe_result.get('time',0)<=probe_request['expires_at']<=probe_result.get('time',0)+15000
            or probe_request.get('expected_revision')!=state['control_revision']
            or probe.get('control_revision')!=state['control_revision']
            or any(probe_request.get(key)!=value for key,value in {
                'world_id':state['world_id'],'world_session':state['world_session'],'dimension':state['dimension'],
                'server':'singleplayer','run_id':worker.run_id,'trial_id':worker.registry['trial_id']}.items())
            or type(probe_result.get('time')) is not int or not 0<=state['time']-probe_result['time']<=3000):
        raise Paused('New inventory probe lacks current authoritative two-sided scope')
    old_totals=quantities(failed['inventory'])[1]
    if exact_side(probe.get('client',{}))!=exact_side(probe.get('server',{})):
        raise Paused('Current server/client complete stack data differs')
    for name in ('client','server'):
        side=probe.get(name,{})
        menu=side.get('menu',side)
        slots,totals=quantities(side.get('inventory'))
        if (side.get('world_id')!=state['world_id'] or side.get('dimension')!=state['dimension']
                or side.get('player_uuid')!=failed.get('player_uuid')
                or not empty_menu(menu) or menu.get('quickcraft_status')!=0
                or type(side.get('observed_at')) is not int or not 0<=state['time']-side['observed_at']<=3000
                or totals!=old_totals or slots[11]['item']!=original['expected_item'] or slots[11]['count']!=1
                or totals.get('minecraft:dirt')!=23):
            raise Paused('Current server/client cursor, grid or complete stock is inconsistent')
    if quantities(state.get('inventory'))[1]!=old_totals or not empty_menu(state.get('menu')):
        raise Paused('Current stock no longer matches the reviewed server probe')
    return {'request_id':original['id'],'review':review,'historical_effects_unresolved':True,
            'old_action_completed':False,'old_action_replayed':False}


def validate_inventory_review(worker,reference,state,pid_alive):
    try:return _validate_inventory_review(worker,reference,state,pid_alive)
    except Paused:raise
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        raise Paused('Historical inventory review is incomplete or malformed') from None


def process_alive(pid):
    if type(pid) is not int or pid<=1:return True
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except (PermissionError,OSError):return True


def retired_inventory_metadata(output,registry,state):
    """References for SDK-backed retired records, not a new material grant."""
    result=[]
    for path in sorted((Path(output)/'legacy-inventory-intents').glob('*/manifest.json')):
        manifest=record({'path':str(path.resolve()),'sha256':file_hash(path.resolve())})
        original,failed=historical_manifest(manifest)
        if not manifest.get('sdk_pending') or original['world_id']!=registry['world_id'] or original['trial_id']!=registry['trial_id']:
            continue
        review=path.parent/'retirement-review.json'
        result.append({'manifest':{'path':str(path.resolve()),'sha256':file_hash(path.resolve())},
            'retirement_review':{'path':str(review.resolve()),'sha256':file_hash(review.resolve())}})
    if len(result)>MAX_INVENTORY_HISTORY:raise Paused('Retired inventory admission limit exceeded')
    return result


def validate_retired_inventory(metadata,registry,state,parent_pid,pid_alive=process_alive):
    """Bridge defense admission: exact retired SDK intent and actual saved quit.

    It intentionally omits fresh inventory-plan admission. The constructor
    retains the pending record; only the independent new probe review may
    authorize fresh material intentions later.
    """
    try:
        manifest=record(metadata.get('manifest'));original,failed=historical_manifest(manifest)
        if not manifest.get('sdk_pending'):raise Paused('Retired SDK admission requires a durable original intent')
        reference=metadata.get('retirement_review');review=record(reference)
        if review.get('manifest')!=metadata.get('manifest'):
            raise Paused('Retirement review differs from the exact SDK manifest')
        worker=SimpleNamespace(registry=registry,run_id=registry['run_id'],parent_pid=parent_pid,
            legacy_pending=[{'id':original['id'],'op':'slot_click'}])
        checked=_validate_inventory_review(worker,reference,state,pid_alive,require_probe=False)
        refs=[metadata['manifest'],reference,manifest['original_intent'],manifest['failed_client'],
              manifest['sdk_pending'],manifest['native_unknown_reply'],*review['artifacts'].values()]
        exit_state=record(review['artifacts']['normal_exit'])
        refs.append(exit_state['save_log'])
        if exit_state.get('source')=='verified_native_saved_quit_and_terminated_process':
            refs.extend([exit_state['quit_request'],exit_state['launcher_stopped']])
            refs.append(record(exit_state['launcher_stopped'])['log_excerpt'])
        frozen={}
        for ref in refs:
            if file_hash(ref['path'])!=ref['sha256']:raise Paused('Retired SDK evidence changed')
            frozen[str(Path(ref['path']))]=ref['sha256']
        return {'request':original,'sdk_pending':record(manifest['sdk_pending']),
                'frozen':frozen,'metadata':metadata,'historical_effects_unresolved':True,
                'old_action_completed':False,'old_action_replayed':False}
    except Paused:raise
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        raise Paused('Retired SDK inventory admission is incomplete') from None


def validate_inventory_reviews(worker,reference,state,pid_alive):
    """Every retired inventory case must have its own independent retirement."""
    root=record(reference)
    references=(root.get('reviews') if root.get('kind')=='operator_retired_inventory_reviews' else [reference])
    if (not isinstance(references,list) or not 1<=len(references)<=MAX_INVENTORY_HISTORY):
        raise Paused('Historical inventory review count is invalid')
    values=[validate_inventory_review(worker,ref,state,pid_alive) for ref in references]
    ids=[value['request_id'] for value in values]
    expected=[row['id'] for row in worker.legacy_pending if row.get('op')=='slot_click']
    if len(set(ids))!=len(ids) or set(ids)!=set(expected):
        raise Paused('Each historical inventory intent needs exactly one matching physical review')
    return ids
