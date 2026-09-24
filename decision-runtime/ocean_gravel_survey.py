"""Find naturally exposed shallow-seafloor gravel from a Kit block scan.

This is read-only reconnaissance. It does not infer a safe dive, air supply, or
item pickup from the block layout alone; those require live checks.
"""

from gravel_harvest import block_kind

GRAVEL = 'Block{minecraft:gravel}'
LAVA = 'Block{minecraft:lava}'
SOURCE_WATER = 'Block{minecraft:water}[level=0]'


def _surface_water(row):
    # Kelp, seagrass and bubble columns also contain water, but their outline
    # can intercept the mining ray before it reaches gravel. Flowing water can
    # carry the player off the selected column. Require a clear source column.
    return row is not None and row.get('fluid') and row['state'] == SOURCE_WATER


def exposed_ocean_gravel(rows, low, high, min_depth=2, max_depth=12):
    if not 1 <= min_depth <= max_depth <= 20:
        raise ValueError('Dive survey depth must be between 1 and 20 blocks')
    blocks = {tuple(row['pos']): row for row in rows}
    fluids = [tuple(row['pos']) for row in rows if row.get('fluid')]
    protected = [tuple(row['pos']) for row in rows if row.get('block_entity')]
    found = []
    for (x, y, z), row in blocks.items():
        if (block_kind(row['state']) != GRAVEL
                or not all(low[i] <= (x, y, z)[i] <= high[i] for i in range(3))):
            continue
        support = blocks.get((x, y-1, z))
        if support is None or not support.get('solid') or support.get('fluid'):
            continue
        depth = 0
        for h in range(y+1, y+max_depth+2):
            above = blocks.get((x, h, z))
            if above is None:
                break
            if not _surface_water(above):
                depth = 0
                break
            depth += 1
        else:
            # Water continues below our maximum verified depth.
            continue
        if not min_depth <= depth <= max_depth:
            continue
        if any(abs(fx-x) <= 2 and abs(fz-z) <= 2 and y-1 <= fy <= y+depth+1
               and block_kind(blocks[(fx, fy, fz)]['state']) == LAVA
               for fx, fy, fz in fluids):
            continue
        if any(abs(px-x) <= 2 and abs(pz-z) <= 2 and y-1 <= py <= y+depth+1
               for px, py, pz in protected):
            continue
        found.append({'pos': [x, y, z], 'water_depth': depth, 'surface_y': y+depth})
    exposed = {tuple(item['pos']) for item in found}
    size = {}
    while exposed:
        start = exposed.pop()
        component = [start]
        for x, y, z in component:
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                for dy in (-1, 0, 1):
                    neighbor = (x+dx, y+dy, z+dz)
                    if neighbor in exposed:
                        exposed.remove(neighbor)
                        component.append(neighbor)
        for pos in component:
            size[pos] = len(component)
    for item in found:
        item['exposed_patch_size'] = size[tuple(item['pos'])]
    return sorted(found, key=lambda item: (-item['exposed_patch_size'],
                                           item['water_depth'], item['pos']))
