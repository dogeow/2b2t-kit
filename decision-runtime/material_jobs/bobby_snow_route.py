"""Crash-safe long snow travel using only Bobby-derived candidate coordinates.

The cache is a hint.  This module owns only the bounded ordinary Kit cruise and
its return trace; discovery still requires a live biome survey and natural snow
scan before a block can be mined.
"""
from __future__ import annotations

import copy
import math
import re
import uuid
from pathlib import Path

from kit_runtime.journal import write_json
from .protocol import server_key


VERSION = 1
LEDGER_KEY = 'bobby_snow_cache'
SEGMENT_LIMIT = 320.0
SEGMENT_STEP = 314.0  # leaves the six-block native arrival tolerance inside 320
WORLD_LIMIT = 29_999_984
RECENT_SEGMENTS = 24
MAX_VISITS = 8192
MAX_ROUTES = 64
ACTIVE_STATES = frozenset((
    'planned', 'outbound_guard_inflight', 'outbound_navigate_inflight',
    'outbound_uncertain', 'candidate_arrived', 'harvesting', 'return_required',
    'return_guard_inflight', 'return_navigate_inflight', 'return_uncertain'))
UNLOADED_AIR_ONLY_REJECTION = (
    'Air-only navigation requires the current material lease and a loaded clear dry path')
SAFE_ID=re.compile(r'[A-Za-z0-9_-]{1,100}')


def _point(value):
    return (isinstance(value, list) and len(value) == 3
            and all(type(number) in (int, float) and math.isfinite(number)
                    for number in value)
            and abs(value[0]) <= WORLD_LIMIT and abs(value[2]) <= WORLD_LIMIT
            and -64 <= value[1] <= 319)


def _candidate(value):
    if not isinstance(value, dict):
        return False
    chunk, tile = value.get('chunk'), value.get('tile')
    target=value.get('target')
    return (value.get('source')=='bobby_cache'
            and isinstance(value.get('cache_server'),str)
            and value['cache_server']
            and value.get('dimension')=='minecraft:overworld'
            and isinstance(chunk, list) and len(chunk) == 2
            and all(type(number) is int for number in chunk)
            and isinstance(tile, list) and len(tile) == 2
            and all(type(number) is int for number in tile)
            and tile == [chunk[0] * 16, chunk[1] * 16]
            and abs(tile[0]) <= WORLD_LIMIT - 15 and abs(tile[1]) <= WORLD_LIMIT - 15
            and _point(target) and target[0]==tile[0]+8.5
            and target[2]==tile[1]+8.5 and 160<=target[1]<=316
            and isinstance(value.get('region_file'), str)
            and value['region_file'].startswith('r.')
            and value['region_file'].endswith('.mca')
            and '/' not in value['region_file'] and '\\' not in value['region_file']
            and isinstance(value.get('fingerprint'), str)
            and len(value['fingerprint']) == 64
            and all(character in '0123456789abcdef'
                    for character in value['fingerprint'])
            and isinstance(value.get('biomes'), list) and value['biomes']
            and all(isinstance(name, str) and name.startswith('minecraft:')
                    for name in value['biomes'])
            and type(value.get('distance_sq')) in (int,float)
            and math.isfinite(value['distance_sq']) and value['distance_sq']>=0
            and type(value.get('mtime_ns')) is int and value['mtime_ns']>=0
            and type(value.get('ctime_ns')) is int and value['ctime_ns']>=0
            and type(value.get('size')) is int and 8192<=value['size']<=128*1024*1024
            and type(value.get('file_id')) is int and 0<=value['file_id']<(1<<48))


def candidate_key(candidate):
    if not _candidate(candidate):
        raise ValueError('Invalid Bobby snow candidate evidence')
    import hashlib
    raw=(candidate['cache_server']+'|'+candidate['dimension']+'|'
         +str(candidate['chunk'][0])+'|'+str(candidate['chunk'][1])+'|'
         +candidate['fingerprint'])
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _visit_record(key,row):
    observed=row.get('observed_at') if isinstance(row,dict) else None
    return (isinstance(key,str) and len(key)==32
            and isinstance(row,dict)
            and row.get('state') in ('cache_changed','server_mismatch','protected',
                                     'survey_unavailable','detailed_unavailable',
                                     'detailed_empty','live_verified')
            and isinstance(row.get('world_session'),str)
            and type(observed) in (int,float) and math.isfinite(observed)
            and _candidate(row.get('candidate'))
            and key==candidate_key(row['candidate']))


def public_candidate(candidate):
    """Copy bounded evidence only.  Cache world paths and seed hashes stay private."""
    if not _candidate(candidate):
        raise ValueError('Invalid Bobby snow candidate evidence')
    return {name: copy.deepcopy(candidate[name]) for name in
            ('source','cache_server','dimension','chunk','tile','target',
             'region_file','fingerprint','biomes','distance_sq',
             'mtime_ns','ctime_ns','size','file_id')}


