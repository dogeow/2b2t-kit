"""Find a single-sapling spruce site from a complete current scan."""
import math
from .acquisition import block_id,SAPLING_SOILS

SOFT={'minecraft:short_grass','minecraft:tall_grass','minecraft:fern','minecraft:large_fern','minecraft:bush'}
FARM={'minecraft:farmland','minecraft:wheat','minecraft:carrots','minecraft:potatoes',
      'minecraft:beetroots','minecraft:sugar_cane','minecraft:cactus','minecraft:bamboo'}


def choose(volume,near,protected=(),*,require_harvest_halo=True,species='minecraft:spruce_log'):
    if species!='minecraft:spruce_log':raise ValueError('This growth-space policy is verified for single-sapling spruce only')
    low,high=volume['min'],volume['max'];rows=volume['blocks']
    if volume.get('complete')is not True or math.prod(b-a+1 for a,b in zip(low,high))>50000:
        raise ValueError('Complete bounded current tree-site scan required')
    cells={tuple(r['pos']):r for r in rows}
    if len(cells)!=len(rows)or any(not all(low[i]<=p[i]<=high[i]for i in range(3))for p in cells):
        raise ValueError('Duplicate or outside tree-site scan block')
    choices=[]
    for p,soil in cells.items():
        x,ground,z=p;y=ground+1
        if (block_id(soil)not in SAPLING_SOILS or soil.get('solid')is not True
                or soil.get('fluid')is not False or soil.get('block_entity')is not False):continue
        # The existing natural-tree harvester independently checks this entire
        # halo. Keep it inside the same complete scan before planting anything.
        box={'min':[x-11,y-5,z-11],'max':[x+11,y+39,z+11]}
        crown={'min':[x-3,y,z-3],'max':[x+3,y+12,z+3]}
        needed=box if require_harvest_halo else crown
        if not all(low[i]<=needed['min'][i]<=needed['max'][i]<=high[i]for i in range(3)):continue
        if any(all(crown['min'][i]<=b['max'][i]and b['min'][i]<=crown['max'][i]for i in range(3))for b in protected):continue
        nearby=[r for q,r in cells.items()if all(box['min'][i]<=q[i]<=box['max'][i]for i in range(3))]
        if any(r.get('block_entity')or any(t in block_id(r)for t in
               ('_planks','_bricks','glass','concrete','_door','_trapdoor'))for r in nearby):continue
        # The larger halo is observation space for the existing tree harvester.
        # Crops outside the actual crown are retained; none becomes tree soil,
        # a landing floor or a clearing target.
        if any(block_id(r)in FARM and all(crown['min'][i]<=r['pos'][i]<=crown['max'][i]for i in range(3))for r in nearby):continue
        root_plant=cells.get((x,y,z))
        if root_plant and (block_id(root_plant)not in('minecraft:short_grass','minecraft:bush')
                or root_plant.get('replaceable')is not True or root_plant.get('fluid')is not False
                or root_plant.get('block_entity')is not False):continue
        # The installed single-sapling spruce/pine features reach at most10
        # trunk blocks, with a two-layer size check (radius0 then2). Existing
        # natural leaves can be replaced by ordinary tree growth. Full logs,
        # persistent decorative leaves and other solids remain obstacles.
        def growth_clear(q,r):
            dy=q[1]-y;radius=0 if dy<2 else 2
            if not 0<=dy<=12 or abs(q[0]-x)>radius or abs(q[2]-z)>radius:return True
            name=block_id(r)
            return (r.get('fluid')is False and r.get('block_entity')is False and
                    (name in SOFT or name.endswith('_leaves')and'persistent=false'in r['state']))
        if any(not growth_clear(q,r)for q,r in cells.items()):continue
        if any(abs(q[0]-x)<=1 and abs(q[2]-z)<=1 and y<=q[1]<=y+1
               and block_id(r)=='minecraft:spruce_sapling'for q,r in cells.items()):continue
        poses=[]
        for dx,dz in((3,0),(-3,0),(0,3),(0,-3)):
            px,pz=x+dx,z+dz;floor=cells.get((px,y-1,pz))
            if (not floor or not floor.get('solid')or floor.get('fluid')or floor.get('block_entity')
                    or block_id(floor)not in SAPLING_SOILS):continue
            if any((px,h,pz)in cells and block_id(cells[px,h,pz])not in SOFT for h in range(y,y+2)):continue
            poses.append([px+.5,y+.2,pz+.5])
        if not poses:continue
        poses.sort(key=lambda q:math.dist(q,near))
        choices.append((math.dist([x+.5,y,z+.5],near),{'species':species,'root':[x,y,z],'soil':soil,
            'stances':poses,'harvest_bounds':box,'growth_radius':3,'growth_height':12,
            'clearing_required':False,'tree_shape':'single_sapling',
            'harvest_halo_observed':require_harvest_halo,'root_before':root_plant}))
    return min(choices,key=lambda r:r[0])[1]if choices else None
