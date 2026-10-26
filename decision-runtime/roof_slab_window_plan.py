"""Plan supported subsets of a dry slab roof without clearing other blocks.

Caller must supply a complete current-world scan and preserve native ownership,
health, entity clearance and printer acknowledgement gates during execution.
"""
import math
from collections import deque

SLAB = 'Block{minecraft:cobblestone_slab}[type=bottom,waterlogged=false]'

def choices(expected, observed, player, *, grid_origin, limit=16, y=72):
    if type(limit) is not int or not 1 <= limit <= 16:
        raise ValueError('One to sixteen carried slabs per window required')
    if len(grid_origin)!=2 or any(type(v)is not int for v in grid_origin):
        raise ValueError('Exact grid origin required')
    wanted = {p for p, state in expected.items() if p[1] == y and state == SLAB}
    # A completed double slab is also a real side face for the next bottom slab.
    # It must match the projection exactly; a wrong half or foreign block is not a support.
    double = 'Block{minecraft:cobblestone_slab}[type=double,waterlogged=false]'
    actual = {p for p, state in expected.items() if p[1] == y and state in (SLAB, double)
              and observed.get(p, {}).get('state') == state
              and observed[p].get('fluid') is False and observed[p].get('block_entity') is False}
    origin_x, origin_z = grid_origin
    tiles = {((p[0]-origin_x)//4, (p[2]-origin_z)//4) for p in wanted}
    results = []
    for i, j in tiles:
        x, z = origin_x+4*i, origin_z+4*j
        if any(x-1 <= p[0] <= x+4 and z-1 <= p[2] <= z+4 and y+1 <= p[1] <= y+11
               for p in observed):
            continue
        missing = {p for p in wanted if x <= p[0] < x+4 and z <= p[2] < z+4 and p not in observed}
        roots = sorted(p for p in missing if any((p[0]+dx,y,p[2]+dz) in actual
                       for dx,dz in [(1,0),(-1,0),(0,1),(0,-1)]))
        queue = deque(roots);seen = set(roots);mask = []
        while queue and len(mask)<limit:
            p = queue.popleft();mask.append(p)
            for dx, dz in [(1,0),(-1,0),(0,1),(0,-1)]:
                q=(p[0]+dx,y,p[2]+dz)
                if q in missing and q not in seen:seen.add(q);queue.append(q)
        if not mask:
            continue
        pose = [x+2., y+2.1, z+2.]
        results.append({'positions':[list(p)for p in mask], 'hover':pose,
                        'count':len(mask), 'distance':math.dist(player,pose)})
    return sorted(results,key=lambda row:(row['distance'],-row['count'],row['hover']))
