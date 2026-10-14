"""Harvest a registered dry natural roof with one existing Kit controller.

The actor stands on a proved floor in adjoining air, removes the upper then
lower cell, and confirms real backpack gain. No native quarry target support,
new lease, old action replay, or clearance from cached geology is assumed.
"""
import json
import math
import time
import re
from pathlib import Path
from collections import deque

from kit_runtime.journal import write_json
from material_trip_policy import room_for_item
from .acquisition import _scan, _safe, _tool, _choose_tool, block_id, carried, NATURAL, LIGHTS
from .colored_sources import _protected
from .local_air_path import move
from .natural_block_pipeline import _dry_natural, _hand_matches
from .protocol import JobBlocked

ITEM = 'minecraft:dripstone_block'
ALLOWED = {'minecraft:stone', ITEM}


def bounds(region):
    low, high = region.get('min'), region.get('max')
    if (region.get('source') != 'natural_survey' or region.get('authorized') is not True
            or not isinstance(low, list) or not isinstance(high, list)
            or len(low) != 3 or len(high) != 3
            or any(type(v) is not int for v in low+high)
            or not -62 <= low[1] < high[1] <= 316 or high[1]-low[1] != 1
            or any(not 1 <= high[i]-low[i]+1 <= 16 for i in (0, 2))):
        raise JobBlocked('Roof harvest needs a registered two-layer natural region, at most 16x16')
    return low, high


def local_rows(rows, pos):
    return [b for b in rows if all(pos[i]-2 <= b['pos'][i] <= pos[i]+2 for i in range(3))]


def retained_light(row):
    return (block_id(row) in LIGHTS and row.get('passable') is True
            and row.get('solid') is False and row.get('fluid') is False
            and row.get('block_entity') is False)


def light_supports(rows):
    """Retaining a torch also requires retaining its real supporting block."""
    protected=set()
    for b in rows:
        if not retained_light(b):continue
        x,y,z=b['pos']
        if block_id(b)=='minecraft:torch':protected.add((x,y-1,z))
        else:
            match=re.search(r'facing=(north|south|west|east)',b.get('state',''))
            offsets={'north':(0,1),'south':(0,-1),'west':(1,0),'east':(-1,0)}
            choices=[offsets[match.group(1)]] if match else list(offsets.values())
            protected.update((x+dx,y,z+dz) for dx,dz in choices)
    return protected


def valid_entry(entry, low, high, position):
    return (isinstance(entry,list) and len(entry)==3 and all(type(v)is int for v in entry)
            and entry[1]==low[1] and all(low[i]<=entry[i]<=high[i] for i in(0,2))
            and low[1]+1<=position[1]<=low[1]+2.5
            and math.hypot(position[0]-(entry[0]+.5),position[2]-(entry[2]+.5))<=2)


def dry_roof_context(rows, pos, plane):
    """A complete full-block floor can separate pointed dripstone below it.

    Never changes the generic natural/quarry hazard rules. Only pointed cells
    strictly beneath the unchanged, completely observed 5x5 floor are isolated.
    Liquids, falling blocks, missing floor, containers and pointed cells in or
    above that floor retain the ordinary refusal.
    """
    local=[b for b in local_rows(rows,pos) if not retained_light(b)]
    pointed=[b for b in local if block_id(b)=='minecraft:pointed_dripstone']
    if not pointed:return _dry_natural(local)
    floor_y=plane-1
    if any(b['pos'][1]>=floor_y for b in pointed):return False
    cells={tuple(b['pos']):b for b in local}
    for x in range(pos[0]-2,pos[0]+3):
        for z in range(pos[2]-2,pos[2]+3):
            floor=cells.get((x,floor_y,z))
            if (not floor or block_id(floor)not in NATURAL or floor.get('solid')is not True
                    or floor.get('fluid')is not False or floor.get('block_entity')is not False):return False
    return _dry_natural([b for b in local if block_id(b)!='minecraft:pointed_dripstone'])


