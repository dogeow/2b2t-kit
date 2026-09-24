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
