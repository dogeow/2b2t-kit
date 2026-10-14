"""Per-server travel limits confirmed by the user; reject before publishing native actions."""
import json
import math
from pathlib import Path
from .protocol import server_key

def validate(rule):
    if (not isinstance(rule,dict) or rule.get('schema')!=1
            or not isinstance(rule.get('server'),str) or rule.get('dimension')!='minecraft:overworld'
            or any(type(rule.get(k))is not int for k in ('min_x','max_x','min_z','max_z','margin'))
            or not -30_000_000<=rule['min_x']<rule['max_x']<=30_000_000
            or not -30_000_000<=rule['min_z']<rule['max_z']<=30_000_000
            or not 1<=rule['margin']<=64):
        raise ValueError('World boundary rule is malformed')
    return rule

def permits(rule,point):
    rule=validate(rule)
    if (not isinstance(point,(list,tuple)) or len(point)!=3
            or any(type(v)not in (int,float) or not math.isfinite(v)for v in point)):
        return False
    margin=rule['margin']
    return (rule['min_x']+margin<point[0]<rule['max_x']-margin
            and rule['min_z']+margin<point[2]<rule['max_z']-margin)

def check(root,state,op,params):
    path=Path(root).parent/'world-travel-bounds.json'
    if not path.exists():return
    if path.is_symlink() or path.stat().st_size>16384:raise RuntimeError('World travel boundary file is unsafe')
    rule=validate(json.loads(path.read_text()))
    if server_key(rule['server'])!=server_key(state.get('server','')) or rule['dimension']!=state.get('dimension'):return
    points=[]
    if op in ('navigate','walk','projection_air_seed'):points=[params.get('target')]
    elif op=='walk_path':points=params.get('path') or []
    elif op in ('approach_block','mine_block','interact'):
        points=[params.get('pos')]
    if any(not permits(rule,p) for p in points):
        raise RuntimeError('目标超出已确认的世界边界；未发送移动或交互')
