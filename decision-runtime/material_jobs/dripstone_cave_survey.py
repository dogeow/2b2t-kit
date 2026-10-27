"""Choose a dry natural entry beside actual exposed cave dripstone."""
import math

from .acquisition import block_id
from .dry_hover_harvest import harvest_context, stations
from .vertical_resource_entry import plan


def entries(rows, low, high, *, protected=()):
    if (len(low) != 3 or len(high) != 3 or any(type(v) is not int for v in low+high)
            or any(a>b for a,b in zip(low,high))
            or math.prod(b-a+1 for a,b in zip(low,high)) > 50000):
        raise ValueError('Complete bounded current source survey required')
    cells = {tuple(r['pos']): r for r in rows}; protected = set(protected)
    results = {}; columns = {}; checked = set()
    for r in rows:
        x,y,z = r['pos']; columns.setdefault((x,z), []).append(r)
    for target in rows:
        p = target['pos']
        if block_id(target) != 'minecraft:dripstone_block' or tuple(p) in protected: continue
        if not all(low[i]+2 <= p[i] <= high[i]-2 for i in range(3)): continue
        local = [cells[(x,y,z)] for x in range(p[0]-2,p[0]+3)
                 for y in range(p[1]-2,p[1]+3) for z in range(p[2]-2,p[2]+3) if (x,y,z) in cells]
        if not harvest_context(local, p): continue
        for station, face in stations(p):
            x,bottom,z = map(math.floor, station)
            key=(x,bottom,z)
            if key in checked: continue
            checked.add(key)
            if (not low[0]+2 <= x <= high[0]-2 or not low[2]+2 <= z <= high[2]-2
                    or not max(8,low[1]) <= bottom <= min(90,high[1]-3)
                    or any((x,y,z) in cells for y in (bottom,bottom+1))): continue
            top = max([r['pos'][1] for r in columns.get((x,z),[]) if r['pos'][1]>=bottom]+[bottom])
            if top-bottom > 64 or top+3 > high[1]: continue
            neighborhood = [r for cx in range(x-2,x+3) for cz in range(z-2,z+3)
                            for r in columns.get((cx,cz),[]) if bottom-1<=r['pos'][1]<=top+3]
            try: opening = plan(neighborhood,x,z,bottom,top)
            except (RuntimeError,ValueError): continue
            if any(tuple(r['pos']) in protected for r in opening): continue
            entry = {'column':[x,z], 'bottom':bottom, 'top':top, 'target':p,
                     'entry_blocks':len(opening), 'station':station, 'face':face}
            if key not in results: results[key]=entry
    return sorted(results.values(), key=lambda e:(e['entry_blocks'],-e['bottom'],e['column']))
