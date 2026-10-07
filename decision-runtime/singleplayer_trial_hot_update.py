"""Replace only a paused Kit Python worker; keep the entered world and JVM.

Lifecycle requests go through the existing exact-world native API. Source is
verified before pausing and is installed only after the old worker has exited.
The trial directory, experience database and journals are never replaced.
"""
import argparse
import ast
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import uuid

from decisions import status
from singleplayer_trial_cli import call
from singleplayer_trial_bridge import (MUTATING_OPS, confirmed_mining_not_sent, confirmed_interaction_not_sent,
                                      canonical_save, validate_registry, validate_scope,
                                      native_inventory_click_proof, guard_pre_dispatch_refusal)
from survival_world import World, block_id, distance, shelter
from trial_native_chop import known_chop_receipt
from trial_selection_receipts import known_select_item_receipt, known_guard_receipt, request_fingerprint

SCHEMA = 1
REQUIRED = {'singleplayer_trial.py', 'singleplayer_trial_bridge.py',
            'singleplayer_experience.py', 'singleplayer_trial_cli.py',
            'singleplayer_trial_capabilities.py', 'singleplayer_trial_hot_update.py',
            'trial_surface_recovery.py', 'survival_cooking.py', 'trial_safety_preparation.py', 'trial_safety_routing.py',
            'trial_native_chop.py', 'trial_selection_receipts.py', 'trial_station_access.py',
            'survival_mining_access.py', 'trial_material_rebaseline.py', 'trial_inventory_audit.py',
            'trial_placement_access.py', 'trial_shelter_access.py', 'trial_material_handoff.py'}
ENVELOPE_KEYS = {'id','op','server','dimension','site','world_session','world_id','trial_id','run_id',
                 'local_trial','local_survival','background_ok','expected_revision','expires_at'}
HOLD_METADATA = ('reason', 'time', 'health', 'escape_result', 'rise')


def _file_digest(path):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError('Legacy evidence is missing or linked; preserve it')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(131072), b''):
            digest.update(part)
    return digest.hexdigest()


def _json_record(path, maximum=2_000_000):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise RuntimeError('Invalid legacy isolation record; preserve it')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError('Invalid legacy isolation record; preserve it')
    return value


def _worker_pid_matches(pid, game):
    if type(pid) is not int or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        result = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True,
                                text=True, timeout=3, check=True)
        args = shlex.split(result.stdout.strip())
        script = str(game / 'config/twob2tkit/material-worker/singleplayer_trial.py')
        return (script in args and '--game' in args
                and Path(args[args.index('--game') + 1]).resolve() == game
                and '--parent-pid' in args and int(args[args.index('--parent-pid') + 1]) > 1)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return False


def _worker_parent_pid(pid,game):
    if not _worker_pid_matches(pid,game):raise RuntimeError('Source worker process identity changed')
    result=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True,timeout=3,check=True)
    args=shlex.split(result.stdout.strip())
    value=int(args[args.index('--parent-pid')+1])
    if value<=1:raise RuntimeError('Source Minecraft process is unconfirmed')
    return value


def _pid_alive(pid):
    try:os.kill(pid,0)
    except ProcessLookupError:return False
    except PermissionError:return True
    return True


def _minecraft_pid_matches(pid,game):
    if type(pid) is not int or pid<=1:return False
    try:
        result=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True,timeout=3,check=True)
        args=shlex.split(result.stdout.strip())
        return ('--gameDir' in args and Path(args[args.index('--gameDir')+1]).resolve()==game
                and any(arg in {'net.minecraft.client.main.Main','net.fabricmc.loader.impl.launch.knot.KnotClient'}
                        for arg in args))
    except (OSError,ValueError,IndexError,subprocess.SubprocessError):return False


def _legacy_identity(row):
    return tuple(row.get(key) for key in ('id', 'op', 'world_id', 'trial_id', 'run_id', 'world_session', 'dimension'))


def _review_worker(game, registry, run, pending, identity_checker, *, phases, wall_time=time.time):
    root = game / 'config/twob2tkit/singleplayer-trial/worker'
    worker = _json_record(root / 'status.json', 262144)
    journal = root / 'material-review-runs' / run / 'journal.jsonl'
    if (worker.get('protocol') != 1 or worker.get('run_id') != run
            or worker.get('trial_id') != registry['trial_id']
            or not same_save(worker.get('world_id'), registry['world_id'])
            or worker.get('legacy_material_review') is not True
            or worker.get('material_macros_enabled') is not False
            or worker.get('legacy_pending') != pending
            or worker.get('phase') not in phases
            or type(worker.get('time')) is not int
            or not 0 <= wall_time() - worker['time'] / 1000 <= 5
            or not identity_checker(worker.get('pid'), game)
            or worker.get('journal_path') != str(journal)
            or any(path.is_symlink() for path in (journal, *journal.parents))
            or not journal.is_file() or journal.stat().st_size > 4_000_000):
        raise RuntimeError('Current worker has no exact paused legacy-review isolation')
    events = [json.loads(line) for line in journal.read_text().splitlines() if line]
    if (not events or any(not isinstance(event, dict) or event.get('run_id') != run
            or event.get('trial_id') != registry['trial_id'] or type(event.get('time')) is not int
            for event in events)):
        raise RuntimeError('Legacy-review journal ownership is unconfirmed')
    starts = [event for event in events if event.get('event') == 'control' and event.get('command') == 'start']
    if len(starts) != 1 or starts[0]['time'] > worker['time']:
        raise RuntimeError('Native Start for this isolated worker is unconfirmed')
    if any(event.get('event') == 'worker_wait' and (event.get('bridge_halted') is not False
            or event.get('active_request') is not None) for event in events):
        raise RuntimeError('Current isolated worker contains an unknown native operation')
    material = [event for event in events if event.get('event') == 'native_request'
                and event.get('op') in MUTATING_OPS - {'guard'}]
    if material or any(event.get('event') in {'macro_started', 'macro_completed'} for event in events):
        raise RuntimeError('Legacy-review worker dispatched ordinary material work')
    return worker


def _capture_legacy_isolation(game, registry, state, checkpoint, identity_checker, wall_time):
    if (not checkpoint or checkpoint.get('source_run_id') == registry['run_id']
            or not isinstance(checkpoint.get('unresolved_native'), list)
            or not checkpoint['unresolved_native']):
        raise RuntimeError('A preserved old material checkpoint is required')
    pending = checkpoint['unresolved_native']
    seen = set()
    for row in pending:
        if (not isinstance(row, dict) or not isinstance(row.get('id'), str)
                or not row['id'].startswith('trial-') or row['id'] in seen
                or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in row['id'])
                or row.get('op') not in MUTATING_OPS - {'guard'}
                or not same_save(row.get('world_id'), registry['world_id'])
                or row.get('trial_id') != registry['trial_id']
                or row.get('run_id') != checkpoint.get('source_run_id')
                or not isinstance(row.get('run_id'), str) or not row['run_id']
                or row['run_id'] == registry['run_id']
                or row.get('world_session') != checkpoint.get('world_session')
                or not isinstance(row.get('world_session'), str) or not row['world_session']
                or row.get('dimension') != state.get('dimension')
                or not isinstance(row.get('arguments'), dict)):
            raise RuntimeError('Legacy isolation may preserve only fully scoped older material intents')
        seen.add(row['id'])
    worker = _review_worker(game, registry, registry['run_id'], pending, identity_checker,
                            phases={'paused'}, wall_time=wall_time)
    root = game / 'config/twob2tkit/singleplayer-trial/worker'
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise RuntimeError('Legacy isolation evidence directory must not contain symlinks')
    bootstrap = _json_record(root / 'bootstrap/status.json')
    if not same_save(bootstrap.get('world_id'), registry['world_id']):
        raise RuntimeError('Legacy bootstrap belongs to another save')
    journal = root / 'journal.jsonl'
    if not journal.is_file() or journal.is_symlink():
        raise RuntimeError('Original legacy material journal is unavailable')
    with journal.open('rb') as stream:
        size = journal.stat().st_size
        offset = max(0, size - 2_000_000)
        stream.seek(offset)
        tail = stream.read()
    if offset:
        tail = tail.split(b'\n', 1)[-1]
    history = [json.loads(line) for line in tail.splitlines() if line]
    if not any(isinstance(event, dict) and event.get('trial_id') == registry['trial_id']
            and event.get('run_id') == checkpoint['source_run_id']
            and (event.get('active_request') in seen or event.get('id') in seen)
            for event in history):
        raise RuntimeError('Original material journal does not identify the preserved unknown action')
    frozen = [root / 'checkpoint.json', root / 'journal.jsonl', root / 'bootstrap/status.json']
    for path in (root / 'bootstrap').rglob('*'):
        if path.is_symlink():
            raise RuntimeError('Legacy bootstrap evidence must not contain symlinks')
        if path.is_file():
            frozen.append(path)
    for row in pending:
        archive = root / 'legacy-material-intents' / (row['id'] + '.request.json')
        if archive.parent.is_symlink():
            raise RuntimeError('Legacy envelope archive must not be linked')
        envelope = _json_record(archive, 131072)
        if (_legacy_identity(envelope) != _legacy_identity(row)
                or envelope.get('local_trial') is not True or envelope.get('local_survival') is not True
                or envelope.get('server') != 'singleplayer'
                or type(envelope.get('expected_revision')) is not int or envelope['expected_revision'] < 0
                or type(envelope.get('expires_at')) is not int or envelope['expires_at'] <= 0
                or any(envelope.get(key) != value for key, value in row['arguments'].items())):
            raise RuntimeError('Full archived legacy envelope differs from its unknown checkpoint')
        frozen.append(archive)
    return {'pending': pending, 'pid': worker['pid'],
            'frozen': {str(path): _file_digest(path) for path in set(frozen)}}


def _legacy_frozen_unchanged(isolation):
    if any(_file_digest(Path(path)) != digest for path, digest in isolation['frozen'].items()):
        raise RuntimeError('Preserved legacy evidence changed; do not install or resume')
    _material_prefix_unchanged(isolation)


