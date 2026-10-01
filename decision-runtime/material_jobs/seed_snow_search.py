"""Strict seed-candidate receipts; the full world seed never crosses this API."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from kit_runtime.journal import write_json
from .protocol import server_key


VERSION = 1
LEDGER_KEY = 'seed_snow_search'
MAX_BATCH = 128
MAX_TOTAL = 131_072
TOKEN = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
ROUTE = TOKEN
FORBIDDEN = {'seed', 'world_seed', 'cracked_seed', 'hashed_seed'}
MISMATCH_LIMIT = 2


def ledger_state(ledger):
    value = ledger.get(LEDGER_KEY)
    if value is None:
        value = {'version': VERSION, 'next_cursor': 0, 'total': None,
                 'radius': None, 'stride': 256, 'candidates': {}, 'routes': [],
                 'active_route': None, 'server_mismatches': 0,
                 'hints_disabled': False}
        ledger[LEDGER_KEY] = value
        return value
    if not isinstance(value,dict):
        raise RuntimeError('种子雪地候选记录损坏；保留原文件，不覆盖')
    # These fields were added without changing the on-disk version.  Old
    # ledgers remain readable, while a confirmed pair of server mismatches is
    # durable and prevents another predicted-seed flight after a restart.
    value.setdefault('server_mismatches', sum(
        isinstance(row, dict) and row.get('state') == 'server_mismatch'
        for row in value.get('candidates', {}).values()))
    value.setdefault('hints_disabled', value['server_mismatches'] >= 2)
    if (value.get('version') != VERSION
            or type(value.get('next_cursor')) is not int or value['next_cursor'] < 0
            or value.get('total') is not None
            and (type(value['total']) is not int or value['total'] < value['next_cursor'])
            or value.get('radius') is not None
            and (type(value['radius']) is not int or not 256 <= value['radius'] <= 32768)
            or value.get('stride') != 256
            or not isinstance(value.get('candidates'), dict)
            or len(value['candidates'])>MAX_TOTAL
            or not isinstance(value.get('routes'), list)
            or len(value['routes'])>MAX_TOTAL
            or value.get('active_route') is not None
            and not isinstance(value.get('active_route'),dict)
            or type(value.get('server_mismatches')) is not int
            or value['server_mismatches'] < 0
            or type(value.get('hints_disabled')) is not bool
            or value['hints_disabled'] is not (value['server_mismatches'] >= 2)):
        raise RuntimeError('种子雪地候选记录损坏；保留原文件，不覆盖')
    for key, row in value['candidates'].items():
        if (not isinstance(key, str) or not isinstance(row, dict)
                or key != f"{row.get('x')}:{row.get('z')}"
                or any(type(row.get(name)) is not int for name in
                       ('sample_cursor', 'x', 'z', 'sample_y', 'distance'))
                or not -64 <= row['sample_y'] <= 319
                or row['distance'] < 0
                or not isinstance(row.get('biome'), str) or not row['biome']
                or row.get('state') not in
                    ('predicted','route_inflight','arrived','returned_before_arrival',
                     'server_mismatch','detailed_empty')):
            raise RuntimeError('种子雪地候选内容损坏；保留原文件，不覆盖')
    if any(not isinstance(row, dict) for row in value['routes']):
        raise RuntimeError('种子雪地路线记录损坏；保留原文件，不覆盖')
    active=value.get('active_route')
    if (active is not None and (active.get('state') not in
            ('route_inflight','outbound_stopped','outbound_uncertain','candidate_arrived',
             'return_inflight','return_uncertain')
            or not isinstance(active.get('route_id'),str)
            or not isinstance(active.get('candidate'),list)
            or len(active['candidate'])!=2
            or any(type(value) is not int for value in active['candidate'])
            or not isinstance(active.get('world_session'),str))):
        raise RuntimeError('种子雪地当前路线记录损坏；保留原文件，不覆盖')
    return value


def refresh_hint_policy(value):
    """Persist the failover after two distinct predictions miss server truth."""
    if not isinstance(value,dict) or not isinstance(value.get('candidates'),dict):
        raise RuntimeError('种子雪地候选记录损坏；保留原文件，不覆盖')
    observed=sum(isinstance(row,dict) and row.get('state')=='server_mismatch'
                 for row in value['candidates'].values())
    value['server_mismatches']=max(value.get('server_mismatches',0),observed)
    value['hints_disabled']=value['server_mismatches']>=2
    return value['hints_disabled']


def _gate_path(directory, server, dimension):
    scope=hashlib.sha256((server_key(server)+'|'+dimension+'|snow-hints').encode()).hexdigest()[:20]
    return Path(directory)/('snow-hint-policy-'+scope+'.json')


def _gate(directory, server, dimension):
    path=_gate_path(directory,server,dimension)
    if not path.exists():
        return path,{'schema':1,'server':server_key(server),'dimension':dimension,
                     'mismatches':{},'disabled':False}
    if path.is_symlink():
        raise RuntimeError('雪地候选禁用记录路径不安全；保留原文件')
    if path.stat().st_size>262_144:
        raise RuntimeError('雪地候选禁用记录过大；保留原文件')
    value=json.loads(path.read_text())
    if (not isinstance(value,dict) or value.get('schema')!=1
            or value.get('server')!=server_key(server)
            or value.get('dimension')!=dimension
            or not isinstance(value.get('mismatches'),dict)
            or type(value.get('disabled')) is not bool
            or value['disabled'] is not (len(value['mismatches'])>=MISMATCH_LIMIT)
            or any(not re.fullmatch(r'[0-9a-f]{32}',key)
                   or not isinstance(row,dict)
                   or type(row.get('loaded_samples')) is not int
                   or row['loaded_samples']<=0
                   or not isinstance(row.get('world_session'),str)
                   or type(row.get('observed_at')) not in (int,float)
                   or not math.isfinite(row['observed_at'])
                   for key,row in value['mismatches'].items())):
        raise RuntimeError('雪地候选禁用记录损坏；保留原文件')
    return path,value


def shared_hints_disabled(directory,server,dimension):
    return _gate(directory,server,dimension)[1]['disabled']


def record_server_mismatch(directory,server,dimension,x,z,*,world_session,
                           observed_at,loaded_samples):
    if (type(x) is not int or type(z) is not int
            or not isinstance(world_session,str) or not world_session
            or type(observed_at) not in (int,float) or not math.isfinite(observed_at)
            or type(loaded_samples) is not int or loaded_samples<=0):
        raise ValueError('Server mismatch evidence is incomplete')
    path,value=_gate(directory,server,dimension)
    identity=hashlib.sha256(
        (server_key(server)+'|'+dimension+'|'+str(x)+'|'+str(z)).encode()).hexdigest()[:32]
    value['mismatches'].setdefault(identity,{
        'world_session':world_session,'observed_at':observed_at,
        'loaded_samples':loaded_samples})
    value['disabled']=len(value['mismatches'])>=MISMATCH_LIMIT
    write_json(path,value)
    return value['disabled']


def parse_reply(reply, request_id, world_session, expected_cursor):
    if (not isinstance(reply, dict) or reply.get('phase') not in (None, 'done')
            or reply.get('id') != request_id
            or reply.get('world_session') != world_session):
        raise ValueError('种子雪地候选回执不属于当前只读请求')
    value = reply.get('snow_seed_candidates')
    if not isinstance(value, dict) or _contains_forbidden_key(value):
        raise ValueError('种子雪地候选回执缺失或包含禁止字段')
    if value.get('protocol')!=VERSION or type(value.get('available')) is not bool:
        raise ValueError('种子雪地候选回执缺少可用性协议')
    if value['available'] is False:
        if value.get('reason')!='sampler_unavailable' or set(value)!={'protocol','available','reason'}:
            raise ValueError('种子雪地候选不可用回执格式无效')
        return value
    required = ('protocol','available','cursor', 'next_cursor', 'processed', 'total',
                'done', 'radius', 'stride', 'candidates')
    if any(name not in value for name in required):
        raise ValueError('种子雪地候选回执缺少进度字段')
    cursor, next_cursor = value['cursor'], value['next_cursor']
    processed, total = value['processed'], value['total']
    if (cursor != expected_cursor
            or any(type(number) is not int for number in
                   (cursor, next_cursor, processed, total, value['radius'], value['stride']))
            or not 0 <= cursor <= next_cursor <= total
            or total > MAX_TOTAL
            or not 0 <= processed <= MAX_BATCH
            or type(value['done']) is not bool or value['done'] != (next_cursor == total)
            or not 256 <= value['radius'] <= 32768 or value['stride'] != 256
            or not isinstance(value['candidates'], list)):
        raise ValueError('种子雪地候选范围、游标或计数无效')
    seen = set()
    for row in value['candidates']:
        target = row.get('target') if isinstance(row, dict) else None
        if (not isinstance(row, dict)
                or any(type(row.get(name)) is not int for name in
                       ('sample_cursor', 'x', 'z', 'sample_y', 'distance', 'expires_at'))
                or not cursor <= row['sample_cursor'] < next_cursor
                or not -64 <= row['sample_y'] <= 319 or row['distance'] < 0
                or not isinstance(row.get('biome'), str) or not row['biome']
                or not isinstance(row.get('token'), str) or not TOKEN.fullmatch(row['token'])
                or not isinstance(row.get('route_id'), str) or not ROUTE.fullmatch(row['route_id'])
                or not isinstance(target, list) or len(target) != 3
                or any(type(number) not in (int, float) or not math.isfinite(number)
                       for number in target)
                or target[0] != row['x'] + .5 or target[2] != row['z'] + .5
                or not 160 <= target[1] <= 316
                or (row['x'], row['z']) in seen):
            raise ValueError('种子雪地候选坐标、群系或短期令牌无效')
        seen.add((row['x'], row['z']))
    return value


def public_candidate(row):
    """Persist coordinates and prediction only; never persist the short-lived token."""
    return {name: row[name] for name in
            ('sample_cursor', 'x', 'z', 'sample_y', 'biome', 'distance')} \
        | {'state': 'predicted'}


def allowed_survey_tiles(center, radius=64, stride=64):
    found = set()
    for x in range(center[0]-radius, center[0]+radius+1, stride):
        for z in range(center[1]-radius, center[1]+radius+1, stride):
            found.add((math.floor(x/16)*16, math.floor(z/16)*16))
    return found


def _contains_forbidden_key(value):
    if isinstance(value, dict):
        return any(str(key).lower() in FORBIDDEN or _contains_forbidden_key(child)
                   for key, child in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden_key(child) for child in value)
    return False
