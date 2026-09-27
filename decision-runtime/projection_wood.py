"""Place ordinary logs on axis-correct supports, then strip them in place using an axe.

No schematic substitution, commands, temporary scaffolds or existing-block removal.
"""
import json,math
from projection_completion import block_state
from material_plan import inventory_counts
from work_access import approach_faces,ApproachUnavailable

POST_ITEM='minecraft:stripped_oak_log'
POST_RAW='minecraft:oak_log'
POST_AXIS='y'
def server_key(value):
    return str(value).lower().removesuffix(':25565')
AXES={'x':(('east',(-1,0,0)),('west',(1,0,0))),
      'y':(('up',(0,-1,0)),('down',(0,1,0))),
      'z':(('south',(0,0,-1)),('north',(0,0,1)))}

def log_target(row):
    wanted,props=block_state(row['expected']);actual,old=block_state(row['actual'])
    if not wanted.startswith('minecraft:stripped_') or not wanted.endswith(('_log','_wood','_stem','_hyphae')) or set(props)!={'axis'} or props['axis'] not in AXES:return None
    raw=wanted.replace('minecraft:stripped_','minecraft:',1)
    if row.get('fluid') or row.get('adjacent_fluid') or row.get('block_entity'):return None
    if actual==raw and old==props:return {'raw':raw,'axis':props['axis'],'strip':True}
    if row.get('kind')=='missing' and actual in ('minecraft:air','minecraft:cave_air'):
        return {'raw':raw,'axis':props['axis'],'strip':False}
    # ProjectionAudit calls a replaceable plant "missing". Only this one
    # courtyard plant is accepted, after a second detailed scan confirms it.
    if (wanted==POST_ITEM and props['axis']==POST_AXIS and row.get('kind')=='missing'
            and actual=='minecraft:short_grass' and not old):
        return {'raw':raw,'axis':props['axis'],'strip':False,'plant':True}
    return None

def anchors(pos,axis,observed):
    cells={tuple(r['pos']):r for r in observed};result=[]
    for face,delta in AXES[axis]:
        p=tuple(a+b for a,b in zip(pos,delta));row=cells.get(p)
        if row and row.get('solid') is True and row.get('fluid') is False and row.get('block_entity') is False:
            name,properties=block_state(row['state'])
            if (name.endswith(('_log','_wood','_planks','_concrete'))
                    or name in ('minecraft:stone','minecraft:stone_bricks','minecraft:quartz_block','minecraft:smooth_quartz')
                    or name=='minecraft:dirt' and not properties
                    or name=='minecraft:grass_block' and set(properties)<= {'snowy'}):
                result.append((face,row))
    return result

def cell_at(client,pos):
    rows=client.request('scan',min=pos,max=pos,details=True)['blocks']
    if len(rows)>1 or rows and rows[0]['pos']!=pos:
        raise RuntimeError('Exact beam cell scan returned an unexpected position')
    return rows[0] if rows else {'pos':pos,'state':'Block{minecraft:air}',
                                 'replaceable':True,'fluid':False,'block_entity':False}

def state_at(client,pos):
    return cell_at(client,pos)['state']

def _scoped_audit(state,audit,key,world,server,dimension):
    selection=state.get('projection_selection') or {}
    if (selection.get('key')!=key or state.get('world_session')!=world
            or state.get('dimension')!=dimension
            or server_key(state.get('server'))!=server_key(server)):
        raise RuntimeError('Beam work scope or selected projection changed')
    if (audit.get('placement_key')!=key or audit.get('loaded_chunks_verified') is not True
            or audit.get('kinds',{}).get('unloaded')
            or server_key(audit.get('server'))!=server_key(server)
            or audit.get('dimension')!=dimension
            or type(audit.get('observed_at')) is not int or audit['observed_at']<=0
            or type(audit.get('matched')) is not int or type(audit.get('total')) is not int
            or not isinstance(audit.get('mismatches'),list)
            or audit['matched']+len(audit['mismatches'])!=audit['total']):
        raise RuntimeError('Beam audit is incomplete or belongs to another site')
    low,high=selection.get('min'),selection.get('max')
    if (not all(isinstance(bound,list) and len(bound)==3 and all(type(n) is int for n in bound)
                for bound in (low,high)) or any(a>b for a,b in zip(low,high))):
        raise RuntimeError('Selected projection bounds are unavailable')
    for row in audit['mismatches']:
        pos=row.get('pos')
        if (not isinstance(pos,list) or len(pos)!=3 or any(type(n) is not int for n in pos)
                or any(not a<=n<=b for n,a,b in zip(pos,low,high))):
            raise RuntimeError('Beam audit contains a cell outside selected projection')
    return selection