def _only_isolated_legacy(pending, isolation):
    expected = {_legacy_identity(row) for row in isolation['pending']}
    if (not pending or {_legacy_identity(row) for row in pending} != expected
            or any(row.get('op') == 'guard' for row in pending)):
        raise RuntimeError('Current-run or changed unknown intent cannot use legacy source replacement')


def _capture_material_plan(game, registry, state, identity_checker, wall_time,parent_reader=_worker_parent_pid,
                           *, stopped=False, worker_status_ref=None):
    """Freeze an admitted plan for fresh same-JVM observation before Resume."""
    root=game/'config/twob2tkit/singleplayer-trial/worker'
    status_path=Path(worker_status_ref['path']) if worker_status_ref else root/'status.json'
    if worker_status_ref and _file_digest(status_path)!=worker_status_ref.get('sha256'):
        raise RuntimeError('Stopped worker evidence changed')
    worker=_json_record(status_path,262144)
    bid=worker.get('material_baseline_id')
    if (worker.get('protocol')!=1 or worker.get('phase') not in ({'stopped','cancelled'} if stopped else {'paused'})
            or worker.get('run_id')!=registry['run_id'] or worker.get('trial_id')!=registry['trial_id']
            or not same_save(worker.get('world_id'),registry['world_id'])
            or worker.get('historical_effects_unresolved') is not True
            or worker.get('historical_replay_enabled') is not False
            or worker.get('material_baseline_session')!=state['world_session']
            or not stopped and worker.get('world_session')!=state['world_session']
            or type(worker.get('time')) is not int or stopped and worker['time']>state['time']
            or not stopped and not 0<=wall_time()-worker['time']/1000<=5
            or type(worker.get('pid')) is not int or worker['pid']<=1
            or (identity_checker(worker.get('pid'),game) if stopped else not identity_checker(worker.get('pid'),game))
            or not isinstance(bid,str) or not bid.startswith('baseline-')
            or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in bid)):
        raise RuntimeError('Exact paused admitted material worker is required')
    review=root/'material-review-runs'/registry['run_id']
    folder=review/'replanned-material'/bid
    if any(path.is_symlink() for path in (folder,*folder.parents)):
        raise RuntimeError('Admitted material plan must not contain symlinks')
    baseline=_json_record(folder/'baseline.json',8_000_000)
    checkpoint=_json_record(folder/'checkpoint.json')
    if (baseline.get('schema')!=1 or baseline.get('source')!='fresh_kit_physical_baseline'
            or baseline.get('newbaseline_id')!=bid
            or any(baseline.get(key)!=value for key,value in {
                'world_id':registry['world_id'],'trial_id':registry['trial_id'],'run_id':registry['run_id'],
                'world_session':state['world_session'],'dimension':state['dimension']}.items())
            or baseline.get('historical_effects_unresolved') is not True
            or baseline.get('old_action_completed') is not False or baseline.get('old_action_replayed') is not False
            or checkpoint.get('schema')!=1 or checkpoint.get('material_baseline_id')!=bid
            or checkpoint.get('source_run_id')!=registry['run_id']
            or any(checkpoint.get(key)!=value for key,value in {
                'world_id':registry['world_id'],'trial_id':registry['trial_id'],
                'world_session':state['world_session'],'game_version':state['game_version']}.items())
            or checkpoint.get('historical_effects_unresolved') is not True
            or checkpoint.get('historical_unresolved_native')!=worker.get('legacy_pending')
            or baseline.get('legacy_pending')!=worker.get('legacy_pending')):
        raise RuntimeError('Admitted material baseline or latest checkpoint scope differs')
    checked,request,report,review_files=_material_review_chain(root,baseline)
    frozen=request.get('frozen_legacy',{})
    if not isinstance(frozen,dict) or not frozen:
        raise RuntimeError('Material review has no immutable historical evidence')
    for name,digest in frozen.items():
        if _file_digest(Path(name))!=digest:
            raise RuntimeError('Historical material evidence changed after its review')
    ref=request.get('report',{})
    report_path=Path(ref.get('path',''))
    if (_file_digest(report_path)!=ref.get('sha256') or ref.get('sha256')!=checked.get('report_sha256')
            or _json_record(report_path)!=report):
        raise RuntimeError('Immutable operator report differs from the admitted baseline')
    preserved={str(path):_file_digest(path) for path in folder.rglob('*') if path.is_file()}
    if any(path.is_symlink() for path in folder.rglob('*')):
        raise RuntimeError('Material plan evidence must not contain symlinks')
    preserved.update(frozen)
    preserved.update(review_files)
    preserved[str(report_path)]=_file_digest(report_path)
    if worker_status_ref:preserved[str(status_path)]=worker_status_ref['sha256']
    inventory_ids={row['id'] for row in worker['legacy_pending'] if row.get('op')=='slot_click'}
    if inventory_ids:
        if set(checked.get('inventory_review_verified_ids',[]))!=inventory_ids:
            raise RuntimeError('Admitted baseline lacks each historical inventory review')
        inventory_review=request.get('inventory_review')
        if not isinstance(inventory_review,dict):raise RuntimeError('Historical inventory review reference is missing')
        _preserve_review_references(inventory_review,preserved)
    sdk_confirmed=_preserve_sdk_inventory(game,registry,worker['legacy_pending'],preserved)
    for reference in report.get('artifacts',{}).values():
        path=Path(reference.get('path',''))
        if _file_digest(path)!=reference.get('sha256'):
            raise RuntimeError('Reviewed terminal or saved-world artifact changed')
        preserved[str(path)]=reference['sha256']
    journal=review/'journal.jsonl'
    if worker.get('journal_path')!=str(journal) or journal.is_symlink() or not journal.is_file():
        raise RuntimeError('Admitted material journal is unavailable')
    content=journal.read_bytes()
    events=[json.loads(line) for line in content.splitlines() if line]
    if (not content.endswith(b'\n') or any(event.get('run_id')!=registry['run_id']
            or event.get('trial_id')!=registry['trial_id'] for event in events)
            or not any(event.get('event') in {'physical_material_rebaseline_accepted','source_material_handoff_accepted'}
                and event.get('baseline_id')==bid and event.get('request_id')==request['id']
                and event.get('historical_effects_unresolved') is True
                and event.get('old_action_replayed') is False for event in events)
            and not any(event.get('event')=='source_material_handoff_accepted'
                and event.get('baseline_id')==bid and event.get('handoff_id')==baseline.get('request_id')
                and event.get('historical_effects_unresolved') is True and event.get('old_action_replayed') is False
                for event in events)):
        raise RuntimeError('Current material journal does not confirm this operator admission')
    return {'pending':worker['legacy_pending'],'pid':worker['pid'],
        'source_parent_pid':parent_reader(worker['pid'],game),'frozen':preserved,
        'material_plan':{'baseline_id':bid,'baseline_path':str(folder/'baseline.json'),
            'checkpoint_path':str(folder/'checkpoint.json'),'checkpoint_sha256':_file_digest(folder/'checkpoint.json'),
            'protected_player_work':{key:checkpoint.get(key) for key in ('stations','owned','small_shelter','camp','excluded')},
            'current_intents':checkpoint.get('unresolved_native',[]),
            'source_scope':{key:state[key] for key in ('world_id','world_session','dimension','control_revision')},
            'automatic_material_resume':False},
        'sdk_current_confirmed':sdk_confirmed,
        'review_prefix':{'path':str(journal),'size':len(content),'sha256':hashlib.sha256(content).hexdigest(),
                         'run_id':registry['run_id'],'trial_id':registry['trial_id']}}


def _material_review_chain(root,baseline,depth=0):
    """Retain original approval through a consumed, exact same-JVM handoff."""
    if depth>8:raise RuntimeError('Material source authorization chain is too deep')
    checked=baseline.get('review',{});request=checked.get('request',{});report=checked.get('report',{})
    handoff=baseline.get('source_handoff')
    if handoff is not None:
        if (handoff.get('kind')!='same_session_source_material_handoff'
                or handoff.get('target_run_id')!=baseline.get('run_id')
                or handoff.get('stock_fresh') is not True or handoff.get('player_work_fresh') is not True
                or handoff.get('source_authorization_inherited') is not True):
            raise RuntimeError('Inherited material authorization is unconfirmed')
        frozen={}
        for ref in (handoff.get('manifest_ref'),handoff.get('source_baseline_ref'),handoff.get('source_checkpoint_ref')):
            _preserve_review_references(ref,frozen)
        manifest=_json_record(Path(handoff['manifest_ref']['path']),8_000_000)
        source=_json_record(Path(handoff['source_baseline_ref']['path']),8_000_000)
        claim_path=root/'source-material-handoff-claims'/(str(manifest.get('id'))+'.json')
        claim=_json_record(claim_path)
        if (manifest.get('schema')!=1 or manifest.get('kind')!=handoff['kind']
                or manifest.get('id')!=baseline.get('request_id')
                or any(manifest.get(key)!=baseline.get(key) for key in ('world_id','trial_id','world_session','dimension'))
                or manifest.get('source_run_id')!=handoff.get('source_run_id')
                or manifest.get('source_parent_pid')!=handoff.get('source_parent_pid')
                or manifest.get('baseline')!=handoff['source_baseline_ref']
                or manifest.get('checkpoint')!=handoff['source_checkpoint_ref']
                or source.get('run_id')!=manifest['source_run_id'] or source.get('review')!=checked
                or any(source.get(key)!=manifest.get(key) for key in ('world_id','trial_id','world_session','dimension'))
                or source.get('legacy_pending')!=manifest.get('historical_pending')
                or baseline.get('legacy_pending')!=source.get('legacy_pending')
                or claim.get('schema')!=1 or claim.get('handoff_id')!=manifest['id']
                or claim.get('manifest_sha256')!=handoff['manifest_ref']['sha256']
                or claim.get('run_id')!=baseline['run_id'] or claim.get('world_session')!=baseline['world_session']
                or claim.get('baseline_id')!=baseline.get('newbaseline_id')
                or claim.get('historical_effects_unresolved') is not True
                or claim.get('old_action_completed') is not False or claim.get('old_action_replayed') is not False):
            raise RuntimeError('Inherited material plan does not match its consumed source handoff')
        for filename,digest in manifest.get('frozen',{}).items():
            if _file_digest(Path(filename))!=digest:raise RuntimeError('Source handoff historical evidence changed')
            frozen[filename]=digest
        frozen[str(claim_path)]=_file_digest(claim_path)
        original=_material_review_chain(root,source,depth+1)
        frozen.update(original[3])
        return (*original[:3],frozen)
    archived=root/'material-review-runs'/str(baseline.get('run_id'))/'rebaseline-requests'/(str(baseline.get('request_id'))+'.json')
    if (_json_record(archived)!=request or request.get('kind')!='fresh_material_replan'
            or request.get('id')!=baseline.get('request_id')
            or any(request.get(key)!=baseline.get(key) for key in ('world_id','trial_id','run_id','world_session','dimension'))
            or type(checked.get('verified_at')) is not int
            or not request.get('created_at',0)<=checked['verified_at']<=request.get('expires_at',0)
            or report.get('decision')!='fresh_replan_allowed' or report.get('historical_effects_unresolved') is not True):
        raise RuntimeError('Admitted plan has no exact archived operator review')
    return checked,request,report,{str(archived):_file_digest(archived)}


