"""Bounded natural-resource discovery with a persistent visited-tile ledger."""
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from kit_runtime.journal import write_json
from .acquisition import ROCK_SOURCES, LOGS, NATURAL, AIR, LIGHTS, FALLING, block_id, rock_choice, _rock_observation, _travel
from .dirt_harvest import candidates as dirt_candidates
from native_sand_quarry import choose_quarry
from .protocol import server_key

ALGORITHM_VERSION = 2
MAX_SEEDS = 96
MAX_ENTRIES_PER_SEED = 8
ENTRY_MATERIALS = frozenset(NATURAL | AIR | LIGHTS)
WILD_GRASS = frozenset('minecraft:'+name for name in ('short_grass','tall_grass','fern','large_fern'))


def excluded(low, high, profile, selection):
    for pos in profile.get('depots', []) + [profile[k] for k in ('workbench','ender_chest') if k in profile]:
        if low[0]-48 <= pos[0] <= high[0]+48 and low[2]-48 <= pos[2] <= high[2]+48:
            return True
    boxes = list(profile.get('protected_regions', []))
    if selection.get('min') and selection.get('max'):
        boxes.append(selection)
    return any(not (high[0]+16 < box['min'][0] or low[0]-16 > box['max'][0]
                       or high[2]+16 < box['min'][2] or low[2]-16 > box['max'][2]) for box in boxes)


