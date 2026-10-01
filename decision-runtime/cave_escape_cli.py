"""One-shot, guarded exit from the known Simpcraft cave pocket.

No excavation, teleport, login or old-scan replay. The historical coordinates
only bound a fresh search; each move needs a new native air-only AABB check.
"""
import argparse
import json
import math
import time
from pathlib import Path

from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from material_client import MaterialClient, Handoff
from material_jobs.navigation import _body_sweep, settled_state, shaft_path

ROOT=Path('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation')
SERVER='simpcraft.com:25565'
SHAFT=(760957,797900)
PARK=[760957.5,145.0,797900.5]
START_X=(760966,760972)
START_Z=(797904,797911)
START_Y=(28,34)
HORIZONTAL_MIN=(760955,797897)
HORIZONTAL_MAX=(760973,797911)
SAFE_NONCOLLIDING={'minecraft:short_grass','minecraft:tall_grass','minecraft:fern',
                   'minecraft:large_fern','minecraft:torch','minecraft:wall_torch'}


class EscapeBlocked(RuntimeError):pass
class FinishUnverified(EscapeBlocked):pass


def _block_id(row):
    state=row.get('state')
    return state.split('}',1)[0].removeprefix('Block{') if isinstance(state,str) and state.startswith('Block{') else ''


def _safe_soft(row):
    return (_block_id(row) in SAFE_NONCOLLIDING and row.get('passable') is True
            and row.get('fluid') is False and row.get('block_entity') is False)


def _scan(client,low,high):
    if (any(type(v) is not int for v in low+high) or any(low[i]>high[i] for i in range(3))
            or math.prod(high[i]-low[i]+1 for i in range(3))>50000):
        raise EscapeBlocked('Escape scan is outside the bounded request')
    reply=client.request('scan',min=low,max=high,details=True)
    if (not isinstance(reply,dict) or reply.get('phase') not in (None,'done')
            or reply.get('world_session')!=client.world or reply.get('id')!=client.last
            or not isinstance(reply.get('blocks'),list)):
        raise EscapeBlocked('Fresh native scan was not confirmed for this world and request')
    seen=set()
    for row in reply['blocks']:
        pos=row.get('pos') if isinstance(row,dict) else None
        if (not isinstance(pos,list) or len(pos)!=3 or any(type(v) is not int for v in pos)
                or any(not low[i]<=pos[i]<=high[i] for i in range(3))
                or not isinstance(row.get('state'),str)
                or any(type(row.get(k)) is not bool for k in ('passable','solid','fluid','block_entity'))
                or tuple(pos) in seen):
            raise EscapeBlocked('Native scan contains an invalid, incomplete or repeated cell')
        seen.add(tuple(pos))
    return reply['blocks']


def _survey_after_clear(client,low,high,*,first=False):
    """Discard a scan if combat occurred before its confirming status read."""
    combat_occurred=False
    for _ in range(3):
        before,waited_before=_await_clear(client,first=first)
        combat_occurred|=waited_before
        rows=_scan(client,low,high)
        after,waited=_await_clear(client,first=first)
        combat_occurred|=waited
        if math.dist(after['pos'],before['pos'])>.20:
            raise EscapeBlocked('Player moved during the fresh cave survey')
        if not waited:
            return rows,after,combat_occurred
    raise EscapeBlocked('Combat repeatedly invalidated the cave survey')


def _safety(state, *, first=False, allow_combat=False):
    if (not state.get('connected') or state.get('server')!=SERVER
            or state.get('dimension')!='minecraft:overworld'
            or state.get('screen') or state.get('manual_movement')
            or state.get('health',0)<14 or state.get('food',0)<8
            or state.get('safety_hold',{}).get('active') or state.get('under_water')
            or not state.get('guard_armed') or not state.get('guard_pve_only')
            or state.get('air_only_navigation_protocol',0)<2
            or not isinstance(state.get('entities'),list)
            or not (state.get('flight') is True or first and state.get('on_ground') is True)):
        raise EscapeBlocked('World, health, manual control, PvE guard or Flight is not ready')
    for entity in state['entities']:
        pos=entity.get('pos') if isinstance(entity,dict) else None
        if (not isinstance(pos,list) or len(pos)!=3
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in pos)
                or type(entity.get('hostile')) is not bool):
            raise EscapeBlocked('Nearby entity coverage is incomplete')
    if not allow_combat and (state.get('health',0)<18 or state.get('guard_busy')
                             or any(e['hostile'] for e in state['entities'])):
        raise EscapeBlocked('Recovery, native defense or hostile clearance is still pending')


