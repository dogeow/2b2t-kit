"""Read-only survey for dry gravel from the land surface to depth 20."""

from collections import defaultdict

from gravel_harvest import WATER_BUFFER

NATURAL_COVER = {
    'Block{minecraft:grass_block}', 'Block{minecraft:dirt}',
    'Block{minecraft:coarse_dirt}', 'Block{minecraft:podzol}',
    'Block{minecraft:stone}', 'Block{minecraft:andesite}',
    'Block{minecraft:diorite}', 'Block{minecraft:granite}',
    'Block{minecraft:tuff}', 'Block{minecraft:deepslate}',
    'Block{minecraft:cobbled_deepslate}', 'Block{minecraft:gravel}',
}


def deep_candidates(rows, low, high, min_depth=0, max_depth=20):
    if min_depth < 0 or max_depth < min_depth or max_depth > 20:
        raise ValueError('Gravel survey is limited to 0..20 blocks below the surface')
    blocks={tuple(row['pos']):row for row in rows}
    columns=defaultdict(list)
    fluids=[];protected=[]
    for row in rows:
        x,y,z=row['pos'];columns[(x,z)].append(row)
        if row.get('fluid'):
            fluids.append((x,y,z))
        if row.get('block_entity'):
            protected.append((x,y,z))
    found=[]
    for x in range(low[0],high[0]+1):
        for z in range(low[2],high[2]+1):
            column=columns.get((x,z),[])
            if not column:continue
            surface=max(column,key=lambda row:row['pos'][1])
            surface_y=surface['pos'][1]
            if surface['state'] not in NATURAL_COVER or not surface.get('solid'):
                continue
            for depth in range(min_depth,max_depth+1):
                y=surface_y-depth
                if y<low[1] or y>high[1]:continue
                target=blocks.get((x,y,z))
                support=blocks.get((x,y-1,z))
                if (target is None or target['state']!='Block{minecraft:gravel}'
                        or support is None or not support.get('solid') or support.get('fluid')):
                    continue
                cover=[blocks.get((x,h,z)) for h in range(surface_y,y,-1)]
                if any(row is None or row['state'] not in NATURAL_COVER
                       or not row.get('solid') or row.get('fluid') for row in cover):
                    continue
                if any(max(abs(px-x),abs(pz-z))<=WATER_BUFFER and y-2<=py<=surface_y+2
                       for px,py,pz in fluids):
                    continue
                if any(max(abs(px-x),abs(pz-z))<=WATER_BUFFER and y-2<=py<=surface_y+2
                       for px,py,pz in protected):
                    continue
                found.append({'pos':[x,y,z],'surface_y':surface_y,'depth':depth,
                              'cover':[{'pos':row['pos'],'state':row['state']}
                                       for row in cover]})
                break
    return found


def terrain_summary(rows, low, high):
    """Classify observed surface columns so scouting can prefer land to ocean."""
    top={}
    for row in rows:
        x,y,z=row['pos']
        if not (low[0]<=x<=high[0] and low[2]<=z<=high[2]):continue
        key=(x,z)
        if key not in top or y>top[key]['pos'][1]:top[key]=row
    result={'land_columns':0,'water_columns':0,'other_columns':0,'unloaded_columns':0}
    for x in range(low[0],high[0]+1):
        for z in range(low[2],high[2]+1):
            surface=top.get((x,z))
            if surface is None:result['unloaded_columns']+=1
            elif surface.get('fluid') or surface['state'].startswith('Block{minecraft:water}'):
                result['water_columns']+=1
            elif surface.get('solid'):result['land_columns']+=1
            else:result['other_columns']+=1
    return result
