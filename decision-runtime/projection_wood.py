"""Place ordinary logs on axis-correct supports, then strip them in place using an axe.

No schematic substitution, commands, temporary scaffolds or existing-block removal.
"""
import json,time,math
from projection_completion import block_state
from material_plan import inventory_counts
from work_access import approach_faces,ApproachUnavailable
AXES={'x':(('east',(-1,0,0)),('west',(1,0,0))),
      'y':(('up',(0,-1,0)),('down',(0,1,0))),
      'z':(('south',(0,0,-1)),('north',(0,0,1)))}

def log_target(row):
    wanted,props=block_state(row['expected']);actual,old=block_state(row['actual'])
    if not wanted.startswith('minecraft:stripped_') or not wanted.endswith(('_log','_wood','_stem','_hyphae')) or set(props)!={'axis'} or props['axis'] not in AXES:return None
    raw=wanted.replace('minecraft:stripped_','minecraft:',1)
    if row.get('fluid') or row.get('adjacent_fluid') or row.get('block_entity'):return None
    if actual==raw and old==props:return {'raw':raw,'axis':props['axis'],'strip':True}
    if row.get('kind')=='missing' and actual in ('minecraft:air','minecraft:cave_air'):return {'raw':raw,'axis':props['axis'],'strip':False}
    return None

def anchors(pos,axis,observed):
    cells={tuple(r['pos']):r for r in observed};result=[]
    for face,delta in AXES[axis]:
        p=tuple(a+b for a,b in zip(pos,delta));row=cells.get(p)
        if row and row.get('solid') and not row.get('fluid') and not row.get('block_entity'):
            name,_=block_state(row['state'])
            if name.endswith(('_log','_wood','_planks','_concrete')) or name in ('minecraft:stone','minecraft:stone_bricks','minecraft:quartz_block','minecraft:smooth_quartz'):
                result.append((face,row))
    return result

def state_at(client,pos):
    rows=client.request('scan',min=pos,max=pos)['blocks']
    return rows[0]['state'] if rows else 'Block{minecraft:air}'

PRE_USE_ERRORS={'Target interaction face is occluded or out of reach','Interaction became occluded while rotating','Target moved out of reach'}
def use_with_margin(client,pos,state,hand,faces,before_use=None):
    # A known pre-use rejection made no mutation. A fresh, closer pose may be tried once.
    for distance in (2.4,1.8):
        try:face=approach_faces(client,pos,state,faces,seconds=90,stand_distance=distance)
        except ApproachUnavailable:continue
        if before_use:before_use()
        reply=client.request('interact',pos=pos,face=face,expected_state=state,expected_hand=hand)
        if reply.get('phase')=='done':return
        if reply.get('phase')=='error' and reply.get('detail') in PRE_USE_ERRORS:continue
        raise RuntimeError(reply.get('detail','Interaction result uncertain; never repeat it'))
    raise ApproachUnavailable('No stable close interaction pose')

def finish_beams(client,limit=16):
    completed=[];deferred=set();selection=client.status()['projection_selection']['key']
    for _ in range(limit*4):
        if len(completed)>=limit:break
        s=client.status()
        if s['projection_selection']['key']!=selection:raise RuntimeError('Projection changed during beam work')
        audit=client.request('projection_audit')['projection_audit']
        if audit['placement_key']!=selection:raise RuntimeError('Beam audit belongs to another projection')
        rows=[r for r in audit['mismatches'] if tuple(r['pos']) not in deferred and log_target(r)]
        rows.sort(key=lambda r:(not log_target(r)['strip'],math.dist(r['pos'],s['pos'])))
        if not rows:break
        selected=None
        observed=client.request('scan',min=[min(r['pos'][i] for r in rows)-1 for i in range(3)],max=[max(r['pos'][i] for r in rows)+1 for i in range(3)],details=True)['blocks']
        for row in rows:
            plan=log_target(row);pos=row['pos']
            if plan['strip']:selected=(row,plan,None);break
            if inventory_counts(s).get(plan['raw'],0)<1:continue
            choices=anchors(pos,plan['axis'],observed)
            if choices:selected=(row,plan,choices);break
        if selected is None:break
        row,plan,choices=selected;pos=row['pos']
        if not plan['strip']:
            client.checked('select_item',item=plan['raw']);placed=False
            before=inventory_counts(client.status())[plan['raw']]
            def still_empty():
                if state_at(client,pos)!=row['actual']:raise RuntimeError('Beam target changed before placement')
            for face,anchor in choices:
                try:use_with_margin(client,anchor['pos'],anchor['state'],plan['raw'],(face,),still_empty)
                except ApproachUnavailable:continue
                placed=True;break
            if not placed:deferred.add(tuple(pos));continue
            raw_state='Block{'+plan['raw']+'}[axis='+plan['axis']+']'
            if state_at(client,pos)!=raw_state or inventory_counts(client.status())[plan['raw']]!=before-1:
                raise RuntimeError('Log placement/axis was not confirmed; no repeated placement')
        else:raw_state=row['actual']
        client.checked('select_item',item='minecraft:diamond_axe')
        try:use_with_margin(client,pos,raw_state,'minecraft:diamond_axe',('up','south','north','east','west','down'))
        except ApproachUnavailable:deferred.add(tuple(pos));continue
        if state_at(client,pos)!=row['expected']:raise RuntimeError('Stripping not confirmed; do not replay axe use')
        completed.append({'pos':pos,'expected':row['expected'],'placed_raw':not plan['strip']})
        with (client.out/'finished-beams.jsonl').open('a') as f:f.write(json.dumps(completed[-1],ensure_ascii=False)+'\n')
        print('BEAM_VERIFIED',len(completed),pos,flush=True)
    return {'completed':completed,'deferred':[list(p) for p in deferred]}
