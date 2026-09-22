"""Observed staircase anchors let bounded native depot routes include a distant stairwell."""
import json,math
from projection_completion import block_state
from work_access import approach_faces,ApproachUnavailable
DIRECTIONS={'north':(0,-1),'south':(0,1),'west':(-1,0),'east':(1,0)}
WOOD_STAIRS={f'minecraft:{wood}_stairs' for wood in ('oak','spruce','birch','jungle','acacia','dark_oak','mangrove','cherry','pale_oak','bamboo','crimson','warped')}

def stairwells(rows):
    stairs={}
    for row in rows:
        name,p=block_state(row['state'])
        if name in WOOD_STAIRS and p.get('half')=='bottom' and p.get('waterlogged')=='false' and p.get('shape')=='straight':
            stairs[tuple(row['pos'])]=(row,p)
    runs=[]
    for pos,(row,p) in stairs.items():
        dx,dz=DIRECTIONS[p['facing']];below=(pos[0]-dx,pos[1]-1,pos[2]-dz)
        if below in stairs and stairs[below][1]['facing']==p['facing']:continue
        run=[row];next_pos=(pos[0]+dx,pos[1]+1,pos[2]+dz)
        while next_pos in stairs and stairs[next_pos][1]['facing']==p['facing']:
            run.append(stairs[next_pos][0]);next_pos=(next_pos[0]+dx,next_pos[1]+1,next_pos[2]+dz)
        if len(run)>=3:runs.append(run)
    return runs

def approach_stairwell(client,placement_key):
    state=client.status();selection=state['projection_selection']
    if selection['key']!=placement_key:raise RuntimeError('Projection changed before transit')
    rows=client.request('scan',min=selection['min'],max=selection['max'],details=True)['blocks']
    runs=stairwells(rows)
    if not runs:raise RuntimeError('No observed stairwell in this construction')
    # Only two distinct anchors, not an unbounded retry over furniture stairs.
    anchors=sorted((min(run,key=lambda row:abs(row['pos'][1]+1-state['pos'][1])) for run in runs),key=lambda row:math.dist(row['pos'],state['pos']))
    tried=set()
    for row in anchors:
        pos=tuple(row['pos'])
        if pos in tried:continue
        tried.add(pos)
        try:face=approach_faces(client,list(pos),row['state'],('up','south','north','east','west'),seconds=90)
        except ApproachUnavailable:
            if len(tried)>=2:break
            continue
        proof={'placement_key':placement_key,'anchor':row,'face':face,'arrived':client.status()['pos']}
        (client.out/'stairwell-transit.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2));print('STAIRWELL_REACHED',list(pos),flush=True);return proof
    raise RuntimeError('Observed staircase access remains blocked')
