"""Validate hot-runtime passenger observations before planning ordinary transport."""
import json
import math
from pathlib import Path

SCOPE='current_client_loaded_server_vehicles_and_passengers'

def read(root,state):
    frame=read_frame(root,state)
    return []if frame is None else frame['vehicles']

def read_frame(root,state,*,allow_dead_passengers=False):
    path=Path(root)/'loaded-vehicle-survey.json'
    try:
        if path.stat().st_size>1048576:return None
        frame=json.loads(path.read_text())
    except (OSError,ValueError,TypeError):return None
    if(not isinstance(frame,dict)or frame.get('protocol')!=1 or frame.get('scope')!=SCOPE
            or frame.get('connected')is not True or state.get('connected')is not True
            or frame.get('truncated')is not False
            or any(frame.get(k)!=state.get(k)for k in ('world_session','server','dimension','player_uuid'))
            or type(frame.get('time'))is not int or type(state.get('time'))is not int
            or not -1000<=state['time']-frame['time']<=1000
            or not isinstance(frame.get('vehicles'),list)or len(frame['vehicles'])>128):return None
    result=[];identities=set()
    for row in frame['vehicles']:
        if not isinstance(row,dict):return None
        pos=row.get('pos');uuid=row.get('uuid');passengers=row.get('passengers')
        if(not isinstance(uuid,str)or not uuid or uuid in identities or type(row.get('id'))is not int
                or row.get('alive')is not True or not isinstance(row.get('type'),str)
                or not isinstance(pos,list)or len(pos)!=3
                or any(type(v)not in(int,float)or not math.isfinite(v)for v in pos)
                or not isinstance(passengers,list)or len(passengers)>8):return None
        if any(not isinstance(p,dict)or not isinstance(p.get('uuid'),str)or not p['uuid']or type(p.get('id'))is not int
               or (p.get('alive')is not True if not allow_dead_passengers else type(p.get('alive'))is not bool)for p in passengers):return None
        identities.add(uuid);result.append({**row,'observed_at':frame['time'],'observation_scope':SCOPE})
    return {**frame,'vehicles':result}

def villagers_aboard(vehicle,expected,*,player_uuid=None):
    """Exact healthy unnamed adult passengers; does not prove destination or safety."""
    passengers=vehicle.get('passengers')
    if not isinstance(passengers,list)or not expected or len(set(expected))!=len(expected):return False
    if {p.get('uuid')for p in passengers}!=set(expected)or len(passengers)!=len(expected):return False
    if any(p.get('type')!='minecraft:villager'or p.get('alive')is not True
           or p.get('is_baby')is not False or p.get('has_custom_name')is not False
           or type(p.get('health'))not in(int,float)or not math.isfinite(p['health'])or p['health']<19 for p in passengers):return False
    return player_uuid is None or(vehicle.get('leashed')is True and vehicle.get('leash_resolved')is True
        and vehicle.get('leash_holder',{}).get('uuid')==player_uuid)