def _preserve_review_references(reference,preserved,seen=None):
    """Freeze the admitted inventory bundle, manifests and retirement evidence."""
    seen=set() if seen is None else seen
    if not isinstance(reference,dict) or not isinstance(reference.get('path'),str):
        raise RuntimeError('Admitted review reference is malformed')
    path=Path(reference['path']);digest=_file_digest(path)
    if digest!=reference.get('sha256'):raise RuntimeError('Admitted inventory review evidence changed')
    if str(path) in seen:return
    seen.add(str(path));preserved[str(path)]=digest
    # Small JSON references only; raw saved-world archives/logs are hashed but
    # never decoded or scanned as if they were a world-state report.
    if path.suffix!='.json' or path.stat().st_size>8_000_000:return
    value=_json_record(path,8_000_000)
    def walk(node):
        if isinstance(node,dict):
            if set(node)>= {'path','sha256'}:
                _preserve_review_references(node,preserved,seen)
            else:
                for child in node.values():walk(child)
        elif isinstance(node,list):
            for child in node:walk(child)
    walk(value)


def _preserve_sdk_inventory(game,registry,historical,preserved):
    """A native timer completion is never an SDK transaction commit."""
    root=game/'config/twob2tkit/automation/trial-sdk-inventory'
    folder=root/'pending'
    if not folder.exists():return []
    if folder.is_symlink():raise RuntimeError('SDK pending directory is linked')
    confirmed=[];old={row['id']:row for row in historical if row.get('op')=='slot_click'}
    for path in folder.glob('*.json'):
        record=_json_record(path,512_000);envelope=record.get('envelope',{})
        if envelope.get('world_id')!=registry['world_id']:continue
        rid=envelope.get('id')
        if record.get('protocol')!=1 or record.get('request_id')!=rid or path.stem!=rid:
            raise RuntimeError('SDK original intent identity differs')
        receipt_path=root/'receipts'/(rid+'.json')
        if envelope.get('run_id')!=registry['run_id'] and not receipt_path.exists():
            row=old.get(rid)
            if (row is None or any(envelope.get(key)!=row.get(key) for key in
                    ('id','world_id','trial_id','run_id','world_session','dimension'))
                    or preserved.get(str(path))!=_file_digest(path)):
                raise RuntimeError('Unscoped or unreviewed historical SDK intent must remain stopped')
            continue
        if envelope.get('trial_id')!=registry['trial_id']:
            raise RuntimeError('Current SDK original intent changed trial')
        receipt=_json_record(receipt_path,1_000_000)
        if (receipt.get('protocol')!=1 or receipt.get('request_id')!=rid
                or receipt.get('intent_sha256')!=_file_digest(path) or receipt.get('replayed') is not False):
            raise RuntimeError('Current SDK transaction lacks its exact immutable receipt')
        native=receipt.get('native_result',{})
        if receipt.get('receipt_class')=='native_guard_busy_before_inventory_dispatch':
            validate_scope(native,registry,envelope['world_session'],envelope['run_id'])
            settled=(native.get('id')==rid and guard_pre_dispatch_refusal('slot_click',native,envelope['expected_revision']))
        else:
            proof=native_inventory_click_proof(native,envelope,record['before'])
            times=receipt.get('witness_times',[])
            settled=(proof['classification']=='no_effect'
                and receipt.get('receipt_class')=='server_processed_inventory_click_no_effect'
                or proof['classification']=='confirmed'
                and receipt.get('receipt_class')=='sdk_inventory_click_committed'
                and receipt.get('sdk_predicate_confirmed') is True
                and receipt.get('confirmation_scope')=='server_processed_inventory_transition_and_two_fresh_sdk_predicates'
                and isinstance(times,list) and len(times)==2 and all(type(n) is int for n in times)
                and native['time']<times[0]<times[1])
        if not settled:raise RuntimeError('Current SDK transaction is still unknown at its actual SDK stage')
        preserved[str(path)]=_file_digest(path);preserved[str(receipt_path)]=_file_digest(receipt_path)
        result_path=root/'native-results'/(rid+'.json')
        if result_path.exists():preserved[str(result_path)]=_file_digest(result_path)
        if envelope.get('run_id')==registry['run_id']:confirmed.append(rid)
    return sorted(confirmed)


def _material_prefix_unchanged(isolation):
    prefix=isolation.get('review_prefix')
    if not prefix:return
    path=Path(prefix['path'])
    if path.is_symlink() or not path.is_file():raise RuntimeError('Material journal changed')
    content=path.read_bytes()
    if hashlib.sha256(content[:prefix['size']]).hexdigest()!=prefix['sha256']:
        raise RuntimeError('Original admitted material journal bytes changed')
    for line in content[prefix['size']:].splitlines():
        event=json.loads(line)
        if (event.get('run_id')!=prefix['run_id'] or event.get('trial_id')!=prefix['trial_id']
                or not (event.get('event')=='control' and event.get('command') in {'pause','cancel'}
                        or event.get('event')=='worker_wait')):
            raise RuntimeError('Material worker dispatched new work during source replacement')


def _material_pending_checkpoint(isolation,registry,state):
    checkpoint=_json_record(Path(isolation['material_plan']['checkpoint_path']))
    result=json.loads(json.dumps(checkpoint))
    for row in result.get('unresolved_native',[]):
        if not isinstance(row,dict) or row.get('op') not in MUTATING_OPS:
            raise RuntimeError('Malformed current material pending record')
        for key,value in {'world_id':registry['world_id'],'trial_id':registry['trial_id'],
                          'run_id':registry['run_id'],'dimension':state['dimension']}.items():
            if key in row and row[key]!=value:
                raise RuntimeError('Current material checkpoint pending scope differs')
            row.setdefault(key,value)
        if row.get('world_session')!=state['world_session']:
            raise RuntimeError('Current material checkpoint session changed')
    return result


def _hold_metadata(state):
    value = state.get('safety_hold', {})
    if not isinstance(value, dict):
        raise RuntimeError('Invalid native safety hold observation')
    return {key: value[key] for key in HOLD_METADATA if key in value}


def _historical_trial_hold(game, state):
    """Capture a hold already exempted by this exact native .6 trial.

    The exception is only for the pause/cancel/install/start lifecycle below.
    It never clears the durable hold or grants any gameplay operation.
    """
    observed = state.get('safety_hold', {})
    if (state.get('kit_version') not in {'2026.10.7.6', '2026.10.7.7', '2026.10.7.8', '2026.10.7.9'}
            or observed.get('active') is not False or observed.get('escaping') is not False
            or not state.get('dimension') or not state.get('player_uuid')):
        return None
    path = Path(game) / 'config/twob2tkit/automation/safety-hold.json'
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 2_000_000:
        return None
    try:
        content = path.read_bytes()
        stored = json.loads(content)
    except (OSError, ValueError):
        return None
    metadata = _hold_metadata(state)
    if (not isinstance(stored, dict) or stored.get('active') is not True
            or set(metadata) != set(HOLD_METADATA)
            or any(stored.get(key) != metadata[key] for key in HOLD_METADATA)
            or stored.get('server') != 'singleplayer'
            or stored.get('dimension') != state['dimension']
            or stored.get('player') != state['player_uuid']
            or type(stored.get('time')) is not int
            or not 0 < stored['time'] < state.get('time', 0)):
        return None
    return {'sha256': hashlib.sha256(content).hexdigest(), 'metadata': metadata,
            'dimension': state['dimension'], 'player_uuid': state['player_uuid']}


def _historical_hold_unchanged(game, state, captured):
    if (state.get('kit_version') not in {'2026.10.7.6', '2026.10.7.7', '2026.10.7.8', '2026.10.7.9'}
            or state.get('dimension') != captured['dimension']
            or state.get('player_uuid') != captured['player_uuid']
            or _hold_metadata(state) != captured['metadata']
            or state.get('safety_hold', {}).get('escaping') is not False):
        return False
    path = Path(game) / 'config/twob2tkit/automation/safety-hold.json'
    try:
        return (path.is_file() and not path.is_symlink() and path.stat().st_size <= 2_000_000
                and hashlib.sha256(path.read_bytes()).hexdigest() == captured['sha256'])
    except OSError:
        return False


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex[:8] + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temp.replace(path)


