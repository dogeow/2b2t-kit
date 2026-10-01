"""Bounded natural-resource discovery with a persistent visited-tile ledger."""
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from kit_runtime.journal import write_json
from .acquisition import ROCK_SOURCES, LOGS, NATURAL, AIR, LIGHTS, FALLING, Unavailable, block_id, rock_choice, _rock_observation, _travel, route_failure, _resource_ledger, _resource_ledger_scope_path
from .dirt_harvest import candidates as surface_soil_candidates
from .snow_harvest import (PRODUCTS as SNOW_PRODUCTS, candidates as surface_snow_candidates,
                           validate_region as validate_snow_region)
from .snow_biome_search import (MAX_ANCHORS_PER_CALL, SAMPLE_STRIDE, SURVEY_RADIUS,
                                anchors as snow_biome_anchors,
                                cold_tiles as snow_biome_cold_tiles,
                                ledger_state as snow_biome_ledger,
                                parse_reply as parse_snow_biome_reply)
from .seed_snow_search import (allowed_survey_tiles as seed_allowed_tiles,
                               ledger_state as seed_snow_ledger,
                               parse_reply as parse_seed_snow_reply,
                               public_candidate as public_seed_candidate,
                               record_server_mismatch,
                               refresh_hint_policy,
                               shared_hints_disabled)
from .bobby_snow_cache import (CacheUnavailable as BobbyCacheUnavailable,
                               candidates as bobby_snow_candidates,
                               validate_candidate as validate_bobby_candidate,
                               validate_current_world as validate_bobby_world)
from .bobby_snow_route import (ledger_state as bobby_snow_ledger,
                               MAX_VISITS as BOBBY_MAX_VISITS,
                               mark_candidate as mark_bobby_candidate,
                               outbound as bobby_outbound,
                               return_home as return_bobby_home)
from native_sand_quarry import choose_quarry
from .protocol import JobPaused, server_key

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


def choose_region(rows, item, x, z, player, checkpoint=lambda:None, diagnostics=None,
                  *, allow_natural_snowpack=False):
    """Return natural material geometry only; all excavation is revalidated later."""
    diag=diagnostics if diagnostics is not None else {}
    rejected=Counter();diag.update(target_blocks=0,seed_buckets=0,seeds_tried=0,quarries_tried=0,entrances_tried=0)
    diag['reject_reasons']=rejected
    if item in ('minecraft:dirt', 'minecraft:grass_block'):
        # Discovery proposes only an exposed surface patch. The acquisition
        # adapter rechecks its site buffer and each block immediately before
        # native movement and mining; it never opens a shaft.
        found=surface_soil_candidates(rows,[x,58,z],[x+15,160,z+15],player,item=item)
        diag['target_blocks']=len(found)
        if not found:
            rejected['no_safe_surface_'+item.split(':')[1]]+=1
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
    if item in SNOW_PRODUCTS:
        found=surface_snow_candidates(
            rows,[x,58,z],[x+15,315,z+15],player,item,
            allow_natural_snowpack=allow_natural_snowpack)
        diag['target_blocks']=len(found)
        if not found:
            rejected['no_safe_surface_'+item.split(':')[1]]+=1
            return None
        y=found[0][0][1]
        return {'item':item,'min':[x,max(58,y-7),z],
                'max':[x+15,min(315,y+8),z+15],
                'source':'natural_survey','surface_y':y}
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


def _search_travel(c,target,checkpoint,ledger,path,tile):
    """Travel once while preserving the existing same-frontier combat hold."""
    trace=[]
    try:
        _travel(c,target,checkpoint,trace)
        return True
    except JobPaused as error:
        guard=next((row for row in reversed(trace)
                    if row.get('route_code')=='guard_displaced'),None)
        if guard is not None:
            hold={'world_session':c.world,'tile':list(tile),
                  'target':list(target),'code':'guard_displaced','reason':str(error),
                  'route_evidence':{'request_id':guard.get('request_id'),
                      'terminal_verified':guard.get('terminal_verified') is True,
                      'combat_confirmed':guard.get('combat_confirmed') is True,
                      'checkpoint_paused':True},
                  'observed_at':guard.get('observed_at')}
            ledger['guard_hold']=hold;write_json(path,ledger)
            c.material_search_progress.update(ledger=str(path),guard_hold=hold)
        raise
    except Unavailable as error:
        if error.code in ('guard_displaced','route_uncertain'):
            hold={'world_session':c.world,'tile':list(tile),
                  'target':list(target),'code':error.code,'reason':error.detail,
                  'route_evidence':error.evidence,
                  'observed_at':c.status().get('time')}
            ledger['guard_hold']=hold;write_json(path,ledger)
            c.material_search_progress.update(ledger=str(path),guard_hold=hold)
            return False
        raise


