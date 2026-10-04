"""Reconcile specific terminal read-only preflights, without replaying requests."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import time

from lighting_cli import later_torch_frame, point, scan_cells, verified_own_torch, stock
from safety_interlock import require_unlocked
from material_jobs.protocol import server_key

ERROR='LightingBlocked: Current entity intersects movement body corridor'
GUARD_ERROR='LightingBlocked: Existing guard stayed busy; no lighting input or interaction dispatched'
OWN_TORCH_ERROR='LightingBlocked: Fresh movement body sweep is occupied'
ERRORS={ERROR:'scan',GUARD_ERROR:'snapshot',OWN_TORCH_ERROR:'scan'}
READ={'snapshot','scan'}
ALLOWED=READ|{'material_session','navigate','select_item','interact','material_job_park'}


def _same_pose(a,b,tolerance=.3):
    return (isinstance(a,list) and isinstance(b,list) and len(a)==len(b)==3
            and all(type(v)in(int,float)and math.isfinite(v)for v in a+b)
            and math.dist(a,b)<=tolerance)


def _same_column_rise(before,target):
    return (isinstance(before,list)and isinstance(target,list)and len(before)==len(target)==3
        and all(type(v)in(int,float)and math.isfinite(v)for v in before+target)
        and math.hypot(before[0]-target[0],before[2]-target[2])<=.5 and target[1]>=before[1]+18)


def _no_work(state):
    return (not any(state.get(k) for k in ('borer_active','planter_active','feeder_active','fisher_active',
                    'printing','chopping','navigating','native_material_busy','guard_busy','under_water',
                    'air_return_active','guard_reconnect_pending','health_recovery_hold'))
        and not any((state.get(k)or{}).get('active') for k in ('gravel','concrete','build_job'))
        and not (state.get('material_task')or{}).get('occupied')
        and not (state.get('material_task')or{}).get('process_alive')
        and not (state.get('professional_printer')or{}).get('enabled')
        and not (state.get('professional_printer')or{}).get('owned'))


def _no_controller(state):
    keys=state.get('movement_keys')
    return isinstance(keys,dict)and bool(keys)and all(v is False for v in keys.values())and _no_work(state)


def _parking_pose(state,world):
    lease=state.get('supervision_lease')or{}
    return (state.get('connected')is True and state.get('world_session')==world
        and state.get('health')==20 and state.get('manual_movement')is False and not state.get('screen')
        and state.get('guard_armed')is True and state.get('guard_pve_only')is True and state.get('flight')is True
        and not (state.get('safety_hold')or{}).get('active') and lease.get('kind')=='parking'
        and lease.get('world_session')==world and lease.get('revision')==state.get('control_revision')
        and _same_pose(state.get('pos'),lease.get('park_target'),.6))


def _native_park(state,world):
    lease=state.get('supervision_lease')or{};safety=state.get('supervision_safety')or{}
    return (_parking_pose(state,world) and safety.get('action')=='KEEP_PVE_GUARD'
        and safety.get('lease')==lease.get('id')and safety.get('job_session')==lease.get('job_session'))


def _historical_finish_proves_park(state,world,receipt):
    """Correlate the exact copied native finish without rewriting stale globals."""
    if not isinstance(receipt,dict):return False
    lease=state.get('supervision_lease')or{};full=receipt.get('snapshot')or{}
    confirmation=receipt.get('parking_confirmation')or{};at=receipt.get('time')
    if (not _parking_pose(state,world)or not _no_controller(state)
        or receipt.get('native_receipt')is not True or receipt.get('action')!='KEEP_PVE_GUARD'
        or receipt.get('cause')!='controller_finished' or receipt.get('lease')!=lease.get('id')
        or receipt.get('job_session')!=lease.get('job_session')or type(at)is not int
        or lease.get('parked_at')!=at or type(state.get('time'))is not int
        or not at<=state['time']<=at+3000 or not _parking_pose(full,world)or not _no_controller(full)):
        return False
    for frame in (full,confirmation):
        observed=frame.get('time');owned=frame.get('supervision_lease')or{}
        if (type(observed)is not int or not at<=observed<=at+3000
            or frame.get('world_session')!=world or frame.get('control_revision')!=state['control_revision']
            or frame.get('connected')is not True or frame.get('health')!=20
            or frame.get('manual_movement')is not False or frame.get('flight')is not True
            or frame.get('guard_armed')is not True or frame.get('guard_pve_only')is not True
            or frame.get('under_water')is not False or (frame.get('safety_hold')or{}).get('active')
            or not _same_pose(frame.get('pos'),state['pos'])
            or any(owned.get(k)!=lease.get(k)for k in
                   ('id','job_session','kind','world_session','revision','park_target','parked_at'))):
            return False
    return (isinstance(state.get('server'),str)and bool(state['server'])
        and isinstance(state.get('dimension'),str)and bool(state['dimension'])
        and isinstance(state.get('player_uuid'),str)and bool(state['player_uuid'])
        and server_key(full.get('server'))==server_key(state.get('server'))
        and full.get('dimension')==state.get('dimension')
        and full.get('player_uuid')==state.get('player_uuid'))


def validate_maintenance_recovery(pending,state,report,recovery,original_parking,*,check_torches=True):
    """A new parking owner proves current safety; it never becomes the old finish."""
    world=pending['world_session'];old=original_parking;new=recovery.get('maintenance_parking')or{}
    oldlease=(old or{}).get('supervision_lease')or{};newlease=new.get('supervision_lease')or{}
    finish=recovery.get('maintenance_finish')
    alternate=False
    if finish is not None:
        alternate=_historical_finish_proves_park(new,world,finish)
        if not alternate:raise ValueError('Explicit historical native maintenance finish or parking confirmation differs')
    historical_state=(not check_torches and alternate and state==new)
    if (pending.get('error')!=OWN_TORCH_ERROR or recovery.get('schema')!=1
        or recovery.get('kind')!='own_torch_preflight_new_maintenance_parking'
        or not isinstance(old,dict) or not _native_park(old,world)
        or oldlease.get('id')!=pending.get('lease') or oldlease.get('job_session')!=pending.get('task_session')
        or report.get('park_native_confirmed')is not True
        or not (_native_park(new,world)or alternate)or not (_native_park(state,world)or historical_state)
        or not _no_controller(new) or not _no_controller(state)
        or not newlease.get('id') or newlease.get('id')==oldlease.get('id')
        or not newlease.get('job_session') or newlease.get('job_session')==oldlease.get('job_session')
        or any((state.get('supervision_lease')or{}).get(k)!=newlease.get(k) for k in ('id','job_session','revision'))
        or not _same_pose(old.get('pos'),new.get('pos')) or not _same_pose(new.get('pos'),state.get('pos'))):
        raise ValueError('Distinct current maintenance parking and original native finish are required')
    idle=recovery.get('idle_handoff')or{};samples=idle.get('idle_samples');release=recovery.get('prelease_scan')or{}
    if (idle.get('world_session')!=world or idle.get('purpose')!='new_maintenance_parking_after_ui_closed_no_original_work_replay'
        or not isinstance(samples,list)or not 2<=len(samples)<=64):
        raise ValueError('Real bounded interface-release samples are required')
    times=[]
    for sample in samples:
        keys=sample.get('movement_keys')or{}
        if (sample.get('world_session')!=world or sample.get('health')!=20 or sample.get('food',0)<18
            or sample.get('manual_movement')is not False or sample.get('screen')!=''
            or sample.get('detail')!='用户界面接管' or not keys or any(v is not False for v in keys.values())
            or not _same_pose(sample.get('pos'),old['pos']) or type(sample.get('time'))is not int
            or type(sample.get('control_revision'))is not int
            or sample['control_revision']<=old['control_revision']):
            raise ValueError('Interface-release sample world, pose, health or control changed')
        times.append(sample['time'])
    revision=samples[0]['control_revision']
    if (times!=sorted(times)or times[-1]-times[0]<5000 or times[0]<old['time']
        or any(s['control_revision']!=revision for s in samples)
        or release.get('phase')!='done' or release.get('world_session')!=world or release.get('control_revision')!=revision
        or release.get('supervision_lease')is not None or not _no_controller(release)
        or release.get('health')!=20 or release.get('food',0)<18 or release.get('manual_movement')is not False
        or release.get('screen')!='' or release.get('connected')is not True
        or release.get('guard_armed')is not True or release.get('guard_pve_only')is not True or release.get('flight')is not True
        or not _same_pose(release.get('pos'),old['pos'])
        or type(release.get('scan_started_at'))is not int or type(release.get('scan_ended_at'))is not int
        or not times[-1]<=release['scan_started_at']<=release['scan_ended_at']<=new['time']
        or release.get('scan_cells_read')!=release.get('scan_total_cells') or release.get('scan_total_cells',0)<1
        or release.get('scan_start_revision')!=revision or release.get('scan_end_revision')!=revision):
        raise ValueError('Full prelease native release witness does not follow five seconds of real idle observations')
    events=recovery.get('maintenance_events')
    if not isinstance(events,list)or not events or events[0].get('request_id')!=release.get('id'):
        raise ValueError('Exact prelease scan is missing from maintenance journal')
    sessions=[e for e in events if e.get('op')=='material_session']
    if (len(sessions)!=1 or sessions[0].get('params',{}).get('task_session')!=newlease['job_session']
        or sessions[0].get('params',{}).get('supervision_lease')!=newlease['id']):
        raise ValueError('New maintenance session scope differs')
    for event in events:
        if (event.get('op') not in READ|{'material_session','material_job_park'}
            or event.get('world_session')!=world or event.get('inventory_delta')!={}
            or event.get('op')!='snapshot' and event.get('phase')!='done'
            or not _same_pose(event.get('position_before'),old['pos'])
            or not _same_pose(event.get('position_after'),old['pos'])):
            raise ValueError('Maintenance performed movement, inventory changes or unknown operations')
    if check_torches:
        _validate_current_torches(pending,report,recovery,new,world)
    return old


def _validate_current_torches(pending,report,recovery,new,world,*,identity=None):
    newlease=new['supervision_lease'];placed=report['placed'];checks=recovery.get('current_torch_checks')
    if not placed or not isinstance(checks,list)or len(checks)!=len(placed):
        raise ValueError('All original verified torches require fresh server checks')
    targets={point(p['target'])for p in placed};seen=set();requests=set();last_stock=placed[-1]['after_stock']
    old_requests={pending['native_request']['request_id']}|{p['interaction_request']for p in placed}
    for check in checks:
        target=point(check.get('target'));actual=check.get('actual')or{};inventory=check.get('inventory')or{}
        if (target in seen or target not in targets or actual.get('phase')!='done' or actual.get('world_session')!=world
            or actual.get('scan_cells_read')!=1 or actual.get('scan_total_cells')!=1
            or type(actual.get('scan_started_at'))is not int or type(actual.get('scan_ended_at'))is not int
            or not new['time']<=actual['scan_started_at']<=actual['scan_ended_at']<=inventory.get('time',0)
            or inventory.get('world_session')!=world or stock(inventory)!=last_stock
            or actual.get('scan_start_revision')!=newlease['revision'] or actual.get('scan_end_revision')!=newlease['revision']
            or not isinstance(actual.get('blocks'),list)or len(actual['blocks'])!=1
            or point(actual['blocks'][0].get('pos'))!=target
            or not isinstance(actual.get('id'),str)or not actual['id']
            or actual['id']in requests or actual['id']in old_requests
            or not verified_own_torch(actual['blocks'][0],placed,pending['world_session'],pending['task_session'],actual['scan_ended_at'])):
            raise ValueError('Fresh actual torch and unchanged carried stock do not match original placements')
        if identity is not None:
            for frame in (actual,inventory):
                if (server_key(frame.get('server'))!=server_key(identity['server'])
                    or frame.get('dimension')!=identity['dimension']or frame.get('player_uuid')!=identity['player_uuid']
                    or frame.get('world_session')!=world or frame.get('control_revision')!=newlease['revision']
                    or frame.get('health')!=20 or frame.get('manual_movement')is not False
                    or frame.get('screen')or (frame.get('safety_hold')or{}).get('active')
                    or (frame.get('supervision_lease')or{}).get('id')!=newlease['id']
                    or (frame.get('supervision_lease')or{}).get('job_session')!=newlease['job_session']):
                    raise ValueError('Current server torch witness identity or native parking changed')
        scan_cells(actual,target,target,world);seen.add(target);requests.add(actual['id'])


def validate_healthy_host_recovery(pending,state,report,recovery,original_parking):
    """Archive a terminal read-only batch after a proved healthy host logout.

    A health-safety exit never qualifies. The old maintenance parking history
    remains historical; a distinct new world/owner is proved independently.
    """
    previous=recovery.get('maintenance_parking')or{}
    history={**recovery,'kind':'own_torch_preflight_new_maintenance_parking'}
    old=validate_maintenance_recovery(pending,previous,report,history,original_parking,check_torches=False)
    logout=recovery.get('healthy_logout')or{};snapshot=logout.get('snapshot')or{}
    oldlease=previous['supervision_lease'];current=recovery.get('current_parking')or{}
    currentlease=current.get('supervision_lease')or{};world=state.get('world_session')
    if (recovery.get('schema')!=1 or recovery.get('kind')!='own_torch_preflight_healthy_host_recovery'
        or logout.get('lease')!=oldlease['id']or logout.get('job_session')!=oldlease['job_session']
        or logout.get('action')!='LOGOUT'or logout.get('cause')!='parking_invalid'
        or logout.get('confirmed')is not True or logout.get('confirmation')!='network_disconnect_event'
        or type(logout.get('time'))is not int or type(logout.get('confirmed_at'))is not int
        or not previous['time']<=logout['time']<=logout['confirmed_at']
        or type(snapshot.get('time'))is not int or abs(snapshot['time']-logout['time'])>1000
        or snapshot.get('world_session')!=pending['world_session']or snapshot.get('control_revision')!=oldlease['revision']
        or snapshot.get('health')!=20 or snapshot.get('food',0)<18
        or snapshot.get('guard_armed')is not True or snapshot.get('guard_pve_only')is not True
        or snapshot.get('flight')is not True or snapshot.get('manual_movement')is not False
        or snapshot.get('screen') or (snapshot.get('safety_hold')or{}).get('active')
        or not _no_work(snapshot) or snapshot.get('recent_hurt_at')!=previous.get('recent_hurt_at')
        or type(snapshot.get('recent_hurt_at'))is not int or snapshot['recent_hurt_at']>previous['time']
        or stock(snapshot)!=report['placed'][-1]['after_stock']
        or not isinstance(snapshot.get('pos'),list)or len(snapshot['pos'])!=3
        or not _same_pose([snapshot['pos'][0],previous['pos'][1],snapshot['pos'][2]],previous['pos'])
        or abs(snapshot['pos'][1]-previous['pos'][1])>4):
        raise ValueError('Only the exact confirmed healthy bounded-drift parking_invalid logout qualifies')
    version=state.get('kit_version','')
    try:version=tuple(int(v)for v in version.split('.'))
    except (ValueError,AttributeError):version=()
    if (not isinstance(world,str)or not world or world==pending['world_session']
        or version<(2026,10,4,1) or not _native_park(current,world)or not _native_park(state,world)
        or not _no_controller(current)or not _no_controller(state)
        or type(current.get('time'))is not int or current['time']<=logout['confirmed_at']
        or not currentlease.get('id')or currentlease['id']in(pending['lease'],oldlease['id'])
        or not currentlease.get('job_session')or currentlease['job_session']in(pending['task_session'],oldlease['job_session'])
        or any((state.get('supervision_lease')or{}).get(k)!=currentlease.get(k)for k in ('id','job_session','revision'))
        or not _same_pose(state.get('pos'),current.get('pos'))):
        raise ValueError('A distinct fresh guarded parking owner on the repaired host and new world is required')
    for frame in (old,previous,snapshot,current,state):
        if (not isinstance(old.get('player_uuid'),str)or not old['player_uuid']
            or frame.get('player_uuid')!=old['player_uuid']or frame.get('dimension')!=old.get('dimension')
            or server_key(frame.get('server'))!=server_key(old.get('server'))
            or (frame.get('projection_selection')or{}).get('key')!=(old.get('projection_selection')or{}).get('key')
            or not (old.get('projection_selection')or{}).get('key')):
            raise ValueError('Server, dimension, player or selected projection changed across healthy recovery')
    _validate_current_torches(pending,report,recovery,current,world,identity=state)
    return old


def validate_pending(pending, state, report, events, scan_reply, *, external_parking=None,
                     maintenance_recovery=None, original_parking=None):
    ownership=state
    crossworld=False
    if maintenance_recovery is not None:
        crossworld=maintenance_recovery.get('kind')=='own_torch_preflight_healthy_host_recovery'
        ownership=(validate_healthy_host_recovery if crossworld else validate_maintenance_recovery)(
            pending,state,report,maintenance_recovery,original_parking)
    ownedlease=ownership.get('supervision_lease')or{};ownedsafety=ownership.get('supervision_safety')or{}
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
    if (state.get('connected') is not True or not crossworld and state.get('world_session')!=pending.get('world_session')
            or state.get('health')!=20 or state.get('manual_movement') is not False
            or state.get('guard_armed') is not True or state.get('guard_pve_only') is not True
            or state.get('flight') is not True or state.get('screen')
            or not _native_park(state,state['world_session']if crossworld else pending['world_session'])
            or ownedlease.get('kind')!='parking' or ownedlease.get('id')!=pending.get('lease')
            or ownedlease.get('job_session')!=pending.get('task_session')
            or ownedlease.get('revision')!=ownership.get('control_revision')
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
    if pending.get('error')==OWN_TORCH_ERROR:
        event=events[exact[0]];params=event.get('params')or{}
        low,high=point(params.get('min')),point(params.get('max'))
        cells=math.prod(b-a+1 for a,b in zip(low,high))
        scanned=scan_cells(scan_reply,low,high,pending['world_session'])
        if (report.get('world_session')!=pending['world_session']or report.get('task_session')!=pending['task_session']
            or native.get('world_session')!=pending['world_session']or native.get('task_session')!=pending['task_session']
            or native.get('lease_id')!=pending['lease']or native.get('base_revision')!=native['expected_revision']
            or event.get('revision_before')!=native['expected_revision']or event.get('revision_after')!=native['expected_revision']
            or event.get('inventory_delta')!={} or params.get('details')is not True
            or scan_reply.get('scan_cells_read')!=cells or scan_reply.get('scan_total_cells')!=cells
            or scan_reply.get('scan_start_revision')!=native['expected_revision']
            or scan_reply.get('scan_end_revision')!=native['expected_revision']
            or type(scan_reply.get('scan_started_at'))is not int or type(scan_reply.get('scan_ended_at'))is not int
            or scan_reply['scan_started_at']>scan_reply['scan_ended_at']
            or not scanned or scan_reply.get('scan_entities')!=[]
            or any(not verified_own_torch(row,placed,pending['world_session'],pending['task_session'],scan_reply['scan_started_at'])
                   for row in scanned.values())):
            raise ValueError('Stopped movement scan is not exclusively passable same-batch verified torches')
        for event in events[exact[0]+1:]:
            if event.get('inventory_delta')!={}:
                raise ValueError('Inventory mutation followed the stopped own-torch preflight')
            if event.get('op') in ('navigate','material_job_park'):
                params=event.get('params')or{};target=params.get('target',params.get('park_target'))
                if (params.get('task_session')!=pending['task_session']
                    or not _same_pose(target,ownership['pos'],.6)
                    or event['op']=='navigate' and (params.get('air_only')is not True
                       or not _same_column_rise(event.get('position_before'),target))):
                    raise ValueError('Post-preflight movement was not the exact original same-column high parking cleanup')
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
        marker=directory/'own-torch-maintenance-recovery.json';maintenance=None;original=None
        if marker.exists():
            maintenance=read(marker)
            original=read(directory/'final-snapshot.json')
            for field,source in (('idle_handoff','idle_handoff_path'),('prelease_scan','prelease_scan_reply_path'),
                                 ('maintenance_parking','maintenance_parking_path')):
                maintenance[field]=read(Path(maintenance[source]))
            if 'maintenance_finish_path' in maintenance:
                maintenance['maintenance_finish']=read(Path(maintenance['maintenance_finish_path']))
            if maintenance.get('kind')=='own_torch_preflight_healthy_host_recovery':
                maintenance['healthy_logout']=read(Path(maintenance['healthy_logout_receipt_path']))
                maintenance['current_parking']=read(Path(maintenance['current_parking_path']))
            raw=Path(maintenance['maintenance_events_path']).read_bytes()
            if len(raw)>8*1024*1024:raise ValueError('Maintenance journal exceeds bound')
            evidence[maintenance['maintenance_events_path']]=hashlib.sha256(raw).hexdigest()
            maintenance['maintenance_events']=[json.loads(row)for row in raw.splitlines()if row.strip()]
            for check in maintenance.get('current_torch_checks',[]):
                check['actual']=read(Path(check['actual_path']));check['inventory']=read(Path(check['inventory_path']))
        count=validate_pending(pending,state,report,events,reply,external_parking=external,
                               maintenance_recovery=maintenance,original_parking=original)
        for index,placed in enumerate(report['placed']):
            target=point(placed['target']);last=placed['before_time']
            key=hashlib.sha256((pending['world_session']+':'+','.join(map(str,target))).encode()).hexdigest()
            if read(worker.root/'lighting-intents'/(key+'.json'))!=placed:raise ValueError('Original durable intent differs')
            for frame in (1,2):
                actual=read(directory/f'actual-torch-{index}-frame-{frame}.json')
                inventory=read(directory/f'inventory-after-{index}-frame-{frame}.json')
                if not later_torch_frame(actual,inventory,target,pending['world_session'],placed['before_stock'],last):
                    raise ValueError('Original two-frame placement witness failed')
                last=inventory['time']
        record={'outcome':'terminal_readonly_preflight_partial_verified','request_replayed':False,
                'region_completed':False,'original_pending':pending,'evidence_sha256':evidence,
                'placed_verified':count,'observed_at':state['time']}
        if maintenance is not None:
            record.update(outcome='terminal_readonly_own_torch_preflight_after_distinct_maintenance_parking',
                original_native_parking=original,
                current_maintenance_lease=state['supervision_lease'],old_finish_reinterpreted_as_current=False)
            if 'maintenance_finish' in maintenance:
                record.update(historical_maintenance_finish=maintenance['maintenance_finish'],
                    historical_snapshot_modified=False,
                    historical_maintenance_proof='exact_native_keep_receipt_and_matching_parking_confirmation')
            if maintenance.get('kind')=='own_torch_preflight_healthy_host_recovery':
                record.update(outcome='terminal_readonly_own_torch_preflight_after_verified_healthy_host_recovery',
                    original_world_session=pending['world_session'],current_world_session=state['world_session'],
                    healthy_logout=maintenance['healthy_logout'],old_world_work_replayed=False)
        worker.book.setdefault('pending_reconciliations',[]).append(record)
        worker.book['batches'].append({'region_index':pending['region_index'],'campaign':worker.book.get('campaign'),
             'mode':'lighting','directory':str(directory),'partial_verified':True,'placed_verified':count,
             'region_completed':False,'eligible_remaining':None})
        worker.book.update(pending=None,phase='waiting_resume',last_revision=None,parking_lease=None,
                           reason='Read-only preflight reconciled; fresh scan required before continuing')
        worker.save()
    return worker.status()
