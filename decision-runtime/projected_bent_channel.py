"""One source pour into the original bounded west-then-south overflow. No automatic retry."""
import time
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projected_source_column import AIR,SOURCE,envelope,coherent,geometry,admission_rejected_before_use,SourceAdmissionRejected,profile_rows,profile_payload

def path_for(low,high,*,profile=None):
    envelope(low,high,profile=profile)
    x,y,z=high[0],high[1]+1,low[2]
    turn=5 if profile_rows(profile)==4 else 3
    return [[x-min(i,turn),y,z+max(0,i-turn)]for i in range(8)]

def scan_bounds(low,high,profile):
    path=path_for(low,high,profile=profile)
    return [min(p[0]for p in path)-1,low[1]-1,low[2]-1],[high[0]+1,high[1]+2,max(p[2]for p in path)+1]


def roof_payload(profile,service,target):
    if service is None:return {}
    if profile_rows(profile)!=4 or service!=[target[0],target[1]+1,target[2]]:raise ValueError('Only the exact short action roof may be open')
    return {'bent_service_ceiling':service}


def flow_after(frame,world,low,high,plan,before,*,seed=False,middle_seed=False,profile=None):
    if seed and middle_seed:return False
    levels=[0,0,0,1,2,3,4,5]if seed else[0,0,1,2,3,4,5,6]if middle_seed else list(range(8))
    lo,hi=scan_bounds(low,high,profile)
    if not coherent(frame,world,lo,hi):return False
    rows={tuple(v['pos']):v['state']for v in frame['blocks']};path=path_for(low,high,profile=profile)
    if any(rows.get(tuple(p),AIR)!=f'Block{{minecraft:water}}[level={levels[i]}]'for i,p in enumerate(path)):return False
    if any(rows.get((x,y,low[2]))!=SOURCE for x in range(low[0],high[0]+1)for y in range(low[1],high[1]+1)):return False
    for pin in plan['column_boundary_pins']:
        actual=rows.get(tuple(pin['pos']),AIR);expected=pin['expected_state']
        if pin['pos'][1]<low[1]:actual=actual.replace('triggered=true','triggered=false');expected=expected.replace('triggered=true','triggered=false')
        if actual!=expected:return False
    allowed={tuple(p)for p in path}|{(x,y,low[2])for x in range(low[0],high[0]+1)for y in range(low[1],high[1]+1)}
    boundary=set()
    for i,p in enumerate(path):
        x,y,z=p
        boundary.add((x,y+1,z))
        if i>=3:boundary.add((x,y-1,z))
        for q in [(x+1,y,z),(x-1,y,z),(x,y,z+1),(x,y,z-1)]:
            if q not in allowed:boundary.add(q)
    if any(rows.get(p,AIR)!=before.get(p,AIR)for p in boundary):return False
    for p,state in rows.items():
        previous=before.get(p,AIR)
        if p not in allowed and state!=previous and any(word in state or word in previous for word in ('minecraft:water','minecraft:lava','waterlogged=true')):return False
    return True

