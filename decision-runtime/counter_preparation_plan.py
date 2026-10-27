"""Pure stock and lighting plans for existing trade-cell preparation."""
def oak_planks_needed(stock,count):
    if type(count)is not int or not 1<=count<=8:raise ValueError('Bounded cell count required')
    gates=max(0,count-stock.get('minecraft:oak_fence_gate',0));doors=max(0,count-stock.get('minecraft:oak_trapdoor',0));sticks=max(0,4*gates-stock.get('minecraft:stick',0))
    required=2*gates+2*((sticks+3)//4)+6*((doors+1)//2)
    return max(0,required-stock.get('minecraft:oak_planks',0))

def roof_light_plan(rows,roof):
    x,y,z=roof
    state=rows.get(tuple(roof),{}).get('state')
    if state not in ('Block{minecraft:dark_oak_planks}','Block{minecraft:cobblestone}'):return {'kind':'defer'}
    if state=='Block{minecraft:cobblestone}'and any(rows.get(tuple(roof),{}).get(k)is not v for k,v in [('solid',True),('fluid',False),('block_entity',False)]):return {'kind':'defer'}
    above=[rows.get((x,h,z))for h in [y+1,y+2]]
    if not any(above):return {'kind':'clear'}
    if above[0]is None or above[0].get('state')!='Block{minecraft:torch}'or above[1]is not None:return {'kind':'defer'}
    for xx,zz in [(x-1,z),(x+1,z),(x,z-1),(x,z+1)]:
        support=rows.get((xx,y,zz),{})
        valid=support.get('state')==state
        if state=='Block{minecraft:cobblestone}':valid=valid and all(support.get(k)is v for k,v in [('solid',True),('fluid',False),('block_entity',False)])
        if valid and not any((xx,h,zz)in rows for h in [y+1,y+2]):return {'kind':'temporary_torch','original':[x,y+1,z],'temporary':[xx,y+1,zz]}
    return {'kind':'defer'}