def ledger_state(ledger, server, dimension):
    canonical = server_key(server)
    value = ledger.get(LEDGER_KEY)
    if value is None:
        value = {'version': VERSION, 'server': canonical, 'dimension': dimension,
                 'visited': {}, 'routes': [], 'active_route': None}
        ledger[LEDGER_KEY] = value
        return value
    if (not isinstance(value, dict) or value.get('version') != VERSION
            or value.get('server') != canonical
            or value.get('dimension') != dimension
            or not isinstance(value.get('visited'), dict)
            or len(value['visited'])>MAX_VISITS
            or not isinstance(value.get('routes'), list)
            or len(value['routes'])>MAX_ROUTES
            or any(not _visit_record(key,row)
                   for key,row in value['visited'].items())
            or any(not isinstance(row, dict) for row in value['routes'])
            or 'visit_history' in value and (
                not isinstance(value['visit_history'],dict)
                or len(value['visit_history'])>MAX_VISITS
                or not set(value['visit_history']).issubset(value['visited'])
                or any(not isinstance(rows,list) or len(rows)>8
                       or any(not isinstance(row,dict) for row in rows)
                       for rows in value['visit_history'].values()))
            or value.get('active_route') is not None
            and not isinstance(value.get('active_route'), dict)):
        raise RuntimeError('Bobby 雪地候选账本损坏；保留原文件')
    active = value.get('active_route')
    if active is not None:
        if (active.get('state') not in ACTIVE_STATES
                or not isinstance(active.get('route_id'), str)
                or not isinstance(active.get('world_session'), str)
                or not isinstance(active.get('task_session'),str)
                or not SAFE_ID.fullmatch(active['task_session'])
                or not _point(active.get('origin'))
                or not _point(active.get('return_target'))
                or not _point(active.get('return_bridge'))
                or active.get('return_source') not in ('saved_home','search_origin')
                or not _candidate(active.get('candidate'))
                or active['candidate'].get('cache_server')!=value['server']
                or active['candidate'].get('dimension')!=value['dimension']
                or not _point(active.get('target'))
                or type(active.get('segment_count')) is not int
                or active['segment_count']<1
                or type(active.get('outbound_confirmed')) is not int
                or not 0<=active['outbound_confirmed']<=active['segment_count']
                or type(active.get('return_confirmed')) is not int
                or type(active.get('return_segment_count')) is not int
                or active['return_segment_count']<active['segment_count']
                or not 0<=active['return_confirmed']<=active['return_segment_count']
                or not isinstance(active.get('recent_segments'),list)
                or len(active['recent_segments'])>RECENT_SEGMENTS
                or any(not _segment_record(active,row,done=True)
                       for row in active['recent_segments'])
                or 'inflight' in active['state']
                   and not _segment_record(active,active.get('current_segment'),done=False)
                or active['state'].endswith('uncertain')
                   and active.get('current_segment') is not None
                   and not _segment_record(active,active.get('current_segment'),done=False)):
            raise RuntimeError('Bobby 雪地在途路线记录损坏；不重放')
        planning_step=active.get('planning_step',SEGMENT_LIMIT)
        if ('planning_step' in active and active['planning_step']!=SEGMENT_STEP):
            raise RuntimeError('Bobby 雪地路线分段版本无效；不移动')
        expected_target,expected_count=_plan(
            active['origin'],active['candidate'],planning_step)
        expected_bridge=(list(active['return_target']) if math.hypot(
            active['origin'][0]-active['return_target'][0],
            active['origin'][2]-active['return_target'][2])<=.25
            else [active['origin'][0],expected_target[1],active['origin'][2]])
        expected_return=expected_count+1+_leg_count(
            expected_bridge,active['return_target'],planning_step)
        if (not _same_point(active['target'],expected_target)
                or active['segment_count']!=expected_count
                or not _same_point(active['return_bridge'],expected_bridge)
                or active['return_segment_count']!=expected_return):
            raise RuntimeError('Bobby 雪地路线派生坐标或段数已改变；不返航')
    return value


def _safe(c, state, *, min_health=19):
    lease = state.get('supervision_lease') or {}
    if (state.get('world_session') != c.world
            or state.get('health', 0) < min_health or state.get('food', 0) < 8
            or state.get('under_water') or state.get('flight') is not True
            or state.get('guard_armed') is not True
            or state.get('guard_pve_only') is not True
            or state.get('manual_movement')
            or (state.get('safety_hold') or {}).get('active')
            or lease.get('kind') != 'materials'
            or lease.get('job_session') != getattr(c, 'task', None)
            or lease.get('world_session') != c.world
            or lease.get('revision') != state.get('control_revision')):
        from .acquisition import Unavailable
        raise Unavailable('Bobby 雪地巡航的防护、飞行或材料租约不完整；保留路线',
                          'waiting', code='route_uncertain')
    return state


def _same_point(left,right):
    return _point(left) and _point(right) and math.dist(left,right)<1e-7


def _same_park_pose(left,right):
    return (_point(left) and _point(right)
            and math.hypot(left[0]-right[0],left[2]-right[2])<=.05
            and abs(left[1]-right[1])<=2.1)


def _host_return(state):
    """Use one immutable host-owned Home, with its task origin as fallback."""
    lease=state.get('supervision_lease') or {}
    configured=lease.get('return_target')
    if isinstance(configured,dict):
        point=[configured.get('x'),configured.get('cruise_y'),configured.get('z')]
        source=configured.get('source')
        if (_point(point) and source in ('saved_home','search_origin')
                and configured.get('dimension')==state.get('dimension')):
            return point,source
    origin=lease.get('search_origin')
    if _point(origin):return list(origin),'search_origin'
    from .acquisition import Unavailable
    raise Unavailable('材料租约没有宿主绑定的 Home 或任务起点；不出发',
                      'waiting',code='route_uncertain')