def _write_material_handoff(game,registry,state,isolation,bundle_hash,*,lifecycle_kind,
                            wall_time=time.time,extra=None):
    root=game/'config/twob2tkit/singleplayer-trial/worker'
    _legacy_frozen_unchanged(isolation)
    pointer=root/'source-material-handoff.json'
    if pointer.exists() or pointer.is_symlink():
        if pointer.is_symlink():raise RuntimeError('Material handoff pointer is linked')
        previous=_json_record(pointer,131072);prior=Path(previous.get('path',''))
        if (_file_digest(prior)!=previous.get('sha256') or prior.parent!=root/'source-material-handoffs'):
            raise RuntimeError('Previous source handoff changed')
        claim=_json_record(root/'source-material-handoff-claims'/(prior.stem+'.json'))
        original=_json_record(prior,8_000_000)
        if (claim.get('schema')!=1 or claim.get('handoff_id')!=prior.stem
                or claim.get('manifest_sha256')!=previous['sha256']
                or claim.get('run_id')!=registry['run_id'] or claim.get('world_session')!=state['world_session']
                or claim.get('baseline_id')!=isolation['material_plan']['baseline_id']
                or original.get('source_run_id')==registry['run_id']
                or claim.get('historical_effects_unresolved') is not True
                or claim.get('old_action_completed') is not False or claim.get('old_action_replayed') is not False):
            raise RuntimeError('Previous material handoff was not claimed by this admitted plan')
    plan=isolation['material_plan']
    value={'schema':1,'kind':'same_session_source_material_handoff','id':'handoff-'+uuid.uuid4().hex,
        **{key:state.get(key) for key in ('world_id','world_session','dimension','game_version','kit_version')},
        'trial_id':registry['trial_id'],'source_run_id':registry['run_id'],'source_worker_pid':isolation['pid'],
        'source_parent_pid':isolation['source_parent_pid'],'source_worker_exited':True,
        'lifecycle_kind':lifecycle_kind,'bundle_sha256':bundle_hash,
        'baseline':{'path':plan['baseline_path'],'sha256':isolation['frozen'][plan['baseline_path']]},
        'checkpoint':{'path':plan['checkpoint_path'],'sha256':plan['checkpoint_sha256']},
        'frozen':isolation['frozen'],'sdk_inventory_confirmed_ids':isolation['sdk_current_confirmed'],
        'historical_pending':isolation['pending'],'protected_player_work':plan['protected_player_work'],
        'source_scope':plan['source_scope'],'source_current_native':state,
        'created_at':int(wall_time()*1000),'old_actions_replayed':False,**(extra or {})}
    folder=root/'source-material-handoffs'
    if any(path.is_symlink() for path in (folder,*folder.parents)):
        raise RuntimeError('Material handoff directory is linked')
    path=folder/(value['id']+'.json')
    atomic_json(path,value)
    ref={'path':str(path),'sha256':_file_digest(path)}
    atomic_json(pointer,ref)
    return ref


def _cold_native(state,registry,session,wall_time):
    from trial_inventory_audit import quantities,empty_menu
    validate_scope(state,registry,session)
    keys=state.get('movement_keys',{});identity=state.get('trial_identity',{})
    if (state.get('singleplayer_trial_api_protocol')!=1 or state.get('kit_version')!='2026.10.7.9'
            or identity.get('process_alive') is not False or identity.get('run_id')!=''
            or identity.get('detail')!='手动移动接管'
            or type(state.get('time')) is not int or not 0<=wall_time()-state['time']/1000<=5
            or state.get('phase')=='running' or state.get('screen') or state.get('manual_movement') is not False
            or state.get('health',0)<=0 or state.get('food',0)<8 or state.get('under_water') is True
            or state.get('safety_hold',{}).get('escaping') is True or state.get('guard_busy') is True
            or any(state.get(key) is not False for key in ('chopping','navigating','borer_active','printing'))
            or not {'forward','back','jump','sneak'}<=keys.keys() or any(v is not False for v in keys.values())
            or not empty_menu(state.get('menu')) or not state.get('player_uuid')):
        raise RuntimeError('Cold source handoff needs an exact fresh released manually stopped trial')
    quantities(state.get('inventory'))
    return state


def prepare_cold_material_handoff(game,bundle,operator_current_native,*,source_parent_pid,worker_status_ref,
                                  reader=status,pid_alive=_pid_alive,minecraft_identity_checker=_minecraft_pid_matches,
                                  import_checker=None,python=sys.executable,wall_time=time.time):
    """Freeze a manual-stop source swap; never install, start, unlock or replay."""
    root=Path(game).resolve()/'config/twob2tkit/singleplayer-trial'
    with (root/'hot-update.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another trial source handoff is already running') from None
        return _prepare_cold_material_handoff(game,bundle,operator_current_native,source_parent_pid=source_parent_pid,
            worker_status_ref=worker_status_ref,reader=reader,pid_alive=pid_alive,
            minecraft_identity_checker=minecraft_identity_checker,import_checker=import_checker,python=python,wall_time=wall_time)


def _prepare_cold_material_handoff(game,bundle,operator_current_native,*,source_parent_pid,worker_status_ref,
                                  reader,pid_alive,minecraft_identity_checker,import_checker,python,wall_time):
    from material_worker_release import verify,check_imports
    game=Path(game).resolve();bundle=Path(bundle).resolve();files=verify(bundle)
    if not REQUIRED<=files.keys():raise RuntimeError('Worker bundle lacks the trial lifecycle modules')
    for name in REQUIRED:ast.parse(files[name],filename=name)
    (import_checker or check_imports)(bundle,python)
    bundle_hash=_file_digest(bundle)
    root=game/'config/twob2tkit/singleplayer-trial'
    registry=validate_registry(_json_record(root/'registry.json'),game)
    session=operator_current_native.get('world_session')
    first=_cold_native(operator_current_native,registry,session,wall_time)
    if not minecraft_identity_checker(source_parent_pid,game):
        raise RuntimeError('Cold source handoff needs the same live Minecraft process')
    isolation=_capture_material_plan(game,registry,first,lambda pid,_:pid_alive(pid),wall_time,
        lambda pid,_:source_parent_pid,stopped=True,worker_status_ref=worker_status_ref)
    current_checkpoint=_material_pending_checkpoint(isolation,registry,first)
    if unresolved_mutations(game,registry,first,current_checkpoint):
        raise RuntimeError('Current source material work remains unknown; preserve it')
    # The audit may read large historical evidence. The source witness is
    # checked again against a new frame before writing the immutable pointer.
    current=_cold_native(reader(game/'config/twob2tkit/automation'),registry,session,wall_time)
    if (current['time']<first['time'] or any(current.get(k)!=first.get(k) for k in
            ('inventory','menu','player_uuid','control_revision','pos','safety_hold'))
            or pid_alive(isolation['pid']) or not minecraft_identity_checker(source_parent_pid,game)):
        raise RuntimeError('Operator handback stock or source ownership changed during the audit')
    status_path=Path(worker_status_ref['path'])
    if _json_record(root/'worker/status.json',262144)!=_json_record(status_path,262144):
        raise RuntimeError('Stopped worker status changed after its immutable capture')
    if _file_digest(bundle)!=bundle_hash:raise RuntimeError('Source bundle changed during the audit')
    isolation['frozen'][isolation['review_prefix']['path']]=_file_digest(Path(isolation['review_prefix']['path']))
    return _write_material_handoff(game,registry,current,isolation,bundle_hash,
        lifecycle_kind='manual_stopped_same_session',wall_time=wall_time,
        extra={'source_stopped_native':first,'source_worker_status':worker_status_ref,
               'operator_current_native':current,'stock_source':'fresh_operator_handback_not_attributed_to_kit'})


def _accepted_handoff_worker(game,registry,state,reference,isolation,identity_checker,wall_time):
    root=game/'config/twob2tkit/singleplayer-trial/worker'
    worker=_json_record(root/'status.json',262144);manifest=_json_record(Path(reference['path']),8_000_000)
    claim=_json_record(root/'source-material-handoff-claims'/(manifest['id']+'.json'))
    if (_file_digest(Path(reference['path']))!=reference['sha256']
            or worker.get('protocol')!=1 or worker.get('run_id')!=registry['run_id']
            or worker.get('trial_id')!=registry['trial_id'] or worker.get('world_id')!=registry['world_id']
            or worker.get('world_session')!=state['world_session']
            or worker.get('phase')!='waiting_material_handoff' or worker.get('material_macros_enabled') is not False
            or worker.get('source_material_handoff_waiting') is not True
            or worker.get('source_material_handoff_id')!=manifest['id']
            or worker.get('source_handoff_parent_pid')!=isolation['source_parent_pid']
            or worker.get('legacy_pending')!=isolation['pending']
            or worker.get('historical_effects_unresolved') is not True
            or worker.get('historical_replay_enabled') is not False
            or type(worker.get('time')) is not int or not 0<=wall_time()-worker['time']/1000<=5
            or not identity_checker(worker.get('pid'),game)
            or claim.get('schema')!=1 or claim.get('handoff_id')!=manifest['id']
            or claim.get('manifest_sha256')!=reference['sha256']
            or claim.get('run_id')!=registry['run_id'] or claim.get('world_session')!=state['world_session']
            or claim.get('baseline_id')!=worker.get('material_baseline_id')
            or claim.get('historical_effects_unresolved') is not True
            or claim.get('old_action_completed') is not False or claim.get('old_action_replayed') is not False):
        raise RuntimeError('New material worker has not freshly claimed the exact source plan')
    folder=root/'material-review-runs'/registry['run_id']/'replanned-material'/worker['material_baseline_id']
    baseline=_json_record(folder/'baseline.json',8_000_000);checkpoint=_json_record(folder/'checkpoint.json')
    handoff=baseline.get('source_handoff',{})
    if (handoff.get('manifest_ref')!=reference or handoff.get('target_run_id')!=registry['run_id']
            or handoff.get('stock_fresh') is not True or handoff.get('player_work_fresh') is not True
            or baseline.get('historical_effects_unresolved') is not True
            or baseline.get('old_action_completed') is not False or baseline.get('old_action_replayed') is not False
            or checkpoint.get('source_run_id')!=registry['run_id']
            or checkpoint.get('unresolved_native')!=[] or checkpoint.get('historical_unresolved_native')!=isolation['pending']
            or any(checkpoint.get(key)!=value for key,value in isolation['material_plan']['protected_player_work'].items())):
        raise RuntimeError('New material handoff lost unknown history or protected player work')
    return worker