def _await_clear(client, *, first=False, seconds=20):
    """Hold the same route while native PvE defense clears a nearby threat.

    No movement request is issued during combat. This is a bounded opportunity
    for the already armed guard, never a new route or a command to attack.
    """
    started=time.monotonic();waited=False
    while True:
        state=client.status()
        _safety(state,first=first,allow_combat=True)
        threats=[e for e in state['entities'] if e['hostile']]
        if state.get('health',0)>=18 and not state.get('guard_busy') and not threats:
            if waited:
                _record_combat(client,'cleared',started,state)
            return state,waited
        waited=True
        if time.monotonic()-started>=seconds:
            _record_combat(client,'timed_out',started,state)
            raise EscapeBlocked('Native PvE guard or health recovery did not clear the same cave route in time')
        time.sleep(.25)


def _record_combat(client,result,started,state):
    try:
        with (client.out/'cave-escape-combat.jsonl').open('a') as stream:
            stream.write(json.dumps({'result':result,'elapsed_seconds':round(time.monotonic()-started,2),
                'health':state.get('health'),'guard_busy':state.get('guard_busy'),
                'hostile_count':sum(bool(e.get('hostile')) for e in state.get('entities',[])),
                'world_session':client.world},ensure_ascii=False)+'\n')
    except OSError:
        pass


def _near_actor(state,start,end):
    direction=[end[i]-start[i] for i in range(3)]
    length=sum(v*v for v in direction)
    for entity in state['entities']:
        if entity.get('type') in ('minecraft:item','minecraft:experience_orb'):
            continue
        position=entity['pos']
        fraction=(max(0,min(1,sum((position[i]-start[i])*direction[i] for i in range(3))/length))
                  if length>.000001 else 0)
        nearest=[start[i]+fraction*direction[i] for i in range(3)]
        if math.dist(position,nearest)<3:
            raise EscapeBlocked('An entity is near the next cave waypoint')


def _clear_sweep(client,start,end,*,allow_ground_first=False):
    low,high=_body_sweep(start,end)
    rows,fresh,_=_survey_after_clear(client,low,high,first=allow_ground_first)
    if any(not _safe_soft(row) for row in rows):
        raise EscapeBlocked('Fresh player-body sweep contains a block, fluid or unsafe plant')
    if math.dist(fresh['pos'],start)>.20:
        raise EscapeBlocked('Player moved after the cave corridor scan')
    _near_actor(fresh,start,end)
    return fresh


def _turns(path):
    if not 1<=len(path)<=32:
        raise EscapeBlocked('Cave exit path exceeds one bounded local search')
    points=[]
    for i,p in enumerate(path):
        if (i==0 or i==len(path)-1 or
                (p[0]-path[i-1][0],p[2]-path[i-1][2])!=(path[i+1][0]-p[0],path[i+1][2]-p[2])):
            points.append(p)
    split=[points[0]]
    for end in points[1:]:
        start=split[-1];length=math.dist(start,end)
        if length>.01:
            for step in range(1,math.ceil(length/8)):
                ratio=(step*8)/length
                split.append([start[i]+(end[i]-start[i])*ratio for i in range(3)])
        split.append(end)
    if len(split)>12 or any(math.dist(a,b)>8.01 for a,b in zip(split,split[1:])):
        raise EscapeBlocked('Cave path is too long or cannot be flown in short axis legs')
    return split


