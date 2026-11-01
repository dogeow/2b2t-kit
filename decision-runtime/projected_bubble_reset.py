"""Reset a closed group of accidental down-bubble sources through normal dirt plugs.

Uses the existing normal interaction and pinned wet-terrain mining interfaces.
No bucket input, native exception, original source removal, or request retry.
Caller owns safe approach/exit and restoration of its service port.
"""
from pathlib import Path
import time
import json
from material_plan import inventory_counts
from projected_source_column import AIR, coherent
from kit_runtime.journal import write_json

BUBBLE = 'Block{minecraft:bubble_column}[drag=true]'
MAGMA = 'Block{minecraft:magma_block}'
DIRT = 'Block{minecraft:dirt}'
SIDES = [('east',1,0,0),('west',-1,0,0),('up',0,1,0),
         ('down',0,-1,0),('north',0,0,-1),('south',0,0,1)]
FLOW = {f'Block{{minecraft:water}}[level={i}]' for i in range(1,8)}

def plan(targets, goals, rows, *, confirmed_plugs=()):
    if not isinstance(targets,list) or not 1 <= len(targets) <= 32:
        raise ValueError('One bounded source group required')
    if any(not isinstance(p,list) or len(p)!=3 or any(type(v)is not int for v in p) for p in targets):
        raise ValueError('Integer targets required')
    cells = {tuple(p) for p in targets}
    if len(cells)!=len(targets) or len({p[1] for p in cells})!=1:
        raise ValueError('Distinct targets in one source layer required')
    seen = set(); todo = [next(iter(cells))]
    while todo:
        p=todo.pop()
        if p in seen: continue
        seen.add(p)
        for _,dx,dy,dz in SIDES:
            q=(p[0]+dx,p[1]+dy,p[2]+dz)
            if dy==0 and q in cells and q not in seen: todo.append(q)
    if seen!=cells: raise ValueError('One connected source group required')
    known={tuple(p)for p in confirmed_plugs}
    if not known<=cells: raise ValueError('Confirmed plugs must belong to this exact group')
    for x,y,z in cells:
        p=(x,y,z); floor=(x,y-1,z)
        if goals.get(p) not in FLOW: raise ValueError('Original ordinary flow required; sources protected')
        if rows.get(p)!=(DIRT if p in known else BUBBLE): raise ValueError('Current bubble or journaled exact dirt plug required')
        if goals.get(floor)!=MAGMA or rows.get(floor)!=MAGMA:
            raise ValueError('Preserved original magma floor required')
        for _,dx,dy,dz in SIDES:
            q=(x+dx,y+dy,z+dz)
            if dy==0 and rows.get(q)==BUBBLE and q not in cells:
                raise ValueError('Adjacent accidental bubble omitted from group')
    return [list(p) for p in sorted(cells)]

def mined(reply):
    seq=reply.get('native_sequence')
    return (reply.get('phase')=='done' and reply.get('server_confirmed') is True
            and type(seq)is int and seq>0 and reply.get('server_ack_sequence')==seq)

def resume_plugs(previous, targets):
    if (previous.get('pending') is not None or previous.get('complete') is not False
        or previous.get('targets')!=targets or previous.get('removed_plugs')!=[]
        or previous.get('automatic_retry_allowed') is not False):
        raise ValueError('Only a known interrupted plug stage may resume; no pending input or mining replay')
    plugs=previous.get('plugs')
    if not isinstance(plugs,dict) or any(k!=','.join(map(str,p))or p not in targets for k,p in plugs.items()):
        raise ValueError('Exact confirmed plug journal required')
    return dict(plugs)