def supersede_unclaimed_material_handoff(game,bundle,operator_current_native,*,original_manifest_ref,
                                        retired_cancel_reply,retired_cancel_native_ref,source_parent_pid,reader=status,pid_alive=_pid_alive,
                                        minecraft_identity_checker=_minecraft_pid_matches,
                                        import_checker=None,python=sys.executable,wall_time=time.time):
    """Replace a rejected cold pointer with new source; preserve every original byte."""
    from material_worker_release import verify,check_imports
    from trial_inventory_audit import quantities,empty_menu
    entered_at=wall_time()
    game=Path(game).resolve();bundle=Path(bundle).resolve()
    root=game/'config/twob2tkit/singleplayer-trial';worker_root=root/'worker'
    with (root/'hot-update.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another trial source handoff is already running') from None
        files=verify(bundle)
        if not REQUIRED<=files.keys():raise RuntimeError('Worker bundle lacks the trial lifecycle modules')
        for name in REQUIRED:ast.parse(files[name],filename=name)
        (import_checker or check_imports)(bundle,python)
        bundle_hash=_file_digest(bundle)
        pointer=worker_root/'source-material-handoff.json';previous=_json_record(pointer,131072)
        if previous!=original_manifest_ref:raise RuntimeError('Unclaimed source pointer changed')
        old_path=Path(previous.get('path',''))
        if (old_path.parent!=worker_root/'source-material-handoffs' or not old_path.stem.startswith('handoff-')
                or _file_digest(old_path)!=previous.get('sha256')):
            raise RuntimeError('Original unclaimed source manifest differs')
        original=_json_record(old_path,8_000_000)
        def unclaimed():
            for path in (worker_root/'source-material-handoff-claims'/(old_path.stem+'.json'),old_path.with_suffix('.receipt.json')):
                if path.exists() or path.is_symlink():raise RuntimeError('Claimed material source cannot be superseded')
            if _json_record(pointer,131072)!=previous or _file_digest(old_path)!=previous['sha256']:
                raise RuntimeError('Unclaimed material source changed during its audit')
        unclaimed()
        registry=validate_registry(_json_record(root/'registry.json'),game)
        if (original.get('schema')!=1 or original.get('kind')!='same_session_source_material_handoff'
                or original.get('id')!=old_path.stem or original.get('lifecycle_kind')!='manual_stopped_same_session'
                or original.get('source_worker_exited') is not True or original.get('old_actions_replayed') is not False
                or original.get('source_parent_pid')!=source_parent_pid
                or original.get('source_run_id')==registry.get('run_id')
                or original.get('world_id')!=registry['world_id'] or original.get('trial_id')!=registry['trial_id']
                or not minecraft_identity_checker(source_parent_pid,game)):
            raise RuntimeError('Only an unaccepted cold same-Minecraft source handoff may be superseded')
        source_registry={**registry,'run_id':original.get('source_run_id')}
        source_state=original.get('source_stopped_native',{})
        validate_scope(source_state,source_registry,original.get('world_session'))
        if (source_state.get('trial_identity',{}).get('process_alive') is not False
                or source_state.get('trial_identity',{}).get('detail')!='手动移动接管'):
            raise RuntimeError('Original manual source retirement is unconfirmed')
        isolation=_capture_material_plan(game,source_registry,source_state,lambda pid,_:pid_alive(pid),wall_time,
            lambda *_:source_parent_pid,stopped=True,worker_status_ref=original.get('source_worker_status'))
        _legacy_frozen_unchanged({'frozen':original.get('frozen',{})})
        if (isolation['pid']!=original.get('source_worker_pid')
                or isolation['pending']!=original.get('historical_pending')
                or isolation['sdk_current_confirmed']!=original.get('sdk_inventory_confirmed_ids')
                or isolation['material_plan']['protected_player_work']!=original.get('protected_player_work')
                or original.get('baseline')!={'path':isolation['material_plan']['baseline_path'],
                    'sha256':_file_digest(Path(isolation['material_plan']['baseline_path']))}
                or original.get('checkpoint')!={'path':isolation['material_plan']['checkpoint_path'],
                    'sha256':isolation['material_plan']['checkpoint_sha256']}
                or any(original['frozen'].get(path)!=digest for path,digest in isolation['frozen'].items())):
            raise RuntimeError('Unaccepted source plan or its completed SDK history changed')
        stopped_worker=_json_record(worker_root/'status.json',262144)
        temporary_run=registry.get('run_id');temporary_pid=stopped_worker.get('pid')
        cancel_id=retired_cancel_reply.get('id');cancel_path=root/('api-intent-'+str(cancel_id)+'.json')
        if (not isinstance(cancel_id,str) or not 1<=len(cancel_id)<=96
                or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in cancel_id)
                or not isinstance(temporary_run,str) or not temporary_run):
            raise RuntimeError('Temporary source cancel identity is invalid')
        cancel_request=_json_record(cancel_path,131072)
        persisted_reply=_json_record(root/('api-reply-'+str(cancel_id)+'.json'),131072)
        identity=retired_cancel_reply.get('trial_identity',{})
        if (persisted_reply!=retired_cancel_reply or retired_cancel_reply.get('protocol')!=1
                or retired_cancel_reply.get('phase')!='done' or cancel_request.get('protocol')!=1
                or cancel_request.get('id')!=cancel_id or cancel_request.get('command')!='cancel'
                or type(cancel_request.get('expected_revision')) is not int
                or type(cancel_request.get('expires_at')) is not int or cancel_request['expires_at']<=0
                or cancel_request.get('world_id')!=original['world_id']
                or cancel_request.get('world_session')!=original['world_session']
                or identity.get('world_id')!=original['world_id'] or identity.get('trial_id')!=original['trial_id']
                or identity.get('run_id')!=temporary_run
                or stopped_worker.get('phase') not in {'cancelled','stopped'}
                or stopped_worker.get('run_id')!=temporary_run or stopped_worker.get('trial_id')!=registry['trial_id']
                or stopped_worker.get('world_id')!=registry['world_id']
                or stopped_worker.get('material_baseline_id') is not None
                or stopped_worker.get('material_macros_enabled') is not False
                or stopped_worker.get('legacy_pending')!=original['historical_pending']
                or type(temporary_pid) is not int or temporary_pid<=1 or pid_alive(temporary_pid)):
            raise RuntimeError('Temporary rejected-source worker has no exact stopped cancel evidence')
        witness=original.get('operator_current_native',{})
        after_path=Path(retired_cancel_native_ref.get('path',''))
        after_digest=_file_digest(after_path)
        if after_digest!=retired_cancel_native_ref.get('sha256'):
            raise RuntimeError('Archived after-cancel native evidence changed')
        after_cancel=_json_record(after_path)
        validate_scope(after_cancel,registry,original['world_session'])
        if (after_cancel.get('trial_identity',{}).get('process_alive') is not False
                or after_cancel.get('trial_identity',{}).get('run_id') not in ('',temporary_run)
                or type(after_cancel.get('time')) is not int
                or after_cancel['time']<cancel_request['expires_at']-30000
                or type(after_cancel.get('control_revision')) is not int
                or after_cancel['control_revision']<cancel_request['expected_revision']):
            raise RuntimeError('Archived native frame does not prove this cancellation finished')
        def safe_current(state,*,fresh_at=None):
            validate_scope(state,registry,original['world_session'])
            keys=state.get('movement_keys',{})
            quantities(state.get('inventory'))
            if (state.get('trial_identity',{}).get('process_alive') is not False
                    or state.get('trial_identity',{}).get('run_id') not in ('',temporary_run)
                    or type(state.get('time')) is not int
                    or not 0<=(wall_time() if fresh_at is None else fresh_at)-state['time']/1000<=5
                    or any(state.get(k)!=original.get(k) for k in ('world_id','world_session','dimension','kit_version','game_version'))
                    or state.get('player_uuid')!=witness.get('player_uuid')
                    or state.get('inventory')!=witness.get('inventory') or state.get('pos')!=witness.get('pos')
                    or state.get('control_revision')!=after_cancel['control_revision']
                    or state.get('phase')=='running' or state.get('manual_movement') is not False
                    or state.get('screen') or state.get('health',0)<=0 or state.get('food',0)<8
                    or state.get('under_water') is True or state.get('guard_busy') is True
                    or state.get('safety_hold',{}).get('escaping') is True
                    or any(state.get(k) is not False for k in ('chopping','navigating','borer_active','printing'))
                    or not {'forward','back','jump','sneak'}<=keys.keys() or any(v is not False for v in keys.values())
                    or not empty_menu(state.get('menu'))):
                raise RuntimeError('Current source supersession stock, scope or stopped control differs')
            return state
        # The supplied frame must be fresh at entry. Expensive historical
        # validation is followed by a separate fresh native read below.
        first=safe_current(operator_current_native,fresh_at=entered_at)
        safe_current(after_cancel,fresh_at=after_cancel['time']/1000)
        if (first['time']<after_cancel['time'] or type(stopped_worker.get('time')) is not int
                or first['time']<stopped_worker['time']
                or any(first.get(k)!=after_cancel.get(k) for k in
                ('inventory','menu','pos','player_uuid','control_revision','safety_hold'))):
            raise RuntimeError('Fresh supersession frame differs from the exact stopped native evidence')
        frozen=dict(original['frozen'])
        _preserve_sdk_inventory(game,registry,original['historical_pending'],frozen)
        pending=unresolved_mutations(game,registry,first,load_checkpoint(game,registry,first))
        old={_legacy_identity(row) for row in original['historical_pending']}
        if any(_legacy_identity(row) not in old for row in pending):
            raise RuntimeError('Temporary source worker still has an unknown current operation')
        current=safe_current(reader(game/'config/twob2tkit/automation'))
        if (current['time']<first['time'] or any(current.get(k)!=first.get(k) for k in ('inventory','menu','pos','control_revision','safety_hold'))
                or _json_record(worker_root/'status.json',262144)!=stopped_worker
                or pid_alive(temporary_pid) or not minecraft_identity_checker(source_parent_pid,game)
                or _file_digest(after_path)!=after_digest
                or _file_digest(bundle)!=bundle_hash):
            raise RuntimeError('Source supersession changed during its fresh audit')
        unclaimed();_legacy_frozen_unchanged({'frozen':original['frozen']})
        value=json.loads(json.dumps(original));value.update(id='handoff-'+uuid.uuid4().hex,bundle_sha256=bundle_hash,
            original_manifest_ref=previous,operator_current_native=current,source_current_native=current,
            created_at=int(wall_time()*1000),superseded_worker_retirement={'run_id':temporary_run,'pid':temporary_pid,
                'worker_status':stopped_worker,'native_cancel_reply':retired_cancel_reply,
                'native_cancel_request_ref':{'path':str(cancel_path),'sha256':_file_digest(cancel_path)},
                'after_cancel_native_ref':retired_cancel_native_ref})
        value['frozen'].update({str(old_path):previous['sha256'],str(cancel_path):_file_digest(cancel_path),
                              str(root/('api-reply-'+str(cancel_id)+'.json')):_file_digest(root/('api-reply-'+str(cancel_id)+'.json')),
                              str(after_path):after_digest})
        new_path=old_path.with_name(value['id']+'.json');atomic_json(new_path,value)
        reference={'path':str(new_path),'sha256':_file_digest(new_path)}
        atomic_json(pointer,reference)
        return reference