def _protected_snow_biome_candidates(candidates,profile,selection):
    """Apply the complete snow worksite/station buffer before persistence."""
    protected={}
    for key,entry in candidates.items():
        x,z=entry['tile'];sample_y=entry['sample'][1]
        region={'min':[x,max(58,sample_y-7),z],
                'max':[x+15,min(315,sample_y+8),z+15]}
        try:validate_snow_region(region,profile,selection)
        except ValueError:continue
        protected[key]=entry
    return protected


def _stored_snow_biome_tiles(coarse,ledger,profile,selection,allowed):
    found=[]
    allowed=set(allowed)
    candidates=_protected_snow_biome_candidates(coarse['candidates'],profile,selection)
    for entry in candidates.values():
        x,z=entry['tile'];prior=ledger['tiles'].get(f'{x}:{z}')
        if (x,z) not in allowed:
            continue
        if (prior and (prior.get('state')=='candidate'
                       or prior.get('algorithm_version',1)>=ALGORITHM_VERSION)):
            continue
        if excluded([x,-64,z],[x+15,319,z+15],profile,selection):
            continue
        found.append((x,z))
    return found


def _coarse_snow_frontier(c,profile,ledger,path,checkpoint,origin,selection,allowed):
    """Observe a few loaded biome grids and return only positively cold tiles."""
    coarse=snow_biome_ledger(ledger)
    stored=_stored_snow_biome_tiles(coarse,ledger,profile,selection,allowed)
    all_anchors=snow_biome_anchors(origin,min(384,profile.get('search_radius',256)))
    pending=[point for point in all_anchors if f'{point[0]}:{point[1]}' not in coarse['visited']]
    if stored:
        return {'available':True,'tiles':stored,'new_cells':0,
                'visited':len(coarse['visited']),'has_more':bool(pending),'held':False}
    initial=c.status()
    if initial.get('snow_biome_survey_protocol',0)<1:
        return {'available':False,'tiles':[],'new_cells':0,
                'visited':len(coarse['visited']),'has_more':False,'held':False,
                'reason':'host_protocol_unavailable'}
    new_cells=0
    for x,z in pending[:MAX_ANCHORS_PER_CALL]:
        checkpoint()
        cruise=max(145,min(250,c.status()['pos'][1]))
        target=[x+.5,cruise,z+.5]
        if not _search_travel(c,target,checkpoint,ledger,path,(x,z)):
            return {'available':True,'tiles':[],'new_cells':new_cells,
                    'visited':len(coarse['visited']),'has_more':True,'held':True}
        try:
            reply=c.request('scan_snow_biomes',center=[x,z],radius=SURVEY_RADIUS,
                            stride=SAMPLE_STRIDE)
            survey=parse_snow_biome_reply(reply,getattr(c,'last',None),c.world,(x,z))
        except (RuntimeError,ValueError,KeyError,TypeError) as error:
            coarse['last_unavailable']={'anchor':[x,z],'world_session':c.world,
                                        'reason':str(error)}
            write_json(path,ledger)
            return {'available':False,'tiles':[],'new_cells':new_cells,
                    'visited':len(coarse['visited']),'has_more':False,'held':False,
                    'reason':'invalid_or_unavailable_reply'}
        if survey['loaded_samples']==0:
            coarse['visited'][f'{x}:{z}']={
                'state':'no_loaded_samples','anchor':[x,z],
                'world_session':c.world,'observed_at':c.status()['time'],
                'loaded_samples':0,'unloaded_samples':survey['unloaded_samples']}
            new_cells+=1;write_json(path,ledger)
            return {'available':False,'tiles':[],'new_cells':new_cells,
                    'visited':len(coarse['visited']),'has_more':False,'held':False,
                    'reason':'no_loaded_samples'}
        observed_candidates=snow_biome_cold_tiles(survey['samples'],allowed)
        candidates=_protected_snow_biome_candidates(observed_candidates,profile,selection)
        coarse['visited'][f'{x}:{z}']={
            'state':('cold_candidates' if candidates else 'loaded_cold_protected'
                     if observed_candidates else 'loaded_no_cold_sample'),
            'anchor':[x,z],'world_session':c.world,'observed_at':c.status()['time'],
            'loaded_samples':survey['loaded_samples'],
            'unloaded_samples':survey['unloaded_samples'],
            'candidate_tiles':sorted(candidates)}
        coarse['candidates'].update(candidates);new_cells+=1;write_json(path,ledger)
        if candidates:break
    stored=_stored_snow_biome_tiles(coarse,ledger,profile,selection,allowed)
    remaining=any(f'{x}:{z}' not in coarse['visited'] for x,z in all_anchors)
    return {'available':True,'tiles':stored,'new_cells':new_cells,
            'visited':len(coarse['visited']),'has_more':remaining,'held':False}


