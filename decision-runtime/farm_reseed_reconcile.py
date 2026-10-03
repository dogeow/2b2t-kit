"""Narrow proof for Kit .1's exact pre-use face rejection, never generic error recovery."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import uuid
import zipfile

from farm_preparation import preparation_lock
from farm_reseed import read,registered
from kit_runtime.journal import write_json
from material_jobs.protocol import server_key
from potato_farm import _counts

REJECTION='Target interaction face is occluded or out of reach'
HOST_VERSION='2026.10.3.1'
HOST_CLASS_SHA256='dad61017f01a0fdf405d3b75e2644415d483682173ce93586377f4e5bcd9ddf7'


def verify_host(root):
    game=Path(root).resolve().parents[2];jars=list((game/'mods').glob('twob2tkit-*.jar'))
    if len(jars)!=1:raise RuntimeError('A unique installed Kit host is required for no-use reconciliation')
    try:
        with zipfile.ZipFile(jars[0]) as archive:
            version=json.loads(archive.read('fabric.mod.json')).get('version')
            code=archive.read('dev/twob2tkit/automation/AutomationBridge.class')
    except (zipfile.BadZipFile,KeyError,ValueError) as error:raise RuntimeError('Installed host contract cannot be inspected') from error
    digest=hashlib.sha256(code).hexdigest()
    if version!=HOST_VERSION or digest!=HOST_CLASS_SHA256 or code.count(REJECTION.encode())!=1:
        raise RuntimeError('Installed host is not the audited exact pre-use rejection contract')
    return {'kit_version':version,'class_sha256':digest,'jar':str(jars[0]),
            'contract':'unique visible-null throw before active rotation or useItemOn; audited bytecode'}


def _proof(book,reply,events,contract):
    pending=book.get('pending') or {};native=pending.get('native_receipt') or {};rid=native.get('id');scope=book.get('scope') or {}
    if (contract.get('kit_version')!=HOST_VERSION or contract.get('class_sha256')!=HOST_CLASS_SHA256
            or book.get('kind')!='explicit_existing_farmland_reseed' or pending.get('operation')!='plant'
            or pending.get('pos') not in book.get('requested_cells',[]) or pending.get('pos') not in (scope.get('layout')or{}).get('cells',[])
            or book.get('new_reseed')!=0 or book.get('receipts') or not isinstance(rid,str) or not rid
            or native.get('phase')!='error' or native.get('detail')!=REJECTION
            or reply.get('id')!=rid or reply.get('phase')!='error' or reply.get('detail')!=REJECTION
            or reply.get('time')!=native.get('time') or reply.get('kit_version')!=HOST_VERSION
            or reply.get('world_session')!=book.get('world_session')
            or server_key(reply.get('server'))!=scope.get('server') or reply.get('dimension')!=scope.get('dimension')
            or dict(_counts(reply))!=pending.get('before_counts') or reply.get('hand')!=pending.get('hand_before')
            or (reply.get('menu') or {}).get('cursor',{}).get('count')!=0):
        raise RuntimeError('The original exact no-use rejection and unchanged inventory/hand are not proved')
    matches=[(index,event) for index,event in enumerate(events) if event.get('request_id')==rid]
    if len(matches)!=1:raise RuntimeError('Original request must occur exactly once in its native event chain')
    index,event=matches[0];params=event.get('params') or {};lease=reply.get('supervision_lease') or {}
    if (event.get('op')!='interact' or event.get('phase')!='error' or event.get('detail')!=REJECTION
            or event.get('world_session')!=book['world_session'] or params.get('pos')!=pending.get('pos') or params.get('face')!='up'
            or type(event.get('time')) not in (int,float) or not math.isfinite(event['time'])
            or abs(event['time']*1000-reply['time'])>2500
            or params.get('expected_state')!=pending.get('expected_state') or params.get('expected_hand')!=pending['hand_before']['item']
            or params.get('task_session')!=lease.get('job_session') or lease.get('kind')!='materials'
            or lease.get('world_session')!=book['world_session'] or lease.get('revision')!=reply.get('control_revision')
            or event.get('inventory_delta')!={} or event.get('revision_before')!=event.get('revision_after')
            or event.get('revision_after')!=reply.get('control_revision') or event.get('position_before')!=event.get('position_after')
            or event.get('position_after')!=reply.get('pos') or event.get('health_before')!=20 or event.get('health_after')!=20):
        raise RuntimeError('Original event/request/scope or no-change proof is inconsistent')
    before_ops={'scan','snapshot','material_session','navigate','select_item','look','approach_block'}
    after_ops={'scan','snapshot','material_job_pause'}
    for offset,other in enumerate(events):
        if offset==index:continue
        if (other.get('world_session')!=book['world_session'] or other.get('inventory_delta')!={}
                or other.get('phase')!='done' or other.get('op') not in (before_ops if offset<index else after_ops)
                or other.get('op')=='material_job_pause' and (other.get('params') or {}).get('task_session')!=lease.get('job_session')):
            raise RuntimeError('Another mutation, unknown request, inventory delta or foreign world exists in the original chain')
    return {'status':'rejected_without_use','operation_completed':False,'new_reseed':0,'request_id':rid,
            'world_session':book['world_session'],'task_session':lease['job_session'],'control_revision':reply['control_revision'],
            'exact_native_receipt':deepcopy(native),'host_contract':contract,'useItemOn_sent':False,
            'inventory_before':deepcopy(pending['before_counts']),'inventory_at_rejection':dict(_counts(reply))}


def archive_rejection(journal,book,proof):
    journal=Path(journal);raw=journal.read_bytes();destination=journal.parent/'rejected-without-use'/uuid.uuid4().hex;destination.mkdir(parents=True)
    (destination/'original-maintenance.json').write_bytes(raw);write_json(destination/'proof.json',proof)
    for name,key in (('original-reply.json','original_reply'),('original-events.jsonl','original_events')):
        if proof.get(key):(destination/name).write_bytes(Path(proof[key]).read_bytes())
    if proof.get('native_reply_snapshot'):write_json(destination/'native-reply-snapshot.json',proof['native_reply_snapshot'])
    updated=deepcopy(book);updated.setdefault('rejected_history',[]).append({'original_pending':deepcopy(book['pending']),
        'proof':str(destination/'proof.json'),'original_sha256':hashlib.sha256(raw).hexdigest()})
    updated.update(pending=None,closed_without_use=True,outcome='rejected_without_use',complete=False,
                   last_wait={'code':'REJECTED_WITHOUT_USE','detail':'Archived exact pre-use rejection; a fresh explicit maintenance request is required'})
    write_json(journal,updated)
    return {'phase':'archived_rejection','outcome':'rejected_without_use','new_reseed':0,'journal':str(journal),
            'archive':str(destination),'game_actions_sent':0,'operation_completed':False}


def reconcile_rejected(root,registry,journal,control_dir,*,archive_verified=False):
    root=Path(root);journal=Path(journal).resolve();control=Path(control_dir).resolve();book=read(journal)
    values=registered(root,registry,book.get('requested_cells'),server=(book.get('scope')or{}).get('server'))
    if (values[2]!=book.get('scope') or control.parent!=journal.parent
            or Path(book.get('original_planting_journal','')).resolve()!=values[-1].resolve()
            or hashlib.sha256(values[-1].read_bytes()).hexdigest()!=book.get('original_planting_sha256')):
        raise RuntimeError('Original maintenance/event scope, planting evidence or directory changed')
    pointer=read(values[0].parent/'reseed-active.json')
    if Path(pointer['journal']).resolve()!=journal:raise RuntimeError('The original fixed maintenance pointer no longer owns this journal')
    pending=book.get('pending') or {};rid=(pending.get('native_receipt')or{}).get('id')
    if not isinstance(rid,str) or not rid.startswith('materials-') or any(ch not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for ch in rid):raise RuntimeError('Original native request identity is missing')
    reply_path=root/('reply-'+rid+'.json');reply=read(reply_path)
    event_path=control/'events.jsonl'
    if not event_path.is_file() or event_path.stat().st_size>4_000_000:raise RuntimeError('Original complete native event chain is unavailable')
    events=[json.loads(line) for line in event_path.read_text().splitlines() if line.strip()]
    proof=_proof(book,reply,events,verify_host(root))
    proof.update(original_reply=str(reply_path),reply_sha256=hashlib.sha256(reply_path.read_bytes()).hexdigest(),
                 original_events=str(event_path),events_sha256=hashlib.sha256(event_path.read_bytes()).hexdigest())
    result={'phase':'verified_rejection','can_archive':True,'outcome':'rejected_without_use','operation_completed':False,
            'new_reseed':0,'journal':str(journal),'proof':proof,'game_actions_sent':0,'writes_performed':False}
    if archive_verified:
        lock_state={'server':values[2]['server'],'dimension':values[2]['dimension'],'world_session':book['world_session']}
        with preparation_lock(root,lock_state,values[5]):
            if read(journal)!=book:raise RuntimeError('Original maintenance changed during rejection verification')
            result=archive_rejection(journal,book,proof)
    return result


def live_rejection(c,journal,book,reply):
    control=getattr(c,'out',None)
    if control is None:return None
    events_path=Path(control)/'events.jsonl'
    if not events_path.exists():return None
    try:
        events=[json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
        proof=_proof(book,reply,events,verify_host(c.root));proof.update(original_events=str(events_path),native_reply_snapshot=deepcopy(reply))
        return proof
    except (RuntimeError,ValueError,OSError,KeyError,zipfile.BadZipFile):return None
