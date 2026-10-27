"""Verify a one-cell south-stall extension before updating its containment policy."""
from village_beds import matches


def verified_bounds(scene, slot, world):
    foot, head, work = (slot.get(k) for k in ('bed_foot', 'bed_head', 'work_block'))
    if any(not isinstance(p,list) or len(p)!=3 or any(type(v)is not int for v in p) for p in (foot,head,work)):
        raise ValueError('Exact current refit coordinates required')
    x,y,z = foot
    item = {'fisherman':'barrel','butcher':'smoker'}.get(slot.get('profession'))
    if (item is None or slot.get('original_container_preserved') is not True
            or head != [x,y,z+1] or work != [x,y,z-2]
            or slot.get('previous_work_block') != [x,y,z-3]):
        raise ValueError('Verified inner-container stall refit required')
    if (not world or scene.get('world_session') != world
            or not scene.get('scan_total_cells')
            or scene.get('scan_total_cells') != scene.get('scan_cells_read')):
        raise ValueError('Complete current-world refit scan required')
    rows = {tuple(v['pos']):v for v in scene.get('blocks',[])}
    walls = [[sx,h,zz] for sx in (x-1,x+1) for h in range(y,y+3) for zz in range(z-2,z+2)]
    walls += [[x,h,z+2] for h in range(y,y+3)]
    walls += [[x,y+3,zz] for zz in range(z-2,z+2)]
    walls += [[x,y-1,zz] for zz in range(z-2,z+2)]
    if any(rows.get(tuple(p),{}).get('solid') is not True
           or rows[tuple(p)].get('fluid') is not False for p in walls):
        raise ValueError('Refit side walls, back, roof and dry floor must be complete')
    for p in ([x,y,z-3], work):
        row = rows.get(tuple(p),{})
        if not row.get('state','').startswith('Block{minecraft:'+item+'}') or row.get('block_entity') is not True:
            raise ValueError('Original and inner work containers must both remain intact')
    if (rows.get((x,y+1,z-3),{}).get('state') != 'Block{minecraft:dark_oak_slab}[type=bottom,waterlogged=false]'
            or rows.get((x,y+2,z-3),{}).get('solid') is not True
            or any((x,h,z-1) in rows for h in (y,y+1))
            or not matches(rows.get(tuple(foot)), 'minecraft:white_bed','foot','south')
            or not matches(rows.get(tuple(head)), 'minecraft:white_bed','head','south')):
        raise ValueError('Refit front, clear walking cell and both bed halves required')
    bounds = {'min':[x,y,z-2], 'max_exclusive':[x+1,y+3,z+2]}
    actors = [v for v in scene.get('scan_entities',[]) if v.get('uuid') == slot.get('occupant_uuid')]
    if len(actors)!=1:
        raise ValueError('Exact enclosed refit resident required')
    actor = actors[0]; box = actor.get('bounds') or {}; low, high = bounds['min'], bounds['max_exclusive']
    if (actor.get('type')!='minecraft:villager' or actor.get('health')!=20 or actor.get('is_baby') is not False
            or not all(low[i] <= box.get('min',[float('-inf')]*3)[i] < box.get('max',[float('inf')]*3)[i] <= high[i] for i in range(3))
            or not all(low[i] <= actor['pos'][i] < high[i] for i in range(3))):
        raise ValueError('Healthy adult must be wholly inside the proven refit')
    return bounds


def with_verified_assignment(policy, scene, slot, world):
    """Copy the policy, updating only this proven one-cell extension or its identical replay."""
    from copy import deepcopy
    bounds = verified_bounds(scene, slot, world)
    uid = slot['occupant_uuid']
    assigned = policy.get('adult_assignment_bounds')
    if policy.get('world_session') != world or not isinstance(assigned,dict) or uid not in assigned:
        raise ValueError('Existing current-world resident assignment required')
    old = assigned[uid]
    if old != bounds and (not isinstance(old,dict) or old.get('min') != bounds['min']
            or not isinstance(old.get('max_exclusive'),list) or len(old['max_exclusive']) != 3
            or old['max_exclusive'][:2] != bounds['max_exclusive'][:2]
            or old['max_exclusive'][2] + 1 != bounds['max_exclusive'][2]):
        raise ValueError('Only the observed single rear-cell extension can update this assignment')
    result = deepcopy(policy)
    result['adult_assignment_bounds'][uid] = bounds
    return result