def _seed_return_home(c, token, route, seed_state, path, ledger, checkpoint):
    """Return through the host-bound unique home/search origin; Python sends no coordinates."""
    route.update(state='return_inflight',return_started_at=c.status().get('time'))
    seed_state['active_route']=route;write_json(path,ledger)
    checkpoint()
    try:
        reply=c.request('navigate',snow_expedition_token=token,
                        snow_expedition_return=True,arrival=8,seconds=5340)
        current=c.status()
    except Exception as error:
        route.update(state='return_uncertain',detail=str(error))
        write_json(path,ledger)
        for name in ('snow_expedition_token','snow_expedition_route_id'):
            if hasattr(c,name):delattr(c,name)
        raise Unavailable('种子雪地返航结果未知；令牌已消费且不会重放',
                          'waiting',code='route_uncertain') from error
    if (reply.get('phase')!='done' or reply.get('id')!=getattr(c,'last',None)
            or reply.get('world_session')!=c.world
            or current.get('world_session')!=c.world
            or current.get('navigating') or current.get('native_material_busy')):
        route.update(state='return_uncertain',returned_at=current.get('time'),
                     detail=reply.get('detail'))
        write_json(path,ledger)
        for name in ('snow_expedition_token','snow_expedition_route_id'):
            if hasattr(c,name):delattr(c,name)
        raise Unavailable('种子雪地返航没有完整确认；短期令牌已消费，不自动重放',
                          'waiting',code='route_uncertain')
    route.update(state='home_arrived',returned_at=current.get('time'))
    c.anchor=list(current['pos'])
    seed_state['routes'].append(route);seed_state['active_route']=None
    write_json(path,ledger)
    for name in ('snow_expedition_token','snow_expedition_route_id'):
        if hasattr(c,name):delattr(c,name)


