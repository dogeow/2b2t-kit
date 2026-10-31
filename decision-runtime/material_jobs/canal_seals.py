"""Read-only admission plan for the verified north-canal cobblestone repair loop."""
from projected_source_column import AIR,coherent
CB='Block{minecraft:cobblestone}'

def plan_seal(model,frame,pos,world,*,protected=()):
    result={'ready':False,'pos':list(pos),'world_changes':False}
    def stop(reason):return {**result,'reason':reason}
    if len(pos)!=3 or any(type(v)is not int or abs(v)>=30000000 for v in pos):return stop('invalid_target')
    pos=tuple(pos)
    if pos in {tuple(p)for p in protected}:return stop('protected_unknown_target')
    x,y,z=pos;lo=[x-1,y-1,z-1];hi=[x+1,y+3,z+1]
    if not coherent(frame,world,lo,hi):return stop('incomplete_or_incoherent_frame')
    goals={tuple(v['pos']):v['state']for v in model['expected']};rows={tuple(v['pos']):v for v in frame['blocks']}
    if len(rows)!=len(frame['blocks']):return stop('duplicate_scan_positions')
    if goals.get(pos,AIR)!=CB:return stop('target_not_original_cobblestone')
    actual=rows.get(pos,{}).get('state',AIR)
    if actual==CB:return stop('already_correct')
    if actual not in ('Block{minecraft:dirt}','Block{minecraft:stone}'):return stop('not_supported_natural_obstruction')
    if rows[pos].get('fluid')is not False or rows[pos].get('block_entity')is not False:return stop('target_has_fluid_or_block_entity')
    for label,p in [('bottom',(x,y-1,z)),('top',(x,y+1,z))]:
        row=rows.get(p,{})
        if goals.get(p,AIR)!=CB or row.get('state')!=CB or row.get('solid')is not True or row.get('fluid')is not False or row.get('block_entity')is not False:return stop(label+'_not_original_cobblestone')
    for p in [(x-1,y,z),(x+1,y,z),(x,y,z+1)]:
        row=rows.get(p,{})
        if row.get('solid')is not True or row.get('fluid')is not False or row.get('block_entity')is not False:return stop('side_not_sealed')
    north=rows.get((x,y,z-1),{})
    if north.get('fluid')is not True or north.get('block_entity')is not False or not north.get('state','').startswith('Block{minecraft:water}'):return stop('north_not_plain_water')
    for p in [(x,y+2,z-1),(x,y+3,z-1)]:
        if rows.get(p,{}).get('state',AIR)!=AIR or goals.get(p,AIR)!=AIR:return stop('work_body_not_air')
    work=rows.get((x,y+1,z-1),{}).get('state',AIR)
    if work!=AIR and not work.startswith('Block{minecraft:water}'):return stop('work_ray_obstruction')
    pins={name:rows.get((x+dx,y+dy,z+dz),{}).get('state',AIR)for name,(dx,dy,dz)in {'east':(1,0,0),'west':(-1,0,0),'up':(0,1,0),'down':(0,-1,0),'south':(0,0,1),'north':(0,0,-1)}.items()}
    return {**result,'ready':True,'reason':'sealed_north_canal','expected_state':actual,'expected_goal_state':CB,'expected_neighbors':pins,'tool':'minecraft:diamond_pickaxe'if actual=='Block{minecraft:stone}'else'minecraft:diamond_shovel','work_pose':[x+.5,y+2.1,z-.68],'support_pos':[x,y-1,z],'support_face':'up'}
