"""Reconcile only a pinned host's exact pre-use wheat planting rejection."""
import copy
import hashlib
import json
import math
import time
from pathlib import Path
from zipfile import ZipFile
from kit_runtime.journal import write_json
from potato_farm import _counts,_key
from live_snapshot import read_fresh

REJECTION='Target interaction face is occluded or out of reach'
HOST='2026.10.10.1'
HOST_CLASS_SHA='00f03248aa8a3eeec90afc3ac28a854e44867214ff083685540506479a52943e'
HOST_CONTRACTS={HOST:HOST_CLASS_SHA,
    '2026.10.10.2':'ef5f1bbccaa2746e9aaff2782c4c58ec8ef15c9cb6a0cf5cf1088a2819c09688',
    '2026.10.10.3':'ef5f1bbccaa2746e9aaff2782c4c58ec8ef15c9cb6a0cf5cf1088a2819c09688',
    '2026.10.11.1':'ef5f1bbccaa2746e9aaff2782c4c58ec8ef15c9cb6a0cf5cf1088a2819c09688'}


def contract(root):
    game=Path(root).resolve().parents[2]
    jars=list((game/'mods').glob('twob2tkit-*.jar'))
    if len(jars)!=1:raise RuntimeError('Unique current Kit host required')
    with ZipFile(jars[0])as z:
        version=json.loads(z.read('fabric.mod.json'))['version']
        code=z.read('dev/twob2tkit/automation/AutomationBridge.class')
    digest=hashlib.sha256(code).hexdigest()
    if HOST_CONTRACTS.get(version)!=digest or code.count(REJECTION.encode())!=1:
        raise RuntimeError('Exact pre-use rejection host contract is not verified')
    return {'kit_version':version,'class_sha256':digest,'rejection_before_use_item_on':True}


def prove(book,reply,event,current,host):
    pending=book.get('pending')or{};native=pending.get('receipt')or{};pos=pending.get('pos')
    harvest=book.get('cells',{}).get(_key(pos),{}).get('harvest',{})if isinstance(pos,list)else{}
    version=host.get('kit_version')
    if (version not in HOST_CONTRACTS or host.get('class_sha256')!=HOST_CONTRACTS.get(version)
            or pending.get('operation')!='plant' or native.get('phase')!='error' or native.get('detail')!=REJECTION
            or not harvest.get('native_mining_confirmed') or harvest.get('remaining_count')!=0
            or reply.get('id')!=native.get('id') or reply.get('phase')!='error' or reply.get('detail')!=REJECTION
            or reply.get('time')!=native.get('time')
            or reply.get('kit_version')!=version or reply.get('world_session')!=book.get('world_session')
            or reply.get('server')!=event.get('server',reply.get('server'))
            or reply.get('dimension')!='minecraft:overworld'
            or event.get('request_id')!=reply['id'] or event.get('op')!='interact'
            or event.get('phase')!='error' or event.get('detail')!=REJECTION
            or event.get('params',{}).get('pos')!=pos or event.get('params',{}).get('face')!='up'
            or event.get('params',{}).get('expected_hand')!='minecraft:wheat_seeds'
            or event.get('params',{}).get('expected_state')!=pending.get('expected_state')
            or event.get('inventory_delta')!={} or event.get('revision_before')!=event.get('revision_after')
            or event.get('revision_after')!=reply.get('control_revision')
            or event.get('position_before')!=event.get('position_after')
            or reply.get('inventory')!=pending.get('before_inventory') or reply.get('hand')!=pending.get('hand_before')
            or dict(_counts(current))!=pending.get('before_counts') or current.get('world_session')!=book.get('world_session')
            or current.get('control_revision')!=reply.get('control_revision')
            or current.get('recent_hurt_at')!=book.get('recent_hurt_at')
            or current.get('health')!=20 or current.get('manual_movement')or current.get('screen')
            or (current.get('supervision_lease')or{}).get('job_session')!=event['params'].get('task_session')):
        raise RuntimeError('Exact rejected planting and unchanged current inventory/owner are not proven')
    return {'outcome':'rejected_without_use','request_id':reply['id'],'world_session':book['world_session'],
            'original_attempt_not_done':True,'seed_debit':0,'host_contract':host,'pos':pos}