def _seed_snow_expedition(c,item,profile,ledger,path,checkpoint,selection,max_tiles):
    """Use seed hints for travel, then trust only loaded server biome/blocks."""
    state=c.status()
    if state.get('snow_seed_locator_protocol',0)<1:
        return {'available':False,'region':None}
    seed_state=seed_snow_ledger(ledger)
    active_route=seed_state.get('active_route')
    if isinstance(active_route,dict):
        raise Unavailable('上一条种子雪地长途路线尚未闭环；不推进游标、不签发新候选',
                          'waiting',code='route_uncertain',
                          evidence={'route_id':active_route.get('route_id'),
                                    'route_state':active_route.get('state')})
    cursor=seed_state['next_cursor']
    reply=c.request('snow_seed_candidates',cursor=cursor,budget=128)
    batch=parse_seed_snow_reply(reply,getattr(c,'last',None),c.world,cursor)
    if batch['available'] is False:
        return {'available':False,'region':None,
                'reason':batch.get('reason','sampler_unavailable')}
    seed_state['radius']=batch['radius'];seed_state['total']=batch['total']
    live=sorted(batch['candidates'],key=lambda row:(row['sample_cursor'],row['distance']))
    for row in live:
        saved=public_seed_candidate(row)
        seed_state['candidates'][f"{row['x']}:{row['z']}"]=saved
    if not live:
        seed_state['next_cursor']=batch['next_cursor'];write_json(path,ledger)
        return {'available':True,'region':None,'processed':batch['processed'],
                'cursor':batch['next_cursor'],'total':batch['total'],
                'has_more':not batch['done']}

    chosen=live[0]
    seed_state['next_cursor']=chosen['sample_cursor']+1
    key=f"{chosen['x']}:{chosen['z']}";saved=seed_state['candidates'][key]
    route={'route_id':chosen['route_id'],'candidate':[chosen['x'],chosen['z']],
           'state':'route_inflight','world_session':c.world,
           'started_at':state.get('time'),
           'scenery_boundary':'single_cruise_passive_chunk_cache'}
    saved['state']='route_inflight';seed_state['active_route']=route
    write_json(path,ledger)
    checkpoint()
    travel=c.request('navigate',target=chosen['target'],arrival=8,
                     snow_expedition_token=chosen['token'],seconds=5340)
    arrived=c.status()
    owned_terminal=(travel.get('phase') in ('waiting','stopped')
        and travel.get('id')==getattr(c,'last',None)
        and travel.get('world_session')==c.world
        and arrived.get('world_session')==c.world
        and not arrived.get('navigating') and not arrived.get('native_material_busy'))
    safe_return=(owned_terminal and arrived.get('health',0)>=18
        and arrived.get('food',0)>=8 and arrived.get('guard_armed')
        and arrived.get('guard_pve_only') and not arrived.get('under_water')
        and not arrived.get('manual_movement')
        and not (arrived.get('safety_hold') or {}).get('active'))
    if safe_return:
        saved['state']='returned_before_arrival';route.update(state='outbound_stopped',
            stopped_at=arrived.get('time'),detail=travel.get('detail'))
        write_json(path,ledger)
        _seed_return_home(c,chosen['token'],route,seed_state,path,ledger,checkpoint)
        return {'available':True,'region':None,'processed':batch['processed'],
                'cursor':seed_state['next_cursor'],'total':batch['total'],'has_more':True}
    if (travel.get('phase')!='done' or travel.get('id')!=getattr(c,'last',None)
            or travel.get('world_session')!=c.world or arrived.get('world_session')!=c.world
            or math.hypot(arrived['pos'][0]-chosen['target'][0],
                          arrived['pos'][2]-chosen['target'][2])>10
            or arrived.get('navigating') or arrived.get('native_material_busy')):
        saved['state']='route_inflight';route.update(state='outbound_uncertain',
            stopped_at=arrived.get('time'),detail=travel.get('detail'))
        seed_state['routes'].append(route);write_json(path,ledger)
        raise Unavailable('种子雪地长途巡航回执不确定；保留同一候选且不重放',
                          'waiting',code='route_uncertain')
    saved['state']='arrived';route.update(state='candidate_arrived',arrived_at=arrived.get('time'))
    c.anchor=list(arrived['pos'])
    write_json(path,ledger)

    survey_reply=c.request('scan_snow_biomes',center=[chosen['x'],chosen['z']],
                           radius=SURVEY_RADIUS,stride=SAMPLE_STRIDE)
    survey=parse_snow_biome_reply(survey_reply,getattr(c,'last',None),c.world,
                                 (chosen['x'],chosen['z']))
    observed=snow_biome_cold_tiles(
        survey['samples'],seed_allowed_tiles((chosen['x'],chosen['z'])))
    protected=_protected_snow_biome_candidates(observed,profile,selection)
    if not protected:
        if not observed:
            saved['state']='server_mismatch'
            route['verification']='no_loaded_server_snow_biome'
            record_server_mismatch(
                path.parent,profile['server'],profile['dimension'],
                chosen['x'],chosen['z'],world_session=c.world,
                observed_at=c.status()['time'],loaded_samples=survey['loaded_samples'])
            refresh_hint_policy(seed_state)
        else:
            saved['state']='detailed_empty'
            route['verification']='loaded_snow_biome_inside_protected_buffer'
        _seed_return_home(c,chosen['token'],route,seed_state,path,ledger,checkpoint)
        return {'available':True,'region':None,'processed':batch['processed'],
                'cursor':seed_state['next_cursor'],'total':batch['total'],'has_more':True}

    pending=sorted((tuple(entry['tile']) for entry in protected.values()),
                   key=lambda tile:math.hypot(tile[0]+8-arrived['pos'][0],
                                              tile[1]+8-arrived['pos'][2]))
    for x,z in pending[:max_tiles]:
        rows=[]
        for bottom,top in ((58,110),(111,164),(165,220),(221,280),(281,319)):
            checkpoint()
            scan=c.request('scan',min=[x-3,bottom,z-3],max=[x+18,top,z+18],details=True)
            if not isinstance(scan.get('blocks'),list):
                raise RuntimeError('种子雪地详细扫描未完整加载，不能记录为空')
            rows.extend(scan['blocks'])
        diagnostics={}
        region=choose_region(rows,item,x,z,c.status()['pos'],checkpoint,diagnostics)
        if region:
            try:validate_snow_region(region,profile,selection)
            except ValueError as error:
                diagnostics['region_validation']=str(error);region=None
        tile_key=f'{x}:{z}';prior=ledger['tiles'].get(tile_key)
        if prior:ledger.setdefault('history',{}).setdefault(tile_key,[]).append(prior)
        ledger['tiles'][tile_key]={'observed_at':c.status()['time'],
            'world_session':c.world,'algorithm_version':ALGORITHM_VERSION,
            'state':'candidate' if region else 'empty_or_unsafe','region':region,
            'diagnostics':diagnostics,'seed_route_id':chosen['route_id']}
        write_json(path,ledger)
        if region:
            region['seed_snow_route']={'route_id':chosen['route_id'],
                'candidate':[chosen['x'],chosen['z']],'radius':batch['radius']}
            c.snow_expedition_token=chosen['token']
            c.snow_expedition_route_id=chosen['route_id']
            c.snow_expedition_route=route
            c.snow_expedition_resource_path=str(path)
            return {'available':True,'region':region,'processed':batch['processed'],
                    'cursor':seed_state['next_cursor'],'total':batch['total'],'has_more':True}
    saved['state']='detailed_empty';route['verification']='no_safe_natural_snow_blocks'
    _seed_return_home(c,chosen['token'],route,seed_state,path,ledger,checkpoint)
    return {'available':True,'region':None,'processed':batch['processed'],
            'cursor':seed_state['next_cursor'],'total':batch['total'],'has_more':True}