def post_work(audit,state):
    """Count only native audited, in-selection oak posts the worker can repair."""
    key=(state.get('projection_selection') or {}).get('key')
    if not key:
        raise RuntimeError('No selected projection for post work')
    _scoped_audit(state,audit,key,state.get('world_session'),state.get('server'),state.get('dimension'))
    rows=[row for row in audit['mismatches']
          if row.get('expected')=='Block{'+POST_ITEM+'}[axis='+POST_AXIS+']']
    plans=[log_target(row) if row.get('neighbors_loaded') is True else None for row in rows]
    return {'eligible':sum(plan is not None for plan in plans),
            'raw_needed':sum(plan is not None and not plan['strip'] for plan in plans),
            'strip_ready':sum(plan is not None and plan['strip'] for plan in plans),
            'unsupported':len(rows)-sum(plan is not None for plan in plans)}

def _exact_target(client,row,plan,key,world,server,dimension):
    audit=client.request('projection_audit')['projection_audit']
    _scoped_audit(client.status(),audit,key,world,server,dimension)
    if not any(other.get('pos')==row['pos'] and other.get('expected')==row['expected']
               and other.get('actual')==row['actual'] and other.get('kind')==row['kind']
               and other.get('neighbors_loaded') is True and log_target(other)==plan
               for other in audit['mismatches']):
        raise RuntimeError('Beam changed in the fresh projection audit')
    observed=cell_at(client,row['pos'])
    if observed['state']!=row['actual']:
        raise RuntimeError('Beam target changed before interaction')
    if (plan.get('plant') and (observed.get('replaceable') is not True
                               or observed.get('fluid') is not False
                               or observed.get('block_entity') is not False)):
        raise RuntimeError('Short grass is no longer a dry replaceable cell')
    return audit['observed_at']

def _usable_axe(state):
    axes=[row for row in state.get('inventory',[]) if row.get('item') in
          ('minecraft:diamond_axe','minecraft:netherite_axe')
          and row.get('count')==1 and type(row.get('slot')) is int and 0<=row['slot']<36
          and type(row.get('durability')) is int and row['durability']>=2]
    if not axes:
        raise RuntimeError('No confirmed durable diamond or netherite axe for post work')
    return max(axes,key=lambda row:row['durability'])

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