def prove_after_park(book,reply,event,current,host,finish,native):
    """Keep the original rejection frame separate from a fresh unchanged park."""
    original=prove(book,reply,event,reply,host)
    lease=current.get('supervision_lease')or{};old=reply.get('supervision_lease')or{}
    saved=finish.get('parking_confirmation')or{};target=lease.get('park_target')
    if (finish.get('native_receipt') is not True or finish.get('local_verified') or native.get('local_verified')
            or finish.get('lease_transition_pending') or native.get('lease_transition_pending')
            or lease.get('kind')!='parking' or lease.get('id')!=old.get('id')
            or lease.get('job_session')!=event['params']['task_session']
            or lease.get('world_session')!=book['world_session'] or lease.get('remote_finish')!='guard'
            or lease.get('revision')!=current.get('control_revision')
            or current.get('control_revision')!=saved.get('control_revision')
            or type(native.get('time')) is not int or native['time']<=reply['time']
            or type(current.get('time')) is not int or current['time']<saved.get('time',0)
            or not isinstance(target,list) or len(target)!=3 or not isinstance(current.get('pos'),list)
            or math.dist(current['pos'],target)>.6
            or dict(_counts(current))!=book['pending']['before_counts']
            or current.get('world_session')!=book['world_session']
            or current.get('recent_hurt_at')!=book['recent_hurt_at']
            or current.get('health')!=20 or current.get('manual_movement') or current.get('screen')
            or not current.get('connected') or not current.get('flight') or current.get('under_water')
            or current.get('guard_armed')is not True or current.get('guard_pve_only')is not True
            or current.get('safety_hold',{}).get('active') or current.get('guard_busy')
            or (native.get('snapshot')or{}).get('world_session')!=book['world_session']
            or any(finish.get(k)!=native.get(k)for k in ('lease','job_session','action','time'))
            or native.get('lease')!=lease.get('id') or native.get('job_session')!=lease.get('job_session')
            or native.get('action')!='KEEP_PVE_GUARD'):
        raise RuntimeError('Original rejection and unchanged current native parking are not proven')
    return {**original,'original_rejection_frame_is_historical':True,
            'fresh_unchanged_parking_revision':current['control_revision'],
            'fresh_unchanged_parking_time':current['time'],'native_finish_time':native['time']}


def reconcile_after_park(root,journal,out,control_dir):
    """Read-only journal reconciliation before a new controller is created."""
    root=Path(root);journal=Path(journal);out=Path(out);directory=Path(control_dir)
    if out.exists():raise RuntimeError('Choose a new proof directory')
    raw=journal.read_bytes();book=json.loads(raw);rid=book['pending']['receipt']['id']
    reply=json.loads((root/('reply-'+rid+'.json')).read_text())
    matches=[r for r in (json.loads(line)for line in(directory/'events.jsonl').read_text().splitlines())if r.get('request_id')==rid]
    if len(matches)!=1:raise RuntimeError('Single original event required')
    finish=json.loads((directory/'stock-safety.json').read_text());lease=finish['lease']
    native=json.loads((root/('supervision-receipt-'+lease+'.json')).read_text());host=contract(root)
    frames=[]
    for _ in range(2):
        deadline=time.monotonic()+6
        while True:
            current=read_fresh(root)
            if not frames or current['time']>frames[-1]['time']:break
            if time.monotonic()>=deadline:raise RuntimeError('Two distinct current parking frames required')
            time.sleep(.1)
        proof=prove_after_park(book,reply,matches[0],current,host,finish,native)
        frames.append(current)
    if journal.read_bytes()!=raw:raise RuntimeError('Original journal changed during observation')
    out.mkdir(parents=True);(out/'original-harvest-journal-before.json').write_bytes(raw)
    evidence=out/'exact-pre-use-rejection-proof.json'
    write_json(evidence,{'proof':proof,'reply':reply,'event':matches[0],'native_finish':native,
                        'fresh_parking_frames':frames})
    pending=book['pending'];book.setdefault('rejected_plant_history',[]).append({'original_pending':copy.deepcopy(pending),'proof':str(evidence)})
    book['pending']={'operation':'await_replant','pos':pending['pos'],'pre_drop_ids':pending.get('pre_drop_ids',[]),
                     'prior_plant_rejected_without_use':str(evidence)}
    write_json(journal,book);return proof


def reconcile(c,journal,out,control_dir=None):
    journal=Path(journal);out=Path(out)
    if out.exists():raise RuntimeError('Choose a new proof directory; no archive overwritten')
    book=json.loads(journal.read_text());pending=book.get('pending')or{};rid=(pending.get('receipt')or{}).get('id')
    reply=json.loads((c.root/('reply-'+str(rid)+'.json')).read_text())
    directory=Path(control_dir)if control_dir is not None else c.out
    events=[json.loads(line)for line in(directory/'events.jsonl').read_text().splitlines()]
    matches=[e for e in events if e.get('request_id')==rid]
    if len(matches)!=1:raise RuntimeError('Single original event required')
    proof=prove(book,reply,matches[0],c.status(),contract(c.root))
    out.mkdir(parents=True);(out/'original-harvest-journal-before.json').write_bytes(journal.read_bytes())
    write_json(out/'exact-pre-use-rejection-proof.json',{'proof':proof,'reply':reply,'event':matches[0]})
    book.setdefault('rejected_plant_history',[]).append({'original_pending':copy.deepcopy(pending),'proof':str(out/'exact-pre-use-rejection-proof.json')})
    book['pending']={'operation':'await_replant','pos':pending['pos'],'pre_drop_ids':pending.get('pre_drop_ids',[]),
                     'prior_plant_rejected_without_use':str(out/'exact-pre-use-rejection-proof.json')}
    write_json(journal,book)
    return proof