def _minecraft_root(c):
    root=Path(getattr(c,'root',''))
    for candidate in (root,*root.parents):
        if (candidate/'.bobby').is_dir() and (candidate/'config').is_dir():
            return candidate
    return None


def _bobby_snow_expedition(c,item,profile,ledger,path,checkpoint,selection,max_tiles):
    """Use current Bobby chunks only as hints; live server evidence authorizes work."""
    route_state=bobby_snow_ledger(ledger,profile['server'],profile['dimension'])
    def return_and_refresh(reason):
        result=return_bobby_home(c,checkpoint,reason=reason)
        fresh=json.loads(path.read_text())
        ledger.clear();ledger.update(fresh)
        return result
    if isinstance(route_state.get('active_route'),dict):
        active=route_state['active_route']
        raise Unavailable('上一条 Bobby 雪地路线尚未闭环；不换候选或重放分段',
                          'waiting',code='route_uncertain',
                          evidence={'route_id':active.get('route_id'),
                                    'route_state':active.get('state')})
    if len(route_state['visited'])>=BOBBY_MAX_VISITS:
        return {'available':False,'region':None,'reason':'visited_ledger_full'}
    root=_minecraft_root(c)
    if root is None:return {'available':False,'region':None,'reason':'cache_unavailable'}
    visited=[row.get('candidate',{}).get('chunk')
             for row in route_state['visited'].values()
             if isinstance(row,dict)]
    visited_chunks={tuple(chunk) for chunk in visited
                    if isinstance(chunk,list) and len(chunk)==2
                    and all(type(value) is int for value in chunk)}
    try:
        hints=bobby_snow_candidates(root,profile['server'],profile['dimension'],
                                    profile.get('search_origin',c.anchor),visited,
                                    max_candidates=64)
    except BobbyCacheUnavailable:
        return {'available':False,'region':None,'reason':'cache_unavailable'}
    chosen=None
    for hint in hints:
        if tuple(hint['chunk']) in visited_chunks:continue
        x,z=hint['tile']
        if (not excluded([x,-64,z],[x+15,319,z+15],profile,selection)):
            chosen=hint;break
    if chosen is None:
        return {'available':bool(hints),'region':None,'has_more':False,
                'reason':'cache_exhausted_or_protected','cached_candidates':len(hints)}
    validate=lambda candidate:validate_bobby_candidate(
        root,profile['server'],profile['dimension'],candidate)
    quick=lambda candidate:validate_bobby_world(
        root,profile['server'],profile['dimension'],candidate)
    route=bobby_outbound(c,chosen,profile['server'],profile['dimension'],path,
                         ledger,checkpoint,validate,quick)
    x,z=chosen['tile'];center=(x+8,z+8)
    if not quick(route['candidate']):
        mark_bobby_candidate(c,path,ledger,'cache_changed')
        return_and_refresh('cache_changed')
        return {'available':True,'region':None,'has_more':True,
                'cached_candidates':len(hints)}
    try:
        survey_reply=c.request('scan_snow_biomes',center=list(center),
                               radius=SURVEY_RADIUS,stride=SAMPLE_STRIDE)
        survey=parse_snow_biome_reply(
            survey_reply,getattr(c,'last',None),c.world,center)
    except (RuntimeError,ValueError,KeyError,TypeError) as error:
        mark_bobby_candidate(c,path,ledger,'survey_unavailable',detail=str(error))
        return_and_refresh('survey_unavailable')
        return {'available':True,'region':None,'has_more':True,
                'cached_candidates':len(hints)}
    observed=snow_biome_cold_tiles(survey['samples'],{(x,z)})
    protected=_protected_snow_biome_candidates(observed,profile,selection)
    if not observed:
        mark_bobby_candidate(c,path,ledger,'server_mismatch')
        return_and_refresh('server_mismatch')
        return {'available':True,'region':None,'has_more':True,
                'cached_candidates':len(hints)}
    if not protected:
        mark_bobby_candidate(c,path,ledger,'protected')
        return_and_refresh('protected')
        return {'available':True,'region':None,'has_more':True,
                'cached_candidates':len(hints)}
    rows=[]
    for bottom,top in ((58,110),(111,164),(165,220),(221,280),(281,319)):
        checkpoint()
        try:
            scan=c.request('scan',min=[x-3,bottom,z-3],
                           max=[x+18,top,z+18],details=True)
        except (RuntimeError,ValueError,KeyError,TypeError) as error:
            mark_bobby_candidate(c,path,ledger,'detailed_unavailable',detail=str(error))
            return_and_refresh('detailed_unavailable')
            return {'available':True,'region':None,'has_more':True,
                    'cached_candidates':len(hints)}
        if not isinstance(scan.get('blocks'),list):
            mark_bobby_candidate(c,path,ledger,'detailed_unavailable',
                                 detail='loaded server chunks incomplete')
            return_and_refresh('detailed_unavailable')
            return {'available':True,'region':None,'has_more':True,
                    'cached_candidates':len(hints)}
        rows.extend(scan['blocks'])
    diagnostics={}
    region=choose_region(rows,item,x,z,c.status()['pos'],checkpoint,diagnostics,
                         allow_natural_snowpack=True)
    if region:
        try:validate_snow_region(region,profile,selection)
        except ValueError as error:
            diagnostics['region_validation']=str(error);region=None
    live=next(iter(protected.values()))
    if region is None:
        mark_bobby_candidate(c,path,ledger,'detailed_empty',detail=diagnostics)
        return_and_refresh('detailed_empty')
        return {'available':True,'region':None,'has_more':True,
                'cached_candidates':len(hints)}
    evidence={'route_id':route['route_id'],'chunk':list(chosen['chunk']),
              'region_file':chosen['region_file'],'fingerprint':chosen['fingerprint'],
              'cache_server':chosen['cache_server'],'dimension':chosen['dimension'],
              'world_session':c.world,'live_biome_verified':True,
              'live_biome':live['biome']}
    region.update(source='natural_survey',allow_natural_snowpack=True,
                  bobby_snow_route=evidence)
    mark_bobby_candidate(c,path,ledger,'live_verified')
    return {'available':True,'region':region,'has_more':True,
            'cached_candidates':len(hints)}


