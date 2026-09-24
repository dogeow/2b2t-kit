"""Reach gravel under at most two natural soil blocks from directly above."""

import json
import time
from pathlib import Path

from build_supervisor import room_for, stocks
from drop_collection import collect_drop
from gravel_harvest import WATER_BUFFER, dry_top_gravel, harvest, water_buffer_clear
from shore_concrete import block_state

SOIL_DROPS = {
    'Block{minecraft:grass_block}': {'minecraft:dirt', 'minecraft:grass_block'},
    'Block{minecraft:dirt}': {'minecraft:dirt'},
    'Block{minecraft:coarse_dirt}': {'minecraft:coarse_dirt'},
    'Block{minecraft:podzol}': {'minecraft:dirt', 'minecraft:podzol'},
}


def shallow_candidates(rows, low, high, max_cover, scan_ceiling):
    if not 1 <= max_cover <= 2:
        raise ValueError('Shallow gravel is limited to one or two soil layers')
    observed = {tuple(row['pos']): row for row in rows}
    result = []
    for row in rows:
        p = row['pos'];x,y,z = p
        if (row['state'] != 'Block{minecraft:gravel}'
                or not all(low[i] <= p[i] <= high[i] for i in range(3))):
            continue
        support = observed.get((x,y-1,z))
        if support is None or not support.get('solid') or support.get('fluid'):
            continue
        for depth in range(1,max_cover+1):
            surface_y=y+depth
            if surface_y >= scan_ceiling:
                continue
            cover = [{'pos':[x,h,z], 'state':block_state(rows,[x,h,z])}
                     for h in range(surface_y,y,-1)]
            if any(layer['state'] not in SOIL_DROPS for layer in cover):
                continue
            if any(block_state(rows,[x,h,z])!='Block{minecraft:air}'
                   for h in range(surface_y+1,scan_ceiling+1)):
                continue
            if not water_buffer_clear(rows,p) or not water_buffer_clear(rows,[x,surface_y,z]):
                continue
            if any(near.get('block_entity')
                   and max(abs(near['pos'][0]-x),abs(near['pos'][2]-z))<=WATER_BUFFER
                   and abs(near['pos'][1]-surface_y)<=3 for near in rows):
                continue
            result.append({'pos':p,'surface_y':surface_y,'cover':cover})
            break
    return result


def _fresh_cover_drops(before, after, position, allowed):
    old={entity['uuid'] for entity in before.get('entities',[])
         if entity.get('type')=='minecraft:item'}
    return [entity for entity in after.get('entities',[])
            if entity.get('type')=='minecraft:item' and entity.get('uuid') not in old
            and entity.get('stack',{}).get('item') in allowed
            and sum((a-(b+.5))**2 for a,b in zip(entity['pos'],position))<=36]


def open_and_harvest(client, candidate, out):
    """One exact vertical column; any ambiguous break or pickup stops the run."""
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    position=candidate['pos'];result={'gravel':position,'cover':[]}
    for layer in candidate['cover']:
        p=layer['pos'];expected=layer['state'];allowed=SOIL_DROPS[expected]
        rows=client.request('scan',min=[p[0]-WATER_BUFFER,position[1]-2,p[2]-WATER_BUFFER],
                            max=[p[0]+WATER_BUFFER,p[1]+2,p[2]+WATER_BUFFER],details=True)['blocks']
        if (block_state(rows,p)!=expected or not water_buffer_clear(rows,position)
                or not water_buffer_clear(rows,p)):
            result['stopped']='Soil or water buffer changed before break'
            return result
        state=client.status()
        if room_for(state,'minecraft:gravel')<1 or not any(room_for(state,item)>=1 for item in allowed):
            raise RuntimeError('No verified backpack room for shallow gravel and soil')
        approached=client.request('approach_block',pos=p,face='up',expected_state=expected,seconds=120)
        if approached.get('phase')!='done':
            result['stopped']='Natural cover cannot be reached from above'
            return result
        client.checked('select_item',item='minecraft:diamond_shovel')
        before=client.status()
        mined=client.request('mine_block',pos=p,face='up',expected_state=expected,seconds=20)
        if mined.get('phase')!='done':
            if mined.get('detail')=='Fluid next to target is protected':
                result['stopped']='Native fluid protection'
                return result
            raise RuntimeError('Natural cover break was not confirmed: '+str(mined.get('detail')))
        if block_state(client.request('scan',min=p,max=p)['blocks'],p)==expected:
            raise RuntimeError('Natural cover is still present after mining reply')
        deadline=time.monotonic()+12;recovered=False
        while time.monotonic()<deadline:
            after=client.status();old=stocks(before);new=stocks(after)
            if any(new.get(item,0)>old.get(item,0) for item in allowed):
                recovered=True;break
            drops=_fresh_cover_drops(before,after,p,allowed)
            if drops:
                recovered=all(collect_drop(client,drop,observation=after) for drop in drops)
                if recovered:break
            time.sleep(.25)
        if not recovered:
            raise RuntimeError('Mined natural cover has no verified inventory recovery')
        result['cover'].append({'pos':p,'state':expected,'recovered':True})
        (out/'progress.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    p=position
    fresh=client.request('scan',min=[p[0]-WATER_BUFFER,p[1]-2,p[2]-WATER_BUFFER],
                         max=[p[0]+WATER_BUFFER,p[1]+3,p[2]+WATER_BUFFER],details=True)['blocks']
    if not dry_top_gravel(fresh,p):
        raise RuntimeError('Gravel or water buffer changed after removing cover')
    result['harvest']=harvest(client,p,p,1,out/'gravel')
    (out/'progress.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result