def point(value):
    return (isinstance(value, (list, tuple)) and len(value) == 3
            and all(type(n) is int and abs(n) <= 30_000_000 for n in value)
            and -64 <= value[1] <= 320)


def same_save(value, expected):
    try:
        return canonical_save(value) == canonical_save(expected)
    except RuntimeError:
        return False


def checkpoint_from_skills(registry, state, skills, pending=None):
    return {'schema': SCHEMA, 'world_id': registry['world_id'], 'trial_id': registry['trial_id'],
            'world_name': registry['world_name'], 'source_run_id': registry.get('run_id'),
            'game_version': state.get('game_version'), 'observed_at': state.get('time'),
            'world_session': state.get('world_session'),
            'camp': skills.camp, 'stations': skills.stations, 'owned': skills.owned,
            'camp_completed': False,  # Always re-audit native blocks; never trust an old flag.
            'excluded': [list(p) for p in sorted(skills.excluded)],
            'explored': [list(p) for p in sorted(skills.explored)],
            'tried_grids': [list(p) for p in sorted(skills.tried_grids)],
            'station_anchor': skills.station_anchor,
            'rejected_routes': [[list(p) for p in route] for route in sorted(skills.rejected_routes)],
            'log_drops': skills.log_drops,
            'small_shelter': getattr(skills,'small_shelter',None),
            'unresolved_native': list((pending or {}).values())}


def load_checkpoint(game, registry, state):
    """Coordinates may only be considered again inside this exact trial save."""
    root = Path(game) / 'config/twob2tkit/singleplayer-trial/worker'
    file = root / 'checkpoint.json'
    if file.is_file():
        if file.is_symlink() or file.stat().st_size > 2_000_000:
            raise RuntimeError('Invalid trial checkpoint file')
        value = json.loads(file.read_text())
        if (value.get('schema') != SCHEMA or not same_save(value.get('world_id'), registry['world_id'])
                or value.get('trial_id') != registry['trial_id']
                or value.get('game_version') != state.get('game_version')):
            return None
        return {**value, 'world_id': registry['world_id']}
    # The first upgrade predates checkpoints. Preserve the old observed camp
    # metadata, but not inventory, progress counters or any completion claim.
    legacy = root / 'bootstrap/status.json'
    if not legacy.is_file() or legacy.is_symlink() or legacy.stat().st_size > 2_000_000:
        return None
    value = json.loads(legacy.read_text())
    if not same_save(value.get('world_id'), registry['world_id']) or value.get('world_name') != registry['world_name']:
        return None
    return {'schema': SCHEMA, 'world_id': registry['world_id'], 'trial_id': registry['trial_id'],
            'world_name': registry['world_name'], 'source_run_id': registry.get('run_id'),
            'game_version': state.get('game_version'), 'observed_at': state.get('time'),
            'camp': value.get('camp'), 'stations': value.get('stations', {}),
            'owned': value.get('owned', {}), 'station_anchor': None,
            'excluded': [], 'explored': [], 'tried_grids': [], 'rejected_routes': [],
            'unresolved_native': [], 'source': 'legacy_native_bootstrap_metadata'}


def _receipt_safe(receipt, request):
    if (request.get('op') == 'interact' and receipt.get('id') == request.get('id')
            and receipt.get('world_session') == request.get('world_session')
            and receipt.get('world_id') == request.get('world_id')
            and receipt.get('dimension') == request.get('dimension')
            and receipt.get('trial_identity', {}).get('trial_id') == request.get('trial_id')
            and receipt.get('trial_identity', {}).get('run_id') == request.get('run_id')
            and confirmed_interaction_not_sent('interact', receipt, request.get('arguments', {}),
                                               request.get('expected_revision'))):
        return True
    if (receipt.get('id') != request.get('id')
            or receipt.get('world_session') != request.get('world_session')
            or receipt.get('op') != request.get('op')):
        return False
    if receipt.get('phase') == 'done' and receipt.get('outcome_pending') is not True:
        return request['op'] != 'mine_block' or receipt.get('server_confirmed') is True
    return confirmed_mining_not_sent(request.get('op'), receipt, request.get('arguments', {}))


def unresolved_mutations(game, registry, state, checkpoint=None):
    automation = Path(game) / 'config/twob2tkit/automation'
    pending = {}
    if checkpoint:
        for row in checkpoint.get('unresolved_native', []):
            if isinstance(row, dict) and row.get('op') in MUTATING_OPS:
                pending[row.get('id')] = row
    mailbox = automation / 'request.json'
    if mailbox.is_file():
        request = json.loads(mailbox.read_text())
        if (request.get('local_trial') is True and same_save(request.get('world_id'), registry['world_id'])
                and request.get('trial_id') == registry['trial_id'] and request.get('op') in MUTATING_OPS):
            pending[request['id']] = {'id': request['id'], 'op': request['op'],
                'world_session': request.get('world_session'),
                'world_id': request.get('world_id'), 'trial_id': request.get('trial_id'),
                'run_id': request.get('run_id'), 'dimension': request.get('dimension'),
                'arguments': {'pos': request.get('pos')}}
            if request['op'] in {'select_item', 'guard'}:
                pending[request['id']].update(request_sha256=request_fingerprint(request),
                    arguments=({'item': request.get('item')} if request['op'] == 'select_item'
                               else {'pve_only': request.get('pve_only')}))
            elif request['op'] == 'interact':
                pending[request['id']].update(expected_revision=request.get('expected_revision'),
                    request_sha256=request_fingerprint(request),
                    arguments={key: value for key, value in request.items() if key not in ENVELOPE_KEYS})
    # Terminal native replies retain trial/run identity. A later read-only scan
    # must not hide an earlier unconfirmed mutation in the same run.
    for path in automation.glob('reply-trial-*.json'):
        if path.is_symlink() or path.stat().st_size > 2_000_000:
            continue
        reply = json.loads(path.read_text())
        identity = reply.get('trial_identity', {})
        if (identity.get('trial_id') == registry['trial_id'] and identity.get('run_id') == registry.get('run_id')
                and same_save(reply.get('world_id'), registry['world_id']) and reply.get('op') in MUTATING_OPS):
            pending[reply['id']] = {'id': reply['id'], 'op': reply['op'],
                'world_session': reply.get('world_session'),
                'world_id': reply.get('world_id'), 'trial_id': identity.get('trial_id'),
                'run_id': identity.get('run_id'), 'dimension': reply.get('dimension'),
                'arguments': {'pos': reply.get('mining_target')}}
    result = []
    for request_id, request in pending.items():
        if not isinstance(request_id, str) or not request_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in request_id):
            raise RuntimeError('Invalid unresolved native request identity')
        reply = automation / ('reply-' + request_id + '.json')
        # Ordinary native chop finishes in status.json rather than a host
        # reply file. Its worker ledger is a copy of the matched native frame,
        # validated against the original request and current trial scope. No
        # missing reply, elapsed timer or unchecked inventory implies success.
        if (request.get('op') == 'chop' and not reply.exists() and not reply.is_symlink()
                and known_chop_receipt(game, registry, request, state) is not None):
            continue
        if (request.get('op') == 'select_item' and not reply.exists() and not reply.is_symlink()
                and known_select_item_receipt(game, registry, request, state) is not None):
            continue
        if (request.get('op') == 'guard' and not reply.exists() and not reply.is_symlink()
                and known_guard_receipt(game, registry, request, state) is not None):
            continue
        if not reply.is_file() or reply.is_symlink() or not _receipt_safe(json.loads(reply.read_text()), request):
            result.append(request)
    return result