def _plan(origin, candidate, step=SEGMENT_STEP):
    tile = candidate['tile']
    cruise = min(300.0, max(220.0, float(origin[1])))
    target = [tile[0] + 8.5, cruise, tile[1] + 8.5]
    distance = math.hypot(target[0] - origin[0], target[2] - origin[2])
    if type(step) not in (int,float) or not 0<step<=SEGMENT_LIMIT:
        raise ValueError('Invalid Bobby route planning step')
    count = max(1, math.ceil(distance / step))
    # The world border itself bounds count.  Waypoints are derived lazily so a
    # very distant destination does not create an unbounded JSON route.
    return target, count


def _leg_count(start,target,step=SEGMENT_STEP):
    if math.dist(start,target)<=.25:return 0
    return max(1,math.ceil(math.hypot(target[0]-start[0],target[2]-start[2])
                           /step))


def _leg_waypoint(start,target,index,count):
    if type(index) is not int or not 1<=index<=count:
        raise ValueError('Invalid Bobby home leg index')
    if index==count:return list(target)
    ratio=index/count
    cruise=min(300.0,max(220.0,float(start[1]),float(target[1])))
    return [start[0]+(target[0]-start[0])*ratio,cruise,
            start[2]+(target[2]-start[2])*ratio]


def _expected_return(route,index):
    outbound=route['segment_count']
    if index==1:return list(route['target'])
    if index<=outbound:return _waypoint(route,outbound-index+1)
    if index==outbound+1:return list(route['return_bridge'])
    home_count=route['return_segment_count']-outbound-1
    return _leg_waypoint(route['return_bridge'],route['return_target'],
                         index-outbound-1,home_count)


def _segment_record(route,row,*,done):
    if not isinstance(row,dict) or row.get('direction') not in ('outbound','return'):
        return False
    index=row.get('index');target=row.get('target');start=row.get('from')
    limit=(route['segment_count'] if row['direction']=='outbound'
           else route['return_segment_count'])
    if (type(index) is not int or not 1<=index<=limit
            or not _point(target) or not _point(start)
            or math.hypot(target[0]-start[0],target[2]-start[2])>SEGMENT_LIMIT
            or row.get('state') not in (('done',) if done else
                ('guard_inflight','navigate_inflight','uncertain'))):return False
    expected=(_waypoint(route,index) if row['direction']=='outbound'
              else _expected_return(route,index))
    return math.dist(target,expected)<1e-5


def _waypoint(route,index):
    count=route['segment_count']
    if type(index) is not int or not 1<=index<=count:
        raise ValueError('Invalid Bobby route segment index')
    ratio=index/count;origin=route['origin'];target=route['target']
    return [origin[0]+(target[0]-origin[0])*ratio,target[1],
            origin[2]+(target[2]-origin[2])*ratio]


def _remember(route,entry):
    route['recent_segments'].append(entry)
    del route['recent_segments'][:-RECENT_SEGMENTS]


def _attach(c, path, route):
    c.bobby_snow_route_id = route['route_id']
    c.bobby_snow_resource_path = str(path)


def _detach(c):
    for name in ('bobby_snow_route_id', 'bobby_snow_resource_path'):
        if hasattr(c, name):
            delattr(c, name)


def _exact_route(c, path, ledger):
    state = ledger_state(ledger, ledger[LEDGER_KEY]['server'],
                         ledger[LEDGER_KEY]['dimension'])
    route = state.get('active_route')
    if (not isinstance(route, dict)
            or route.get('route_id') != getattr(c, 'bobby_snow_route_id', None)
            or route.get('world_session') != c.world
            or route.get('task_session') != getattr(c,'task',None)):
        raise RuntimeError('Bobby 雪地路线与当前材料会话不匹配')
    current=_safe(c,c.status(),min_health=18)
    host_target,host_source=_host_return(current)
    if (host_source!=route['return_source']
            or not _same_point(host_target,route['return_target'])):
        raise RuntimeError('Bobby 雪地返航目标与宿主冻结 Home 不一致')
    return state, route


def _write(path, ledger):
    write_json(Path(path), ledger)