def place(c,low,high,key,out,*,seed=False,profile=None,service_ceiling=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);book={'pending':None,'dispatch_started':False,'complete':False,'automatic_retry_allowed':False};write_json(out/'progress.json',book);s=c.status();lease=s.get('supervision_lease')or{}
    if s.get('projected_bent_channel_protocol')!=1 or s.get('health')!=20 or s.get('air_supply',0)<285 or s.get('screen')or s.get('manual_movement')or s.get('guard_busy')or not s.get('guard_armed')or lease.get('job_session')!=c.task:
        raise RuntimeError('Current healthy guarded overflow owner and protocol required')
    if seed and s.get('projected_bent_channel_seed_protocol')!=1:raise RuntimeError('Native staged overflow protocol required')
    if profile_rows(profile)==4 and s.get('projected_short_source_profile_protocol')!=1:raise RuntimeError('Native short source profile required')
    model=c.request('projection_model')['projection_model'];a,b=envelope(low,high,profile=profile)
    plan=geometry(model,c.checked('scan',min=a,max=b,details=True,include_predictions=True),low,high,c.world,completed_overflow=seed,profile=profile)
    lo,hi=scan_bounds(low,high,profile)
    frame=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True)
    if not coherent(frame,c.world,lo,hi)or model.get('placement_key')!=key:raise RuntimeError('Coherent current overflow required')
    before={tuple(v['pos']):v['state']for v in frame['blocks']};path=path_for(low,high,profile=profile);target=path[2]if seed else path[0]
    if seed:
        if before.get(tuple(path[0]))!=SOURCE or before.get(tuple(path[1]))!='Block{minecraft:water}[level=1]'or before.get(tuple(target),AIR)!=AIR:raise RuntimeError('Original source and first flow plus dry third cell required')
    elif any(before.get(tuple(p),AIR)!=AIR for p in path):raise RuntimeError('Only an entirely dry original overflow can be poured')
    c.checked('select_item',item='minecraft:water_bucket');s=c.status();stock=inventory_counts(s)
    if s.get('hand',{}).get('item')!='minecraft:water_bucket'or s['hand'].get('count')!=1:raise RuntimeError('Singleton water bucket required')
    support=[target[0],target[1],target[2]-1]if seed else[target[0]+1,target[1],target[2]]
    extra={**profile_payload(profile),**roof_payload(profile,service_ceiling,target)}
    book.update(pending='one_bent_overflow_use',dispatch_started=True);write_json(out/'progress.json',book)
    try:
        reply=c.request('bucket_place',pos=target,expected_state=AIR,expected_hand='minecraft:water_bucket',support=support,face='south'if seed else'west',expected_support_state=before.get(tuple(support)),projected_bent_channel=True,projected_bent_channel_seed=seed,placement_key=key,source_column_bounds=plan['source_column_bounds'],column_boundary_pins=plan['column_boundary_pins'],**extra)
    finally:
        book['request_id']=c.last;write_json(out/'progress.json',book)
    write_json(out/'native-reply.json',reply)
    if admission_rejected_before_use(reply,c.last,c.world):
        book.update(pending=None,rejected_before_use=True);write_json(out/'progress.json',book);raise SourceAdmissionRejected(reply.get('detail','Overflow admission rejected before input'))
    ack=reply.get('bucket_water')or{}
    if not(reply.get('id')==c.last and reply.get('world_session')==c.world and reply.get('phase')=='done'and ack.get('request_id')==c.last and ack.get('world_session')==c.world and ack.get('pos')==target and (profile in (None,'nine_rows')or profile=='four_rows'and ack.get('source_column_profile')==profile)and ack.get('projected_bent_channel')is True and ack.get('projected_bent_channel_seed')is seed and ack.get('operation')=='bucket_place'and ack.get('use_count')==1 and ack.get('confirmed')is True and ack.get('unknown_outcome')is False and ack.get('server_block_confirmed')is True and ack.get('server_inventory_confirmed')is True):raise RuntimeError('Overflow use unresolved; retain original receipt and never replay')
    book.update(pending=None,source_confirmed=True);write_json(out/'progress.json',book);stamps=[];end=time.monotonic()+15
    while len(stamps)<3:
        frame=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True);write_json(out/'latest-flow-frame.json',frame);state=c.status();counts=inventory_counts(state)
        if state.get('world_session')!=c.world or state.get('screen')or state.get('manual_movement'):raise RuntimeError('Control changed after confirmed pour; no replay')
        if flow_after(frame,c.world,low,high,plan,before,seed=seed,profile=profile)and counts.get('minecraft:water_bucket',0)==stock.get('minecraft:water_bucket',0)-1 and counts.get('minecraft:bucket',0)==stock.get('minecraft:bucket',0)+1:
            stamp=frame.get('time')
            if not stamps or stamp>stamps[-1]:stamps.append(stamp);write_json(out/f'flow-frame-{len(stamps)}.json',frame)
        else:stamps=[]
        if time.monotonic()>end:raise RuntimeError('Pour confirmed but full downstream flow not verified; no replay')
        time.sleep(.3)
    book.update(complete=True,temporary_seed=seed,flow_levels=[0,0,0,1,2,3,4,5]if seed else list(range(8)),source_cells_preserved=len(plan['source_cells']),frames=stamps);write_json(out/'progress.json',book);return book