def restore_checkpoint(skills, checkpoint, registry, state):
    """Re-read actual station/camp blocks; old coordinates are only hypotheses."""
    if not checkpoint:
        return {'restored': False, 'reason': 'no_compatible_checkpoint'}
    if (checkpoint.get('schema') != SCHEMA or not same_save(checkpoint.get('world_id'), registry['world_id'])
            or checkpoint.get('trial_id') != registry['trial_id']
            or checkpoint.get('game_version') != state.get('game_version')):
        return {'restored': False, 'reason': 'different_trial_or_version'}
    unresolved = unresolved_mutations(skills.b.root.parents[2], registry, state, checkpoint)
    if unresolved:
        raise RuntimeError('Checkpoint has unconfirmed native mutations; preserve it for physical review')
    restored = {}
    for name, target in checkpoint.get('stations', {}).items():
        if name not in {'crafting_table', 'furnace'} or not point(target) or distance(state['pos'], target) > 32:
            continue
        result = skills.b.request('scan', min=target, max=target, details=True)
        row = next((r for r in result.get('blocks', []) if r.get('pos') == target), None)
        if row and block_id(row.get('state', '')) == name:
            skills.stations[name] = list(target)
            restored[name] = list(target)
    camp = checkpoint.get('camp')
    if point(camp) and distance(state['pos'], camp) <= 24:
        x, y, z = camp
        low, high = [x - 2, y - 1, z - 2], [x + 2, y + 2, z + 2]
        result = skills.b.request('scan', min=low, max=high, details=True)
        world = World(result.get('blocks', []), low, high)
        if world.stand(tuple(camp)) and all(world.full((px, y - 1, pz))
                for px in range(x - 2, x + 3) for pz in range(z - 2, z + 3)):
            skills.camp = list(camp)
            layout, door = shelter(camp)
            skills.camp_completed = all(world.earth(p) for p in layout) and world.name(door).endswith('_door')
    anchor = checkpoint.get('station_anchor')
    if point(anchor) and distance(state['pos'], anchor) <= 10:
        low, high = [anchor[0], anchor[1] - 1, anchor[2]], [anchor[0], anchor[1] + 1, anchor[2]]
        result = skills.b.request('scan', min=low, max=high, details=True)
        if World(result.get('blocks', []), low, high).stand(tuple(anchor)):
            skills.station_anchor = list(anchor)
    # Ownership only excludes old user construction from mining; it does not
    # assert a block exists or authorize rebuilding it.
    owned = checkpoint.get('owned', {})
    if isinstance(owned, dict) and len(owned) <= 4096:
        skills.owned = {key: value for key, value in owned.items()
                        if isinstance(key, str) and isinstance(value, str) and len(key) <= 64 and len(value) <= 96}
    small = checkpoint.get('small_shelter')
    if isinstance(small,dict) and small.get('schema')==1 and small.get('world_id')==registry['world_id'] and small.get('dimension')==state.get('dimension') and point(small.get('inside')):
        from trial_safety_preparation import _layout, _house_verified
        layout=_layout(small['inside'])
        if all(small.get(k)==v for k,v in layout.items()) and distance(state['pos'],small['inside'])<=24:
            x,y,z=small['inside'];lo=[x-2,y-1,z-2];hi=[x+2,y+3,z+2]
            observed=skills.b.request('scan',min=lo,max=hi,details=True)
            world=World(observed['blocks'],lo,hi)
            skills.small_shelter={**small,'verified':_house_verified(world,layout,small.get('door_item',''))}
    skills.excluded = {tuple(p) for p in checkpoint.get('excluded', []) if point(p)}
    for name in ('explored', 'tried_grids'):
        values = checkpoint.get(name, [])
        setattr(skills, name, {tuple(p) for p in values[:256] if isinstance(p, list)
                              and len(p) == 2 and all(type(n) is int for n in p)})
    skills.rejected_routes = {tuple(tuple(p) for p in route)
                              for route in checkpoint.get('rejected_routes', [])[:256]
                              if isinstance(route, list) and len(route) <= 32 and all(point(p) for p in route)}
    drops = checkpoint.get('log_drops', {})
    if isinstance(drops, dict) and len(drops) <= 128:
        skills.log_drops = {identity: row for identity, row in drops.items()
                           if isinstance(identity, str) and isinstance(row, dict)
                           and isinstance(row.get('pos'), list) and len(row['pos']) == 3
                           and all(type(n) in (int, float) and math.isfinite(n) and abs(n) <= 30_000_000 for n in row['pos'])
                           and type(row.get('count')) is int and row['count'] > 0
                           and isinstance(row.get('item'), str) and row['item'].endswith('_log')
                           and type(row.get('observed_at')) is int
                           and 0 <= state.get('time', 0) - row['observed_at'] <= 240_000}
    return {'restored': True, 'stations_native_checked': sorted(restored),
            'camp_native_checked': skills.camp is not None,
            'camp_completed_native_checked': skills.camp_completed,
            'inventory_restored': False, 'native_request_replayed': False}