def _move(c, route, route_state, path, ledger, checkpoint, target, direction,
          index, *, validate=None, min_health=19):
    """One exactly journaled segment.  Unknown results are never replayed."""
    from .acquisition import Unavailable
    current = _safe(c, c.status(), min_health=min_health)
    if math.hypot(target[0] - current['pos'][0], target[2] - current['pos'][2]) > SEGMENT_LIMIT:
        raise Unavailable('Bobby 雪地路线分段记录超出 320 格；不移动',
                          'waiting', code='route_uncertain')
    entry = {'direction': direction, 'index': index,
             'from': list(current['pos']), 'target': list(target),
             'state': 'guard_inflight', 'cache_preload': 'bobby_voxy_passive'}
    route['state'] = direction + '_guard_inflight'
    route['current_segment'] = entry
    route_state['active_route'] = route
    _write(path, ledger)
    try:
        if validate is not None and not validate(route['candidate']):
            raise Unavailable('Bobby 雪地候选已不属于当前服务器缓存；不移动',
                              'waiting', code='route_uncertain')
        checkpoint()
        c.anchor = list(current['pos'])
        c.checked('guard', pve_only=True)
        armed = _safe(c, c.status(), min_health=min_health)
        c.anchor = list(armed['pos'])
        entry['from']=list(armed['pos'])
        if math.hypot(target[0]-armed['pos'][0],target[2]-armed['pos'][2])>SEGMENT_LIMIT:
            raise Unavailable('Bobby 防护重锚后分段超出 320 格；未发送巡航',
                              'waiting',code='route_uncertain')
        entry['state'] = 'navigate_inflight'
        entry['pre_dispatch_control_revision']=armed.get('control_revision')
        route['state'] = direction + '_navigate_inflight'
        _write(path, ledger)
        distance = math.dist(armed['pos'], target)
        if distance<=.3:
            arrived=armed;reply={'phase':'done','id':getattr(c,'last',None),
                                 'world_session':c.world}
        else:
            reply = c.request('navigate', target=list(target), arrival=4,
                              seconds=min(600, max(90, math.ceil(distance / 2) + 45)))
            arrived = _safe(c, c.status(), min_health=min_health)
            entry.update(request_id=getattr(c,'last',None),
                         native_phase=reply.get('phase'),
                         native_detail=reply.get('detail'),
                         terminal_pos=list(arrived['pos']))
            if reply.get('phase')=='error':entry['detail']=reply.get('detail')
            _write(path,ledger)
        if (reply.get('phase') != 'done' or reply.get('id') != getattr(c, 'last', None)
                or reply.get('world_session') != c.world
                or arrived.get('navigating') or arrived.get('native_material_busy')
                or math.hypot(arrived['pos'][0] - target[0],
                              arrived['pos'][2] - target[2]) > 6
                or abs(arrived['pos'][1] - target[1]) > 6):
            raise Unavailable('Bobby 雪地分段巡航回执不确定；不重放该段',
                              'waiting', code='route_uncertain')
    except Exception as error:
        entry['state'] = 'uncertain'
        entry.setdefault('detail',str(error))
        route['state'] = direction + '_uncertain'
        _write(path, ledger)
        raise
    entry.update(state='done', actual=list(arrived['pos']),
                 observed_at=arrived.get('time'))
    _remember(route,entry)
    if direction=='outbound':route['outbound_confirmed']=index
    else:route['return_confirmed']=index
    route.pop('current_segment', None)
    route['state']='planned' if direction=='outbound' else 'return_required'
    c.anchor = list(arrived['pos'])
    _write(path, ledger)
    return arrived


def outbound(c, candidate, server, dimension, path, ledger, checkpoint,
             validate_candidate, validate_candidate_quick=None):
    """Cruise to one current-cache candidate and retain its exact return path."""
    state = ledger_state(ledger, server, dimension)
    if isinstance(state.get('active_route'), dict):
        from .acquisition import Unavailable
        raise Unavailable('上一条 Bobby 雪地路线尚未返回；不换候选、不重放',
                          'waiting', code='route_uncertain')
    initial = _safe(c, c.status())
    public = public_candidate(candidate)
    if not validate_candidate(public):
        from .acquisition import Unavailable
        raise Unavailable('Bobby 雪地候选在出发前已不属于当前缓存',
                          'waiting',code='route_uncertain')
    return_target,return_source=_host_return(initial)
    target, segment_count = _plan(list(initial['pos']), public)
    return_bridge=(list(return_target) if math.hypot(
        initial['pos'][0]-return_target[0],initial['pos'][2]-return_target[2])<=.25
        else [initial['pos'][0],target[1],initial['pos'][2]])
    home_count=_leg_count(return_bridge,return_target)
    route = {'route_id': str(uuid.uuid4()), 'state': 'planned',
             'world_session': c.world,'task_session':getattr(c,'task',None),
             'origin': list(initial['pos']),
             'return_target':return_target,'return_source':return_source,
             'return_bridge':return_bridge,
             'candidate': public, 'target': target,
             'planning_step':SEGMENT_STEP,
             'segment_count':segment_count,'outbound_confirmed':0,
             'return_segment_count':segment_count+1+home_count,
             'return_confirmed':0,'recent_segments':[],
             'started_at': initial.get('time'),
             'scenery_preload': {'mode': 'passive_bobby_voxy',
                                  'single_flight_controller': True}}
    state['active_route'] = route
    try:
        _write(path, ledger)
        _attach(c, path, route)
        for index in range(1,segment_count+1):
            point=_waypoint(route,index)
            _move(c, route, state, path, ledger, checkpoint, point, 'outbound',
                  index, validate=(validate_candidate_quick or validate_candidate))
    except Exception as error:
        terminal=getattr(c,'last_terminal_evidence',None)
        if isinstance(terminal,dict):
            proof=dict(terminal,route_id=route['route_id'])
            try:
                recover_unmoved_first_rejection(c,path,ledger,proof)
            except (OSError,RuntimeError,ValueError,TypeError,KeyError,AttributeError):
                pass
            else:
                from .acquisition import Unavailable
                raise Unavailable('Bobby 首段旧 air-only 预检拒绝已确认未移动并安全归档',
                                  'waiting',code='route_rejected_unmoved') from error
        _detach(c)
        raise
    route.update(state='candidate_arrived', arrived_at=c.status().get('time'))
    _write(path, ledger)
    return route