def tiles(origin, radius):
    x,z=math.floor(origin[0]/16)*16,math.floor(origin[2]/16)*16
    for r in range(3, min(24, max(0, radius//16))+1):
        ring=[(dx,-r) for dx in range(-r,r+1)]
        ring += [(r,dz) for dz in range(-r+1,r+1)]
        ring += [(dx,r) for dx in range(r-1,-r-1,-1)]
        ring += [(-r,dz) for dz in range(r-1,-r,-1)]
        for dx,dz in ring:
            yield x+dx*16,z+dz*16


def frontier(origin, radius, profile):
    """Prefer already authorized resource ground, without extending the original search radius."""
    original=list(tiles(origin,radius));allowed=set(original);seen=set();ordered=[]
    hints=sorted(enumerate(profile.get('resource_regions',[])),
                 key=lambda pair:(not str(pair[1].get('source','')).startswith('previous_authorized'),pair[0]))
    for _,region in hints:
        low,high=region.get('min'),region.get('max')
        if (not isinstance(low,list) or not isinstance(high,list) or len(low)!=3 or len(high)!=3
                or any(type(n) is not int for n in low+high) or any(a>b for a,b in zip(low,high))):continue
        # Iterate bounded frontier tiles, rather than trusting an arbitrarily large hint extent.
        for tile in original:
            if tile in seen or tile not in allowed:continue
            tx,tz=tile
            if tx<=high[0] and tx+15>=low[0] and tz<=high[2] and tz+15>=low[2]:
                ordered.append(tile);seen.add(tile)
    return ordered+[tile for tile in original if tile not in seen]


def representative_seeds(candidates,x,z,player):
    """Round-robin depth layers, with one representative per 4x4x16 spatial bucket."""
    buckets={}
    for row in candidates:
        sx,sy,sz=row['pos'];key=((sx-x)//4,sy//16,(sz-z)//4)
        centre=(x+key[0]*4+1.5,key[1]*16+7.5,z+key[2]*4+1.5)
        score=(sx-centre[0])**2+(sz-centre[2])**2+((sy-centre[1])/4)**2
        if key not in buckets or score<buckets[key][0]:buckets[key]=(score,row)
    layers=defaultdict(list)
    for key,(_,row) in buckets.items():layers[key[1]].append(row)
    for layer in layers.values():layer.sort(key=lambda row:math.hypot(row['pos'][0]-player[0],row['pos'][2]-player[2]))
    ordered=[]
    for index in range(max((len(layer) for layer in layers.values()),default=0)):
        for depth in sorted(layers,reverse=True):
            if index<len(layers[depth]):ordered.append(layers[depth][index])
            if len(ordered)>=MAX_SEEDS:return ordered,len(buckets)
    return ordered,len(buckets)


def _entry_reject(row, *, inside):
    name=block_id(row)
    if row.get('fluid') or name in ('minecraft:water','minecraft:lava'):return 'wet_entry'
    if row.get('block_entity'):return 'container_entry'
    if name in FALLING or name.endswith('_concrete_powder'):return 'falling_entry'
    if name in ('minecraft:fire','minecraft:soul_fire','minecraft:cobweb','minecraft:powder_snow','minecraft:pointed_dripstone'):
        return 'hazard_entry'
    if name.endswith(('_log','_wood','_leaves')):return 'tree_entry' if inside else None
    if name in ENTRY_MATERIALS:return None
    if inside:return 'non_natural_entry'
    return None


def _entrance(columns,cells,cx,cz,quarry_top,cache):
    key=(cx,cz,quarry_top)
    if key in cache:return cache[key]
    column=[row for x in (cx,cx+1) for z in (cz,cz+1) for row in columns.get((x,z),())
            if row['pos'][1]>quarry_top]
    surface=max([row['pos'][1] for row in column if block_id(row) in NATURAL]+[quarry_top])
    for row in column:
        # Native clear stops at the highest natural ground. Harmless grass
        # above that surface is outside the excavated volume, not a building.
        if row['pos'][1]>surface and block_id(row) in WILD_GRASS and row.get('passable') and not row.get('fluid') and not row.get('block_entity'):
            continue
        reason=_entry_reject(row,inside=True)
        if reason:cache[key]=(None,reason);return cache[key]
    if surface>=164:
        cache[key]=(None,'surface_above_scan');return cache[key]
    # The same dry buffer will be checked natively for each 18-block segment.
    for x in range(cx-3,cx+5):
        for z in range(cz-3,cz+5):
            for row in columns.get((x,z),()):
                if quarry_top-1<=row['pos'][1]<=surface+2:
                    reason=_entry_reject(row,inside=False)
                    if reason:cache[key]=(None,reason);return cache[key]
    # Avoid proposing a segmented shaft whose fixed slice would open a cave.
    top=surface;bottom=quarry_top+1
    while top>=bottom:
        segment_low=max(bottom,top-17)
        if segment_low==top and top==surface:segment_low-=1
        if any(not cells.get((x,segment_low-1,z),{}).get('solid') for x in (cx,cx+1) for z in (cz,cz+1)):
            cache[key]=(None,'unsupported_entry');return cache[key]
        top=segment_low-1
    result={'surface_y':surface}
    if surface>quarry_top:result['access_shaft']={'min':[cx,quarry_top+1,cz],'max':[cx+1,surface,cz+1]}
    cache[key]=(result,None);return cache[key]


def choose_region(rows, item, x, z, player, checkpoint=lambda:None, diagnostics=None):
    """Return natural material geometry only; all excavation is revalidated later."""
    diag=diagnostics if diagnostics is not None else {}
    rejected=Counter();diag.update(target_blocks=0,seed_buckets=0,seeds_tried=0,quarries_tried=0,entrances_tried=0)
    diag['reject_reasons']=rejected
    if item == 'minecraft:dirt':
        # Discovery proposes only an exposed dirt patch. The acquisition
        # adapter rechecks its site buffer and each block immediately before
        # native movement and mining; it never opens a shaft.
        found=dirt_candidates(rows,[x,58,z],[x+15,160,z+15],player)
        diag['target_blocks']=len(found)
        if not found:
            rejected['no_safe_surface_dirt']+=1
            return None
        y=found[0][1]
        return {'item':item,'min':[x,max(58,y-7),z],
                'max':[x+15,min(160,y+8),z+15],
                'source':'natural_survey','surface_y':y}
    if item=='minecraft:sand':
        diag['target_blocks']=sum(block_id(row)==item and x<=row['pos'][0]<=x+15 and z<=row['pos'][2]<=z+15 for row in rows)
        choice=choose_quarry(rows,[x,64,z],[x+15,120,z+15],player)
        if choice is None:rejected['no_dry_sand_box']+=1
        return dict(choice,item=item) if choice else None
    if item in LOGS:
        logs=[r for r in rows if block_id(r)==item and x<=r['pos'][0]<=x+15 and z<=r['pos'][2]<=z+15]
        diag['target_blocks']=len(logs)
        leaves=[r for r in rows if block_id(r).endswith('_leaves')]
        if len(logs)>=3 and len(leaves)>=4:
            return {'item':item,'min':[x,48,z],'max':[x+15,160,z+15]}
        rejected['no_natural_tree']+=1;return None
    wanted=ROCK_SOURCES.get(item)
    if not wanted:
        return None
    cells={tuple(r['pos']):r for r in rows}
    columns=defaultdict(list)
    for pos,row in cells.items():columns[(pos[0],pos[2])].append(row)
    candidates=[r for r in rows if block_id(r) in wanted and x<=r['pos'][0]<=x+15 and z<=r['pos'][2]<=z+15]
    diag['target_blocks']=len(candidates)
    seeds,bucket_count=representative_seeds(candidates,x,z,player);diag['seed_buckets']=bucket_count
    if not seeds:rejected['no_target_blocks']+=1
    seen=set();entry_cache={}
    for seed in seeds:
        checkpoint()
        diag['seeds_tried']+=1
        sx,sy,sz=seed['pos']
        low=[max(x,sx-2),max(-58,sy-10),max(z,sz-2)]
        high=[min(x+15,low[0]+5),min(120,low[1]+17),min(z+15,low[2]+5)]
        key=tuple(low+high)
        if key in seen:
            continue
        seen.add(key)
        plans=[]
        for cx in range(low[0],high[0]):
            for cz in range(low[2],high[2]):
                diag['entrances_tried']+=1
                plan,reason=_entrance(columns,cells,cx,cz,high[1],entry_cache)
                if plan is None:rejected[reason]+=1
                else:plans.append((cx,cz,plan))
        plans.sort(key=lambda entry:(entry[2]['surface_y']-high[1],
                                    math.hypot(entry[0]+1-player[0],entry[1]+1-player[2])))
        if not plans:continue
        nearby=[cells[p] for xx in range(low[0]-3,high[0]+4)
                for yy in range(low[1]-2,high[1]+3) for zz in range(low[2]-3,high[2]+4)
                if (p:=(xx,yy,zz)) in cells]
        for cx,cz,entry in plans[:MAX_ENTRIES_PER_SEED]:
            checkpoint();diag['quarries_tried']+=1
            required={'min':[cx,high[1]+1,cz],'max':[cx+1,entry['surface_y'],cz+1]}
            choice=rock_choice(nearby,low,high,item,player,required_entry=required)
            if choice is None:rejected['no_supported_rock_box']+=1;continue
            choice.update(item=item,source='natural_survey',**entry)
            diag['candidate_target_blocks']=choice['available']
            return choice
    return None


def _region_bounds(region):
    if not isinstance(region,dict):return None
    low,high=region.get('min'),region.get('max')
    if (not isinstance(low,list) or not isinstance(high,list) or len(low)!=3 or len(high)!=3
            or any(type(n) is not int for n in low+high) or any(a>b for a,b in zip(low,high))):return None
    return low,high


def _extend_known_shaft(c,item,profile,ledger,path,checkpoint,origin,selection,max_probes):
    """Reuse only the caller's already-attempted 2x2 natural regions.

    Backend tries its profile regions before calling discovery. Historical tile
    candidates alone therefore cannot authorize an extension; the parent must
    also be in this job's known-region list. A record is a location hint, never
    stock or permission to skip a fresh scan/native excavation validation.
    """
    if item not in ROCK_SOURCES or profile.get('dimension')!='minecraft:overworld':return None
    known=[r for r in profile.get('resource_regions',[]) if r.get('item')==item and _region_bounds(r)]
    registered={tuple(r['min']+r['max']) for r in known}
    extensions=ledger.get('extensions',{})
    if not isinstance(extensions,dict):raise RuntimeError('矿井延伸记录格式无效，保留旧记录')
    radius=min(384,profile.get('search_radius',256));probes=0;considered=set()
    for parent in sorted(known,key=lambda r:r['min'][1]):
        bounds=_region_bounds(parent);shaft=_region_bounds(parent.get('access_shaft'))
        if parent.get('source')!='natural_survey' or shaft is None:continue
        old_low,old_high=bounds;shaft_low,shaft_high=shaft;surface=parent.get('surface_y')
        if (old_high[0]-old_low[0]!=1 or old_high[2]-old_low[2]!=1
                or type(surface) is not int or not old_high[1]<surface<320
                or shaft_low[1]!=old_high[1]+1 or shaft_high[1]!=surface
                or any(shaft_low[i]!=old_low[i] or shaft_high[i]!=old_high[i] for i in (0,2))):continue
        top=old_low[1]-1;bottom=max(-58,top-17)
        if top-bottom+1<2 or not -58<=bottom<=top<=319:continue
        low=[old_low[0],bottom,old_low[2]];high=[old_high[0],top,old_high[2]]
        signature=tuple(low+high)
        if signature in registered or signature in considered:continue
        considered.add(signature)
        current=c.status()
        corners=[(x,z) for x in (low[0],high[0]) for z in (low[2],high[2])]
        column_high=[high[0],surface,high[2]]
        if (any(abs(x-origin[0])>radius or abs(z-origin[2])>radius
                or math.hypot(x-c.anchor[0],z-c.anchor[2])>440
                or math.hypot(x-current['pos'][0],z-current['pos'][2])>384 for x,z in corners)
                or excluded(low,column_high,profile,selection)):continue
        if (current.get('world_session')!=c.world or current.get('dimension')!=profile['dimension']
                or server_key(current.get('server'))!=server_key(profile['server'])):
            raise RuntimeError('矿井延伸的当前服务器、维度或世界会话不匹配')
        key=hashlib.sha256(json.dumps([item,low,high,surface],separators=(',',':')).encode()).hexdigest()[:24]
        prior=extensions.get(key)
        if (isinstance(prior,dict) and prior.get('state')=='empty_or_unsafe'
                and prior.get('world_session')==c.world and prior.get('algorithm_version')==ALGORITHM_VERSION
                and prior.get('dimension')==profile['dimension']
                and server_key(prior.get('server'))==server_key(profile['server'])
                and prior.get('min')==low and prior.get('max')==high):continue
        if probes>=max_probes:break
        checkpoint();probes+=1
        scan_low=[low[0]-3,low[1]-2,low[2]-3];scan_high=[high[0]+3,high[1]+2,high[2]+3]
        reply=c.request('scan',min=scan_low,max=scan_high,details=True)
        # Native read-only scan replies carry snapshot + id + blocks, and do
        # not necessarily have a phase. Match the exact just-issued request;
        # accepting a missing phase must not accept stale/foreign observations.
        if (not isinstance(reply,dict) or reply.get('phase') not in (None,'done')
                or not isinstance(getattr(c,'last',None),str) or not c.last or reply.get('id')!=c.last
                or reply.get('world_session')!=c.world or not isinstance(reply.get('blocks'),list)):
            raise RuntimeError('矿井延伸扫描未完整确认，不把未知区域记录为空')
        rows=reply['blocks'];positions=[]
        for row in rows:
            pos=row.get('pos') if isinstance(row,dict) else None
            if (not isinstance(pos,list) or len(pos)!=3 or any(type(n) is not int for n in pos)
                    or any(not scan_low[i]<=pos[i]<=scan_high[i] for i in range(3))
                    or not isinstance(row.get('state'),str)
                    or any(type(row.get(flag)) is not bool for flag in ('solid','passable','fluid','block_entity'))):
                raise RuntimeError('矿井延伸扫描缺少完整方块属性，保留未知状态')
            positions.append(tuple(pos))
        if len(positions)!=len(set(positions)):
            raise RuntimeError('矿井延伸扫描坐标重复，保留未知状态')
        fresh=c.status()
        if (fresh.get('world_session')!=c.world or fresh.get('dimension')!=profile['dimension']
                or server_key(fresh.get('server'))!=server_key(profile['server'])):
            raise RuntimeError('矿井延伸扫描期间世界已改变')
        observed=_rock_observation(rows,low,high,item)
        candidate=None
        if observed is not None and observed['available']>0:
            candidate={**observed,'item':item,'min':low,'max':high,'source':'natural_survey','surface_y':surface,
                       'access_shaft':{'min':[low[0],top+1,low[2]],'max':[high[0],surface,high[2]]},
                       'extended_from':{'min':list(old_low),'max':list(old_high)}}
        entry={'state':'candidate' if candidate else 'empty_or_unsafe','min':low,'max':high,
               'parent':{'min':list(old_low),'max':list(old_high)},'world_session':c.world,
               'server':profile['server'],'dimension':profile['dimension'],'algorithm_version':ALGORITHM_VERSION,
               'observed_at':fresh['time'],'region':candidate,
               'reason':'target_observed' if candidate else 'unsafe_or_unsupported' if observed is None else 'no_target_blocks',
               'available':0 if observed is None else observed['available']}
        if prior is not None:ledger.setdefault('extension_history',{}).setdefault(key,[]).append(prior)
        ledger.setdefault('extensions',{})[key]=entry;extensions=ledger['extensions'];write_json(path,ledger)
        c.material_search_progress.update(extension_probes=probes,extension_candidates=1 if candidate else 0)
        if candidate:return candidate
    return None


def discover(c,item,profile,directory,checkpoint,max_tiles=8):
    c.material_search_progress={'new_tiles':0,'scanned_total':0,'has_more':False,'ledger':None}
    if item not in ROCK_SOURCES and item not in LOGS and item not in ('minecraft:sand','minecraft:dirt'):
        return None
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    scope=hashlib.sha256((profile['server']+'|'+profile['dimension']+'|'+item).encode()).hexdigest()[:20]
    path=directory/(scope+'.json')
    ledger=json.loads(path.read_text()) if path.exists() else {'schema':1,'item':item,'tiles':{}}
    ledger['algorithm_version']=ALGORITHM_VERSION
    state=c.status(); origin=profile.get('search_origin',c.anchor)
    selection=state.get('projection_selection',{})
    if type(max_tiles) is not int or not 1<=max_tiles<=32:raise ValueError('Discovery budget must be 1..32 tiles')
    extension=_extend_known_shaft(c,item,profile,ledger,path,checkpoint,origin,selection,max_tiles)
    if extension is not None:
        c.material_search_progress.update(ledger=str(path),has_more=True,algorithm_version=ALGORITHM_VERSION)
        return extension
    pending=[]; remembered=[]
    known_regions=[r for r in profile.get('resource_regions',[]) if r.get('item')==item]
    for x,z in frontier(origin,min(384,profile.get('search_radius',256)),profile):
        key=f'{x}:{z}'
        prior=ledger['tiles'].get(key)
        if excluded([x,-64,z],[x+15,319,z+15],profile,selection):
            continue
        if math.hypot(x+8-c.anchor[0],z+8-c.anchor[2])>440:
            continue
        region=prior.get('region') if prior else None
        if (prior and prior.get('state')=='candidate' and isinstance(region,dict)
                and region.get('item')==item and not any(
                    r.get('min')==region.get('min') and r.get('max')==region.get('max') for r in known_regions)):
            # A prior job finding a deposit does not mean it exhausted it.
            # Re-scan the tile before using it; never treat cached ore as stock.
            remembered.append((x,z));continue
        already_seen=prior and (prior.get('state')=='candidate' or prior.get('algorithm_version',1)>=ALGORITHM_VERSION)
        if already_seen:continue
        pending.append((x,z))
    pending=remembered+pending
    count=0
    def progress():
        value={'new_tiles':count,'scanned_total':sum(row.get('algorithm_version',1)>=ALGORITHM_VERSION for row in ledger['tiles'].values()),
               'has_more':len(pending)>count,'ledger':str(path),'algorithm_version':ALGORITHM_VERSION}
        c.material_search_progress=value;ledger['search_progress']=value;write_json(path,ledger)
    progress()
    for x,z in pending[:max_tiles]:
        key=f'{x}:{z}';checkpoint()
        # Native cruise still performs collision/guard checks; never disable
        # flight or claim to traverse unknown terrain in a synthetic snapshot.
        cruise=max(145,min(250,c.status()['pos'][1]))
        _travel(c,[x+8.5,cruise,z+8.5],checkpoint,[])
        rows=[]
        for bottom,top in ((-60,-1),(0,59),(60,120),(121,164)):
            checkpoint()
            reply=c.request('scan',min=[x-3,bottom,z-3],max=[x+18,top,z+18],details=True)
            if not isinstance(reply.get('blocks'),list):
                raise RuntimeError('资源扫描未完整加载，不能记录为空区域')
            rows.extend(reply['blocks'])
        diagnostics={}
        candidate=choose_region(rows,item,x,z,c.status()['pos'],checkpoint,diagnostics)
        prior=ledger['tiles'].get(key)
        if prior:ledger.setdefault('history',{}).setdefault(key,[]).append(prior)
        ledger['tiles'][key]={'observed_at':c.status()['time'],'world_session':c.world,
                              'algorithm_version':ALGORITHM_VERSION,
                              'state':'candidate' if candidate else 'empty_or_unsafe','region':candidate,
                              'diagnostics':diagnostics}
        count+=1;progress()
        if candidate:
            return candidate
    return None
