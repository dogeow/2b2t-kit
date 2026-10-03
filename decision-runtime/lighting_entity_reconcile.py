"""Reconcile specific terminal read-only preflights, without replaying requests."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import time

from lighting_cli import later_torch_frame, point
from safety_interlock import require_unlocked

ERROR='LightingBlocked: Current entity intersects movement body corridor'
GUARD_ERROR='LightingBlocked: Existing guard stayed busy; no lighting input or interaction dispatched'
ERRORS={ERROR:'scan',GUARD_ERROR:'snapshot'}
READ={'snapshot','scan'}
ALLOWED=READ|{'material_session','navigate','select_item','interact','material_job_park'}


def validate_pending(pending, state, report, events, scan_reply, *, external_parking=None):
    lease=state.get('supervision_lease') or {};safety=state.get('supervision_safety') or {}
    native=pending.get('uncertain_request') or {}
    external_valid=False
    if external_parking is not None:
        oldlease=external_parking.get('supervision_lease')or{};oldsafety=external_parking.get('supervision_safety')or{}
        external_valid=(pending.get('error')==GUARD_ERROR and report.get('placed')==[]
            and external_parking.get('world_session')==pending.get('world_session')
            and external_parking.get('connected')is True and external_parking.get('health')==20
            and external_parking.get('guard_armed')is True and external_parking.get('guard_pve_only')is True
            and external_parking.get('flight')is True and oldlease.get('kind')=='parking'
            and oldlease.get('id')==pending.get('lease') and oldlease.get('job_session')==pending.get('task_session')
            and oldlease.get('revision')==external_parking.get('control_revision')
            and oldsafety.get('action')=='KEEP_PVE_GUARD' and oldsafety.get('lease')==pending.get('lease')
            and oldsafety.get('job_session')==pending.get('task_session'))
        if not external_valid:raise ValueError('External original-task parking proof is invalid')
    expected_op=ERRORS.get(pending.get('error'))
    if (expected_op is None or pending.get('stage')!='lighting'
            or pending.get('handoff')!='late_owned_native_parking_observed_read_only' and not external_valid
            or native.get('op')!=expected_op or native!=pending.get('native_request')):
        raise ValueError('Only the exact terminal entity preflight may be reconciled')
    if (state.get('connected') is not True or state.get('world_session')!=pending.get('world_session')
            or state.get('health')!=20 or state.get('manual_movement') is not False
            or state.get('guard_armed') is not True or state.get('guard_pve_only') is not True
            or state.get('flight') is not True or state.get('screen')
            or lease.get('kind')!='parking' or lease.get('id')!=pending.get('lease')
            or lease.get('job_session')!=pending.get('task_session')
            or lease.get('revision')!=state.get('control_revision')
            or safety.get('action')!='KEEP_PVE_GUARD' or safety.get('lease')!=lease.get('id')
            or safety.get('job_session')!=lease.get('job_session')
            or time.time()*1000-state.get('time',0)>3000
            or report.get('park_native_confirmed') is not True and not external_valid):
        raise ValueError('Original owned healthy native parking is not current')
    pos,target=state.get('pos'),lease.get('park_target')
    if (not isinstance(pos,list) or not isinstance(target,list) or len(pos)!=3 or len(target)!=3
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in pos+target)
            or math.dist(pos,target)>.6):raise ValueError('Current original parking pose changed')
    placed=report.get('placed');rid=native.get('request_id')
    if (not isinstance(placed,list) or not events or scan_reply.get('id')!=rid
            or (expected_op=='scan' and scan_reply.get('phase')!='done') or scan_reply.get('world_session')!=pending['world_session']
            or scan_reply.get('control_revision')!=native.get('expected_revision')):
        raise ValueError('Original exact scan or placement report unavailable')
    exact=[i for i,e in enumerate(events) if e.get('request_id')==rid]
    if len(exact)!=1 or events[exact[0]].get('op')!=expected_op or expected_op=='scan' and events[exact[0]].get('phase')!='done':
        raise ValueError('Original preflight has no exact terminal event')
    for index,event in enumerate(events):
        retained_partial_read=(external_valid and placed==[] and event.get('op')=='scan'
            and event.get('phase')=='waiting' and event.get('inventory_delta')=={}
            and str(event.get('detail','')).startswith('scan stopped; partial records retained: Server chunk is not loaded: '))
        if (event.get('op') not in ALLOWED or event.get('world_session')!=pending['world_session']
                or event.get('op')!='snapshot' and event.get('phase')!='done' and not retained_partial_read
                or index>exact[0] and event.get('op') not in READ|{'material_job_park','navigate'}):
            raise ValueError('Unknown operation or mutation after the stopped preflight')
    interactions=[e for e in events if e.get('op')=='interact']
    if (len(interactions)!=len(placed) or len({p.get('interaction_request') for p in placed})!=len(placed)
            or sum(e.get('inventory_delta',{}).get('minecraft:torch',0) for e in events)!=-len(placed)):
        raise ValueError('Placement count or exact inventory conservation disagrees')
    for placement in placed:
        if (placement.get('state')!='verified' or placement.get('later_verified_frames')!=2
                or placement.get('world_session')!=pending['world_session']
                or placement.get('task_session')!=pending['task_session']
                or placement.get('before_stock',0)-placement.get('after_stock',0)!=1
                or not any(e.get('request_id')==placement.get('interaction_request')
                           and e.get('inventory_delta',{}).get('minecraft:torch')==-1 for e in interactions)):
            raise ValueError('Unknown or unverified torch interaction remains')
    return len(placed)


def reconcile(worker, *, allowed_error=ERROR):
    with worker.worker_lock():
        pending=deepcopy(worker.book.get('pending'))
        if not pending:raise ValueError('No original pending batch')
        if allowed_error not in ERRORS or pending.get('error')!=allowed_error:raise ValueError('Requested preflight category differs')
        state=worker.observer();require_unlocked(worker.root,state)
        directory=Path(pending['directory']);evidence={}
        def read(path):
            raw=path.read_bytes()
            if len(raw)>16*1024*1024:raise ValueError('Evidence exceeds bounded read')
            evidence[str(path)]=hashlib.sha256(raw).hexdigest()
            return json.loads(raw)
        report=read(directory/'report.json')
        raw=(directory/'events.jsonl').read_bytes()
        if len(raw)>8*1024*1024:raise ValueError('Event journal exceeds bound')
        evidence[str(directory/'events.jsonl')]=hashlib.sha256(raw).hexdigest()
        events=[json.loads(row) for row in raw.splitlines() if row.strip()]
        rid=(pending.get('uncertain_request')or{}).get('request_id','')
        if not isinstance(rid,str) or not rid or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in rid):raise ValueError('Invalid exact request id')
        reply=read(worker.root/('reply-'+rid+'.json'))
        recovered=directory/'owned-park-recovery/native-parking-verified.json'
        external=read(recovered) if recovered.exists() else None
        count=validate_pending(pending,state,report,events,reply,external_parking=external)
        for index,placed in enumerate(report['placed']):
            target=point(placed['target']);last=placed['before_time']
            key=hashlib.sha256((state['world_session']+':'+','.join(map(str,target))).encode()).hexdigest()
            if read(worker.root/'lighting-intents'/(key+'.json'))!=placed:raise ValueError('Original durable intent differs')
            for frame in (1,2):
                actual=read(directory/f'actual-torch-{index}-frame-{frame}.json')
                inventory=read(directory/f'inventory-after-{index}-frame-{frame}.json')
                if not later_torch_frame(actual,inventory,target,state['world_session'],placed['before_stock'],last):
                    raise ValueError('Original two-frame placement witness failed')
                last=inventory['time']
        record={'outcome':'terminal_readonly_preflight_partial_verified','request_replayed':False,
                'region_completed':False,'original_pending':pending,'evidence_sha256':evidence,
                'placed_verified':count,'observed_at':state['time']}
        worker.book.setdefault('pending_reconciliations',[]).append(record)
        worker.book['batches'].append({'region_index':pending['region_index'],'campaign':worker.book.get('campaign'),
             'mode':'lighting','directory':str(directory),'partial_verified':True,'placed_verified':count,
             'region_completed':False,'eligible_remaining':None})
        worker.book.update(pending=None,phase='waiting_resume',last_revision=None,parking_lease=None,
                           reason='Read-only preflight reconciled; fresh scan required before continuing')
        worker.save()
    return worker.status()
