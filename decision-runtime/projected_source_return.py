"""One water return to an unchanged completed source chamber; no retry or fake ACK."""
import time
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projected_source_column import SOURCE,envelope,coherent,geometry,profile_payload,profile_rows,admission_rejected_before_use,SourceAdmissionRejected

def return_receipt(reply,request,world,source,profile=None):
    a=reply.get('bucket_water')or{}
    return (reply.get('id')==request and reply.get('world_session')==world and reply.get('phase')=='done'
            and a.get('request_id')==request and a.get('world_session')==world and a.get('operation')=='bucket_place'
            and a.get('pos')==source and a.get('projected_source_return')is True
            and a.get('source_column_profile')==('four_rows'if profile_rows(profile)==4 else'nine_rows')
            and type(a.get('use_count'))is int and a['use_count']==1
            and type(a.get('source_return_block_probe_count'))is int and a['source_return_block_probe_count']==1
            and a.get('confirmed')is True and a.get('unknown_outcome')is False
            and a.get('server_block_confirmed')is True and a.get('server_inventory_confirmed')is True
            and a.get('server_observed_state')==SOURCE)

def return_water(c,low,high,source,support,face,key,out,*,profile=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);book={'pending':None,'dispatch_started':False,'complete':False,'automatic_retry_allowed':False};write_json(out/'progress.json',book)
    s=c.status();lease=s.get('supervision_lease')or{}
    if (s.get('projected_source_return_protocol')!=1 or s.get('health')!=20 or s.get('food',0)<16 or s.get('air_supply',0)<285
            or s.get('screen')or s.get('manual_movement')or s.get('guard_busy')or not s.get('guard_armed')or lease.get('job_session')!=c.task):raise RuntimeError('Healthy guarded source return owner and installed native protocol required')
    lo,hi=envelope(low,high,profile=profile)
    if source[0]!=low[0]+1 or source[2]!=low[2]or not low[1]<=source[1]<=high[1]:raise ValueError('Only a completed middle source can receive returned water')
    model=c.request('projection_model')['projection_model']
    for _ in range(4):
        frame=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True)
        if coherent(frame,c.world,lo,hi):break
    plan=geometry(model,frame,low,high,c.world,completed_overflow=True,profile=profile);before={tuple(v['pos']):v['state']for v in frame['blocks']}
    if model.get('placement_key')!=key or [before.get((x,high[1]+1,low[2]))for x in range(low[0],high[0]+1)]!=[f'Block{{minecraft:water}}[level={i}]'for i in [2,1,0]]:raise RuntimeError('Current locked completed overflow required')
    if before.get(tuple(support))not in ['Block{minecraft:glass}','Block{minecraft:cobblestone}']:raise RuntimeError('Original dry inert support required')
    c.checked('select_item',item='minecraft:water_bucket');s=c.status();stock=inventory_counts(s)
    if s.get('hand',{}).get('item')!='minecraft:water_bucket'or s['hand'].get('count')!=1:raise RuntimeError('Singleton filled water bucket required')
    book.update(pending='one_water_return_and_inert_probe',dispatch_started=True);write_json(out/'progress.json',book)
    try:reply=c.request('bucket_place',pos=source,expected_state=SOURCE,expected_hand='minecraft:water_bucket',support=support,face=face,expected_support_state=before[tuple(support)],projected_source_return=True,placement_key=key,source_column_bounds=plan['source_column_bounds'],column_boundary_pins=plan['column_boundary_pins'],**profile_payload(profile))
    finally:book['request_id']=c.last;write_json(out/'progress.json',book)
    write_json(out/'native-reply.json',reply)
    if admission_rejected_before_use(reply,c.last,c.world):
        book.update(pending=None,rejected_before_use=True);write_json(out/'progress.json',book);raise SourceAdmissionRejected(reply.get('detail','Source return rejected before input'))
    if not return_receipt(reply,c.last,c.world,source,profile):raise RuntimeError('Original water return unresolved; retain its identity and do not replay')
    book.update(pending=None,return_confirmed=True);write_json(out/'progress.json',book);stamps=[];end=time.monotonic()+12
    while len(stamps)<3:
        frame=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True);write_json(out/'latest-preserved-source-frame.json',frame);q=c.status();counts=inventory_counts(q);rows={tuple(v['pos']):v['state']for v in frame['blocks']}
        if q.get('world_session')!=c.world or q.get('screen')or q.get('manual_movement'):raise RuntimeError('Control changed after confirmed source return')
        same=coherent(frame,c.world,lo,hi)and all(rows.get(p)==state or p[1]<low[1]and rows.get(p,'').replace('triggered=true','triggered=false')==state.replace('triggered=true','triggered=false')for p,state in before.items())and set(rows)==set(before)
        if same and counts.get('minecraft:water_bucket',0)==stock.get('minecraft:water_bucket',0)-1 and counts.get('minecraft:bucket',0)==stock.get('minecraft:bucket',0)+1:
            if not stamps or frame['time']>stamps[-1]:stamps.append(frame['time']);write_json(out/f'preserved-source-frame-{len(stamps)}.json',frame)
        else:stamps=[]
        if time.monotonic()>end:raise RuntimeError('Return use confirmed but unchanged source envelope not proved; do not replay')
        time.sleep(.3)
    book.update(complete=True,frames=stamps,original_source_cells_preserved=len(plan['source_cells']));write_json(out/'progress.json',book);return book
