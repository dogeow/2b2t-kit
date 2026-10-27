"""Conservative planting and harvesting geometry for registered paper cane roots."""
GROUND=frozenset(('minecraft:grass_block','minecraft:dirt','minecraft:sand','minecraft:red_sand'))
def block(row):return (row or{}).get('state','').split('}',1)[0].removeprefix('Block{')
def suitable(rows,root):
    """Caller must supply a complete same-world scan covering root and neighbors."""
    by={tuple(r['pos']):r for r in rows};x,y,z=root;floor=by.get((x,y-1,z))
    return bool(floor and block(floor)in GROUND and floor.get('solid')is True
                and floor.get('fluid')is False and floor.get('block_entity')is False
                and all((x,y+i,z)not in by for i in range(3))
                and any(block(by.get(p))=='minecraft:water'and by[p].get('fluid')is True
                        for p in [(x-1,y-1,z),(x+1,y-1,z),(x,y-1,z-1),(x,y-1,z+1)]))
def harvest_targets(rows,roots):
    """Only the second block of a continuous registered stalk; retain every root."""
    by={tuple(r['pos']):r for r in rows};result=[]
    for x,y,z in roots:
        if block(by.get((x,y,z)))=='minecraft:sugar_cane'and block(by.get((x,y+1,z)))=='minecraft:sugar_cane':result.append([x,y+1,z])
    return result

def single_block_harvest_order(rows,roots):
    """Top down order for single-drop collectors; reject stacks beyond natural height."""
    by={tuple(r['pos']):r for r in rows};result=[]
    for x,y,z in roots:
        if block(by.get((x,y,z)))!='minecraft:sugar_cane'or block(by.get((x,y+3,z)))=='minecraft:sugar_cane':continue
        upper=[]
        for yy in (y+1,y+2):
            if block(by.get((x,yy,z)))!='minecraft:sugar_cane':break
            upper.append([x,yy,z])
        result.extend(reversed(upper))
    return result
