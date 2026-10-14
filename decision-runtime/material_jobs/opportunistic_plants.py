"""Read actual loaded land during a trip, including cactus; never credits or harvests."""
import math
from pathlib import Path
from kit_runtime.journal import write_json


PLANTS=frozenset('minecraft:'+name for name in
                ('cactus','cactus_flower','poppy','dandelion','cornflower',
                 'rose_bush','lilac','peony','sunflower','blue_orchid',
                 'red_tulip','orange_tulip','allium'))


def survey(c,checkpoint,out):
    state=checkpoint();x,z=math.floor(state['pos'][0]),math.floor(state['pos'][2])
    reply=c.request('scan_snow_biomes',center=[x,z],radius=32,stride=32)
    if (reply.get('id')!=c.last or reply.get('world_session')!=c.world
            or reply.get('phase')not in(None,'done')):
        raise RuntimeError('Opportunistic biome survey scope is unconfirmed')
    biomes=reply.get('snow_biome_survey')or{}
    samples=biomes.get('samples')
    if (not isinstance(samples,list) or biomes.get('loaded_samples')!=len(samples)
            or not 0<=len(samples)<=9):
        raise RuntimeError('Opportunistic biome survey is incomplete')
    book={'world_session':c.world,'biome_request_id':c.last,'patches':[],
          'plants':[],'inventory_credit':0,'actual_land_only':True}
    seen=set()
    for sample in samples:
        biome=sample.get('biome','')
        if 'ocean'in biome or 'river'in biome:continue
        pos=sample.get('pos')
        if (not isinstance(pos,list)or len(pos)!=3 or any(type(v)is not int for v in pos)
                or not -64<=pos[1]<=319):
            raise RuntimeError('Loaded surface position is malformed')
        sx,sy,sz=pos;tx,tz=sx//16*16,sz//16*16
        if (tx,tz)in seen:continue
        # The surface height may be a tree crown. Include the forest floor;
        # a shallow canopy-only scan cannot establish that flowers are absent.
        depth=18 if any(name in biome for name in ('forest','taiga','grove','jungle')) else 3
        seen.add((tx,tz));low=[tx,max(-64,sy-depth),tz];high=[tx+15,min(319,sy+8),tz+15]
        checkpoint();scan=c.request('scan',min=low,max=high,details=True)
        cells=math.prod(high[i]-low[i]+1 for i in range(3))
        if (scan.get('id')!=c.last or scan.get('world_session')!=c.world
                or scan.get('phase')not in(None,'done') or scan.get('scan_cells_read')!=cells
                or scan.get('scan_total_cells')!=cells or not isinstance(scan.get('blocks'),list)):
            book['patches'].append({'min':low,'max':high,'complete':False})
            continue
        plants=[row for row in scan['blocks']if row.get('state','').split('}',1)[0].removeprefix('Block{')in PLANTS]
        book['plants'].extend(plants);book['patches'].append({'min':low,'max':high,
            'complete':True,'request_id':c.last,'biome':biome,'plants':len(plants)})
    checkpoint();write_json(Path(out),book);return book
