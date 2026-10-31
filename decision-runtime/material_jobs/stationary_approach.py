"""Prove a nearby stationary work pose without relabeling failed exact navigation.
Only read-only observations occur here. Every later action keeps native ray/reach guards.
"""
import math,time
from pathlib import Path
from kit_runtime.journal import write_json
from projected_source_column import coherent
from native_outcome_fence import wait_exact_idle_terminal
DRIFT='Restored Flight settings did not keep the precise waypoint stable'
def eligible_reply(r,world):
    return (r.get('phase')=='stopped'and r.get('detail')==DRIFT and r.get('world_session')==world
            and isinstance(r.get('id'),str)and (r.get('material_air_navigation')or{}).get('injury_interrupted')is False)
def stationary_owner(s,target,world,task,lease_id,revision,hurt):
    p=s.get('pos');v=s.get('velocity');lease=s.get('supervision_lease')or{}
    if not(isinstance(p,list)and isinstance(v,list)and len(p)==len(v)==3
           and all(type(n)in(int,float)and math.isfinite(n)for n in p+v+list(target))):return False
    return (s.get('connected')is True and s.get('world_session')==world and s.get('control_revision')==revision
        and s.get('health')==20 and s.get('recent_hurt_at')==hurt and not s.get('safety_hold',{}).get('active')
        and not s.get('screen')and s.get('manual_movement')is False and s.get('guard_armed')is True
        and s.get('guard_pve_only')is True and s.get('guard_busy')is False and s.get('flight')is True
        and s.get('under_water')is False and s.get('air_supply',0)>=285
        and not s.get('navigating')and not s.get('native_material_busy')and not s.get('pending_scan')
        and lease.get('kind')=='materials'and lease.get('job_session')==task and lease.get('id')==lease_id
        and lease.get('world_session')==world and lease.get('revision')==revision
        and not any((s.get('movement_keys')or{}).values())
        and math.hypot(p[0]-target[0],p[2]-target[2])<=.75 and abs(p[1]-target[1])<=.15
        and math.hypot(v[0],v[2])<=.01 and abs(v[1])<=.1)
def dry_body(frame,pos):
    return all(v.get('state')=='Block{minecraft:cobblestone_slab}[type=top,waterlogged=false]'
               and v['pos'][1]+.5>=pos[1]+1.8+1e-7 for v in frame.get('blocks',[]))
def observe_nearby(c,reply,target,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    if not eligible_reply(reply,c.world):raise RuntimeError('Not a known restored-Flight drift terminal')
    if c.unconfirmed_native_request or getattr(c,'native_inflight',None):raise RuntimeError('Native outcome pending')
    s=wait_exact_idle_terminal(c);revision=s['control_revision'];hurt=s.get('recent_hurt_at');previous=None;stamps=[]
    if s.get('last_request')!=reply['id']:raise RuntimeError('Another command followed the terminal')
    write_json(out/'original-terminal.json',reply)
    for i in range(3):
        s=c.status()
        if not stationary_owner(s,target,c.world,c.task,c.heartbeat.id,revision,hurt):raise RuntimeError('Nearby pose ownership/health/stationarity changed')
        pos=s['pos'];lo=[math.floor(pos[j]-(.31 if j!=1 else 0))for j in range(3)];hi=[math.floor(pos[j]+(.31 if j!=1 else 1.8))for j in range(3)]
        frame=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True);write_json(out/f'frame-{i}.json',frame);after=wait_exact_idle_terminal(c)
        if (not coherent(frame,c.world,lo,hi)or not dry_body(frame,pos)
            or not stationary_owner(after,target,c.world,c.task,c.heartbeat.id,revision,hurt)
            or math.dist(after['pos'],pos)>.005 or previous is not None and math.dist(pos,previous)>.005
            or stamps and frame['time']<=stamps[-1]):raise RuntimeError('Three unchanged dry-body observations not proved')
        stamps.append(frame['time']);previous=after['pos'];time.sleep(.2)
    result={'native_phase':'stopped','exact_waypoint_confirmed':False,'nearby_stationary_work_pose':previous,
            'target':target,'world_session':c.world,'frames':stamps,'no_navigation_retry':True,'native_action_guards_required':True}
    write_json(out/'result.json',result);return result