def recover_unmoved_first_rejection(c,path,ledger,evidence):
    """Clear only the proven first-segment pre-dispatch rejection.

    Generic uncertain movement remains locked.  This one recovery is safe
    because both the durable route and the current native snapshot prove that
    the first navigate request never moved or acquired movement keys.
    """
    if not isinstance(evidence,dict):
        raise RuntimeError('Bobby rejection recovery needs explicit evidence')
    state=ledger_state(ledger,ledger[LEDGER_KEY]['server'],
                       ledger[LEDGER_KEY]['dimension'])
    route=state.get('active_route');current=_safe(c,c.status(),min_health=18)
    lease=current.get('supervision_lease') or {}
    segment=_unmoved_rejection(route,evidence)
    request_id=evidence.get('request_id')
    exact=(segment is not None and route.get('world_session')==c.world
        and route.get('task_session')==getattr(c,'task',None)
        and route['candidate']['cache_server']==server_key(current.get('server'))
        and route['candidate']['dimension']==current.get('dimension')
        and request_id==getattr(c,'last',None)==current.get('last_request')
        and current.get('control_revision')==evidence.get('revision_after')
        and current.get('phase')=='error'
        and current.get('detail')==UNLOADED_AIR_ONLY_REJECTION
        and _same_point(evidence.get('terminal_pos'),current.get('pos'))
        and _same_point(segment.get('from'),current.get('pos'))
        and evidence.get('movement_keys')==current.get('movement_keys')
        and evidence.get('velocity')==current.get('velocity')
        and lease.get('kind')=='materials'
        and lease.get('job_session')==route.get('task_session')
        and lease.get('world_session')==route.get('world_session'))
    if not exact:
        raise RuntimeError('Bobby uncertain route is not the exact unmoved first-segment rejection')
    host_target,host_source=_host_return(current)
    if (host_source!=route['return_source']
            or not _same_point(host_target,route['return_target'])):
        raise RuntimeError('Bobby rejection recovery Home no longer matches the host lease')
    return _archive_unmoved(c,path,ledger,state,route,current,request_id)


def _unmoved_rejection(route,evidence):
    if not isinstance(route,dict) or not isinstance(evidence,dict):return None
    segment=route.get('current_segment');params=evidence.get('params')
    keys=evidence.get('movement_keys');velocity=evidence.get('velocity')
    exact=(route.get('state')=='outbound_uncertain'
        and route.get('route_id')==evidence.get('route_id')
        and route.get('task_session')==evidence.get('task_session')
        and route.get('world_session')==evidence.get('world_session')
        and route['candidate']['cache_server']==server_key(evidence.get('server'))
        and route['candidate']['dimension']==evidence.get('dimension')
        and route.get('outbound_confirmed')==0 and route.get('return_confirmed')==0
        and route.get('recent_segments')==[]
        and _segment_record(route,segment,done=False)
        and segment.get('direction')=='outbound' and segment.get('index')==1
        and segment.get('state')=='uncertain'
        and segment.get('request_id')==evidence.get('request_id')
        and segment.get('pre_dispatch_control_revision')==evidence.get('revision_before')
        and segment.get('native_phase')=='error'
        and segment.get('native_detail')==UNLOADED_AIR_ONLY_REJECTION
        and segment.get('detail')==UNLOADED_AIR_ONLY_REJECTION
        and _same_point(segment.get('terminal_pos'),segment.get('from'))
        and evidence.get('op')=='navigate' and evidence.get('phase')=='error'
        and evidence.get('pre_dispatch_rejected') is True
        and evidence.get('detail')==UNLOADED_AIR_ONLY_REJECTION
        and isinstance(params,dict) and params.get('air_only') is True
        and _same_point(params.get('target'),segment.get('target'))
        and _same_point(evidence.get('position_before'),segment.get('from'))
        and _same_point(evidence.get('terminal_pos'),segment.get('from'))
        and type(evidence.get('revision_before')) is int
        and evidence.get('revision_after')==evidence.get('revision_before')
        and isinstance(evidence.get('request_id'),str) and bool(evidence['request_id'])
        and isinstance(keys,dict) and bool(keys)
        and all(type(value) is bool and value is False for value in keys.values())
        and isinstance(velocity,list) and len(velocity)==3
        and all(type(value) in (int,float) and math.isfinite(value)
                and abs(value)<=1e-7 for value in velocity))
    return segment if exact else None