def reset_group(c, targets, key, model, out, approach, leave, *, resume_from=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    book={'complete':False,'pending':None,'plugs':{},'removed_plugs':[],
          'automatic_retry_allowed':False,'bucket_uses':0}
    def save(): write_json(out/'progress.json',book)
    save(); goals={tuple(v['pos']):v['state'] for v in model['expected']}
    if resume_from is not None:
        previous=Path(resume_from)
        old=json.loads(previous.read_text())
        book['plugs']=resume_plugs(old,targets)
        original_frame=json.loads((previous.parent/'group-before-0.json').read_text())
        if original_frame.get('world_session')!=c.world:
            raise ValueError('Plug-stage resume needs the original current world; reconcile separately after rejoin')
        book['resumed_from']=str(previous)
        save()
    lo=[min(p[i]for p in targets)-1 for i in range(3)]
    hi=[max(p[i]for p in targets)+1 for i in range(3)]
    def owner():
        s=c.status();lease=s.get('supervision_lease')or{}
        if (s.get('world_session')!=c.world or lease.get('job_session')!=c.task
            or s.get('projection_selection',{}).get('key')!=key or model.get('placement_key')!=key
            or s.get('health',0)<19 or s.get('food',0)<18 or s.get('air_supply',0)<270
            or s.get('projected_wet_terrain_mining_protocol')!=1 or s.get('guard_pve_only')is not True
            or not s.get('guard_armed') or s.get('guard_busy') or s.get('screen') or s.get('manual_movement')):
            raise RuntimeError('Current healthy guarded original-model owner required')
        return s
    def sample(low,high,label):
        owner()
        for attempt in range(4):
            r=c.checked('scan',min=low,max=high,details=True,include_predictions=True)
            write_json(out/f'{label}-{attempt}.json',r)
            if coherent(r,c.world,low,high): return r
        raise RuntimeError('No current coherent group frame')
    def states(r): return {tuple(v['pos']):v['state'] for v in r['blocks']}
    frame=sample(lo,hi,'group-before'); targets=plan(targets,goals,states(frame),confirmed_plugs=list(book['plugs'].values()))
    if inventory_counts(owner()).get('minecraft:dirt',0)<len(targets)-len(book['plugs']):
        raise RuntimeError('Enough dirt for the whole source group is required')
    book['targets']=targets;save()
    try:
        for i,p in enumerate(targets):
            if ','.join(map(str,p))in book['plugs']: continue
            approach(p,'plug-'+str(i)); floor=[p[0],p[1]-1,p[2]]
            r=sample(floor,p,'plug-before-'+str(i)); rows=states(r)
            if rows.get(tuple(p))!=BUBBLE or rows.get(tuple(floor))!=MAGMA:
                raise RuntimeError('Source or protected floor changed; no plug input')
            for e in r.get('scan_entities',[]):
                b=e.get('bounds')or{}
                if e.get('alive')and b.get('min')and all(b['max'][a]>p[a]and b['min'][a]<p[a]+1 for a in range(3)):
                    raise RuntimeError('Entity occupies source; no plug input')
            c.checked('select_item',item='minecraft:dirt');before=inventory_counts(owner())
            book['pending']={'kind':'one_temporary_source_plug','target':p};save()
            reply=c.request('interact',pos=floor,face='up',expected_state=MAGMA,expected_hand='minecraft:dirt')
            write_json(out/f'plug-{i}-native.json',reply)
            if reply.get('phase')!='done': raise RuntimeError('Original plug result unresolved; do not replay')
            frames=[];deadline=time.monotonic()+8
            while len(frames)<3:
                r=sample(p,p,'plug-after-'+str(i));counts=inventory_counts(owner())
                if states(r).get(tuple(p))==DIRT and counts.get('minecraft:dirt',0)==before.get('minecraft:dirt',0)-1:
                    if not frames or r['time']>frames[-1]: frames.append(r['time'])
                else: frames=[]
                if time.monotonic()>deadline: raise RuntimeError('Plug postcondition unresolved; no second input')
                time.sleep(.2)
            book['plugs'][','.join(map(str,p))]=p;book['pending']=None;save();leave(p,'plug-'+str(i))
        for i,p in enumerate(targets):
            approach(p,'remove-'+str(i));x,y,z=p
            r=sample([x-1,y-1,z-1],[x+1,y+1,z+1],'remove-before-'+str(i));rows=states(r)
            if rows.get(tuple(p))!=DIRT: raise RuntimeError('Known temporary plug changed')
            pins={name:rows.get((x+dx,y+dy,z+dz),AIR)for name,dx,dy,dz in SIDES}
            if any('bubble_column'in v for v in pins.values()): raise RuntimeError('Unplugged source still adjacent')
            c.checked('select_item',item='minecraft:diamond_shovel');s=owner()
            book['pending']={'kind':'remove_known_source_plug','target':p};save()
            reply=c.request('mine_block',pos=p,face='up',expected_state=DIRT,seconds=10,
                projected_wet_terrain=True,placement_key=key,expected_goal_state=goals[tuple(p)],
                expected_tool_slot=s['selected_slot'],expected_neighbors=pins)
            write_json(out/f'remove-{i}-native.json',reply)
            if not mined(reply): raise RuntimeError('Original mining receipt unresolved; no replay')
            r=sample(p,p,'removed-'+str(i));state=states(r).get(tuple(p),AIR)
            if state!=AIR and state not in FLOW and not state.startswith('Block{minecraft:water}[level='):
                raise RuntimeError('Removed plug did not become air or water')
            book['plugs'].pop(','.join(map(str,p)));book['removed_plugs'].append(p)
            book['pending']=None;save();leave(p,'remove-'+str(i))
        frames=[]
        for i in range(3):
            r=sample(lo,hi,'group-after-'+str(i));rows=states(r)
            if any(rows.get(tuple(p),AIR) not in FLOW|{AIR} for p in targets):
                raise RuntimeError('Extra source regrew or still wrong; group not complete')
            frames.append(r['time']);time.sleep(.3)
        book.update(complete=True,verification_frames=frames,full_water_network_still_unverified=True)
        save();return book
    except BaseException as error:
        book['error']=repr(error);save();raise
