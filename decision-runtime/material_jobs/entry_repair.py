"""Replan a natural mine's entry from a complete current local scan.

Only a location hint is produced. Native acquisition still checks every slice,
tool, block and receipt. Original route holds and source records are retained.
"""
from collections import defaultdict
import math

from .acquisition import ROCK_SOURCES, _bounds, _rock_observation
from .discovery import _entrance, excluded


def choose(rows, region, player, profile, selection):
    if region.get('source') != 'natural_survey' or region.get('item') not in ROCK_SOURCES:
        return None
    low, high = _bounds(region)
    if not (1 <= high[0]-low[0] <= 5 and 1 <= high[2]-low[2] <= 5):
        return None
    cells = {tuple(r['pos']):r for r in rows}
    columns = defaultdict(list)
    for row in rows:
        columns[(row['pos'][0],row['pos'][2])].append(row)
    plans=[]
    for x in range(low[0],high[0]):
        for z in range(low[2],high[2]):
            for top in range(high[1],min(low[1]+17,120)+1):
                lo,hi=[x,low[1],z],[x+1,top,z+1]
                observed=_rock_observation(rows,lo,hi,region['item'])
                if not observed or not observed['available']:
                    continue
                entry,_=_entrance(columns,cells,x,z,top,{})
                if entry is None or not entry.get('access_shaft'):
                    continue
                column_high=[x+1,entry['surface_y'],z+1]
                if excluded(lo,column_high,profile,selection):
                    continue
                candidate={'item':region['item'],'min':lo,'max':hi,
                           'source':'natural_survey',**entry}
                cost=observed['remaining']+(entry['surface_y']-top)*4
                distance=math.hypot(x+1-player[0],z+1-player[2])
                plans.append(((-observed['available'],cost,distance,top),candidate,observed))
    if not plans:
        return None
    _,candidate,observed=min(plans,key=lambda p:p[0])
    return {'region':candidate,'observed_target_blocks':observed['available'],
            'observed_work_blocks':observed['remaining'],'inventory_credit':0}


def observe(client, region, profile, out):
    from pathlib import Path
    from kit_runtime.journal import write_json
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    # Eligibility is known before reading world blocks. Wide legacy sand sites
    # cannot use the narrow rock-shaft algorithm; do not scan 50k cells for it.
    low,high=_bounds(region)
    if (region.get('source')!='natural_survey' or region.get('item')not in ROCK_SOURCES
            or not(1<=high[0]-low[0]<=5 and 1<=high[2]-low[2]<=5)):
        proof={'world_session':client.world,'original_region':region,'planned':None,
               'reason':'region_not_eligible_for_rock_shaft_repair','game_movement_sent':False,
               'inventory_credit':0,'original_route_hold_unchanged':True}
        write_json(out/'entry-repair-plan.json',proof);return proof
    state=client.status();low,high=_bounds(region)
    center=[(low[i]+high[i]+1)/2 for i in range(3)]
    if math.hypot(state['pos'][0]-center[0],state['pos'][2]-center[2])>96:
        raise RuntimeError('Entry repair requires a current nearby observer; no travel sent')
    lo=[low[0]-3,low[1]-1,low[2]-3]
    hi=[high[0]+3,min(319,max(high[1]+22,math.ceil(state['pos'][1]+3))),high[2]+3]
    total=math.prod(hi[i]-lo[i]+1 for i in range(3))
    if total>50000:
        raise RuntimeError('Entry repair scan exceeds the bounded native volume')
    reply=client.checked('scan',min=lo,max=hi,details=True)
    write_json(out/'current-entry-scan.json',reply)
    if (reply.get('world_session')!=client.world or reply.get('scan_cells_read')!=total
            or reply.get('scan_total_cells')!=total or reply.get('control_revision')!=client.rev):
        raise RuntimeError('Entry repair scan is incomplete; original source retained')
    rows=reply.get('blocks',[]);seen=set()
    for row in rows:
        pos=tuple(row['pos'])
        if pos in seen or any(not lo[i]<=pos[i]<=hi[i] for i in range(3)):
            raise RuntimeError('Entry repair scan contains duplicate or outside cells')
        seen.add(pos)
    actual=client.status()
    if math.dist(actual['pos'],state['pos'])>.3:
        raise RuntimeError('Entry repair observer moved; original source retained')
    planned=choose(rows,region,actual['pos'],profile,actual.get('projection_selection',{}))
    proof={'world_session':client.world,'observed_at':reply['time'],
           'original_region':region,'planned':planned,'game_movement_sent':False,
           'inventory_credit':0,'original_route_hold_unchanged':True}
    write_json(out/'entry-repair-plan.json',proof)
    return proof