def _bind_legacy_unmoved_rejection(route,evidence):
    """Upgrade exactly one pre-fix route after durable evidence identifies it."""
    if not isinstance(route,dict):return False
    segment=route.get('current_segment')
    if (not isinstance(segment,dict)
            or any(name in segment for name in ('request_id','pre_dispatch_control_revision',
                                                'native_phase','native_detail','terminal_pos'))):
        return False
    candidate=copy.deepcopy(route);upgraded=candidate['current_segment']
    upgraded.update(request_id=evidence.get('request_id'),
        pre_dispatch_control_revision=evidence.get('revision_before'),
        native_phase='error',native_detail=UNLOADED_AIR_ONLY_REJECTION,
        detail=UNLOADED_AIR_ONLY_REJECTION,
        terminal_pos=copy.deepcopy(evidence.get('terminal_pos')))
    if _unmoved_rejection(candidate,evidence) is None:return False
    segment.clear();segment.update(upgraded)
    return True


def _archive_unmoved(c,path,ledger,state,route,current,request_id):
    archived=copy.deepcopy(route)
    archived.update(state='outbound_rejected_unmoved',
                    recovered_at=current.get('time'),request_id=request_id,
                    native_rejection=UNLOADED_AIR_ONLY_REJECTION)
    state['routes'].append(archived);del state['routes'][:-MAX_ROUTES]
    state['active_route']=None;_write(path,ledger);_detach(c)
    return {'state':'outbound_rejected_unmoved','route_id':route['route_id'],
            'request_id':request_id,'moved':False}


def recover_parked_unmoved_first_rejection(c,path,ledger,evidence,finish_evidence):
    """One-time legacy recovery after verified vertical high-park cleanup."""
    if not isinstance(finish_evidence,dict):
        raise RuntimeError('Bobby parked rejection recovery needs finish evidence')
    state=ledger_state(ledger,ledger[LEDGER_KEY]['server'],
                       ledger[LEDGER_KEY]['dimension'])
    route=state.get('active_route');segment=_unmoved_rejection(route,evidence)
    current=c.status();lease=current.get('supervision_lease') or {}
    terminal=evidence.get('terminal_pos');snapshot=finish_evidence.get('snapshot')
    snapshot_lease=(snapshot.get('supervision_lease')
                    if isinstance(snapshot,dict) else None)
    parked=(segment is not None
        and current.get('world_session')==route.get('world_session')
        and route['candidate']['cache_server']==server_key(current.get('server'))
        and route['candidate']['dimension']==current.get('dimension')
        and current.get('health',0)>=18 and current.get('flight') is True
        and current.get('guard_armed') is True and current.get('guard_pve_only') is True
        and not current.get('under_water') and not current.get('manual_movement')
        and not (current.get('safety_hold') or {}).get('active')
        and current.get('phase')=='parking'
        and lease.get('kind')=='parking'
        and isinstance(lease.get('id'),str) and bool(lease['id'])
        and lease.get('job_session')==route.get('task_session')
        and lease.get('world_session')==route.get('world_session')
        and lease.get('revision')==current.get('control_revision')
        and math.hypot(current['pos'][0]-terminal[0],current['pos'][2]-terminal[2])<=.05
        and current['pos'][1]>=terminal[1]
        and finish_evidence.get('action')=='KEEP_PVE_GUARD'
        and finish_evidence.get('lease')==lease.get('id')
        and finish_evidence.get('job_session')==route.get('task_session')
        and isinstance(snapshot,dict)
        and snapshot.get('world_session')==route.get('world_session')
        and snapshot.get('dimension')==route['candidate']['dimension']
        and server_key(snapshot.get('server'))==route['candidate']['cache_server']
        and _same_park_pose(snapshot.get('pos'),current.get('pos'))
        and snapshot.get('health',0)>=18 and snapshot.get('flight') is True
        and snapshot.get('guard_armed') is True
        and snapshot.get('guard_pve_only') is True
        and snapshot.get('control_revision')==lease.get('revision')
        and isinstance(snapshot_lease,dict)
        and snapshot_lease.get('id')==finish_evidence.get('lease')==lease.get('id')
        and snapshot_lease.get('job_session')==route.get('task_session')
        and snapshot_lease.get('world_session')==route.get('world_session')
        and snapshot_lease.get('kind')=='parking'
        and snapshot_lease.get('revision')==snapshot.get('control_revision')
        and snapshot_lease.get('return_target')==lease.get('return_target'))
    if not parked:
        raise RuntimeError('Bobby rejection finish evidence is not the exact vertical safe park')
    host_target,host_source=_host_return(current)
    snapshot_target,snapshot_source=_host_return(snapshot)
    if (host_source!=route['return_source']
            or snapshot_source!=route['return_source']
            or not _same_point(host_target,route['return_target'])
            or not _same_point(snapshot_target,route['return_target'])):
        raise RuntimeError('Bobby parked rejection Home no longer matches the host lease')
    return _archive_unmoved(c,path,ledger,state,route,current,evidence['request_id'])


