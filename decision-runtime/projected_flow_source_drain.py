"""Remove one extra plain source from an original flowing-water cell, without replay."""
import time
from pathlib import Path
from material_plan import inventory_counts
from projected_source_column import coherent,AIR,SourceAdmissionRejected,admission_rejected_before_use
from kit_runtime.journal import write_json
SOURCE='Block{minecraft:water}[level=0]'
def removed(state):
    return state==AIR or state.startswith('Block{minecraft:water}[level=')and state!=SOURCE

def confirmed(r,request,world,target):
    a=r.get('bucket_water')or{}
    return(r.get('id')==request and r.get('world_session')==world and r.get('phase')=='done'
        and a.get('request_id')==request and a.get('world_session')==world and a.get('pos')==target
        and a.get('operation')=='bucket_fill'and a.get('projected_flow_source_drain')is True
        and type(a.get('use_count'))is int and a['use_count']==1 and a.get('confirmed')is True
        and a.get('unknown_outcome')is False and a.get('server_block_confirmed')is True and a.get('server_inventory_confirmed')is True)

def drain(c,target,key,model,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);book={'complete':False,'pending':None,'dispatch_started':False,'automatic_retry_allowed':False};write_json(out/'progress.json',book)
    goal=next((v['state']for v in model['expected']if v['pos']==target),None)
    if goal not in [f'Block{{minecraft:water}}[level={i}]'for i in range(1,8)]:raise RuntimeError('Original ordinary flowing-water cell required')
    s=c.status();lease=s.get('supervision_lease')or{}
    if(s.get('projected_flow_source_drain_protocol')!=1 or s.get('health')!=20 or s.get('food',0)<18 or s.get('air_supply',0)<270
       or not s.get('guard_armed')or s.get('guard_busy')or s.get('screen')or s.get('manual_movement')
       or lease.get('job_session')!=c.task or s.get('projection_selection',{}).get('key')!=key or model.get('placement_key')!=key):raise RuntimeError('Healthy current original-flow owner required')
    frame=c.checked('scan',min=target,max=target,details=True,include_predictions=True);write_json(out/'before.json',frame)
    if not coherent(frame,c.world,target,target):raise RuntimeError('Current target frame required')
    actual=frame['blocks'][0]['state']if frame['blocks']else AIR
    if removed(actual):book.update(already_source_absent=True,source_removed=True);write_json(out/'progress.json',book);return book
    if actual!=SOURCE:raise RuntimeError('Only a plain extra source may be picked up')
    bucket=next((v for v in s['inventory']if v.get('slot',99)<36 and v.get('item')=='minecraft:bucket'and v.get('count')==1),None)
    if bucket is None:raise RuntimeError('Singleton empty bucket required')
    c.checked('select_item',item='minecraft:bucket',slot=bucket['slot']);before=inventory_counts(c.status());book.update(pending='one_extra_source_pickup',dispatch_started=True);write_json(out/'progress.json',book)
    try:r=c.request('bucket_fill',pos=target,expected_state=SOURCE,expected_hand='minecraft:bucket',projected_flow_source_drain=True,placement_key=key)
    finally:book['request_id']=c.last;write_json(out/'progress.json',book)
    write_json(out/'native-reply.json',r)
    if admission_rejected_before_use(r,c.last,c.world):book.update(pending=None,rejected_before_use=True);write_json(out/'progress.json',book);raise SourceAdmissionRejected(r.get('detail','Rejected before input'))
    if not confirmed(r,c.last,c.world,target):raise RuntimeError('Exact pickup unresolved; preserve original request')
    book.update(pending=None,native_confirmed=True);write_json(out/'progress.json',book);stamps=[];end=time.monotonic()+8
    while len(stamps)<3:
        frame=c.checked('scan',min=target,max=target,details=True,include_predictions=True);write_json(out/'latest-frame.json',frame);state=frame['blocks'][0]['state']if frame['blocks']else AIR;stock=inventory_counts(c.status())
        good=(coherent(frame,c.world,target,target)and removed(state)and stock.get('minecraft:bucket',0)==before.get('minecraft:bucket',0)-1 and stock.get('minecraft:water_bucket',0)==before.get('minecraft:water_bucket',0)+1)
        if good:
            if not stamps or frame['time']>stamps[-1]:stamps.append(frame['time'])
        else:stamps=[]
        if time.monotonic()>end:book['source_regrew_or_observation_changed']=True;write_json(out/'progress.json',book);raise RuntimeError('Pickup confirmed but source removal not stable; do not replay')
        time.sleep(.2)
    book.update(complete=True,source_removed=True,frames=stamps,full_channel_still_requires_observation=True);write_json(out/'progress.json',book);return book