def plan(client):
    state,_=_await_clear(client,first=True)
    x,y,z=state['pos']
    if (not START_X[0]<=x<=START_X[1] or not START_Z[0]<=z<=START_Z[1]
            or not START_Y[0]<=y<=START_Y[1]):
        raise EscapeBlocked('Player is outside this one known cave pocket')
    floor=math.floor(y)
    low=[HORIZONTAL_MIN[0],floor-1,HORIZONTAL_MIN[1]]
    high=[HORIZONTAL_MAX[0],floor+3,HORIZONTAL_MAX[1]]
    # Prove the target column BEFORE flying across the cave; a remembered shaft
    # or an old source coordinate is never an entry receipt.
    shaft_low=[SHAFT[0],floor,SHAFT[1]]
    shaft_high=[SHAFT[0],math.ceil(PARK[1])+2,SHAFT[1]]
    for _ in range(3):
        rows,fresh,_=_survey_after_clear(client,low,high,first=True)
        if math.dist(fresh['pos'],state['pos'])>.20:
            raise EscapeBlocked('Player moved during the first cave survey')
        shaft_rows,newest,shaft_combat=_survey_after_clear(client,shaft_low,shaft_high,first=True)
        if math.dist(newest['pos'],fresh['pos'])>.20:
            raise EscapeBlocked('Player moved during the shaft survey')
        if not shaft_combat:
            break
    else:
        raise EscapeBlocked('Combat repeatedly invalidated the cave and shaft surveys')
    occupied=[row for row in rows if not _safe_soft(row)]
    current_low,current_high=_body_sweep(fresh['pos'],fresh['pos'])
    if any(all(current_low[i]<=r['pos'][i]<=current_high[i] for i in range(3)) for r in occupied):
        raise EscapeBlocked('Current player body is not in confirmed dry air')
    if fresh.get('flight') is not True:
        supported={tuple(r['pos']):r for r in rows}
        below_y=floor-1
        for fx in range(current_low[0],current_high[0]+1):
            for fz in range(current_low[2],current_high[2]+1):
                support=supported.get((fx,below_y,fz))
                if not support or support.get('solid') is not True or support.get('fluid') is not False:
                    raise EscapeBlocked('Grounded takeoff lacks confirmed support under the whole body')
    if any(not _safe_soft(row) for row in shaft_rows):
        raise EscapeBlocked('Target shaft is no longer open to the high guarded altitude')
    goal={'min':[SHAFT[0],floor,SHAFT[1]],'max':[SHAFT[0],floor,SHAFT[1]]}
    path=shaft_path(occupied,fresh['pos'],goal,low,high)
    turns=_turns(path)
    # Re-read after the second scan so a combat displacement cannot authorize
    # a route from the old feet position.
    return {'world_session':client.world,'start':list(fresh['pos']),
            'turns':turns,'shaft':list(SHAFT),'park':list(PARK),
            'scan_requests':[getattr(client,'last',None)]}


def _move_once(client,target,trace):
    before,_=_await_clear(client,first=not trace)
    _near_actor(before,before['pos'],target)
    _clear_sweep(client,before['pos'],target,allow_ground_first=not trace)
    reply=client.request('navigate',target=list(target),arrival=.25,seconds=20,air_only=True)
    if reply.get('phase')!='done':
        trace.append({'target':list(target),'phase':reply.get('phase'),'detail':reply.get('detail')})
        raise EscapeBlocked('Native air-only movement did not confirm arrival; no retry')
    _await_clear(client)
    reached=settled_state(client,target,.45)
    _safety(reached)
    if math.dist(reached['pos'],target)>.45:
        raise EscapeBlocked('Actual cave waypoint differs from the acknowledged target')
    trace.append({'target':list(target),'phase':'done','actual':list(reached['pos'])})


def execute(client,output):
    itinerary=plan(client);trace=[]
    write_json(output/'cave-escape-plan.json',itinerary)
    first=client.status()
    if first.get('flight') is not True:
        # On login the player may be grounded with Flight off. A fresh local
        # body/floor scan preceded the plan; native navigate enables Flight.
        # Use an exact no-op waypoint so no lateral or vertical motion occurs
        # before Flight itself is confirmed by a fresh status observation.
        takeoff=list(first['pos'])
        _move_once(client,takeoff,trace)
    for waypoint in itinerary['turns']:
        if math.dist(client.status()['pos'],waypoint)>.08:
            _move_once(client,waypoint,trace)
    current,_=_await_clear(client)
    if math.hypot(current['pos'][0]-SHAFT[0]-.5,current['pos'][2]-SHAFT[1]-.5)>.35:
        raise EscapeBlocked('Player body has not reached the verified shaft centre')
    for level in (50,70,90,110,130,145):
        state,_=_await_clear(client)
        if state['pos'][1]>=level-.25:continue
        target=[state['pos'][0],float(level),state['pos'][2]]
        _move_once(client,target,trace)
    final,_=_await_clear(client)
    if math.dist(final['pos'],PARK)>.65:
        raise EscapeBlocked('High cave park was not physically confirmed')
    write_json(output/'cave-escape-receipt.json',{'world_session':client.world,
        'from':itinerary['start'],'actual':final['pos'],'guard_armed':True,
        'moves':trace,'completed_at':time.time(),'confirmed':True})
    return trace


