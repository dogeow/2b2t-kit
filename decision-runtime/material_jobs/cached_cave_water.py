"""Read-only current-world Bobby hints for water with two air cells above it."""
from pathlib import Path
import math
from . import bobby_snow_cache as cache

AIR={'minecraft:air','minecraft:cave_air','minecraft:void_air'}
def decode(section):
    states=section.get('block_states')or{};palette=states.get('palette');y=section.get('Y')
    if type(y)is not int or not isinstance(palette,list)or not 1<=len(palette)<=4096:return None
    names=[p.get('Name')if isinstance(p,dict)else None for p in palette]
    if any(not isinstance(n,str)for n in names):return None
    if len(names)==1:return y,names,[0]*4096
    bits=max(4,(len(names)-1).bit_length());per=64//bits;mask=(1<<bits)-1;data=states.get('data')
    if not isinstance(data,(list,tuple))or len(data)!=math.ceil(4096/per):return None
    if any(type(v)is not int or not -(1<<63)<=v<(1<<63)for v in data):return None
    values=[(data[i//per]>>((i%per)*bits))&mask for i in range(4096)]
    if any(v>=len(names)for v in values):return None
    return y,names,values

def surfaces(tag):
    sections={}
    for section in tag.get('sections',[]):
        decoded=decode(section)
        if decoded:sections[decoded[0]]=decoded[1:]
    def name(x,y,z):
        data=sections.get(y//16)
        if data is None:return None
        names,values=data;return names[values[((y%16)*16+z)*16+x]]
    result=[]
    for sy,(names,values)in sections.items():
        if not -4<=sy<=1 or'minecraft:water'not in names:continue
        water={i for i,n in enumerate(names)if n=='minecraft:water'}
        for i,v in enumerate(values):
            if v not in water:continue
            y=sy*16+i//256;x=i%16;z=(i//16)%16
            if y>30 or name(x,y+1,z)not in AIR or name(x,y+2,z)not in AIR:continue
            result.append([tag['xPos']*16+x,y,tag['zPos']*16+z])
    return result

def water_volume(tag):
    """Count cached water, requiring explicit level zero for source credit."""
    total=sources=0
    for section in tag.get('sections',[]):
        decoded=decode(section)
        if not decoded or not -4<=decoded[0]<=1:continue
        sy,names,values=decoded;palette=section['block_states']['palette']
        water={i for i,n in enumerate(names)if n=='minecraft:water'}
        source={i for i in water if isinstance(palette[i].get('Properties'),dict)
                and palette[i]['Properties'].get('level')=='0'}
        for index,value in enumerate(values):
            if sy*16+index//256<=30:
                total+=value in water;sources+=value in source
    return {'cached_low_water_cells':total,'cached_source_cells':sources}

def locate(game,server,dimension,centres,*,radius=4,reference=None,prefer_volume=False):
    if type(prefer_volume)is not bool or type(radius)is not int or not 0<=radius<=4 or not 1<=len(centres)<=4:raise ValueError('Bounded existing current-world cache areas required')
    folders=cache._current_dimensions(Path(game),server,dimension);seen=set();hints=[];reads=0
    for ox,oz in centres:
        for cx in range(ox//16-radius,ox//16+radius+1):
            for cz in range(oz//16-radius,oz//16+radius+1):
                if(cx,cz)in seen or not cache._inside_world(cx,cz):continue
                seen.add((cx,cz))
                for _,directory in folders:
                    path=directory/('r.%d.%d.mca'%(cx//32,cz//32))
                    if not path.is_file()or path.is_symlink():continue
                    stat=path.stat()
                    if not 8192<=stat.st_size<=cache.MAX_REGION_BYTES:continue
                    try:tag=cache._read_chunk(path,cx//32,cz//32,cx,cz,stat.st_size)
                    except(cache._Rejected,OSError,ValueError):continue
                    if not cache._same_file(stat,path.stat())or not isinstance(tag,dict)or tag.get('Status')!='full'or tag.get('xPos')!=cx or tag.get('zPos')!=cz:continue
                    reads+=1;points=surfaces(tag);volume=water_volume(tag)
                    for p in points:hints.append({'pos':p,'air_pose_hint':[p[0]+.5,p[1]+1.1,p[2]+.5],'cache_mtime':stat.st_mtime,'source':'current_world_cached_water_with_two_air_cells','live_source_verified':False,**volume})
                    break
    distance=lambda h:math.dist(h['air_pose_hint'],reference)if reference is not None else 0
    hints.sort(key=lambda h:(-h['cached_source_cells'],-h['cached_low_water_cells'],distance(h))if prefer_volume else(distance(h),))
    return {'chunks_read':reads,'hint_count':len(hints),'hints':hints[:128],'hint_only':True,'inventory_credit':0,'requires_fresh_server_chunk_and_route_validation':True}
