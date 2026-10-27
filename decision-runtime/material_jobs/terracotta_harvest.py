"""Plain terracotta from a bounded, freshly loaded badlands source.

Seed positions are travel hints. They cannot authorize mining without a new
server-backed biome survey and dry natural strata at each individual target.
"""
import math
from pathlib import Path

from kit_runtime.journal import write_json
from .acquisition import block_id

ITEM='minecraft:terracotta'
BADLANDS=frozenset('minecraft:'+n for n in ('badlands','wooded_badlands','eroded_badlands'))
STRATA=frozenset({'minecraft:terracotta'}|{'minecraft:'+n+'_terracotta'for n in
    ('white','orange','magenta','light_blue','yellow','lime','pink','gray','light_gray',
     'cyan','purple','blue','brown','green','red','black')})
GROUND=frozenset('minecraft:'+n for n in
    ('stone','granite','diorite','andesite','red_sandstone','smooth_red_sandstone',
     'dirt','coarse_dirt','grass_block'))
SOFT=frozenset('minecraft:'+n for n in('dead_bush','short_grass','tall_grass','fern','large_fern'))


def natural_context(rows,target):
    """Keep containers, constructions, water, cactus and falling sand intact."""
    if not isinstance(rows,list):return False
    if any(r.get('pos')==[target[0],target[1]+1,target[2]]and block_id(r)in SOFT for r in rows):return False
    if any(not isinstance(r,dict)or r.get('fluid')is not False
           or r.get('block_entity')is not False
           or not(block_id(r)in STRATA|GROUND
                  or block_id(r)in SOFT and r.get('solid')is False
                     and r.get('passable')is True)for r in rows):return False
    strata=[r for r in rows if block_id(r)in STRATA]
    return (any(r.get('pos')==target and block_id(r)==ITEM for r in strata)
            and len(strata)>=12 and len({r['pos'][1]for r in strata})>=2)


def exposed_targets(rows,low,high):
    """Potential real faces from a complete scan; no reachability or stock claim."""
    from .dry_hover_harvest import stations,visible_face
    cells={tuple(r['pos']):r for r in rows};result=[]
    for r in rows:
        p=r['pos']
        if block_id(r)!=ITEM or not all(low[i]+2<=p[i]<=high[i]-2 for i in range(3)):continue
        local=[cells[(x,y,z)]for x in range(p[0]-2,p[0]+3)
               for y in range(p[1]-2,p[1]+3)for z in range(p[2]-2,p[2]+3)if(x,y,z)in cells]
        if not natural_context(local,p):continue
        for point,face in stations(p):
            x,y,z=map(math.floor,point)
            if(not all(low[i]<=math.floor(point[i])<=high[i]for i in range(3))or y+1>high[1]
                    or(x,y,z)in cells or(x,y+1,z)in cells):continue
            if visible_face(local,point,p,face):result.append(p);break
    return result


def validate_biomes(reply,request_id,world,center,region):
    survey=reply.get('snow_biome_survey')or{};samples=survey.get('samples')
    if (reply.get('id')!=request_id or reply.get('world_session')!=world
            or reply.get('phase')not in(None,'done') or survey.get('center')!=center
            or survey.get('radius')!=16 or survey.get('stride')!=16
            or survey.get('requested_samples')!=9 or survey.get('loaded_samples')!=9
            or survey.get('unloaded_samples')!=0 or not isinstance(samples,list)or len(samples)!=9):
        raise RuntimeError('Badlands needs a complete current server biome survey')
    expected={(center[0]+dx,center[1]+dz)for dx in(-16,0,16)for dz in(-16,0,16)}
    observed=set();chunks={}
    for row in samples:
        p=row.get('pos');chunk=row.get('chunk')
        if (not isinstance(p,list)or len(p)!=3 or any(type(v)is not int for v in p)
                or not -64<=p[1]<=319 or(p[0],p[2])not in expected
                or(p[0],p[2])in observed or chunk!=[p[0]//16,p[2]//16]):
            raise RuntimeError('Badlands biome coordinates are incomplete or malformed')
        observed.add((p[0],p[2]));chunks[tuple(chunk)]=row.get('biome')
    if observed!=expected:raise RuntimeError('Badlands biome samples are incomplete')
    low,high=region['min'],region['max']
    needed={(x,z)for x in range(low[0]//16,high[0]//16+1)
                    for z in range(low[2]//16,high[2]//16+1)}
    if any(chunks.get(chunk)not in BADLANDS for chunk in needed):
        raise RuntimeError('Every source chunk must currently be a loaded badlands biome')
    return {'chunks':sorted(map(list,needed)),'source':'current_loaded_server_biomes',
            'inventory_credit':0,'seed_hint_used_as_proof':False}


def verify_region(c,region,checkpoint,out):
    low,high=region.get('min'),region.get('max')
    if (region.get('item')!=ITEM or not isinstance(low,list)or not isinstance(high,list)
            or len(low)!=3 or len(high)!=3 or any(type(v)is not int for v in low+high)
            or any(not 0<=high[i]-low[i]<=15 for i in range(3))
            or not -64<=low[1]<=high[1]<=319):
        raise ValueError('Terracotta requires its own surveyed source of at most16 cubed')
    path=Path(out)/'current-badlands-biomes.json'
    if path.exists():raise RuntimeError('Original badlands biome proof retained; no replay')
    checkpoint();state=c.status();center=[math.floor(state['pos'][i])for i in(0,2)]
    reply=c.request('scan_snow_biomes',center=center,radius=16,stride=16)
    proof=validate_biomes(reply,c.last,c.world,center,region)
    path.parent.mkdir(parents=True,exist_ok=True)
    write_json(path,{'world_session':c.world,'request_id':c.last,'region':region,
                     'native_reply':reply,**proof})
    return proof