def remove_seed(c,low,high,key,out,*,index=2,profile=None,service_ceiling=None):
    """Collect index2 then the regenerated index1; never the original index0 source."""
    if index not in (1,2):raise ValueError("Only the staged or regenerated source can be collected")
    out=Path(out);out.mkdir(parents=True,exist_ok=False);book={'pending':None,'dispatch_started':False,'complete':False,'automatic_retry_allowed':False};write_json(out/'progress.json',book);s=c.status();lease=s.get('supervision_lease')or{}
    if s.get('projected_bent_channel_seed_protocol')!=1 or s.get('health')!=20 or s.get('screen')or s.get('manual_movement')or s.get('guard_busy')or lease.get('job_session')!=c.task:raise RuntimeError('Current healthy seed owner required')
    if profile_rows(profile)==4 and s.get('projected_short_source_profile_protocol')!=1:raise RuntimeError('Native short source profile required')
    model=c.request('projection_model')['projection_model'];a,b=envelope(low,high,profile=profile);plan=geometry(model,c.checked('scan',min=a,max=b,details=True,include_predictions=True),low,high,c.world,completed_overflow=True,profile=profile)
    lo,hi=scan_bounds(low,high,profile)
    frame=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True);before={tuple(v['pos']):v['state']for v in frame['blocks']}
    if model.get('placement_key')!=key or not flow_after(frame,c.world,low,high,plan,before,seed=index==2,middle_seed=index==1,profile=profile):raise RuntimeError('Complete staged gradient required before collecting temporary source')
    bucket=next((v for v in s.get('inventory',[])if v.get('slot',99)<36 and v.get('item')=='minecraft:bucket'and v.get('count')==1),None)
    if not bucket:raise RuntimeError('Singleton empty bucket required')
    c.checked('select_item',item='minecraft:bucket',slot=bucket['slot']);stock=inventory_counts(c.status());target=path_for(low,high,profile=profile)[index]
    if profile_rows(profile)==4 and s.get('projected_bent_collection_protocol')!=1:raise RuntimeError('Native staged collection protocol required')
    extra=dict(projected_bent_channel_collect_index=index,placement_key=key,source_column_bounds=plan['source_column_bounds'],column_boundary_pins=plan['column_boundary_pins'],**profile_payload(profile),**roof_payload(profile,service_ceiling,target))if profile_rows(profile)==4 else{}
    book.update(pending='one_seed_collection',dispatch_started=True);write_json(out/'progress.json',book)
    try:reply=c.request('bucket_fill',pos=target,expected_state=SOURCE,expected_hand='minecraft:bucket',**extra)
    finally:book['request_id']=c.last;write_json(out/'progress.json',book)
    write_json(out/'native-reply.json',reply)
    if admission_rejected_before_use(reply,c.last,c.world):
        book.update(pending=None,rejected_before_use=True);write_json(out/'progress.json',book);raise SourceAdmissionRejected(reply.get('detail','Seed collection rejected before input'))
    ack=reply.get('bucket_water')or{}
    if not(reply.get('id')==c.last and reply.get('world_session')==c.world and reply.get('phase')=='done'and ack.get('request_id')==c.last and ack.get('world_session')==c.world and ack.get('pos')==target and (profile_rows(profile)!=4 or ack.get('source_column_profile')==profile and ack.get('projected_bent_channel_collect_index')==index)and ack.get('operation')=='bucket_fill'and ack.get('use_count')==1 and ack.get('confirmed')is True and ack.get('unknown_outcome')is False and ack.get('server_block_confirmed')is True and ack.get('server_inventory_confirmed')is True):raise RuntimeError('Original seed collection unresolved; never replay')
    book.update(pending=None,fill_confirmed=True);write_json(out/'progress.json',book);stamps=[];end=time.monotonic()+15
    while len(stamps)<3:
        frame=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True);write_json(out/'latest-flow-frame.json',frame);state=c.status();counts=inventory_counts(state)
        if state.get('world_session')!=c.world or state.get('screen')or state.get('manual_movement'):raise RuntimeError('Control changed after seed collection')
        if flow_after(frame,c.world,low,high,plan,before,middle_seed=index==2,profile=profile)and counts.get('minecraft:bucket',0)==stock.get('minecraft:bucket',0)-1 and counts.get('minecraft:water_bucket',0)==stock.get('minecraft:water_bucket',0)+1:
            stamp=frame.get('time')
            if not stamps or stamp>stamps[-1]:stamps.append(stamp);write_json(out/f'restored-flow-frame-{len(stamps)}.json',frame)
        else:stamps=[]
        if time.monotonic()>end:raise RuntimeError('Temporary source collected but restored flow unverified; no replay')
        time.sleep(.3)
    book.update(complete=True,collected_index=index,flow_levels=[0,0,1,2,3,4,5,6]if index==2 else list(range(8)),source_cells_preserved=len(plan['source_cells']),frames=stamps);write_json(out/'progress.json',book);return book
