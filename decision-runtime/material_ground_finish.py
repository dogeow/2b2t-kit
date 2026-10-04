"""A returned ground walk may settle at a new, physically observed pose.

Only exact owned native evidence permits this path. Old arrival bounds prove
the original walk result; fresh stable frames and full current-body scans
authorize a distinct vertical safety ascent. Unknown outcomes are retained.
"""
import json
import math
import time
from functools import wraps
from copy import deepcopy


class GroundFinishStop(RuntimeError):
    pass


def retain_evidence_failure(fn):
    @wraps(fn)
    def guarded(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except GroundFinishStop:raise
        except (RuntimeError,KeyError,TypeError,ValueError,OSError) as error:
            raise GroundFinishStop('Ground finish proof unavailable; retain original owner: '+str(error))from error
    return guarded


def observe(c):
    # No interface wait or stale-status retry may extend the settlement budget.
    return c.raw(wait_seconds=0)


def main_inventory(state):
    rows=state.get('inventory')
    if not isinstance(rows,list):raise GroundFinishStop('Ground finish lacks complete main inventory')
    main=[row for row in rows if isinstance(row,dict)and type(row.get('slot'))is int and 0<=row['slot']<36]
    if (len(main)!=36 or {row['slot']for row in main}!=set(range(36))
            or any(not isinstance(row.get('item'),str)or type(row.get('count'))is not int or row['count']<0 for row in main)):
        raise GroundFinishStop('Ground finish lacks complete main inventory')
    return sorted(main,key=lambda row:row['slot'])


def optional_main_inventory(state):
    # Missing optional rebase evidence must not turn a returned native walk
    # into an uncertain action or prevent its original receipt from logging.
    try:return main_inventory(state)
    except GroundFinishStop:return None


def vector(value):
    return isinstance(value,list)and len(value)==3 and all(type(v)in(int,float)and math.isfinite(v)for v in value)


def _busy_controller(s):
    return (any(s.get(k)for k in ('navigating','native_material_busy','printing','chopping','borer_active',
                                 'planter_active','feeder_active','fisher_active'))
            or any((s.get(k)or{}).get('active')for k in ('build_job','concrete','gravel','projection_batch'))
            or any((s.get('professional_printer')or{}).get(k)for k in ('enabled','owned','travel_pending','waiting_for_server')))


def _idle_ground_frame(s,*,returned_scan=None):
    """A returned scan's own pending publication is not another unknown read."""
    lease=s.get('supervision_lease')or{};menu=s.get('menu')or{};keys=s.get('movement_keys')
    selected=s.get('projection_selection');hold=s.get('safety_hold')
    pending=s.get('pending_scan')
    pending_known=(returned_scan is not None and isinstance(pending,dict)
                   and pending.get('id')==returned_scan and pending.get('world_session')==s.get('world_session')
                   and pending.get('control_revision')==s.get('control_revision'))
    if (s.get('connected')is not True or s.get('game_mode')!='survival'
            or any(not isinstance(s.get(k),str)or not s[k]for k in ('server','dimension','world_session','player_uuid'))
            or type(s.get('control_revision'))is not int or type(s.get('time'))is not int
            or not isinstance(selected,dict)or not isinstance(selected.get('key'),str)or not selected['key']
            or any(not isinstance(selected.get(k),list)or len(selected[k])!=3
                   or any(type(v)is not int for v in selected[k])for k in ('min','max'))
            or s.get('health')!=20 or s.get('food',0)<18 or s.get('flight')is not False
            or s.get('on_ground')is not True or s.get('screen')!=''or s.get('interface_paused')is True
            or s.get('manual_movement')is not False or s.get('under_water')is not False
            or not isinstance(hold,dict)or hold.get('active')is not False or s.get('health_recovery_hold')
            or any(s.get(k)is not True for k in ('guard_armed','guard_pve_only','kill_aura','auto_log'))
            or s.get('guard_busy')is not False
            or _busy_controller(s)
            or pending is not None and not pending_known
            or menu.get('type')!='InventoryMenu'or type((menu.get('cursor')or{}).get('count'))is not int
            or menu['cursor']['count']!=0
            or not vector(s.get('pos'))or not vector(s.get('velocity'))
            or math.hypot(s['velocity'][0],s['velocity'][2])>.03 or abs(s['velocity'][1])>.1
            or not isinstance(keys,dict)or not {'forward','back','jump','sneak'}.issubset(keys)
            or any(v is not False for v in keys.values())
            or type(s.get('recent_hurt_at'))is not int
            or lease.get('kind')!='materials'or lease.get('world_session')!=s['world_session']
            or lease.get('revision')!=s['control_revision']or lease.get('remote_finish')!='guard'
            or any(not isinstance(lease.get(k),str)or not lease[k]for k in ('id','job_session'))):
        raise GroundFinishStop('A complete idle grounded read frame is unavailable')
    main_inventory(s)


def idle_read_proof(c,op,params,before,receipt,current):
    """Capture original frames only at an exact successfully returned read."""
    try:
        rid=getattr(c,'last',None);terminal=getattr(c,'last_terminal_evidence',None)or{}
        phase=receipt.get('phase');lease=before.get('supervision_lease')or{}
        if (op not in ('scan','snapshot')or not isinstance(rid,str)or not rid
                or receipt.get('id')!=rid or terminal.get('request_id')!=rid or terminal.get('op')!=op
                or terminal.get('phase')!=phase or phase not in ((None,'done')if op=='snapshot'else('done',))
                or terminal.get('world_session')!=c.world or terminal.get('task_session')!=c.task
                or terminal.get('revision_after')!=c.rev or type(c.rev)is not int
                or getattr(c,'unconfirmed_native_request',None)is not None
                or lease.get('id')!=c.heartbeat.id or lease.get('job_session')!=c.task
                or before.get('world_session')!=c.world or before.get('control_revision')!=c.rev
                or receipt.get('world_session')!=c.world or receipt.get('control_revision')!=c.rev
                or current.get('last_request')!=rid):
            return None
        _idle_ground_frame(before)
        _idle_ground_frame(receipt,returned_scan=rid if op=='scan'else None)
        _idle_ground_frame(current,returned_scan=rid if op=='scan'else None)
        fields=('server','dimension','world_session','player_uuid','projection_selection','control_revision',
                'recent_hurt_at','recent_attacker','safety_hold')
        if (any(receipt.get(k)!=before.get(k)or current.get(k)!=before.get(k)for k in fields)
                or any((frame.get('supervision_lease')or{}).get(k)!=lease.get(k)
                       for frame in (receipt,current)for k in ('id','job_session','kind','world_session','revision','remote_finish'))
                or main_inventory(before)!=main_inventory(receipt)or main_inventory(before)!=main_inventory(current)
                or not before['time']<=receipt['time']<=current['time']
                or math.dist(before['pos'],receipt['pos'])>.08 or math.dist(before['pos'],current['pos'])>.08):
            return None
        if op=='scan':
            low,high=params.get('min'),params.get('max')
            if (any(not isinstance(v,list)or len(v)!=3 or any(type(n)is not int for n in v)for v in (low,high))
                    or any(low[i]>high[i]for i in range(3))):return None
            total=math.prod(high[i]-low[i]+1 for i in range(3))
            if (not isinstance(receipt.get('blocks'),list)
                    or any(type(receipt.get(k))is not int or receipt[k]!=total for k in ('scan_cells_read','scan_total_cells'))
                    or any(type(receipt.get(k))is not int or receipt[k]!=c.rev for k in ('scan_start_revision','scan_end_revision'))):
                return None
        return {'idle_ground_read_schema':1,'op':op,'phase':phase,'request_id':rid,
                'world_session':c.world,'task_session':c.task,'revision':c.rev,'params':deepcopy(params),
                'before':deepcopy(before),'returned_receipt':deepcopy(receipt),'terminal':deepcopy(current),
                'before_inventory':deepcopy(main_inventory(before)),
                'before_damage':{k:before.get(k)for k in ('recent_hurt_at','recent_attacker')},
                'before_safety_hold':deepcopy(before['safety_hold']),
                'original_walk_performed':False,'original_request_replayed':False}
    except (GroundFinishStop,AttributeError,KeyError,TypeError,ValueError):
        return None  # Optional evidence cannot change a returned native result.


@retain_evidence_failure
def idle_context(c):
    cached=getattr(c,'last_owned_idle_ground_read',None)
    if not isinstance(cached,dict)or cached.get('idle_ground_read_schema')!=1:
        raise GroundFinishStop('Ground finish has no exact current idle-read baseline')
    proof=idle_read_proof(c,cached['op'],cached['params'],cached['before'],cached['returned_receipt'],cached['terminal'])
    if proof!=cached or cached['request_id']!=c.last:
        raise GroundFinishStop('Original idle ground read identity or complete frames changed')
    return cached


@retain_evidence_failure
def context(c):
    proof=getattr(c,'last_owned_ground_walk',None)
    if not isinstance(proof,dict)or proof.get('pose_rebase_schema')!=1:
        raise GroundFinishStop('Ground finish has no exact supported completed-walk proof')
    term=proof.get('terminal')or{};params=proof.get('params')or{}
    if (proof.get('op')!='walk'or proof.get('phase')!='done'or params.get('restore_flight')is not False
            or params.get('water_descend')or 'freefall_brake_y'in params
            or proof.get('world_session')!=c.world or proof.get('task_session')!=c.task
            or proof.get('revision')!=c.rev or not isinstance(proof.get('request_id'),str)or not proof['request_id']
            or term.get('last_request')!=proof['request_id']or term.get('control_revision')!=c.rev
            or type(term.get('time'))is not int or type(term.get('recent_hurt_at'))is not int
            or term.get('flight')is not False
            or not vector(term.get('pos'))or not vector(params.get('target'))
            or proof.get('before_inventory')!=main_inventory(term)
            or not isinstance(term.get('player_uuid'),str)or not term['player_uuid']
            or not isinstance(term.get('projection_selection'),dict)
            or proof.get('before_safety_hold')!=term.get('safety_hold')
            or proof.get('before_damage')!={k:term.get(k)for k in ('recent_hurt_at','recent_attacker')}):
        raise GroundFinishStop('Original completed ground walk identity or conservation is unproved')
    check(c,term,proof,expected_request=proof['request_id'],check_return=False)
    return proof


@retain_evidence_failure
def check(c,s,proof,*,expected_request=None,check_return=True,grounded=False,flight=False):
    term=proof['terminal'];lease=s.get('supervision_lease')or{};keys=s.get('movement_keys');hold=s.get('safety_hold')
    if (s.get('connected')is not True or s.get('world_session')!=c.world
            or s.get('control_revision')!=c.rev or s.get('last_request')!=(expected_request or c.last)
            or s.get('server')!=term.get('server')or s.get('dimension')!=term.get('dimension')
            or s.get('player_uuid')!=term.get('player_uuid')or s.get('projection_selection')!=term.get('projection_selection')
            or s.get('screen')!=''or s.get('health')!=20 or s.get('food',0)<18
            or s.get('flight')is not flight or s.get('interface_paused')is True
            or s.get('manual_movement')is not False or s.get('under_water')is not False
            or s.get('guard_armed')is not True or s.get('guard_pve_only')is not True or s.get('guard_busy')is not False
            or s.get('kill_aura')is not True or s.get('auto_log')is not True
            or _busy_controller(s)or s.get('pending_scan')is not None
            or not isinstance(hold,dict)or hold.get('active')is not False or hold!=term.get('safety_hold')
            or any(s.get(k)!=term.get(k)for k in ('recent_hurt_at','recent_attacker'))
            or lease.get('kind')!='materials'or lease.get('id')!=c.heartbeat.id
            or lease.get('job_session')!=c.task or lease.get('world_session')!=c.world
            or lease.get('revision')!=c.rev or lease.get('remote_finish')!='guard'
            or not vector(s.get('pos'))or not vector(s.get('velocity'))
            or not isinstance(keys,dict)or not {'forward','back','jump','sneak'}.issubset(keys)
            or any(v is not False for v in keys.values())
            or type(s.get('time'))is not int or s['time']<term['time']
            or main_inventory(s)!=proof['before_inventory']):
        raise GroundFinishStop('Ground finish world, owner, inventory, health, input or activity changed')
    if check_return:
        returned=getattr(c,'last_terminal_evidence',None)or{}
        known=(returned.get('phase')=='done'and returned.get('op')in ('walk','scan','material_job_park')
               or flight is True and returned.get('phase')=='done'and returned.get('op')=='navigate'
               or returned.get('phase')is None and returned.get('op')=='snapshot')
        if (not known or returned.get('request_id')!=c.last or returned.get('task_session')!=c.task
                or returned.get('world_session')!=c.world or returned.get('revision_after')!=c.rev
                or getattr(c,'native_inflight',None)is not None
                or getattr(c,'unconfirmed_native_request',None)is not None):
            raise GroundFinishStop('Ground finish retains an unproved original native outcome; no next operation')
    if proof.get('idle_ground_read_schema')==1:
        # This is a new ascent baseline, never a manufactured completed walk.
        _idle_ground_frame(s) if not flight else None
        if (s.get('menu',{}).get('type')!='InventoryMenu'or (s.get('menu',{}).get('cursor')or{}).get('count')!=0):
            raise GroundFinishStop('Idle read ground finish menu changed')
    if grounded and (s.get('on_ground')is not True or math.hypot(s['velocity'][0],s['velocity'][2])>.03
                    or abs(s['velocity'][1])>.1):
        raise GroundFinishStop('Current ground finish pose is not physically settled')
    return s


@retain_evidence_failure
def settle(c,state):
    walk=getattr(c,'last_owned_ground_walk',None)
    proof=context(c)if walk is not None else idle_context(c)
    idle=proof.get('idle_ground_read_schema')==1
    term=proof['terminal'];origin=term['pos'];first=None
    if state.get('pending_scan')is not None or state.get('last_request')!=c.last:
        state=after_return(c,proof,grounded=False)
    deadline=time.monotonic()+3
    while True:
        check(c,state,proof)
        pos=state['pos'];velocity=state['velocity']
        if (idle and math.dist(pos,origin)>.08
                or not idle and (math.hypot(pos[0]-origin[0],pos[2]-origin[2])>1.5 or abs(pos[1]-origin[1])>1.5)):
            raise GroundFinishStop('Known walk residual exceeded the bounded current-pose settlement domain')
        if state.get('on_ground')is True and math.hypot(velocity[0],velocity[2])<=.03 and abs(velocity[1])<=.1:
            if first is not None and state['time']>first['time']and state['time']-first['time']>=400 and math.dist(pos,first['pos'])<=.08:
                evidence={'scope':'known_owned_idle_ground_baseline'if idle else 'exact_owned_completed_walk_current_pose_rebase',
                    'world_session':c.world,'walk_request_id':None if idle else proof['request_id'],
                    'idle_read_request_id':proof['request_id']if idle else None,
                    'last_returned_request':c.last,'original_terminal_pos':origin,
                    'old_target':None if idle else proof['params']['target'],'old_arrival':None if idle else proof['params'].get('arrival',.65),
                    'settled':pos,'observed_span_ms':state['time']-first['time'],'original_walk_replayed':False,
                    'original_walk_performed':not idle,
                    'frames':[first,state],'new_ascent_permitted':False}
                (c.out/'park-ground-settlement.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
                c.ground_finish_rebase={'proof':proof,'settled':state,'evidence':evidence}
                return state
            if first is None or math.dist(pos,first['pos'])>.08:first=state
        else:first=None
        if time.monotonic()>=deadline:raise GroundFinishStop('Known ground walk has not settled within three seconds; no new movement')
        time.sleep(.05);state=observe(c)


@retain_evidence_failure
def _scan(c,low,high,tag):
    try:r=c.request('scan',min=low,max=high,details=True,seconds=30)
    except Exception as error:raise GroundFinishStop('Ground finish scan outcome remains unproved: '+str(error))from error
    (c.out/(tag+'.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    total=math.prod(b-a+1 for a,b in zip(low,high))
    term=c.ground_finish_rebase['proof']['terminal']
    if (r.get('id')!=c.last or r.get('phase')!='done'or r.get('world_session')!=c.world
            or r.get('server')!=term['server']or r.get('dimension')!=term['dimension']
            or any(type(r.get(k))is not int or r[k]!=c.rev for k in ('control_revision','scan_start_revision','scan_end_revision'))
            or r.get('scan_cells_read')!=total or r.get('scan_total_cells')!=total or not isinstance(r.get('blocks'),list)):
        raise GroundFinishStop('Complete current same-revision ground finish scan is unproved')
    from lighting_cli import scan_cells
    try:cells=scan_cells(r,low,high,c.world)
    except Exception as error:raise GroundFinishStop('Ground finish block/entity scan is incomplete: '+str(error))from error
    if any(any(type(row.get(k))is not bool for k in ('solid','fluid','passable','block_entity'))for row in cells.values()):
        raise GroundFinishStop('Current ground finish collision details are unproved')
    return r,cells


@retain_evidence_failure
def after_return(c,proof,grounded=True,flight=False):
    # A complete synchronous scan can precede pending_scan removal in status.
    deadline=time.monotonic()+3
    while True:
        s=observe(c)
        if s.get('pending_scan')is None and s.get('last_request')==c.last:
            return check(c,s,proof,grounded=grounded,flight=flight)
        lease=s.get('supervision_lease')or{}
        if (s.get('connected')is not True or s.get('world_session')!=c.world or s.get('health')!=20
                or s.get('manual_movement')or lease.get('id')!=c.heartbeat.id or lease.get('job_session')!=c.task
                or time.monotonic()>=deadline):
            raise GroundFinishStop('Original returned ground scan status remains unproved; no next operation')
        time.sleep(.05)


@retain_evidence_failure
def ascend(c,state):
    record=getattr(c,'ground_finish_rebase',None)
    if not isinstance(record,dict):raise GroundFinishStop('Current-pose ground rebase proof is absent')
    proof=record['proof'];check(c,state,proof,grounded=True)
    start=list(state['pos']);low=[math.floor(start[0]-.35),-64,math.floor(start[2]-.35)]
    high=[math.floor(start[0]+.35),319,math.floor(start[2]+.35)]
    column,cells=_scan(c,low,high,'park-ground-current-column')
    current=after_return(c,proof)
    if math.dist(current['pos'],start)>.08:raise GroundFinishStop('Actual ground pose moved during its full-body column proof')
    tops=[p[1]+1 for p,row in cells.items()if row.get('fluid')is True or row.get('passable')is not True]
    if not tops:raise GroundFinishStop('Current ground column has no observed support')
    ground=max(tops);target=[current['pos'][0],max(ground+24,current['pos'][1]+24),current['pos'][2]]
    if target[1]+1.8>=319 or math.dist(current['pos'],target)>31:
        raise GroundFinishStop('Current column cannot support a bounded high ascent')
    sweep_low=[low[0],math.floor(current['pos'][1]),low[2]]
    sweep_high=[high[0],math.floor(target[1]+1.8),high[2]]
    body,body_cells=_scan(c,sweep_low,sweep_high,'park-ground-current-ascent-body')
    for pos,row in body_cells.items():
        below_chest=(row.get('state','').startswith(('Block{minecraft:chest}','Block{minecraft:ender_chest}'))
                     and row.get('fluid')is False and pos[1]+14/16<=current['pos'][1]+1e-6)
        if not below_chest and not (row.get('passable')is True and row.get('fluid')is False and row.get('block_entity')is False):
            raise GroundFinishStop('Current ground ascent body contains an obstacle; no movement')
    from lighting_cli import swept_entities
    try:entities=swept_entities(body,current['pos'],target,sweep_low,sweep_high,c.world,c.rev)
    except Exception as error:raise GroundFinishStop('Current ground ascent entity proof is unverified: '+str(error))from error
    if entities:raise GroundFinishStop('A current entity intersects the exact ascent body; no movement')
    fresh=after_return(c,proof)
    if math.dist(fresh['pos'],start)>.08:raise GroundFinishStop('Current ground pose changed after its actual ascent scan')
    current=fresh
    actual_low=[math.floor(min(current['pos'][i],target[i])-(.35 if i!=1 else 0))for i in range(3)]
    actual_high=[math.floor(max(current['pos'][i],target[i])+(.35 if i!=1 else 1.8))for i in range(3)]
    if (math.dist(current['pos'],target)>31 or math.dist(current['pos'],start)>.08
            or any(not sweep_low[i]<=actual_low[i]<=actual_high[i]<=sweep_high[i]for i in range(3))):
        raise GroundFinishStop('Actual ascent origin left the fully scanned body corridor; no movement')
    if swept_entities(body,current['pos'],target,sweep_low,sweep_high,c.world,c.rev):
        raise GroundFinishStop('An entity intersects the latest actual ascent origin; no movement')
    try:nav=c.request('navigate',target=target,arrival=.25,seconds=90,air_only=True)
    except Exception as error:raise GroundFinishStop('Current ground ascent outcome remains unknown; no retry: '+str(error))from error
    (c.out/'park-ground-ascent-reply.json').write_text(json.dumps(nav,ensure_ascii=False,indent=2)+'\n')
    if (nav.get('id')!=c.last or nav.get('phase')!='done'or nav.get('world_session')!=c.world
            or nav.get('control_revision')!=c.rev):
        raise GroundFinishStop('Current ground ascent was not confirmed; no retry or finish')
    result=after_return(c,proof,grounded=False,flight=True)
    if math.dist(result['pos'],target)>.55 or result['pos'][1]-ground<20:
        raise GroundFinishStop('Actual bounded high arrival or inventory is unproved')
    (c.out/'park-ground-high-arrival.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    # The native setter requires Flight: publish it after real confirmed ascent.
    try:park=c.request('material_job_park',park_target=target)
    except Exception as error:raise GroundFinishStop('High park setter outcome remains unknown: '+str(error))from error
    if (park.get('id')!=c.last or park.get('phase')!='done'or park.get('world_session')!=c.world
            or park.get('control_revision')!=c.rev):
        raise GroundFinishStop('High park setter was not accepted')
    result=after_return(c,proof,grounded=False,flight=True)
    if math.dist(result['pos'],target)>.55 or result['pos'][1]-ground<20:
        raise GroundFinishStop('Current high parking position changed after setter')
    c.park_target=list(target)  # Adopt only the exact accepted canonical setter.
    c.ground_finish_rebase=None
    return result
