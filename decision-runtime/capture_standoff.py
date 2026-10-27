"""Leave a named bait's melee area through the existing native owner, once."""
import math,time
from capture_target import NAME,BAIT_TYPES,acknowledgement
from loaded_hostiles import read

def validate(state,request,ack,mob,destination):
    lease=state.get('supervision_lease')or{}
    if (state.get('connected')is not True or state.get('health')!=20
            or state.get('manual_movement')is not False or state.get('screen')
            or state.get('guard_armed')is not True or state.get('guard_pve_only')is not True
            or state.get('guard_busy')is not False or state.get('health_recovery_hold')
            or state.get('safety_hold',{}).get('active')
            or lease.get('kind')!='materials' or not lease.get('id') or not lease.get('job_session')
            or request.get('world_session')!=state.get('world_session') or lease.get('world_session')!=state.get('world_session')
            or request.get('lease_id')!=lease['id'] or request.get('task_session')!=lease['job_session']
            or request.get('player_uuid')!=state.get('player_uuid')
            or type(request.get('control_revision'))is not int or request['control_revision']>state.get('control_revision',-1)
            or not ack or ack.get('active')is not True or ack.get('named')is not True
            or ack.get('id')!=request.get('id') or ack.get('entity_uuid')!=request.get('entity_uuid')
            or request.get('expected_type')not in BAIT_TYPES
            or mob.get('uuid')!=request.get('entity_uuid') or mob.get('type')!=request.get('expected_type')
            or mob.get('health')!=20 or mob.get('has_custom_name')is not True or mob.get('name')!=NAME):
        raise ValueError('Retreat requires the same healthy named bait and active sole owner')
    try:
        points=[state['pos'],destination,mob['bounds']['min'],mob['bounds']['max']]
        if any(not isinstance(p,list)or len(p)!=3 or any(type(v)not in(int,float)or not math.isfinite(v)for v in p)for p in points):raise ValueError()
        lo,hi=mob['bounds']['min'],mob['bounds']['max']
        if any(lo[i]>=hi[i]for i in range(3)):raise ValueError()
        player_lo=[destination[0]-.3,destination[1],destination[2]-.3]
        player_hi=[destination[0]+.3,destination[1]+1.8,destination[2]+.3]
        gap=sum(max(lo[i]-player_hi[i],player_lo[i]-hi[i],0)**2 for i in range(3))
        if gap<9 or math.dist(destination,state['pos'])>12 or math.dist(destination,mob['pos'])>32:raise ValueError()
    except(KeyError,TypeError,ValueError):
        raise ValueError('A finite local retreat must put the full player body three blocks beyond the bait body')from None

def retreat(builder,protection,destination):
    """Normal navigation preflights the path; an interrupted move is never replayed."""
    if 'named_bait_retreat'in builder.book:
        raise RuntimeError('Original named-bait retreat already has a journal; observe it without replay')
    request=protection['request'];state=builder.check();frame=read(builder.root,state)
    if frame is None or frame['truncated']:raise RuntimeError('Fresh complete bait observation required')
    observed=next((v for v in frame['hostiles']if v['uuid']==request['entity_uuid']),None)
    named=next((v for v in state.get('entities',[])if v['uuid']==request['entity_uuid']),None)
    if observed is None or named is None:raise RuntimeError('Exact nearby named bait is no longer observed')
    mob={**observed,'name':named.get('name')};ack=acknowledgement(builder.root,request,int(time.time()*1000))
    validate(state,request,ack,mob,destination)
    entry=dict(pending=True,from_pose=state['pos'],target=destination,bait_before=mob,complete=False)
    builder.book['named_bait_retreat']=entry;builder.save()
    result=builder.n('navigate',target=destination,arrival=.1,air_only=True,seconds=25)
    if result.get('phase')!='done':raise RuntimeError('Original retreat is not complete; retain its receipt')
    entry.update(pending=False,complete=True,receipt=result['id'],evidence_scope='native_pilot_retreat_not_bait_transport_or_survival_credit');builder.save()
    return entry
