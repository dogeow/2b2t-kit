"""Replant the four witnessed stump cells from outside the future trunk.

Uses the existing village owner and ordinary placement. A grown tree may
replace the saplings immediately; inventory debit still proves planting.
"""
import math
from material_plan import inventory_counts
from material_jobs.fixed_tree_ground import FLOORS

SAPLING = 'minecraft:dark_oak_sapling'
LOG = 'minecraft:dark_oak_log'
SOILS = frozenset(('minecraft:dirt', 'minecraft:grass_block', 'minecraft:podzol',
                  'minecraft:coarse_dirt', 'minecraft:rooted_dirt', 'minecraft:moss_block'))


def block_id(row):
    return row.get('state', '').split('}', 1)[0].removeprefix('Block{')


def stance(root, rows):
    """A dry two-block ground pose outside the trunk, reaching all four soils."""
    x, y, z = root
    roots = [(x+dx, y, z+dz) for dx in (0, 1) for dz in (0, 1)]
    choices = []
    for (px, py, pz), floor in rows.items():
        if py != y-1 or block_id(floor) not in FLOORS or not floor.get('solid') or floor.get('fluid'):
            continue
        pose = [px+.5, y+.1, pz+.5]
        # Leave a full block between the player's body and the future 2x2 trunk.
        if not (pose[0]+.3 <= x-1 or pose[0]-.3 >= x+3
                or pose[2]+.3 <= z-1 or pose[2]-.3 >= z+3):
            continue
        if any((px, yy, pz) in rows for yy in (y, y+1)):
            continue
        eye = [pose[0], pose[1]+1.62, pose[2]]
        if any(math.dist(eye, [a+.5, b-.001, c+.5]) > 4.1 for a, b, c in roots):
            continue
        choices.append(pose)
    if not choices:
        raise RuntimeError('No clear ground stance outside the future dark-oak trunk; no seeds placed')
    return min(choices, key=lambda p: math.dist(p, [x+1, y+.1, z+1]))


def replant(builder, root):
    from village_air_route import move
    x, y, z = root
    roots = [[x+dx, y, z+dz] for dx in (0, 1) for dz in (0, 1)]
    scene, rows = builder.scan([x-4, y-1, z-4], [x+5, y+2, z+5])
    if all(block_id(rows.get(tuple(p), {})) in (SAPLING, LOG) for p in roots):
        return {'already_renewed': True, 'scene': scene, 'roots': roots}
    if any(tuple(p) in rows for p in roots):
        raise RuntimeError('Stump is not four empty cells; preserve the existing tree')
    if any(block_id(rows.get((p[0], y-1, p[2]), {})) not in SOILS for p in roots):
        raise RuntimeError('Four actual planting soils are required')
    before = inventory_counts(builder.check())[SAPLING]
    if before < 4:
        raise RuntimeError('Four carried seeds required before starting renewal')
    pose = stance(root, rows)
    move(builder, pose)
    for p in roots:
        builder.place(p, [p[0], y-1, p[2]], 'up', item=SAPLING,
                      expected='Block{minecraft:dark_oak_sapling}[stage=0]',
                      acceptable_states=['Block{minecraft:dark_oak_sapling}[stage=0]',
                                         'Block{minecraft:dark_oak_sapling}[stage=1]',
                                         'Block{minecraft:dark_oak_log}[axis=y]'])
    after = inventory_counts(builder.check())[SAPLING]
    scene, rows = builder.scan([x, y, z], [x+1, y, z+1])
    if after != before-4 or not all(block_id(rows.get(tuple(p), {})) in (SAPLING, LOG) for p in roots):
        raise RuntimeError('Renewal input retained; debit or current roots not confirmed')
    return {'already_renewed': False, 'stance': pose, 'scene': scene, 'roots': roots,
            'seeds_before': before, 'seeds_after': after,
            'next_move': 'horizontal_clear_ground_before_ascending'}