def offers(rows, low, high, position):
    """Input must be a complete native scan of the envelope expanded by two."""
    cells = {tuple(b['pos']): b for b in rows if not retained_light(b)}
    protected_lights=light_supports(rows)
    floor_y = low[1]-1
    columns = []
    for x in range(low[0], high[0]+1):
        for z in range(low[2], high[2]+1):
            blocks = [cells.get((x,y,z)) for y in (low[1], high[1])]
            floor = cells.get((x, floor_y, z))
            if (not any(blocks) or not floor or not floor.get('solid') or floor.get('fluid')
                    or floor.get('block_entity')
                    or any((x,y,z)in protected_lights for y in (low[1],high[1]))
                    or any(b and (block_id(b) not in ALLOWED
                                  or not dry_roof_context(rows,b['pos'],low[1])) for b in blocks)):
                continue
            columns.append((x,z,any(b and block_id(b)==ITEM for b in blocks)))
    targets = [(x,z) for x,z,drip in columns if drip]
    result = []
    if not targets:return result
    # A nearby air pocket can be isolated behind stone. Use the same complete
    # scan for three-dimensional connectivity before proposing a station.
    first=tuple(math.floor(v) for v in position)
    scan_low=[low[i]-2 for i in range(3)]
    scan_high=[high[i]+2 for i in range(3)]
    def clear(q):
        return (all(scan_low[i]<=q[i]<=scan_high[i] for i in (0,2))
                and scan_low[1]<=q[1]<scan_high[1]
                and q not in cells and (q[0],q[1]+1,q[2]) not in cells)
    reachable=set();queue=deque()
    if clear(first):reachable.add(first);queue.append(first)
    while queue:
        q=queue.popleft()
        for delta in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
            nxt=tuple(q[i]+delta[i] for i in range(3))
            if nxt not in reachable and clear(nxt):reachable.add(nxt);queue.append(nxt)
    for x,z,_ in columns:
        for dx,dz,face in ((-1,0,'west'),(1,0,'east'),(0,-1,'north'),(0,1,'south')):
            sx,sz=x+dx,z+dz
            support=cells.get((sx,floor_y,sz))
            station=[sx+.5,float(low[1])+.2,sz+.5]
            if (support and support.get('solid') and not support.get('fluid')
                    and not support.get('block_entity')
                    and all((sx,y,sz) not in cells for y in (low[1],high[1]))
                    and (sx,low[1],sz) in reachable
                    and math.dist(position,station)<=12):
                distance=min(abs(x-tx)+abs(z-tz) for tx,tz in targets)
                result.append((distance,math.dist(position,station),x,z,face,station))
    return result


def completed_mine(reply, request_id, world, removed):
    # Save request_id before the following scan changes client.last.
    return (reply.get('id') == request_id and reply.get('world_session') == world
            and reply.get('phase') == 'done' and removed == [])