def finish_beams(client,limit=16,*,expected_key=None,expected_world=None,expected_server=None,
                 expected_dimension=None,target_item=None,target_axis=None):
    if type(limit) is not int or not 1<=limit<=16:
        raise ValueError('Beam batch must contain 1 to 16 cells')
    initial=client.status()
    selection=(initial.get('projection_selection') or {}).get('key')
    if not selection or expected_key is not None and selection!=expected_key:
        raise RuntimeError('Selected projection changed before beam work')
    world=expected_world or initial['world_session']
    server=expected_server or initial['server']
    dimension=expected_dimension or initial['dimension']
    completed=[];deferred=set()
    for _ in range(limit*4):
        if len(completed)>=limit:break
        s=client.status()
        audit=client.request('projection_audit')['projection_audit']
        _scoped_audit(s,audit,selection,world,server,dimension)
        def plan_for(row):
            if row.get('neighbors_loaded') is not True:return None
            name,props=block_state(row['expected'])
            if ((target_item and name!=target_item)
                    or (target_axis and props.get('axis')!=target_axis)):
                return None
            return log_target(row)
        rows=[r for r in audit['mismatches'] if tuple(r['pos']) not in deferred and plan_for(r)]
        rows.sort(key=lambda r:(not log_target(r)['strip'],math.dist(r['pos'],s['pos'])))
        if not rows:break
        selected=None
        for row in rows:
            plan=log_target(row);pos=row['pos']
            if plan['strip']:selected=(row,plan,None);break
            if inventory_counts(s).get(plan['raw'],0)<1:continue
            observed=client.request('scan',min=[n-1 for n in pos],max=[n+1 for n in pos],details=True)['blocks']
            current=next((cell for cell in observed if cell['pos']==pos),None)
            if plan.get('plant') and (current is None or current.get('state')!=row['actual']
                                      or current.get('replaceable') is not True
                                      or current.get('fluid') is not False
                                      or current.get('block_entity') is not False):
                deferred.add(tuple(pos));continue
            choices=anchors(pos,plan['axis'],observed)
            if choices:selected=(row,plan,choices);break
        if selected is None:break
        row,plan,choices=selected;pos=row['pos']
        axe=_usable_axe(client.status())
        if not plan['strip']:
            client.checked('select_item',item=plan['raw']);placed=False
            before=inventory_counts(client.status()).get(plan['raw'],0)
            if before<1:raise RuntimeError('Raw log disappeared before placement')
            placement_audit=[None]
            def still_empty():placement_audit[0]=_exact_target(client,row,plan,selection,world,server,dimension)
            for face,anchor in choices:
                try:use_with_margin(client,anchor['pos'],anchor['state'],plan['raw'],(face,),still_empty)
                except ApproachUnavailable:continue
                placed=True;break
            if not placed:deferred.add(tuple(pos));continue
            raw_state='Block{'+plan['raw']+'}[axis='+plan['axis']+']'
            if state_at(client,pos)!=raw_state or inventory_counts(client.status()).get(plan['raw'],0)!=before-1:
                raise RuntimeError('Log placement/axis was not confirmed; no repeated placement')
            fresh=client.request('projection_audit')['projection_audit']
            _scoped_audit(client.status(),fresh,selection,world,server,dimension)
            strip_row=next((other for other in fresh['mismatches'] if other['pos']==pos
                            and other['expected']==row['expected'] and other['actual']==raw_state),None)
            if strip_row is None or not log_target(strip_row) or not log_target(strip_row)['strip']:
                raise RuntimeError('Placed raw log was not confirmed in the fresh projection audit')
        else:
            raw_state=row['actual'];strip_row=row;placement_audit=[None]
        client.checked('select_item',item=axe['item'],slot=axe['slot'])
        strip_audit=[None]
        def still_raw():strip_audit[0]=_exact_target(client,strip_row,log_target(strip_row),selection,world,server,dimension)
        try:use_with_margin(client,pos,raw_state,axe['item'],('up','south','north','east','west','down'),still_raw)
        except ApproachUnavailable:deferred.add(tuple(pos));continue
        post_scan=cell_at(client,pos)
        if post_scan['state']!=row['expected']:raise RuntimeError('Stripping not confirmed; do not replay axe use')
        completed.append({'pos':pos,'expected':row['expected'],'before_state':row['actual'],
                          'raw_state':raw_state,'post_scan_state':post_scan['state'],
                          'placed_raw':not plan['strip'],'placement_audit_at':placement_audit[0],
                          'strip_audit_at':strip_audit[0],'axe':axe['item'], 'placement_key':selection,
                          'server':server,'dimension':dimension,'world_session':world})
        with (client.out/'finished-beams.jsonl').open('a') as f:f.write(json.dumps(completed[-1],ensure_ascii=False)+'\n')
        print('BEAM_VERIFIED',len(completed),pos,flush=True)
    return {'completed':completed,'deferred':[list(p) for p in deferred]}
