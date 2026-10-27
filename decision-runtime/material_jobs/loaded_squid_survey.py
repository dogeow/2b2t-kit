"""Current hot-runtime entity observations, never chunk-cache spawn guesses."""
import json
import math
from pathlib import Path


def read(root, state):
    return _read(root,state,glow=False)

def read_glow(root,state):
    return _read(root,state,glow=True)

def _read(root, state,*,glow):
    path = Path(root)/'loaded-squid-survey.json'
    try:
        if path.stat().st_size > 1048576:
            return []
        q = json.loads(path.read_text())
    except (OSError, ValueError, TypeError):
        return []
    scope='current_client_loaded_server_entities_wild_glow_squid'if glow else'current_client_loaded_server_entities_ordinary_unnamed_squid_y50_64'
    rows_key='glow_squids'if glow else'squids'
    species='minecraft:glow_squid'if glow else'minecraft:squid'
    if (not isinstance(q, dict) or q.get('protocol') != 1 or glow and q.get('glow_protocol')!=1 or q.get('connected') is not True
            or state.get('connected') is not True
            or any(q.get(k) != state.get(k) for k in ('world_session', 'server', 'dimension'))
            or type(q.get('time')) is not int or type(state.get('time')) is not int
            or not -1000 <= state['time']-q['time'] <= 1000
            or q.get('glow_scope'if glow else'scope') != scope
            or not isinstance(q.get(rows_key), list) or len(q[rows_key]) > 4096):
        return []
    result = []
    for e in q[rows_key]:
        p = e.get('pos') if isinstance(e, dict) else None
        if (not isinstance(e, dict) or e.get('type') != species
                or e.get('alive') is not True or e.get('has_custom_name') is not False
                or type(e.get('health')) not in (int, float) or not math.isfinite(e['health']) or e['health'] <= 0
                or not isinstance(p, list) or len(p) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in p)
                or not (-64<=p[1]<320 if glow else 50<=p[1]<=64) or not isinstance(e.get('uuid'), str)
                or type(e.get('id')) is not int):
            continue
        result.append({**e, 'observed_at': q['time'], 'source': 'current_loaded_glow_squid_survey'if glow else'current_loaded_squid_survey'})
    return result