def install_and_restart(game, bundle, *, python=sys.executable, timeout=30,
                        reader=status, native=call, installer=None,
                        import_checker=None, worker_checker=None,
                        sleeper=time.sleep, preserve_legacy_review=False,
                        worker_identity_checker=None, wall_time=time.time,
                        preserve_material_plan=False,worker_parent_reader=_worker_parent_pid):
    # Release tooling is deliberately excluded from the installed worker. Keep
    # this import lazy so checkpoint restoration needs only bundled modules.
    from material_worker_release import verify, check_imports, install, worker_running
    installer = installer or install
    import_checker = import_checker or check_imports
    worker_checker = worker_checker or worker_running
    worker_identity_checker = worker_identity_checker or _worker_pid_matches
    if preserve_material_plan and preserve_legacy_review:
        raise RuntimeError('Choose one exact source replacement mode')
    game, bundle = Path(game).resolve(), Path(bundle).resolve()
    root = game / 'config/twob2tkit/singleplayer-trial'
    automation = game / 'config/twob2tkit/automation'
    files = verify(bundle)
    if not REQUIRED.issubset(files):
        raise RuntimeError('Worker bundle lacks the trial lifecycle modules')
    for name in REQUIRED:
        ast.parse(files[name], filename=name)
    import_checker(bundle, python)
    bundle_hash = hashlib.sha256(bundle.read_bytes()).hexdigest()
    registry = validate_registry(json.loads((root / 'registry.json').read_text()), game)
    first = reader(automation)
    run = registry.get('run_id')
    validate_scope(first, registry, run_id=run)
    if (first.get('singleplayer_trial_api_protocol') != 1
            or first.get('trial_identity', {}).get('process_alive') is not True
            or not isinstance(run, str) or not run):
        raise RuntimeError('An existing native-owned trial worker is required')
    session = first['world_session']
    original_hold_metadata = _hold_metadata(first)
    historical_hold = _historical_trial_hold(game, first)
    cancelled = False
    def safe(state, *, old_run=True, released=False):
        validate_scope(state, registry, session, run if old_run else None)
        if (state.get('kit_version') != first.get('kit_version')
                or state.get('dimension') != first.get('dimension')):
            raise RuntimeError('Trial host or dimension changed during source replacement')
        if (_hold_metadata(state) != original_hold_metadata
                or historical_hold and not _historical_hold_unchanged(game, state, historical_hold)):
            raise RuntimeError('A safety hold record changed; preserve it and do not resume')
        identity = state.get('trial_identity', {})
        if (cancelled and released
                and (identity.get('run_id') not in ('', run)
                     or type(identity.get('process_alive')) is not bool)):
            raise RuntimeError('Cancelled trial ownership changed; do not install or resume')
        keys = state.get('movement_keys', {})
        # In this exact host the recovery window returns recovering &&
        # !actualStandaloneGuardBusy, then forces guard_busy. Only source
        # replacement may treat that paired state as idle; no guard/player
        # field is cleared and the restarted worker still honours the hold.
        recovery_only = (state.get('kit_version') == '2026.10.7.5'
            and state.get('guard_busy') is True and state.get('health_recovery_hold') is True
            and state.get('guard_armed') is True and state.get('guard_pve_only') is True
            and state.get('phase') != 'running'
            and {'forward','back','jump','sneak'}.issubset(keys)
            and all(value is False for value in keys.values()))
        # Native cancel ends activeHere immediately, while the old Python
        # process can take two seconds to exit. The unchanged historical hold
        # therefore becomes active again. Only this exact cancelled lifecycle
        # may observe that state; installation/Start separately require exit.
        historical_transition = (cancelled and not old_run and released and historical_hold
            and identity.get('run_id') in ('', run)
            and type(identity.get('process_alive')) is bool
            and state.get('safety_hold', {}).get('active') is True
            and state.get('time', 0) > first.get('time', 0))
        if (state.get('health', 0) <= 0 or state.get('food', 0) < 8
                or state.get('safety_hold', {}).get('active') is True and not historical_transition
                or state.get('safety_hold', {}).get('escaping') is True
                or state.get('under_water') is True or state.get('screen')
                or any(state.get(k) for k in ('printing', 'chopping', 'navigating', 'borer_active'))
                or state.get('guard_busy') and not recovery_only):
            raise RuntimeError('Trial hot update requires alive idle control; no health lock is changed')
        if released:
            keys = state.get('movement_keys', {})
            if (state.get('phase') == 'running' or not {'forward', 'back', 'jump', 'sneak'}.issubset(keys)
                    or any(value is not False for value in keys.values())):
                raise RuntimeError('Native owned inputs have not been confirmed released')
        return state
    safe(first)
    if preserve_legacy_review or preserve_material_plan:
        safe(first, released=True)
    checkpoint = load_checkpoint(game, registry, first)
    isolation = (_capture_legacy_isolation(game, registry, first, checkpoint,
                    worker_identity_checker, wall_time) if preserve_legacy_review else None)
    if preserve_material_plan:
        isolation=_capture_material_plan(game,registry,first,worker_identity_checker,wall_time,worker_parent_reader)
    current_checkpoint=(_material_pending_checkpoint(isolation,registry,first)
                        if preserve_material_plan else checkpoint)
    unresolved = unresolved_mutations(game, registry, first, current_checkpoint)
    if isolation:
        if preserve_material_plan:
            if unresolved:raise RuntimeError('Current admitted plan still has unknown native work; preserve it')
        else:_only_isolated_legacy(unresolved, isolation)
        _legacy_frozen_unchanged(isolation)
        # Historical receipts can be large. Never use the frame captured
        # before that audit to admit the following native lifecycle command.
        safe(reader(automation), released=True)
    elif unresolved:
        raise RuntimeError('Unconfirmed native mutation preserved; hot resume requires physical review')
    lock = (root / 'hot-update.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError('Another trial hot update is already running') from None
    proof = {'schema': 1, 'world_id': registry['world_id'], 'trial_id': registry['trial_id'],
             'before_run_id': run, 'world_session': session, 'bundle_sha256': bundle_hash,
             'minecraft_restarted': False, 'native_actions_replayed': False}
    if isolation:
        proof.update(legacy_material_review_preserved=True, material_macros_enabled=False,
                     legacy_unknown_ids=[row['id'] for row in isolation['pending']],
                     preserved_legacy_sha256=isolation['frozen'], legacy_outcomes_confirmed=False)
        if preserve_material_plan:
            proof.update(admitted_material_plan_preserved=True,material_plan_handoff=isolation['material_plan'],
                         automatic_material_resume=False,current_checkpoint_bytes_preserved=True,
                         new_scope_operator_review_required=True)
            proof['sdk_inventory_confirmed_ids']=isolation['sdk_current_confirmed']
            mailbox=automation/'request.json'
            if mailbox.is_file():
                envelope=_json_record(mailbox,131072)
                if envelope.get('run_id')==run:
                    proof['preserved_current_envelope']={'request':envelope,'sha256':_file_digest(mailbox)}
    try:
        paused = native(game, 'pause')
        if paused.get('trial_identity', {}).get('run_id') != run:
            raise RuntimeError('Native pause reply belongs to another run')
        until = time.monotonic() + timeout
        while True:
            current = safe(reader(automation))
            keys = current.get('movement_keys', {})
            if (current.get('time', 0) > first.get('time', 0) and current.get('phase') != 'running'
                    and {'forward', 'back', 'jump', 'sneak'}.issubset(keys)
                    and all(value is False for value in keys.values())):
                break
            if time.monotonic() >= until:
                raise RuntimeError('A fresh paused native snapshot was not observed')
            sleeper(.1)
        checkpoint = load_checkpoint(game, registry, current) or checkpoint
        paused_checkpoint=(_material_pending_checkpoint(isolation,registry,current)
                           if preserve_material_plan else checkpoint)
        pending = unresolved_mutations(game, registry, current, paused_checkpoint)
        if isolation:
            if preserve_material_plan:
                if pending:raise RuntimeError('Paused admitted plan has unknown native work; do not replace source')
            else:_only_isolated_legacy(pending, isolation)
            _legacy_frozen_unchanged(isolation)
            if preserve_material_plan:
                paused_worker=_json_record(root/'worker/status.json',262144)
                if (paused_worker.get('phase')!='paused' or paused_worker.get('run_id')!=run
                        or paused_worker.get('material_baseline_id')!=isolation['material_plan']['baseline_id']
                        or not worker_identity_checker(paused_worker.get('pid'),game)
                        or not 0<=wall_time()-paused_worker.get('time',0)/1000<=5):
                    raise RuntimeError('Admitted material worker changed before cancellation')
            else:
                paused_worker = _review_worker(game, registry, run, isolation['pending'], worker_identity_checker,
                                                phases={'paused'}, wall_time=wall_time)
            if paused_worker['pid'] != isolation['pid']:
                raise RuntimeError('Isolated worker PID changed before cancellation')
            current = safe(reader(automation), released=True)
        elif pending:
            raise RuntimeError('Paused mutation is unconfirmed; preserve it and do not restart')
        if checkpoint and not isolation:
            checkpoint['unresolved_native'] = []  # Cleared solely by exact native receipts above.
            atomic_json(root / 'worker/checkpoint.json', checkpoint)
        proof['pause_confirmed'] = True
        if isolation:
            _legacy_frozen_unchanged(isolation)
            safe(reader(automation), released=True)
        cancelled_reply = native(game, 'cancel')
        cancelled_identity = cancelled_reply.get('trial_identity', {})
        if (cancelled_reply.get('phase') != 'done'
                or cancelled_identity.get('trial_id') != registry['trial_id']
                or cancelled_identity.get('run_id') != run
                or not same_save(cancelled_identity.get('world_id'), registry['world_id'])):
            raise RuntimeError('Native cancel receipt differs; do not install or resume')
        cancelled = True
        until = time.monotonic() + timeout
        while True:
            current = safe(reader(automation), old_run=False, released=True)
            if current.get('trial_identity', {}).get('process_alive') is False:
                break
            if time.monotonic() >= until:
                raise RuntimeError('Old native trial process is still alive; do not replace worker code')
            sleeper(.1)
        def running():
            if isolation:
                _legacy_frozen_unchanged(isolation)
            current = safe(reader(automation), old_run=False, released=True)
            return current.get('trial_identity', {}).get('process_alive') is not False or worker_checker()
        proof['old_worker_exit_confirmed'] = True
        # Source replacement has its own stage/hash/backup/rollback behavior.
        proof['installation'] = installer(bundle, game, python=python, running=running)
        if isolation:
            _legacy_frozen_unchanged(isolation)
        if hashlib.sha256(bundle.read_bytes()).hexdigest() != bundle_hash:
            raise RuntimeError('Worker artifact changed during installation; do not start it')
        before_start = safe(reader(automation), old_run=False, released=True)
        if before_start.get('trial_identity', {}).get('process_alive') is not False or worker_checker():
            raise RuntimeError('An old worker is still alive; do not start another controller')
        if preserve_material_plan:
            _legacy_frozen_unchanged(isolation)
            for reply,command in ((paused,'pause'),(cancelled_reply,'cancel')):
                request_path=root/('api-intent-'+str(reply.get('id'))+'.json')
                request=_json_record(request_path,131072)
                if (reply.get('protocol')!=1 or reply.get('phase')!='done' or request.get('protocol')!=1
                        or request.get('id')!=reply.get('id') or request.get('command')!=command
                        or request.get('world_id')!=registry['world_id'] or request.get('world_session')!=session
                        or type(request.get('expected_revision')) is not int
                        or request['expected_revision']!=first['control_revision']):
                    raise RuntimeError('Source lifecycle has no exact archived native intent')
                isolation['frozen'][str(request_path)]=_file_digest(request_path)
            isolation['frozen'][isolation['review_prefix']['path']]=_file_digest(Path(isolation['review_prefix']['path']))
            proof['material_handoff']=_write_material_handoff(game,registry,before_start,isolation,bundle_hash,
                lifecycle_kind='native_pause_cancel',wall_time=wall_time,
                extra={'native_pause_reply':paused,'native_cancel_reply':cancelled_reply,
                       'after_cancel_native':before_start})
        started = native(game, 'start')
        started_identity = started.get('trial_identity', {})
        new_run = started_identity.get('run_id')
        if (started.get('phase') != 'done'
                or started_identity.get('trial_id') != registry['trial_id']
                or not same_save(started_identity.get('world_id'), registry['world_id'])
                or not isinstance(new_run, str) or not new_run or new_run == run):
            raise RuntimeError('New native worker run was not confirmed; do not replay Start')
        start_received_at = int(time.time() * 1000)
        proof.update(start_receipt_confirmed=True, after_run_id=new_run)
        until = time.monotonic() + timeout
        while True:
            if isolation:
                _legacy_frozen_unchanged(isolation)
            current = reader(automation)
            identity = current.get('trial_identity', {})
            # The lifecycle receipt precedes the next periodic status write.
            # Observe only the already exited cancellation state from before
            # that receipt; never replay Start to make the status catch up.
            cancel_observation = (identity.get('run_id') in ('', run)
                and identity.get('process_alive') is False
                and type(current.get('time')) is int
                and before_start.get('time', 0) <= current['time'] <= start_received_at)
            current = safe(current, old_run=False, released=cancel_observation)
            if not cancel_observation and identity.get('run_id') != new_run:
                raise RuntimeError('Native trial ownership changed after Start; do not replay it')
            if identity.get('run_id') == new_run and identity.get('process_alive') is True:
                if not isolation:
                    break
                worker_path = root / 'worker/status.json'
                observed_worker = _json_record(worker_path, 262144)
                if (preserve_material_plan and observed_worker.get('run_id')==new_run
                        and observed_worker.get('phase')=='waiting_material_handoff'):
                    new_registry=validate_registry(_json_record(root/'registry.json'),game)
                    if new_registry['run_id']!=new_run or new_registry['trial_id']!=registry['trial_id']:
                        raise RuntimeError('New handoff worker registry changed after Start')
                    reviewed=_accepted_handoff_worker(game,new_registry,current,proof['material_handoff'],
                                                      isolation,worker_identity_checker,wall_time)
                    if current.get('guard_armed') is not True or current.get('guard_pve_only') is not True:
                        raise RuntimeError('New handoff worker has no same-session PvE guardian')
                    proof.update(legacy_new_worker_pid=reviewed['pid'],legacy_new_worker_phase=reviewed['phase'],
                                 material_plan_freshly_inherited=True,new_scope_operator_review_required=False)
                    break
                if (observed_worker.get('run_id') == new_run
                        and observed_worker.get('phase') == 'waiting_material_review'):
                    new_registry = validate_registry(_json_record(root / 'registry.json'), game)
                    if new_registry['run_id'] != new_run or new_registry['trial_id'] != registry['trial_id']:
                        raise RuntimeError('New isolated worker registry changed after Start')
                    reviewed = _review_worker(game, new_registry, new_run, isolation['pending'],
                        worker_identity_checker, phases={'waiting_material_review'}, wall_time=wall_time)
                    if (observed_worker.get('world_session') != session
                            or current.get('guard_armed') is not True
                            or current.get('guard_pve_only') is not True):
                        raise RuntimeError('New isolated worker has no confirmed same-session PvE guardian')
                    proof.update(legacy_new_worker_pid=reviewed['pid'],
                                 legacy_new_worker_phase=reviewed['phase'])
                    break
            if time.monotonic() >= until:
                raise RuntimeError('New worker process is unconfirmed; preserve Start and do not replay')
            sleeper(.1)
        proof.update(after_run_id=new_run, new_worker_native_confirmed=True,
                     checkpoint_preserved=checkpoint is not None,
                     experience_and_journals_replaced=False, native_completion_claimed=False)
        if historical_hold:
            proof.update(historical_hold_preserved=True,
                         historical_hold_sha256=historical_hold['sha256'],
                         historical_hold_time=historical_hold['metadata']['time'])
        atomic_json(root / 'hot-update-proof.json', proof)
        return proof
    except Exception:
        atomic_json(root / 'hot-update-interrupted.json', {**proof, 'automatic_retry_allowed': False,
                    'resume_confirmed': False, 'detail': 'Preserve native requests and verify fresh state before another lifecycle command'})
        raise
    finally:
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--preserve-legacy-review', action='store_true',
                        help='Replace source only while preserving exact isolated older unknown material work')
    parser.add_argument('--preserve-material-plan', action='store_true',
                        help='Preserve an admitted paused material plan; new worker freshly verifies stock and construction before Resume')
    args = parser.parse_args()
    print(json.dumps(install_and_restart(args.game, args.bundle, python=args.python,
        preserve_legacy_review=args.preserve_legacy_review,
        preserve_material_plan=args.preserve_material_plan), ensure_ascii=False))


if __name__ == '__main__':
    main()
