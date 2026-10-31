"""One bottom-up normal bucket use in an original seven-cell bubble lift. No retry."""
import time
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projected_source_column import AIR,SOURCE,coherent,admission_rejected_before_use,SourceAdmissionRejected
BUBBLE='Block{minecraft:bubble_column}[drag=false]'

def cells_for(low,high):
    if (not isinstance(low,list)or not isinstance(high,list)or len(low)!=3 or len(high)!=3
            or any(type(v)is not int or abs(v)>=30000000 for v in low+high)
            or high!=[low[0],low[1]+6,low[2]]):raise ValueError('Exact one-wide seven-cell bubble bounds required')
    cells=[[low[0],y,low[2]]for y in range(low[1],high[1]+1)]
    outlet=[[high[0]-min(i,6),high[1],high[2]-(1 if i==7 else 0)]for i in range(1,8)]
    return cells,outlet

def scan_bounds(low,high):
    cells_for(low,high)
    return [low[0]-7,low[1]-1,low[2]-2],[high[0]+1,high[1]+1,high[2]+1]

def geometry(model,frame,low,high,world):
    cells,outlet=cells_for(low,high);lo,hi=scan_bounds(low,high)
    if not coherent(frame,world,lo,hi):raise RuntimeError('Coherent bubble envelope without predictions required')
    goals={tuple(v['pos']):v['state']for v in model['expected']};rows={tuple(v['pos']):v for v in frame['blocks']}
    if len(rows)!=len(frame['blocks']):raise RuntimeError('Duplicate bubble scan positions')
    for p in cells:
        if goals.get(tuple(p))!=BUBBLE or rows.get(tuple(p),{}).get('state',AIR)not in (AIR,SOURCE,BUBBLE):raise RuntimeError('Only original upward bubbles and actual air/source/upward bubble states allowed')
    for i,p in enumerate(outlet,1):
        if goals.get(tuple(p))!=f'Block{{minecraft:water}}[level={i}]':raise RuntimeError('Exact original outlet required')
    allowed={tuple(p)for p in cells+outlet};boundaries=set()
    for x,y,z in allowed:
        for dx,dy,dz in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]:
            p=x+dx,y+dy,z+dz
            if p not in allowed:boundaries.add(p)
    cap=(high[0],high[1]+1,high[2]);pins=[]
    for p in sorted(boundaries):
        goal=goals.get(p,AIR);row=rows.get(p,{});actual=row.get('state',AIR)
        if row.get('block_entity')is True:raise RuntimeError('Bubble boundary containers are protected')
        if p==cap:
            if goal!='Block{minecraft:glass}'or actual!=AIR:raise RuntimeError('Only the exact original glass cap may be open')
        elif actual!=goal:raise RuntimeError('Bubble seal does not match the original model')
        pins.append({'pos':list(p),'expected_state':goal})
    if goals.get((low[0],low[1]-1,low[2]))!='Block{minecraft:soul_sand}':raise RuntimeError('Original soul sand required')
    return dict(bubble_bounds={'min':low,'max':high},bubble_boundary_pins=pins,bubble_service_cap=list(cap),bubble_cells=cells,outlet_cells=outlet)

