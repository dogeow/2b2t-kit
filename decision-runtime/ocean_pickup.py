"""Choose the supported water-column center for a verified item drop."""

import math


def pickup_pose(drop_pos, column_rows):
    if len(drop_pos) != 3 or not all(math.isfinite(v) for v in drop_pos):
        return None
    x, y, z = drop_pos
    cell_x, cell_y, cell_z = math.floor(x), math.floor(y), math.floor(z)
    solid = [row['pos'][1] for row in column_rows
             if row.get('solid') and row.get('pos', [None,None,None])[0] == cell_x
             and row['pos'][2] == cell_z and row['pos'][1] <= cell_y]
    if not solid:
        return None
    feet_y = max(solid) + 1
    if not feet_y - .75 <= y <= feet_y + 1.75:
        return None
    return {'cell': [cell_x, cell_y, cell_z],
            'floor_y': feet_y - 1,
            'target': [cell_x + .5, feet_y, cell_z + .5]}


def supported_drop_neighborhood(rows, target):
    """Allow a verified one-block seabed step, but never an unbounded cavity."""
    x, y, z = target
    solid = {tuple(row['pos']) for row in rows if row.get('solid')}
    return all(any((x+dx, y-1-drop, z+dz) in solid for drop in (0,1))
               for dx in (-1, 0, 1) for dz in (-1, 0, 1))


def within_mining_reach(state, target, max_reach=4.15):
    eye=[state['pos'][0],state['pos'][1]+1.62,state['pos'][2]]
    top=[target[0]+.5,target[1]+1,target[2]+.5]
    return math.dist(eye,top)<=max_reach


def within_pickup_column(state, target, max_horizontal=1.25):
    return math.hypot(target[0]+.5-state['pos'][0],
                      target[2]+.5-state['pos'][2])<=max_horizontal


def select_next_gravel(state, choices, rows, previous):
    """Choose a reachable supported neighbor, skipping unsuitable candidates."""
    blocks={tuple(row['pos']):row.get('state') for row in rows}
    for row in sorted(choices, key=lambda row: math.dist(
            [row['pos'][0]+.5, row['pos'][1]+1, row['pos'][2]+.5], state['pos'])):
        target=row['pos']
        if (target!=previous
                and abs(target[0]-previous[0])<=1
                and abs(target[2]-previous[2])<=1
                and .99<=state['pos'][1]-target[1]<=4.5
                and within_mining_reach(state,target)
                and within_pickup_column(state,target)
                and blocks.get(tuple(target))=='Block{minecraft:gravel}'
                and supported_drop_neighborhood(rows,target)):
            return row
    return None