def discover(c,item,profile,directory,checkpoint,max_tiles=8):
    c.material_search_progress={'new_tiles':0,'scanned_total':0,'has_more':False,'ledger':None}
    if (item not in ROCK_SOURCES and item not in LOGS
            and item not in ('minecraft:sand','minecraft:dirt','minecraft:grass_block')
            and item not in SNOW_PRODUCTS):
        return None
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    path=_resource_ledger_scope_path(directory,profile['server'],profile['dimension'],item)
    ledger=_resource_ledger(path,item,create=True)
    ledger['algorithm_version']=ALGORITHM_VERSION
    seed_state=seed_snow_ledger(ledger) if item in SNOW_PRODUCTS else None
    bobby_state=(bobby_snow_ledger(ledger,profile['server'],profile['dimension'])
                 if item in SNOW_PRODUCTS else None)
    for provider,provider_state in (('seed',seed_state),('bobby',bobby_state)):
        active=provider_state.get('active_route') if isinstance(provider_state,dict) else None
        if isinstance(active,dict):
            raise Unavailable(f'上一条{provider}雪地路线尚未闭环；不开始其他候选',
                              'waiting',code='route_uncertain',
                              evidence={'route_id':active.get('route_id'),
                                        'route_state':active.get('state')})
    state=c.status(); origin=profile.get('search_origin',c.anchor)
    selection=state.get('projection_selection',{})
    if type(max_tiles) is not int or not 1<=max_tiles<=32:raise ValueError('Discovery budget must be 1..32 tiles')
    if item in SNOW_PRODUCTS and state.get('snow_biome_survey_protocol',0)<1:
        # Do not launch the old tile-by-tile flight on an old host.  The host
        # capability is checked before equipment discovery can move the actor.
        value={'new_tiles':0,'scanned_total':sum(
                   row.get('algorithm_version',1)>=ALGORITHM_VERSION
                   for row in ledger['tiles'].values()),
               'has_more':False,'ledger':str(path),'algorithm_version':ALGORITHM_VERSION,
               'coarse_new_cells':0,'coarse_visited':0,'coarse_has_more':False,
               'coarse_fallback':'host_protocol_unavailable'}
        c.material_search_progress=value;ledger['search_progress']=value;write_json(path,ledger)
        return None
    hold=ledger.get('guard_hold')
    if isinstance(hold,dict) and hold.get('world_session')==c.world:
        c.material_search_progress.update(ledger=str(path),guard_hold=hold)
        return None  # Do not choose a different frontier after combat displaced this route.
    # An older candidate may have a same-session combat incident from a
    # previous material job. Preserve the original region instead of making
    # the discovery frontier silently pick another deposit.
    for prior in ledger.get('tiles',{}).values():
        region=prior.get('region') if isinstance(prior,dict) else None
        if (isinstance(region,dict) and region.get('item')==item):
            held=route_failure(c,profile,item,region)
            if held and held.get('code') in ('guard_displaced','route_uncertain'):
                c.material_search_progress.update(ledger=str(path),guard_hold=held)
                return None
    if item in SNOW_PRODUCTS:
        refresh_hint_policy(seed_state)
        if shared_hints_disabled(path.parent,profile['server'],profile['dimension']):
            seed_state['hints_disabled']=True
            seed_state['server_mismatches']=max(seed_state['server_mismatches'],2)
            write_json(path,ledger)
    if (item in SNOW_PRODUCTS and not seed_state['hints_disabled']
            and state.get('snow_seed_locator_protocol',0)>=1
            and state.get('snow_seed_locator_available') is True):
        seeded=_seed_snow_expedition(c,item,profile,ledger,path,checkpoint,
                                     selection,max_tiles)
        if seeded['available']:
            value={'new_tiles':1 if seeded.get('region') else 0,
                   'scanned_total':sum(row.get('algorithm_version',1)>=ALGORITHM_VERSION
                                       for row in ledger['tiles'].values()),
                   'has_more':seeded.get('has_more',False),
                   'ledger':str(path),'algorithm_version':ALGORITHM_VERSION,
                   'seed_processed':seeded.get('processed',0),
                   'seed_cursor':seeded.get('cursor',0),
                   'seed_total':seeded.get('total',0)}
            c.material_search_progress=value;ledger['search_progress']=value;write_json(path,ledger)
            if seeded.get('region') is not None:return seeded['region']
            if seeded.get('has_more'):return None
    if item in SNOW_PRODUCTS:
        cached=_bobby_snow_expedition(c,item,profile,ledger,path,checkpoint,
                                      selection,max_tiles)
        if cached['available']:
            value={'new_tiles':1 if cached.get('region') else 0,
                   'scanned_total':sum(row.get('algorithm_version',1)>=ALGORITHM_VERSION
                                       for row in ledger['tiles'].values()),
                   'has_more':cached.get('has_more',False),
                   'ledger':str(path),'algorithm_version':ALGORITHM_VERSION,
                   'bobby_cached_candidates':cached.get('cached_candidates',0),
                   'bobby_checked':1,
                   'bobby_route':'live_verified' if cached.get('region') else 'checked'}
            c.material_search_progress=value;ledger['search_progress']=value;write_json(path,ledger)
            if cached.get('region') is not None:return cached['region']
            if cached.get('has_more'):return None
    extension=_extend_known_shaft(c,item,profile,ledger,path,checkpoint,origin,selection,max_tiles)
    if extension is not None:
        c.material_search_progress.update(ledger=str(path),has_more=True,algorithm_version=ALGORITHM_VERSION)
        return extension
    pending=[]; remembered=[]; search_tiles=[]
    known_regions=[r for r in profile.get('resource_regions',[]) if r.get('item')==item]
    for x,z in frontier(origin,min(384,profile.get('search_radius',256)),profile):
        key=f'{x}:{z}'
        prior=ledger['tiles'].get(key)
        if excluded([x,-64,z],[x+15,319,z+15],profile,selection):
            continue
        if math.hypot(x+8-c.anchor[0],z+8-c.anchor[2])>440:
            continue
        search_tiles.append((x,z))
        region=prior.get('region') if prior else None
        if (prior and prior.get('state')=='candidate' and isinstance(region,dict)
                and region.get('item')==item and not any(
                    r.get('min')==region.get('min') and r.get('max')==region.get('max') for r in known_regions)):
            if route_failure(c,profile,item,region):
                continue  # Same-session unsafe route is not exhausted ore or permission to retry.
            # A prior job finding a deposit does not mean it exhausted it.
            # Re-scan the tile before using it; never treat cached ore as stock.
            remembered.append((x,z));continue
        already_seen=prior and (prior.get('state')=='candidate' or prior.get('algorithm_version',1)>=ALGORITHM_VERSION)
        if already_seen:continue
        pending.append((x,z))
    normal_pending=list(pending)
    coarse_new=0;coarse_visited=0;coarse_has_more=False;coarse_reason=None
    if item in SNOW_PRODUCTS and not remembered:
        coarse=_coarse_snow_frontier(c,profile,ledger,path,checkpoint,origin,selection,search_tiles)
        coarse_new=coarse['new_cells'];coarse_visited=coarse['visited']
        coarse_has_more=coarse['has_more'];coarse_reason=coarse.get('reason')
        if coarse['held']:
            return None
        if coarse['available'] and coarse['tiles']:
            here=c.status()['pos']
            pending=sorted(set(coarse['tiles']),
                           key=lambda tile:math.hypot(tile[0]+8-here[0],tile[1]+8-here[2]))
        elif coarse['available'] and coarse_has_more:
            value={'new_tiles':0,
                   'scanned_total':sum(row.get('algorithm_version',1)>=ALGORITHM_VERSION
                                       for row in ledger['tiles'].values()),
                   'has_more':True,'ledger':str(path),'algorithm_version':ALGORITHM_VERSION,
                   'coarse_new_cells':coarse_new,'coarse_visited':coarse_visited,
                   'coarse_has_more':True}
            c.material_search_progress=value;ledger['search_progress']=value;write_json(path,ledger)
            return None
        else:
            # An old host, a partial/unavailable reply, or exhausted coarse
            # coverage falls back to the existing bounded detailed frontier.
            pending=normal_pending
    pending=remembered+pending
    count=0
    def progress():
        value={'new_tiles':count,'scanned_total':sum(row.get('algorithm_version',1)>=ALGORITHM_VERSION for row in ledger['tiles'].values()),
               'has_more':len(pending)>count or coarse_has_more,
               'ledger':str(path),'algorithm_version':ALGORITHM_VERSION}
        if item in SNOW_PRODUCTS:
            value.update(coarse_new_cells=coarse_new,coarse_visited=coarse_visited,
                         coarse_has_more=coarse_has_more)
            if coarse_reason:value['coarse_fallback']=coarse_reason
        c.material_search_progress=value;ledger['search_progress']=value;write_json(path,ledger)
    progress()
    for x,z in pending[:max_tiles]:
        key=f'{x}:{z}';checkpoint()
        # Native cruise still performs collision/guard checks; never disable
        # flight or claim to traverse unknown terrain in a synthetic snapshot.
        cruise=max(145,min(250,c.status()['pos'][1]))
        if not _search_travel(c,[x+8.5,cruise,z+8.5],checkpoint,ledger,path,(x,z)):
            return None
        rows=[]
        levels=(((58,110),(111,164),(165,220),(221,280),(281,319))
                if item in SNOW_PRODUCTS else
                ((-60,-1),(0,59),(60,120),(121,164)))
        for bottom,top in levels:
            checkpoint()
            reply=c.request('scan',min=[x-3,bottom,z-3],max=[x+18,top,z+18],details=True)
            if not isinstance(reply.get('blocks'),list):
                raise RuntimeError('资源扫描未完整加载，不能记录为空区域')
            rows.extend(reply['blocks'])
        diagnostics={}
        candidate=choose_region(rows,item,x,z,c.status()['pos'],checkpoint,diagnostics)
        if candidate and item in SNOW_PRODUCTS:
            try:
                # Discovery and execution must authorize the same exact snow
                # region.  In particular, frontier ring three begins only 48
                # blocks from search_origin: persisting that candidate would
                # make acquisition reject it forever before searching onward.
                validate_snow_region(candidate,profile,selection)
            except ValueError as error:
                rejected=diagnostics.setdefault('reject_reasons',Counter())
                rejected['protected_site_buffer']+=1
                diagnostics['region_validation']=str(error)
                candidate=None
        held_route=route_failure(c,profile,item,candidate) if candidate else None
        prior=ledger['tiles'].get(key)
        if prior:ledger.setdefault('history',{}).setdefault(key,[]).append(prior)
        ledger['tiles'][key]={'observed_at':c.status()['time'],'world_session':c.world,
                              'algorithm_version':ALGORITHM_VERSION,
                              'state':'candidate' if candidate else 'empty_or_unsafe','region':candidate,
                              'diagnostics':diagnostics,
                              **({'route_hold':held_route['code']} if held_route else {})}
        count+=1;progress()
        if candidate and held_route and held_route.get('code') in ('guard_displaced','route_uncertain'):
            c.material_search_progress.update(guard_hold=held_route)
            return None
        if candidate and not held_route:
            return candidate
    return None
