"""Arm one runtime attack exclusion through the existing sole material owner.

The acknowledgement protects an identity; it proves neither capture nor naming.
Unknown acknowledgements are retained and never rewritten or replayed.
"""
import json,time,uuid,math
from pathlib import Path
from material_plan import inventory_counts
from kit_runtime.journal import write_json

NAME='Kit Iron Farm'
ENGINE_VERSIONS=frozenset(('1.8.14','1.8.15','1.8.16','1.8.17','1.8.18','1.8.19','1.8.20','1.8.21','1.8.22','1.8.23','1.8.24','1.8.25','1.8.26','1.8.27','1.8.28'))
BAIT_TYPES=frozenset(('minecraft:zombie','minecraft:drowned'))

def request_for(state,entity_uuid,now,identity,observation=None,*,boat_uuid=None,window_ms=15000):
    if(type(window_ms)is not int or not 15000<=window_ms<=60000
       or window_ms!=15000 and state.get('runtime_version')not in('1.8.26','1.8.27','1.8.28')):
        raise ValueError('Extended bounded preparation requires runtime 1.8.26 and at most 60 seconds')
    if boat_uuid is not None:
        uuid.UUID(boat_uuid)
        if state.get('runtime_version')not in('1.8.21','1.8.22','1.8.23','1.8.24','1.8.25','1.8.26','1.8.27','1.8.28'):raise ValueError('Boat-bound protection needs runtime 1.8.21, 1.8.22 or 1.8.23')
    lease=state.get('supervision_lease')or{}
    mob=next((r for r in state.get('entities',[])if r.get('uuid')==entity_uuid),None)
    from loaded_hostiles import valid as current_hostiles
    if isinstance(observation,dict)and current_hostiles(observation,state,now):
        mob=next((r for r in observation['hostiles']if r.get('uuid')==entity_uuid),mob)
    if mob is None and isinstance(observation,dict):
        if (observation.get('world_session')==state.get('world_session')
            and observation.get('id')==state.get('last_request') and observation.get('phase')=='done'
            and observation.get('scan_total_cells',0)>0
            and observation.get('scan_cells_read')==observation.get('scan_total_cells')
            and not observation.get('unloaded_chunks')
            and 0<=now-observation.get('time',0)<=1000):
            mob=next((r for r in observation.get('scan_entities',[])if r.get('uuid')==entity_uuid),None)
    if (state.get('connected')is not True or state.get('screen')or state.get('manual_movement')is not False
        or state.get('health')!=20 or state.get('guard_armed')is not True
        or state.get('guard_pve_only')is not True or state.get('guard_busy')is not False
        or state.get('safety_hold',{}).get('active')or state.get('health_recovery_hold')
        or lease.get('kind')!='materials'or not lease.get('id')or not lease.get('job_session')
        or lease.get('world_session')!=state.get('world_session')
        or not 0<=now-state.get('time',0)<=1000 or state.get('runtime_version')not in ENGINE_VERSIONS
        or boat_uuid is None and inventory_counts(state)['minecraft:name_tag']!=1
        or not mob or mob.get('type')not in BAIT_TYPES or mob.get('health')!=20
        or mob.get('type')=='minecraft:drowned'and state.get('runtime_version')not in ('1.8.19','1.8.20','1.8.21','1.8.22','1.8.23','1.8.24','1.8.25','1.8.26','1.8.27','1.8.28')
        or mob.get('type')=='minecraft:drowned'and state.get('runtime_version')in('1.8.20','1.8.21','1.8.22','1.8.23','1.8.24','1.8.25','1.8.26','1.8.27','1.8.28')and (not mob.get('main_hand')or mob['main_hand']=='minecraft:trident')
        or mob.get('is_baby')is not False or mob.get('has_custom_name')is not False
        or math.dist(mob['pos'],state['pos'])>64):
        raise ValueError('Fresh healthy unowned adult zombie, one tag, and current idle material owner required')
    uuid.UUID(entity_uuid)
    result={'protocol':1,'id':identity,'world_session':state['world_session'],
            'lease_id':lease['id'],'task_session':lease['job_session'],
            'control_revision':state['control_revision'],'player_uuid':state['player_uuid'],
            'entity_uuid':entity_uuid,'expected_type':mob['type'],
            'issued_at':now,'expires_at':now+window_ms}
    if boat_uuid is not None:result['boat_uuid']=boat_uuid
    return result

def acknowledgement(root,request,now):
    try:reply=json.loads((Path(root)/'capture-target-state.json').read_text())
    except(OSError,ValueError):return None
    if(reply.get('protocol')!=1 or reply.get('runtime_version')not in ENGINE_VERSIONS
       or reply.get('id')!=request['id'] or not 0<=now-reply.get('time',0)<=750):return None
    return reply

def arm(queue,entity_uuid,out,*,observation=None,boat_uuid=None,window_ms=15000):
    out=Path(out);out.mkdir(exist_ok=False);book={'complete':False,'pending':'arm','capture_credit':0,'name_credit':0}
    path=out/'protection.json';state=queue.status();request=request_for(state,entity_uuid,int(time.time()*1000),'capture-'+uuid.uuid4().hex,observation,boat_uuid=boat_uuid,window_ms=window_ms)
    existing=Path(queue.root)/'capture-target-state.json'
    if existing.exists():
        current=json.loads(existing.read_text())
        if current.get('active'):raise RuntimeError('An existing protected target must not be replaced')
    book.update(request=request,player_before=state['pos']);write_json(path,book)
    write_json(Path(queue.root)/'capture-target.json',request)
    end=time.monotonic()+5
    while time.monotonic()<end:
        queue.status();reply=acknowledgement(queue.root,request,int(time.time()*1000))
        if reply is not None:
            if reply.get('active')is not True or reply.get('entity_uuid')!=entity_uuid:
                book.update(pending=None,rejection=reply);write_json(path,book)
                raise RuntimeError('Exact target protection was rejected; no approach authorized')
            book.update(complete=True,pending=None,acknowledgement=reply);write_json(path,book);return book
        time.sleep(.1)
    write_json(path,book)
    raise RuntimeError('Original protection acknowledgement unknown; do not rewrite or approach')