def verify_guard_finish(client,output):
    """A normal finish() return alone never proves a retained safe guard."""
    path=output/'stock-safety.json'
    if not path.is_file():raise FinishUnverified('Native high-guard receipt is missing')
    receipt=json.loads(path.read_text())
    if (receipt.get('action')!='KEEP_PVE_GUARD' or receipt.get('lease')!=client.heartbeat.id
            or receipt.get('job_session')!=client.task):
        raise FinishUnverified('High-guard receipt belongs to another lease or was a logout')
    state=read_fresh(client.root)
    # The native KEEP_PVE_GUARD receipt is emitted when the materials lease is
    # released. A safe parked player can therefore have no supervision lease;
    # an active lease owned by somebody else is a handoff, not our success.
    lease=state.get('supervision_lease') or {}
    entities=state.get('entities')
    entity_coverage=(isinstance(entities,list) and all(
        isinstance(entity,dict) and type(entity.get('hostile')) is bool
        and isinstance(entity.get('pos'),list) and len(entity['pos'])==3
        and all(type(v) in (int,float) and math.isfinite(v) for v in entity['pos'])
        for entity in entities))
    if (not state.get('connected') or state.get('world_session')!=client.world
            or state.get('server')!=SERVER or state.get('dimension')!='minecraft:overworld'
            or state.get('manual_movement') or state.get('screen') or state.get('under_water')
            or state.get('health',0)<18 or state.get('food',0)<8
            or not state.get('flight') or not state.get('guard_armed')
            or not state.get('guard_pve_only') or state.get('guard_busy')
            or not entity_coverage or any(e['hostile'] for e in entities)
            or lease and (lease.get('id')!=client.heartbeat.id or lease.get('kind')!='parking')
            or not isinstance(state.get('pos'),list) or len(state['pos'])!=3
            or math.dist(state['pos'],PARK)>.75):
        raise FinishUnverified('High-guard receipt is not backed by a fresh safe player state')
    write_json(output/'cave-escape-guard-verified.json',{'world_session':client.world,
        'lease':client.heartbeat.id,'actual':state['pos'],'health':state['health'],
        'verified_at':state['time'],'confirmed':True})


def main(argv=None):
    parser=argparse.ArgumentParser(description='One-shot guarded cave exit; no digging, placing, teleport or login')
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--execute',action='store_true',help='Required to acquire the material lease and move')
    args=parser.parse_args(argv)
    if not args.execute:
        print('Add --execute after entering the world and confirming Kit protection; no action was sent.')
        return 0
    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        raise EscapeBlocked('Escape output directory already contains a run; choose a fresh directory')
    args.out.mkdir(parents=True,exist_ok=True)
    state=read_fresh(args.root)
    if (not state.get('connected') or state.get('server')!=SERVER
            or state.get('dimension')!='minecraft:overworld' or state.get('health',0)<18
            or state.get('safety_hold',{}).get('active') or state.get('manual_movement')
            or any(state.get(k) for k in ('borer_active','chopping','navigating','printing'))
            or state.get('build_job',{}).get('active')
            or state.get('professional_printer',{}).get('enabled')
            or state.get('professional_printer',{}).get('owned')
            or state.get('professional_printer',{}).get('waiting_for_server')
            or state.get('material_task',{}).get('occupied')
            or state.get('material_task',{}).get('process_alive')):
        raise EscapeBlocked('Fresh connected world, health and manual-control checks failed; no login attempted')
    client=MaterialClient(args.root,args.out,server=SERVER,remote_finish='guard',park_target=PARK)
    try:
        execute(client,args.out)
        client.finish()
        verify_guard_finish(client,args.out)
        return 0
    except FinishUnverified as error:
        # finish() may already have requested a logout; never replay it.
        write_json(args.out/'cave-escape-failed.json',{'reason':str(error),
            'action':'finish_unverified_no_replay','time':time.time()})
        return 2
    except Handoff:
        # User movement, changed revision or a new world owns the player now.
        client.heartbeat.close()
        raise
    except Exception as error:
        write_json(args.out/'cave-escape-failed.json',{'reason':str(error),
            'action':'single_safe_logout_if_still_owned','time':time.time()})
        try:
            fresh=client.status()
            if not fresh.get('manual_movement') and fresh.get('guard_armed'):
                client.request('safe_logout')
        except (Handoff,RuntimeError):
            pass  # Unknown owned action is never replayed; native lease handles its timeout.
        finally:
            client.heartbeat.close()
        raise


if __name__=='__main__':raise SystemExit(main())