def recover_parked_rejection_files(c,resource_path,movement_path,events_path,
                                   finish_path):
    """Deterministically reconcile one legacy rejection from durable evidence."""
    import json
    def document(raw,limit):
        file=Path(raw)
        if file.is_symlink() or not file.is_file() or file.stat().st_size>limit:
            raise RuntimeError('Bobby rejection evidence file is missing or oversized')
        value=json.loads(file.read_text())
        if not isinstance(value,dict):raise RuntimeError('Bobby rejection evidence is malformed')
        return file,value
    resource_file,ledger=document(resource_path,16*1024*1024)
    movement_file,movement=document(movement_path,2*1024*1024)
    _,finish=document(finish_path,2*1024*1024)
    prefix='movement-failure-';suffix='.json';name=movement_file.name
    if not name.startswith(prefix) or not name.endswith(suffix):
        raise RuntimeError('Bobby movement evidence filename has no request identity')
    request_id=name[len(prefix):-len(suffix)]
    event_file=Path(events_path)
    if event_file.is_symlink() or not event_file.is_file() or event_file.stat().st_size>8*1024*1024:
        raise RuntimeError('Bobby event evidence file is missing or oversized')
    matches=[]
    for line in event_file.read_text().splitlines():
        try:row=json.loads(line)
        except json.JSONDecodeError:raise RuntimeError('Bobby event evidence is malformed') from None
        if isinstance(row,dict) and row.get('request_id')==request_id:matches.append(row)
    if len(matches)!=1:raise RuntimeError('Bobby rejection needs one exact native event')
    event=matches[0];samples=movement.get('last_inflight')
    sample=samples[-1] if isinstance(samples,list) and samples else None
    state=ledger_state(ledger,ledger[LEDGER_KEY]['server'],ledger[LEDGER_KEY]['dimension'])
    route=state.get('active_route');snapshot=finish.get('snapshot')
    if (not isinstance(route,dict) or not isinstance(samples,list)
            or not _idle_movement_samples(samples,movement.get('terminal_pos'))
            or not isinstance(sample,dict)
            or not isinstance(snapshot,dict)
            or movement.get('op')!=event.get('op')
            or movement.get('params')!=event.get('params')
            or movement.get('detail')!=event.get('detail')
            or movement.get('terminal_pos')!=event.get('position_after')):
        raise RuntimeError('Bobby durable rejection evidence does not agree')
    evidence={'route_id':route['route_id'],'task_session':finish.get('job_session'),
        'world_session':event.get('world_session'),'server':snapshot.get('server'),
        'dimension':snapshot.get('dimension'),'request_id':request_id,
        'op':event.get('op'),'params':event.get('params'),'phase':event.get('phase'),
        'detail':event.get('detail'),'pre_dispatch_rejected':True,
        'position_before':event.get('position_before'),
        'terminal_pos':movement.get('terminal_pos'),
        'revision_before':event.get('revision_before'),
        'revision_after':event.get('revision_after'),
        'movement_keys':sample.get('movement_keys'),'velocity':sample.get('velocity')}
    if _unmoved_rejection(route,evidence) is None:
        if not _bind_legacy_unmoved_rejection(route,evidence):
            raise RuntimeError('Bobby durable evidence cannot bind the persisted route request')
        _write(resource_file,ledger)
    return recover_parked_unmoved_first_rejection(
        c,resource_file,ledger,evidence,finish)


def _idle_movement_samples(samples,terminal):
    if not isinstance(samples,list) or not 1<=len(samples)<=3:return False
    for row in samples:
        keys=row.get('movement_keys') if isinstance(row,dict) else None
        velocity=row.get('velocity') if isinstance(row,dict) else None
        if (not isinstance(row,dict) or row.get('pos')!=terminal
                or not isinstance(keys,dict) or not keys
                or any(type(value) is not bool or value is not False
                       for value in keys.values())
                or not isinstance(velocity,list) or len(velocity)!=3
                or any(type(value) not in (int,float) or not math.isfinite(value)
                       or abs(value)>1e-7 for value in velocity)):
            return False
    return True


def mark_candidate(c, path, ledger, state_name, *, detail=None):
    state, route = _exact_route(c, path, ledger)
    key = candidate_key(route['candidate'])
    previous = state['visited'].get(key)
    if previous is None and len(state['visited'])>=MAX_VISITS:
        raise RuntimeError('Bobby 雪地访问账本已达有界上限；停止新候选')
    if previous is not None:
        history=state.setdefault('visit_history', {}).setdefault(key, [])
        history.append(previous);del history[:-8]
    row = {'state': state_name, 'world_session': c.world,
           'candidate': public_candidate(route['candidate']),
           'observed_at': c.status().get('time')}
    if detail is not None:
        row['detail'] = str(detail)
    state['visited'][key] = row
    _write(path, ledger)


def mark_harvesting(c, path, ledger):
    state, route = _exact_route(c, path, ledger)
    route['state'] = 'harvesting'
    _write(path, ledger)


def authorizes_natural_snowpack(c,region):
    """Bind the relaxed natural-snow rule to this exact active cache route."""
    raw=getattr(c,'bobby_snow_resource_path',None)
    evidence=region.get('bobby_snow_route') if isinstance(region,dict) else None
    if raw is None or not isinstance(evidence,dict):return False
    try:
        path=Path(raw)
        if path.is_symlink() or not path.is_file() or path.stat().st_size>16*1024*1024:
            return False
        import json
        ledger=json.loads(path.read_text());_,route=_exact_route(c,path,ledger)
        candidate=route['candidate'];low,high=region.get('min'),region.get('max')
        tile=candidate['tile']
        from .bobby_snow_cache import SNOW_BIOMES
        return (route.get('state')=='harvesting'
            and region.get('allow_natural_snowpack') is True
            and evidence.get('route_id')==route['route_id']
            and evidence.get('world_session')==c.world
            and evidence.get('live_biome_verified') is True
            and evidence.get('live_biome') in SNOW_BIOMES
            and evidence.get('chunk')==candidate['chunk']
            and evidence.get('region_file')==candidate['region_file']
            and evidence.get('fingerprint')==candidate['fingerprint']
            and evidence.get('cache_server')==candidate['cache_server']
            and evidence.get('dimension')==candidate['dimension']
            and isinstance(low,list) and isinstance(high,list)
            and len(low)==len(high)==3
            and tile[0]<=low[0]<=high[0]<=tile[0]+15
            and tile[1]<=low[2]<=high[2]<=tile[1]+15)
    except (OSError,RuntimeError,ValueError,TypeError,KeyError,AttributeError):
        return False


