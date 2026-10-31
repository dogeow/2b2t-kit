"""One original planar water-source repair, exact native receipts and stable full-path observations."""
import time
from pathlib import Path
from material_plan import inventory_counts
from kit_runtime.journal import write_json
from projected_source_column import coherent,AIR,admission_rejected_before_use,SourceAdmissionRejected
SOURCE='Block{minecraft:water}[level=0]'
def layout(model,target):
    goals={tuple(v['pos']):v['state']for v in model['expected']};root=tuple(target)
    if len(target)!=3 or any(type(v)is not int for v in target)or goals.get(root)!=SOURCE:raise ValueError('Original integer source required')
    todo=[root];seen=set();cells={}
    while todo:
        p=todo.pop()
        if p in seen:continue
        seen.add(p);state=goals.get(p,AIR)
        if not state.startswith('Block{minecraft:water}[level='):continue
        level=int(state.split('level=')[1].split(']')[0])
        if level>7:raise ValueError('Falling water needs its dedicated layout')
        cells[p]=state
        if len(cells)>256:raise ValueError('Planar network too large')
        x,y,z=p
        todo.extend([(x+1,y,z),(x-1,y,z),(x,y,z+1),(x,y,z-1)])
    lo=[min(p[i]for p in cells)-(1 if i==1 else 2)for i in range(3)];hi=[max(p[i]for p in cells)+(1 if i==1 else 2)for i in range(3)]
    if not 3<=hi[0]-lo[0]+1<=33 or not 3<=hi[2]-lo[2]+1<=33 or (hi[0]-lo[0]+1)*3*(hi[2]-lo[2]+1)>4096:raise ValueError('Network bounds exceed native limits')
    return {'min':lo,'max':hi},cells

def receipt(reply,identity,world,target):
    a=reply.get('bucket_water')or{}
    return(reply.get('id')==identity and reply.get('world_session')==world and reply.get('phase')=='done'
        and a.get('request_id')==identity and a.get('world_session')==world and a.get('pos')==target
        and a.get('operation')=='bucket_place'and a.get('projected_model_water_source')is True
        and type(a.get('use_count'))is int and a['use_count']==1 and a.get('confirmed')is True
        and a.get('unknown_outcome')is False and a.get('server_block_confirmed')is True
        and a.get('server_inventory_confirmed')is True and a.get('server_observed_state')==SOURCE)

def place(c,target,support,face,key,model,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);book={'pending':None,'dispatch_started':False,'complete':False,'automatic_retry_allowed':False};write_json(out/'progress.json',book)
    bounds,cells=layout(model,target);s=c.status();lease=s.get('supervision_lease')or{}
    if(s.get('projected_model_water_source_protocol')!=1 or s.get('health')!=20 or s.get('food',0)<18
       or s.get('air_supply',0)<270 or s.get('screen')or s.get('manual_movement')or s.get('guard_busy')
       or not s.get('guard_armed')or not s.get('guard_pve_only')or lease.get('job_session')!=c.task
       or model.get('placement_key')!=key or s.get('projection_selection',{}).get('key')!=key):raise RuntimeError('Healthy current guarded original-network owner required')
    lo=[min(target[i],support[i])for i in range(3)];hi=[max(target[i],support[i])for i in range(3)]
    frame=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True);write_json(out/'before.json',frame);rows={tuple(v['pos']):v for v in frame.get('blocks',[])}
    if not coherent(frame,c.world,lo,hi):raise RuntimeError('Fresh source/support frame required')
    actual=rows.get(tuple(target),{}).get('state',AIR);anchor=rows.get(tuple(support),{})
    if actual==SOURCE:book.update(already_source_on_fresh_read=True,source_only_verified_by_read=True,full_flow_still_requires_observation=True);write_json(out/'progress.json',book);return book
    if actual!=AIR and not(actual.startswith('Block{minecraft:water}[level=')and actual!=SOURCE):raise RuntimeError('Original source cell is occupied')
    if anchor.get('solid')is not True or anchor.get('fluid')is True or anchor.get('block_entity')is True:raise RuntimeError('Dry inert full support required')
    c.checked('select_item',item='minecraft:water_bucket');s=c.status();before=inventory_counts(s)
    if s['hand']['item']!='minecraft:water_bucket'or s['hand']['count']!=1:raise RuntimeError('Singleton full bucket required')
    book.update(pending='one_original_source_use',dispatch_started=True,target=target,bounds=bounds);write_json(out/'progress.json',book)
    try:r=c.request('bucket_place',pos=target,expected_state=actual,expected_hand='minecraft:water_bucket',support=support,face=face,expected_support_state=anchor['state'],projected_model_water_source=True,placement_key=key,model_water_bounds=bounds)
    finally:book['request_id']=c.last;write_json(out/'progress.json',book)
    write_json(out/'native-reply.json',r)
    if admission_rejected_before_use(r,c.last,c.world):book.update(pending=None,rejected_before_use=True);write_json(out/'progress.json',book);raise SourceAdmissionRejected(r.get('detail','Native source rejected before use'))
    if not receipt(r,c.last,c.world,target):raise RuntimeError('Original source use unresolved; retain and never replay')
    book.update(pending=None,source_confirmed=True);write_json(out/'progress.json',book)
    lo=[min(p[i]for p in cells)-(1 if i!=1 else 1)for i in range(3)];hi=[max(p[i]for p in cells)+1 for i in range(3)];stamps=[];deadline=time.monotonic()+18
    while len(stamps)<3:
        frame=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True);write_json(out/'latest-flow-frame.json',frame);s=c.status();counts=inventory_counts(s);rows={tuple(v['pos']):v['state']for v in frame.get('blocks',[])}
        good=(coherent(frame,c.world,lo,hi)and all(rows.get(p,AIR)==state for p,state in cells.items())
              and counts.get('minecraft:water_bucket',0)==before.get('minecraft:water_bucket',0)-1
              and counts.get('minecraft:bucket',0)==before.get('minecraft:bucket',0)+1)
        if good:
            if not stamps or frame['time']>stamps[-1]:stamps.append(frame['time']);write_json(out/f'verified-flow-{len(stamps)}.json',frame)
        else:stamps=[]
        if time.monotonic()>deadline:book['flow_not_yet_original']=True;write_json(out/'progress.json',book);raise RuntimeError('Use confirmed but original full flow not stable; no repeat')
        time.sleep(.25)
    book.update(complete=True,flow_frames=stamps,original_flow_cells=len(cells));write_json(out/'progress.json',book);return book
