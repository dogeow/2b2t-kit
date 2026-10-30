"""One sealed 3x1x9 source-chamber use, with native admission and independent observations.

No movement, refilling, overflow placement, retry or safety-lock acknowledgement is implicit.
"""
import re
import time
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts

AIR='Block{minecraft:air}'
SOURCE='Block{minecraft:water}[level=0]'
WATER=re.compile(r'Block\{minecraft:water\}\[level=([0-9]|1[0-5])\]')
DROPPER=re.compile(r'Block\{minecraft:dropper\}\[facing=up,triggered=(true|false)\]')


class SourceAdmissionRejected(RuntimeError):
    """This exact new request was refused before input; not a missing use receipt."""


def admission_rejected_before_use(reply,request,world):
    diagnostic=reply.get('last_bucket_admission_rejection')or{}
    ack=reply.get('bucket_water')or{}
    return (reply.get('id')==request and reply.get('world_session')==world and reply.get('phase')=='error'
            and diagnostic.get('request_id')==request and diagnostic.get('world_session')==world
            and type(diagnostic.get('protocol'))is int and diagnostic['protocol']>=2
            and diagnostic.get('input_sent')is False and diagnostic.get('material_owner_current')is True
            and diagnostic.get('bucket_task_active')is False and diagnostic.get('active_request_id')==''
            and diagnostic.get('active_command')=='' and diagnostic.get('navigation_active')is False
            and not(ack.get('request_id')==request and ack.get('use_count',0)>0))


def envelope(low,high):
    if (not isinstance(low,list)or not isinstance(high,list)or len(low)!=3 or len(high)!=3
            or any(type(x)is not int or abs(x)>=30000000 for x in low+high)
            or [high[i]-low[i]for i in range(3)]!=[2,8,0]):
        raise ValueError('Exact integer 3x1x9 chamber bounds required')
    return [low[0]-1,low[1]-1,low[2]-1],[high[0]+1,high[1]+1,high[2]+1]


def coherent(frame,world,low,high):
    count=(high[0]-low[0]+1)*(high[1]-low[1]+1)*(high[2]-low[2]+1)
    prediction=frame.get('scan_predictions')or{}
    return (frame.get('world_session')==world and frame.get('phase')=='done'
            and frame.get('scan_cells_read')==count and frame.get('scan_total_cells')==count
            and frame.get('scan_coherent')is True and not frame.get('unloaded_chunks')
            and prediction.get('complete')is True and prediction.get('pending_count')==0)


def geometry(model,frame,low,high,world):
    lo,hi=envelope(low,high)
    if not coherent(frame,world,lo,hi):raise RuntimeError('Coherent loaded envelope with no pending predictions required')
    goal={tuple(v['pos']):v['state']for v in model['expected']}
    actual={tuple(v['pos']):v for v in frame['blocks']}
    if len(actual)!=len(frame['blocks']):raise RuntimeError('Duplicate scan positions')
    cells=[[x,y,low[2]]for y in range(low[1],high[1]+1)for x in range(low[0],high[0]+1)]
    sources=[]
    for p in cells:
        state=actual.get(tuple(p),{}).get('state',AIR)
        if goal.get(tuple(p))!=SOURCE or state!=AIR and not WATER.fullmatch(state):
            raise RuntimeError('Chamber must contain only projected source cells and actual air/plain water')
        if state==SOURCE:sources.append(p)
    pins=[]
    for x in range(low[0],high[0]+1):
        p=(x,low[1]-1,low[2]);state=actual.get(p,{}).get('state','')
        if not DROPPER.fullmatch(state)or not DROPPER.fullmatch(goal.get(p,''))or actual[p].get('fluid')is not False:
            raise RuntimeError('All three original UP floor droppers must be installed before water')
        pins.append({'pos':list(p),'expected_state':state})
    for y in range(low[1],high[1]+1):
        positions=[(low[0]-1,y,low[2]),(high[0]+1,y,low[2])]
        positions +=[(x,y,z)for x in range(low[0],high[0]+1)for z in [low[2]-1,low[2]+1]]
        for p in positions:
            row=actual.get(p,{})
            if row.get('fluid')is not False or row.get('block_entity')is not False:
                raise RuntimeError('Every boundary needs an observed dry non-container seal')
            stair='Block{minecraft:cobblestone_stairs}[facing=south,half=bottom,shape=straight,waterlogged=false]'
            if row.get('solid')is not True and not(p[2]==low[2]-1 and row.get('state')==goal.get(p)==stair):
                raise RuntimeError('Non-full boundaries must exactly match their original geometry')
            pins.append({'pos':list(p),'expected_state':row['state']})
    for x in range(low[0],high[0]+1):
        p=(x,high[1]+1,low[2])
        if goal.get(p)!=f'Block{{minecraft:water}}[level={high[0]-x}]'or p in actual:
            raise RuntimeError('Separate top overflow must have its original model and remain dry')
    return {'source_column_bounds':{'min':low,'max':high},'column_boundary_pins':pins,
            'preserved_sources':sources,'source_cells':cells}


def source_receipt(reply,request,world,target):
    ack=reply.get('bucket_water')or{}
    return (reply.get('id')==request and reply.get('world_session')==world and reply.get('phase')=='done'
            and ack.get('request_id')==request and ack.get('world_session')==world and ack.get('pos')==target
            and ack.get('operation')=='bucket_place' and ack.get('projected_source_column')is True and ack.get('confirmed')is True
            and ack.get('unknown_outcome')is False and ack.get('use_count')==1
            and ack.get('server_block_confirmed')is True and ack.get('server_inventory_confirmed')is True
            and ack.get('server_observed_state')==SOURCE)


