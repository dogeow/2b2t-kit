"""One bounded inverse of a known completed leg after cargo injury.

This never resumes transport, replays an uncertain move, or overrides a player
health/manual hold. Missing/changed passengers must not block rescue of survivors.
"""
import math,time
from vehicle_observation import read_frame
from kit_runtime.journal import write_json

def retreat_plan(state,book,move,reply,frame):
    lease=state.get('supervision_lease')or{}
    if(not frame or state.get('connected')is not True or state.get('world_session')!=book.get('world_session')
       or state.get('manual_movement')is not False or state.get('health')!=20 or state.get('food',0)<18
       or state.get('screen')or state.get('safety_hold',{}).get('active')or state.get('health_recovery_hold')
       or state.get('guard_armed')is not True or state.get('guard_pve_only')is not True
       or state.get('guard_busy')or state.get('navigating')or state.get('native_material_busy')
       or lease.get('kind')!='materials'or not book.get('lease_id')or lease.get('id')!=book['lease_id']
       or lease.get('job_session')!=book.get('task_session')or lease.get('world_session')!=book['world_session']
       or reply.get('phase')!='done'or reply.get('world_session')!=book['world_session']
       or move.get('request_id')!=reply.get('id')or move.get('op')!='navigate'
       or reply.get('control_revision')!=state.get('control_revision')
       or not isinstance(state.get('movement_keys'),dict)or any(state['movement_keys'].values())):return None
    read=book.get('last_read_only')or{}
    if state.get('last_request')!=reply['id'] and not(read.get('id')==state.get('last_request')
        and read.get('phase')=='done'and read.get('world_session')==book['world_session']
        and read.get('control_revision')==reply['control_revision']):return None
    if any(frame.get(k)!=state.get(k)for k in ('world_session','server','dimension','player_uuid')):return None
    if not -1000<=state['time']-frame.get('time',0)<=1000:return None
    boat=next((v for v in frame.get('vehicles',[])if v.get('uuid')==book.get('uuid')),None)
    if not boat or boat.get('alive')is not True or boat.get('leashed')is not True or boat.get('leash_resolved')is not True or boat.get('leash_holder',{}).get('uuid')!=state.get('player_uuid'):return None
    baseline=book.get('baseline_health')or{};before={p['uuid']:p for p in(move.get('boat_before')or{}).get('passengers',[])}
    if not baseline or set(before)!=set(baseline)or any(before[u].get('health')!=h for u,h in baseline.items()):return None
    current={p['uuid']:p for p in boat.get('passengers',[])}
    damaged=any(u not in current or current[u].get('alive')is not True or type(current[u].get('health'))not in(int,float)or current[u]['health']<h for u,h in baseline.items())
    if not damaged:return None
    target=move.get('from');point=state.get('pos');actual=reply.get('pos')
    if any(not isinstance(p,list)or len(p)!=3 or any(type(v)not in(int,float)or not math.isfinite(v)for v in p)for p in(target,point,actual)):return None
    if math.dist(point,target)>3.5 or math.dist(point,actual)>.3 or not -62<=target[1]<317 or any(abs(target[i])>=799968 for i in(0,2)):return None
    scope={k:book[k]for k in ['world_session','uuid','baseline_health','lease_id','task_session']};scope['last_read_only']=book.get('last_read_only')
    return dict(target=list(target),world_session=book['world_session'],boat_uuid=book['uuid'],original_move=move,original_reply=reply,trip_scope=scope,observed_boat=boat)

def return_after_known_move(client,book,move,reply,path):
    if any(r.get('original_move_id')==reply.get('id')for r in book.get('safety_returns',[])):return None
    if getattr(client,'native_inflight',None)is not None or getattr(client,'unconfirmed_native_request',None)is not None:return None
    status=getattr(client,'safety_status',client.status)
    try:
        state=status();frame=read_frame(client.root,state,allow_dead_passengers=True);plan=retreat_plan(state,book,move,reply,frame)
    except Exception:return None
    if plan is None:return None
    record=dict(original_move_id=reply['id'],target=plan['target'],pending=True,complete=False,original_move_not_replayed=True,transport_resume_forbidden=True)
    book.setdefault('safety_returns',[]).append(record);write_json(path,book);previous=state['last_request']
    try:
        callback=getattr(client,'cargo_safety_retreat',None)
        response=callback(plan)if callback else client.request('navigate',target=plan['target'],arrival=.2,air_only=True,seconds=15)
        record['reply']={k:response.get(k)for k in ['id','phase','detail','world_session','control_revision','pos']}
        record['complete']=response.get('phase')=='done'and response.get('world_session')==book['world_session']
        record['pending']=not record['complete']
        try:
            after=status();record['boat_after']=next((v for v in(read_frame(client.root,after,allow_dead_passengers=True)or{}).get('vehicles',[])if v['uuid']==book['uuid']),None)
        except Exception:pass
    except Exception as error:record['error']=repr(error)
    finally:
        try:
            current=status()['last_request'];record['request_id']=current if current!=previous else None
        except Exception:pass
        write_json(path,book)
    return record