def fill(c,low,high,target,key,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);book={'pending':None,'dispatch_started':False,'complete':False,'automatic_retry_allowed':False};write_json(out/'progress.json',book)
    s=c.status();lease=s.get('supervision_lease')or{}
    if (s.get('projected_bubble_column_protocol')!=1 or s.get('health')!=20 or s.get('air_supply',0)<285
            or s.get('screen')or s.get('manual_movement')or s.get('guard_busy')or not s.get('guard_armed')or lease.get('job_session')!=c.task):raise RuntimeError('Current healthy guarded bubble owner and native protocol required')
    model=c.request('projection_model')['projection_model'];lo,hi=scan_bounds(low,high);frame=None
    for _ in range(4):
        frame=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True)
        if coherent(frame,c.world,lo,hi):break
    plan=geometry(model,frame,low,high,c.world);before={tuple(v['pos']):v['state']for v in frame['blocks']}
    if model.get('placement_key')!=key or target not in plan['bubble_cells']:raise RuntimeError('Current locked original bubble target required')
    index=plan['bubble_cells'].index(target)
    if any(before.get(tuple(p),AIR)!=(BUBBLE if i<index else AIR)for i,p in enumerate(plan['bubble_cells']))or any(before.get(tuple(p),AIR)!=AIR for p in plan['outlet_cells']):raise RuntimeError('Only a new dry target above all completed bubbles and a dry outlet may be used')
    support=[target[0],target[1],target[2]-1]
    if before.get(tuple(support))!='Block{minecraft:glass}':raise RuntimeError('Exact original north glass support required')
    c.checked('select_item',item='minecraft:water_bucket');s=c.status();stock=inventory_counts(s)
    if s.get('hand',{}).get('item')!='minecraft:water_bucket'or s['hand'].get('count')!=1:raise RuntimeError('Singleton water bucket required')
    book.update(pending='one_upward_bubble_use',dispatch_started=True,target=target);write_json(out/'progress.json',book)
    try:
        reply=c.request('bucket_place',pos=target,expected_state=AIR,expected_hand='minecraft:water_bucket',support=support,face='south',expected_support_state='Block{minecraft:glass}',projected_bubble_column=True,placement_key=key,**{k:plan[k]for k in ['bubble_bounds','bubble_boundary_pins','bubble_service_cap']})
    finally:book['request_id']=c.last;write_json(out/'progress.json',book)
    write_json(out/'native-reply.json',reply)
    if admission_rejected_before_use(reply,c.last,c.world):
        book.update(pending=None,rejected_before_use=True);write_json(out/'progress.json',book);raise SourceAdmissionRejected(reply.get('detail','Bubble admission refused before input'))
    ack=reply.get('bucket_water')or{}
    if not(reply.get('id')==c.last and reply.get('world_session')==c.world and reply.get('phase')=='done'and ack.get('request_id')==c.last and ack.get('world_session')==c.world and ack.get('pos')==target and ack.get('projected_bubble_column')is True and ack.get('expected_bubble_state')==BUBBLE and ack.get('operation')=='bucket_place'and ack.get('use_count')==1 and ack.get('confirmed')is True and ack.get('unknown_outcome')is False and ack.get('server_block_confirmed')is True and ack.get('server_inventory_confirmed')is True):raise RuntimeError('Original bubble use unresolved; retain receipt and do not replay')
    book.update(pending=None,target_confirmed=True);write_json(out/'progress.json',book);stamps=[];end=time.monotonic()+15
    while len(stamps)<3:
        frame=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True);write_json(out/'latest-bubble-frame.json',frame);q=c.status();counts=inventory_counts(q)
        if q.get('world_session')!=c.world or q.get('screen')or q.get('manual_movement'):raise RuntimeError('Control changed after confirmed bubble use')
        rows={tuple(v['pos']):v['state']for v in frame['blocks']};good=coherent(frame,c.world,lo,hi)
        good&=all(rows.get(tuple(p),AIR)==(BUBBLE if i<=index else AIR)for i,p in enumerate(plan['bubble_cells']))
        good&=all(rows.get(tuple(p),AIR)==(f'Block{{minecraft:water}}[level={i}]'if index==6 else AIR)for i,p in enumerate(plan['outlet_cells'],1))
        good&=all(rows.get(tuple(pin['pos']),AIR)==(AIR if pin['pos']==plan['bubble_service_cap']else pin['expected_state'])for pin in plan['bubble_boundary_pins'])
        allowed={tuple(p)for p in plan['bubble_cells']+plan['outlet_cells']}
        good&=not any(p not in allowed and rows.get(p,AIR)!=before.get(p,AIR)and any(word in rows.get(p,AIR)or word in before.get(p,AIR)for word in ('minecraft:water','minecraft:lava','waterlogged=true','minecraft:bubble_column'))for p in set(before)|set(rows))
        good&=counts.get('minecraft:water_bucket',0)==stock.get('minecraft:water_bucket',0)-1 and counts.get('minecraft:bucket',0)==stock.get('minecraft:bucket',0)+1
        if good:
            stamp=frame['time']
            if not stamps or stamp>stamps[-1]:stamps.append(stamp);write_json(out/f'confirmed-frame-{len(stamps)}.json',frame)
        else:stamps=[]
        if time.monotonic()>end:raise RuntimeError('Bubble use confirmed but complete downstream proof missing; do not replay')
        time.sleep(.3)
    book.update(complete=True,completed_bubbles=index+1,frames=stamps);write_json(out/'progress.json',book);return book