def observed_after(frame,world,lo,hi,plan,target,before):
    if not coherent(frame,world,lo,hi):return False
    rows={tuple(v['pos']):v['state']for v in frame['blocks']}
    if len(rows)!=len(frame['blocks']):return False
    for p in plan['source_cells']:
        state=rows.get(tuple(p),AIR)
        if state!=AIR and not WATER.fullmatch(state):return False
    if rows.get(tuple(target))!=SOURCE or any(rows.get(tuple(p))!=SOURCE for p in plan['preserved_sources']):return False
    for pin in plan['column_boundary_pins']:
        p=tuple(pin['pos']);old=pin['expected_state'];new=rows.get(p)
        if DROPPER.fullmatch(old or'')and DROPPER.fullmatch(new or''):continue
        if new!=old:return False
    # Any newly wet cell outside the chamber is an observed failure, never an excuse to pour again.
    cells={tuple(p)for p in plan['source_cells']}
    for p,state in rows.items():
        if p not in cells and (WATER.fullmatch(state)or state.startswith('Block{minecraft:lava}'))and before.get(p,AIR)==AIR:return False
    return True


def place(c,low,high,target,support,face,placement_key,out):
    lo,hi=envelope(low,high);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    state=c.status();lease=state.get('supervision_lease')or{}
    if (state.get('projected_source_column_protocol')!=1 or state.get('health')!=20
            or state.get('food',0)<16 or state.get('air_supply',0)<270
            or state.get('screen')or state.get('manual_movement')or state.get('guard_busy')
            or not state.get('guard_armed')or lease.get('kind')!='materials'or lease.get('job_session')!=c.task
            or state.get('projection_selection',{}).get('key')!=placement_key):
        raise RuntimeError('Installed source-column protocol and exact healthy guarded material owner required')
    model=c.request('projection_model')['projection_model']
    if model.get('placement_key')!=placement_key:raise RuntimeError('Projection changed')
    frame=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True)
    plan=geometry(model,frame,low,high,c.world);write_json(out/'geometry-before.json',{'model_hash':model['content_hash'],'scan':frame,'plan':plan})
    if target not in plan['source_cells']or target in plan['preserved_sources']:raise RuntimeError('Exact unfinished source target required; existing sources are preserved')
    offsets={'up':[0,1,0],'down':[0,-1,0],'west':[-1,0,0],'east':[1,0,0],'north':[0,0,-1],'south':[0,0,1]}
    if (face not in offsets or not isinstance(support,list)or len(support)!=3
            or any(type(x)is not int for x in support)or [support[i]+offsets[face][i]for i in range(3)]!=target):raise ValueError('Adjacent normal bucket support and face required')
    rows={tuple(v['pos']):v['state']for v in frame['blocks']};support_state=rows.get(tuple(support))
    if support_state is None:raise RuntimeError('Fresh support state required')
    c.checked('select_item',item='minecraft:water_bucket');state=c.status();stock=inventory_counts(state)
    if state.get('hand',{}).get('item')!='minecraft:water_bucket'or state.get('hand',{}).get('count')!=1:raise RuntimeError('Singleton water bucket required')
    book={'pending':'one_bucket_use','automatic_retry_allowed':False,'complete':False,'target':target,'world_session':c.world}
    write_json(out/'progress.json',book)
    try:
        reply=c.request('bucket_place',pos=target,expected_state=rows.get(tuple(target),AIR),expected_hand='minecraft:water_bucket',
                        support=support,face=face,expected_support_state=support_state,projected_source_column=True,
                        placement_key=placement_key,source_column_bounds=plan['source_column_bounds'],column_boundary_pins=plan['column_boundary_pins'])
    finally:
        book['request_id']=c.last;write_json(out/'progress.json',book)
    write_json(out/'native-reply.json',reply)
    if admission_rejected_before_use(reply,c.last,c.world):
        book.update(pending=None,rejected_before_use=True,admission_diagnostic=reply['last_bucket_admission_rejection'])
        write_json(out/'progress.json',book)
        raise SourceAdmissionRejected(reply.get('detail','Native admission refused before input'))
    if not source_receipt(reply,c.last,c.world,target):raise RuntimeError('Original water use unconfirmed; inspect it and never resend')
    book['pending']=None;book['source_confirmed']=True;write_json(out/'progress.json',book);stamps=[];deadline=time.monotonic()+10
    while len(stamps)<2:
        frame=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True);state=c.status();counts=inventory_counts(state)
        if state.get('world_session')!=c.world or state.get('manual_movement')or state.get('screen'):raise RuntimeError('Control changed after confirmed use; no replay')
        if (observed_after(frame,c.world,lo,hi,plan,target,rows)
                and counts.get('minecraft:water_bucket',0)==stock.get('minecraft:water_bucket',0)-1
                and counts.get('minecraft:bucket',0)==stock.get('minecraft:bucket',0)+1):
            stamp=frame.get('scan_ended_at',frame.get('time'))
            if type(stamp)is int and(not stamps or stamp>stamps[-1]):stamps.append(stamp);write_json(out/f'verified-frame-{len(stamps)}.json',frame)
        else:stamps=[]
        if time.monotonic()>deadline:raise RuntimeError('Source use confirmed but boundary/flow evidence incomplete; do not retry')
        time.sleep(.2)
    book.update(complete=True,observations=stamps);write_json(out/'progress.json',book);return book