def run(c, profile, region, target_count, out, checkpoint):
    low,high=bounds(region)
    if type(target_count) is not int or not 1 <= target_count <= 64:
        raise ValueError('Roof target is an absolute main-backpack total 1..64')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'roof-harvest.json'
    world=c.world
    def state():
        checkpoint();q=c.status();_safe(q)
        lease=q.get('supervision_lease') or {}
        if (q.get('world_session')!=world or lease.get('world_session')!=world
                or lease.get('kind')!='materials' or lease.get('job_session')!=c.task
                or lease.get('revision')!=q.get('control_revision')
                or q.get('dimension')!=profile.get('dimension')
                or q.get('server','').removesuffix(':25565')!=profile.get('server','').removesuffix(':25565')):
            raise JobBlocked('Roof controller, profile or current world changed')
        return q
    first=state()
    if any(_protected([x,low[1],z],profile,first)
           for x in (low[0],high[0]) for z in (low[2],high[2])):
        raise JobBlocked('Roof region overlaps protected construction or storage')
    if path.exists():
        book=json.loads(path.read_text())
        if any(book.get(k)!=v for k,v in {'world_session':world,'min':low,'max':high,
                'target':target_count}.items()):raise JobBlocked('Roof journal scope changed')
        if book.get('pending'):raise JobBlocked('Unknown roof intent retained; never replay')
    else:
        book={'world_session':world,'min':low,'max':high,'target':target_count,
              'target_scope':'actual_backpack','initial':carried(first,ITEM),
              'pending':None,'receipts':[],'columns':[]}
        write_json(path,book)

    def mine(pos,face):
        rows=_scan(c,[v-2 for v in pos],[v+2 for v in pos],state)
        if not dry_roof_context(rows,pos,low[1]):raise JobBlocked('Roof local hazards or separating floor changed; mining not dispatched')
        b=next((b for b in rows if b['pos']==pos),None)
        if b is None or retained_light(b):return
        if tuple(pos)in light_supports(rows):raise JobBlocked('Existing torch support is retained; no mining sent')
        if block_id(b) not in ALLOWED or _protected(pos,profile,state()):
            raise JobBlocked('Roof target is no longer an ordinary authorized natural cell')
        tool=_tool(state(),'pickaxe',33,no_silk=True);_choose_tool(c,tool,state)
        q=state();selected=tool['slot'] if tool['slot']<9 else 5
        if not _hand_matches(q,tool,selected):raise JobBlocked('Held pickaxe metadata changed')
        live_rows=_scan(c,[v-2 for v in pos],[v+2 for v in pos],state)
        live=next((row for row in live_rows if row['pos']==pos),None)
        if (live is None or live['state']!=b['state']
                or not dry_roof_context(live_rows,pos,low[1])
                or tuple(pos)in light_supports(live_rows)):
            raise JobBlocked('Roof target or separating floor changed before mining')
        dropped=ITEM if block_id(b)==ITEM else 'minecraft:cobblestone'
        if room_for_item(q,dropped)<1:raise JobBlocked('No real backpack room for the next roof drop; no mining sent')
        book['pending']={'kind':'mine','pos':pos,'expected_state':b['state'],'face':face,
                         'tool':tool,'before':carried(q,ITEM)};write_json(path,book)
        try:
            reply=c.request('mine_block',pos=pos,face=face,expected_state=b['state'],seconds=20)
        finally:
            book['pending']['request_id']=c.last;write_json(path,book)
        rid=c.last;q=state();removed=_scan(c,pos,pos,state)
        if not completed_mine(reply,rid,world,removed) or not _hand_matches(q,tool,selected,mined=True):
            raise JobBlocked('Roof mining result uncertain; preserve intent without replay')
        book['receipts'].append({**book['pending'],'native':reply,'removed_verified':True})
        book['pending']=None;write_json(path,book)

    entry=region.get('entry_position')
    if entry is not None and not book.get('entry_complete') and carried(state(),ITEM)<target_count:
        q=state();position=q['pos']
        if not valid_entry(entry,low,high,position):
            raise JobBlocked('Roof entry requires the existing adjoining upper air, not remote mining')
        rows=_scan(c,[v-2 for v in entry],[v+2 for v in entry],state)
        above=next((b for b in rows if b['pos']==[entry[0],high[1],entry[2]]),None)
        if above and not retained_light(above):raise JobBlocked('Roof entry upper body cell is not already open')
        before=carried(q,ITEM);cell=next((b for b in rows if b['pos']==entry),None)
        expected=int(cell is not None and block_id(cell)==ITEM)
        mine(entry,'up')
        verified=_scan(c,[entry[0],low[1]-1,entry[2]],
                       [entry[0],high[1],entry[2]],state)
        floor=next((b for b in verified if b['pos']==[entry[0],low[1]-1,entry[2]]),None)
        if (not floor or block_id(floor)not in NATURAL or floor.get('solid')is not True
                or any(b['pos'][1]>=low[1]and not retained_light(b)for b in verified)):
            raise JobBlocked('Roof entry floor or body clearance not confirmed')
        book['pending']={'kind':'entry_pickup','pos':entry,'before':before,'expected_gain':expected}
        write_json(path,book);step=out/'entry-air';step.mkdir(exist_ok=False)
        move(c,[entry[0]+.5,float(low[1])+.2,entry[2]+.5],step,max_straight=2,foot_offset=.2)
        deadline=time.monotonic()+4
        while carried(state(),ITEM)<before+expected and time.monotonic()<deadline:time.sleep(.15)
        after=carried(state(),ITEM)
        if after!=before+expected:raise JobBlocked('Roof entry pickup remains uncertain; no replay')
        book['entry_receipt']={**book['pending'],'after':after}
        book['entry_complete']=True;book['pending']=None;write_json(path,book)

    maximum=(high[0]-low[0]+1)*(high[2]-low[2]+1)
    while carried(state(),ITEM)<target_count and len(book['columns'])<maximum:
        rows=_scan(c,[low[0]-2,low[1]-2,low[2]-2],
                   [high[0]+2,high[1]+2,high[2]+2],state)
        choices=offers(rows,low,high,state()['pos'])
        if not choices:break
        _,_,x,z,face,station=min(choices);index=len(book['columns'])
        if math.dist(state()['pos'],station)>.15:
            step=out/('station-'+str(index));step.mkdir(exist_ok=False);move(c,station,step,max_straight=2,foot_offset=.2)
        before=carried(state(),ITEM)
        expected=sum(block_id(b)==ITEM and b['pos'][0]==x and b['pos'][2]==z
                     and low[1]<=b['pos'][1]<=high[1] for b in rows)
        mine([x,high[1],z],face);mine([x,low[1],z],face)
        fresh=_scan(c,[x,low[1]-1,z],[x,high[1]+1,z],state)
        floor=next((b for b in fresh if b['pos']==[x,low[1]-1,z]),None)
        if (not floor or not floor.get('solid') or floor.get('fluid') or floor.get('block_entity')
                or any(low[1]<=b['pos'][1]<=high[1] and not retained_light(b) for b in fresh)):
            raise JobBlocked('New roof column lacks current floor or body clearance')
        book['pending']={'kind':'pickup','pos':[x,low[1],z],'before':before,'expected_gain':expected}
        write_json(path,book)
        step=out/('pickup-'+str(index));step.mkdir(exist_ok=False)
        move(c,[x+.5,float(low[1])+.2,z+.5],step,max_straight=2,foot_offset=.2)
        deadline=time.monotonic()+4
        while carried(state(),ITEM)<before+expected and time.monotonic()<deadline:time.sleep(.15)
        after=carried(state(),ITEM)
        if after!=before+expected:raise JobBlocked('Roof removal does not prove exact backpack gain; no replay')
        book['columns'].append({**book['pending'],'after':after})
        book['pending']=None;write_json(path,book)
        print('ROOF_ACTUAL_BACKPACK',after,flush=True)
    final=carried(state(),ITEM)
    result={'phase':'done' if final>=target_count else 'waiting','item':ITEM,
            'target_scope':'actual_backpack','count':final,'gained':final-book['initial'],
            'safe_columns':len(book['columns']),'old_actions_replayed':False}
    write_json(out/'result.json',result);return result