def return_home(c, checkpoint, *, acquisition_path=None,
                acquisition_ledger=None, reason='completed'):
    """Return through confirmed outward segments; never accept Python coordinates."""
    raw = getattr(c, 'bobby_snow_resource_path', None)
    if raw is None:
        return None
    path = Path(raw)
    import json
    ledger = json.loads(path.read_text())
    state, route = _exact_route(c, path, ledger)
    if route.get('state') not in ('candidate_arrived', 'harvesting', 'return_required'):
        from .acquisition import Unavailable
        _detach(c)
        raise Unavailable('Bobby 雪地路线不在可返航状态；不重放',
                          'waiting', code='route_uncertain')
    route.update(state='return_required', return_reason=reason,
                 return_started_at=c.status().get('time'))
    if acquisition_ledger is not None and acquisition_path is not None:
        acquisition_ledger['bobby_return'] = {
            'state': 'inflight', 'route_id': route['route_id'],
            'world_session': c.world, 'reason': reason}
        expedition = acquisition_ledger.get('bobby_expedition')
        if isinstance(expedition, dict):
            expedition['state'] = 'return_inflight'
        _write(acquisition_path, acquisition_ledger)
    _write(path, ledger)
    if route.get('outbound_confirmed')!=route.get('segment_count'):
        from .acquisition import Unavailable
        route.update(state='return_uncertain',detail='outbound segment count changed')
        if acquisition_ledger is not None and acquisition_path is not None:
            acquisition_ledger['bobby_return'].update(
                state='uncertain',detail='outbound segment count changed')
            expedition=acquisition_ledger.get('bobby_expedition')
            if isinstance(expedition,dict):expedition['state']='return_uncertain'
            _write(acquisition_path,acquisition_ledger)
        _write(path,ledger);_detach(c)
        raise Unavailable('Bobby 雪地出站段未全部确认；不生成返航路线',
                          'waiting',code='route_uncertain')
    try:
        index=0
        # First regain the exact candidate cruise point after local harvesting,
        # then reverse outbound points lazily.  This stays constant-size even
        # for a route spanning most of the Minecraft world border.
        index+=1
        _move(c,route,state,path,ledger,checkpoint,list(route['target']),'return',
              index,min_health=18)
        for outbound_index in range(route['segment_count']-1,0,-1):
            index+=1;point=_waypoint(route,outbound_index)
            _move(c, route, state, path, ledger, checkpoint, point, 'return',
                  index, min_health=18)
        index+=1
        _move(c,route,state,path,ledger,checkpoint,list(route['return_bridge']),'return',
              index,min_health=18)
        home_count=route['return_segment_count']-route['segment_count']-1
        for home_index in range(1,home_count+1):
            index+=1
            point=_leg_waypoint(route['return_bridge'],route['return_target'],
                                home_index,home_count)
            _move(c,route,state,path,ledger,checkpoint,point,'return',index,
                  min_health=18)
    except Exception as error:
        route.update(state='return_uncertain', detail=str(error))
        if acquisition_ledger is not None and acquisition_path is not None:
            acquisition_ledger['bobby_return'].update(state='uncertain', detail=str(error))
            expedition = acquisition_ledger.get('bobby_expedition')
            if isinstance(expedition, dict):
                expedition['state'] = 'return_uncertain'
            _write(acquisition_path, acquisition_ledger)
        _write(path, ledger)
        _detach(c)
        from .acquisition import Unavailable
        raise Unavailable('Bobby 雪地返航回执不确定；该段不会自动重放',
                          'waiting', code='route_uncertain') from error
    arrived = c.status()
    route.update(state='home_arrived', returned_at=arrived.get('time'))
    state['routes'].append(copy.deepcopy(route))
    del state['routes'][:-MAX_ROUTES]
    state['active_route'] = None
    _write(path, ledger)
    if acquisition_ledger is not None and acquisition_path is not None:
        acquisition_ledger['bobby_return'].update(
            state='home_arrived', returned_at=arrived.get('time'))
        expedition = acquisition_ledger.get('bobby_expedition')
        if isinstance(expedition, dict):
            expedition['state'] = 'home_arrived'
        _write(acquisition_path, acquisition_ledger)
    c.anchor = list(arrived['pos'])
    result = {'route_id': route['route_id'], 'returned_at': arrived.get('time'),
              'route_replay': False, 'segments': route['return_segment_count'],
              'return_source':route['return_source']}
    _detach(c)
    return result
