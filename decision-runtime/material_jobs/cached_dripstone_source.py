"""Bounded read-only block geometry hints from the current Bobby world."""
import math

from . import bobby_snow_cache as cache


def section_hint(section, cx, cz):
    if not isinstance(section, dict): return None
    y = section.get('Y'); states = section.get('block_states') or {}
    if type(y) is not int or not -2 <= y <= 5 or not isinstance(states, dict): return None
    palette = states.get('palette')
    if (not isinstance(palette, list) or not 1 <= len(palette) <= 4096
            or any(not isinstance(p, dict) or not isinstance(p.get('Name'), str) for p in palette)): return None
    names = [p['Name'] for p in palette]
    wanted = {i for i,n in enumerate(names) if n == 'minecraft:dripstone_block'}
    if not wanted: return None
    air = {i for i,n in enumerate(names) if n in ('minecraft:air','minecraft:cave_air','minecraft:void_air')}
    if len(palette) == 1: values = [0]*4096
    else:
        bits=max(4,(len(palette)-1).bit_length()); per=64//bits; mask=(1<<bits)-1
        data=states.get('data')
        if (not isinstance(data,(list,tuple)) or len(data)!=math.ceil(4096/per)
                or any(type(v) is not int or not -(1<<63)<=v<(1<<63) for v in data)): return None
        values=[(data[i//per]>>((i%per)*bits))&mask for i in range(4096)]
        if any(v>=len(palette) for v in values): return None
    points=[i for i,n in enumerate(values) if n in wanted]; exposed=0
    for i in points:
        x=i%16; z=(i//16)%16; height=i//256
        adjacent=[i+d for d,ok in ((-1,x>0),(1,x<15),(-16,z>0),(16,z<15),(-256,height>0),(256,height<15)) if ok]
        if any(values[j] in air for j in adjacent): exposed+=1
    return {'chunk':[cx,cz], 'section_y':y*16, 'cached_dripstone':len(points),
            'cached_exposed':exposed, 'cached_air':sum(v in air for v in values),
            'target_hint':[cx*16+8,y*16+8,cz*16+8],
            'source':'current_world_bobby_cached_blocks_hint_only',
            'live_source_verified':False, 'inventory_credit':0}


def locate(game, server, dimension, centers, *, radius=4):
    if (type(radius) is not int or not 0<=radius<=4 or not isinstance(centers,list)
            or not 1<=len(centers)<=4 or any(not isinstance(p,(list,tuple)) or len(p)!=2
                or any(type(v) is not int for v in p) for p in centers)):
        raise ValueError('At most four bounded current-world cache areas required')
    folders=cache._current_dimensions(game,server,dimension); seen=set(); results=[]; reads=0
    for ox,oz in centers:
        for cx in range(ox//16-radius,ox//16+radius+1):
            for cz in range(oz//16-radius,oz//16+radius+1):
                if (cx,cz) in seen or not cache._inside_world(cx,cz): continue
                seen.add((cx,cz))
                for _,directory in folders:
                    path=directory/('r.%d.%d.mca'%(cx//32,cz//32))
                    if not path.is_file() or path.is_symlink(): continue
                    stat=path.stat()
                    if not 8192<=stat.st_size<=cache.MAX_REGION_BYTES: continue
                    try: tag=cache._read_chunk(path,cx//32,cz//32,cx,cz,stat.st_size)
                    except (cache._Rejected,OSError,ValueError): continue
                    if (not cache._same_file(stat,path.stat()) or not isinstance(tag,dict)
                            or tag.get('Status')!='full' or tag.get('xPos')!=cx or tag.get('zPos')!=cz): continue
                    reads+=1
                    for section in tag.get('sections',[]):
                        hint=section_hint(section,cx,cz)
                        if hint: results.append({**hint,'cache_mtime':stat.st_mtime})
                    break
    results.sort(key=lambda r:(r['cached_exposed'],r['cached_dripstone']),reverse=True)
    return {'chunks_read':reads,'sources':results,'hint_only':True,'inventory_credit':0}
