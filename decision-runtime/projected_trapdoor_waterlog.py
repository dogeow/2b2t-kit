"""Normal single bucket transfers between wrong waterlogged floors and contained original trapdoor rows."""
from pathlib import Path
import time
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projection_completion import block_state
from projected_source_column import coherent,AIR,admission_rejected_before_use,SourceAdmissionRejected

def _begin(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    book={'pending':None,'complete':False,'dispatch_started':False,'automatic_retry_allowed':False};write_json(out/'progress.json',book);return out,book

def _owner(c,key,model):
    s=c.status();lease=s.get('supervision_lease')or{}
    if s.get('health')!=20 or s.get('food',0)<16 or s.get('air_supply',0)<270 or s.get('guard_busy')or not s.get('guard_armed')or s.get('screen')or s.get('manual_movement')or lease.get('job_session')!=c.task or s.get('projection_selection',{}).get('key')!=key or model.get('placement_key')!=key:
        raise RuntimeError('Healthy current guarded model owner required')
    return s

def _goal(model,target):
    if not isinstance(target,list)or len(target)!=3 or any(type(v)is not int for v in target):raise ValueError('Integer target required')
    state=next((v['state']for v in model['expected']if v['pos']==target),None)
    if state is None:raise RuntimeError('Original target absent from cached immutable model')
    return state

def row_bounds(model,target):
    goal=_goal(model,target);block,props=block_state(goal)
    if block!='minecraft:spruce_trapdoor'or props.get('half')!='bottom'or props.get('open')!='false'or props.get('powered')!='false'or props.get('waterlogged')!='true'or props.get('facing')not in('north','south'):
        raise RuntimeError('Original closed bottom source trapdoor required')
    row=sorted(v['pos'][0]for v in model['expected']if v['pos'][1:]==target[1:]and v['state']==goal)
    if len(row)!=29 or len(set(row))!=29 or row[-1]-row[0]!=28:raise RuntimeError('Exactly29 contiguous original row cells required')
    return {'min':[row[0],target[1],target[2]],'max':[row[-1],target[1],target[2]]}

def receipt(reply,request,world,target,op,flag,expected):
    a=reply.get('bucket_water')or{}
    return (reply.get('id')==request and reply.get('world_session')==world and reply.get('phase')=='done'
        and a.get('request_id')==request and a.get('world_session')==world and a.get('pos')==target and a.get('operation')==op
        and a.get(flag)is True and a.get('confirmed')is True and a.get('unknown_outcome')is False and a.get('use_count')==1
        and a.get('server_block_confirmed')is True and a.get('server_inventory_confirmed')is True and a.get('server_observed_state')==expected)

def _request(c,out,book,target,op,flag,expected,**params):
    book.update(pending='one_normal_bucket_use',dispatch_started=True,target=target,operation=op);write_json(out/'progress.json',book)
    try:r=c.request(op,**params)
    finally:book['request_id']=c.last;book['world_session']=c.world;write_json(out/'progress.json',book)
    write_json(out/'native-reply.json',r)
    if admission_rejected_before_use(r,c.last,c.world):
        book.update(pending=None,rejected_before_use=True);write_json(out/'progress.json',book);raise SourceAdmissionRejected(r.get('detail','Native admission rejected before input'))
    if not receipt(r,c.last,c.world,target,op,flag,expected):raise RuntimeError('Original bucket use unresolved; retain identity and never replay')
    book.update(pending=None,native_confirmed=True);write_json(out/'progress.json',book)
    return r

def _observe(c,out,book,target,expected,stock,fill,lo,hi,row=None,before=None):
    end=time.monotonic()+12;stamps=[]
    while len(stamps)<3:
        r=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True);write_json(out/'latest-frame.json',r);s=c.status();counts=inventory_counts(s)
        if s.get('world_session')!=c.world or s.get('screen')or s.get('manual_movement'):raise RuntimeError('Control changed after confirmed transfer; no replay')
        rows={tuple(v['pos']):v['state']for v in r.get('blocks',[])}
        good=(coherent(r,c.world,lo,hi)and rows.get(tuple(target),AIR)==expected
            and counts.get('minecraft:bucket',0)==stock.get('minecraft:bucket',0)+(-1 if fill else 1)
            and counts.get('minecraft:water_bucket',0)==stock.get('minecraft:water_bucket',0)+(1 if fill else-1))
        if good and row is not None:
            for p,state in rows.items():
                old=before.get(p,AIR)
                in_row=row['min'][0]<=p[0]<=row['max'][0]and p[1:]==tuple(row['min'][1:])
                if in_row:
                    if state.replace('waterlogged=true','waterlogged=false')!=expected.replace('waterlogged=true','waterlogged=false')or'waterlogged=true'in old and'waterlogged=true'not in state:good=False
                elif state!=old and any(token in state or token in old for token in ('minecraft:water','minecraft:lava','waterlogged=true')):good=False
        if good:
            stamp=r['time']
            if not stamps or stamp>stamps[-1]:stamps.append(stamp);write_json(out/('verified-frame-'+str(len(stamps))+'.json'),r)
        else:stamps=[]
        if time.monotonic()>end:
            book.update(postcheck_failed=True);write_json(out/'progress.json',book);raise RuntimeError('Transfer confirmed but requested stable water state not proven; no repeated use')
        time.sleep(.2)
    book.update(complete=True,observations=stamps);write_json(out/'progress.json',book);return book

def waterlog(c,target,key,model,out):
    out,book=_begin(out);s=_owner(c,key,model)
    if s.get('projected_trapdoor_waterlog_protocol')!=1:raise RuntimeError('Native contained-row waterlogging protocol required')
    row=row_bounds(model,target);wet=_goal(model,target);dry=wet.replace('waterlogged=true','waterlogged=false');direction=1 if block_state(wet)[1]['facing']=='south'else-1
    lo=[target[0]-1,target[1]-1,min(target[2]-direction,target[2]+2*direction)];hi=[target[0]+1,target[1]+1,max(target[2]-direction,target[2]+2*direction)]
    r=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True);before={tuple(v['pos']):v['state']for v in r['blocks']}
    if not coherent(r,c.world,lo,hi)or before.get(tuple(target),AIR)!=dry:raise RuntimeError('Fresh unchanged dry original trapdoor required; existing sources are skipped')
    c.checked('select_item',item='minecraft:water_bucket');s=c.status();stock=inventory_counts(s)
    if s.get('hand',{}).get('item')!='minecraft:water_bucket'or s['hand'].get('count')!=1:raise RuntimeError('Singleton full water bucket required')
    write_json(out/'before.json',r)
    _request(c,out,book,target,'bucket_place','projected_trapdoor_waterlog',wet,pos=target,expected_state=dry,expected_hand='minecraft:water_bucket',support=target,face='down',expected_support_state=dry,projected_trapdoor_waterlog=True,expected_wet_state=wet,placement_key=key,trapdoor_row_bounds=row)
    return _observe(c,out,book,target,wet,stock,False,lo,hi,row,before)

def drain(c,target,key,model,out):
    out,book=_begin(out);s=_owner(c,key,model)
    if s.get('projected_waterlog_drain_protocol')!=1:raise RuntimeError('Native original waterlog drain protocol required')
    dry=_goal(model,target);block,props=block_state(dry)
    if block not in('minecraft:cobblestone_slab','minecraft:spruce_trapdoor')or props.get('waterlogged')!='false'or props.get('type')=='double':raise RuntimeError('Original dry single slab or trapdoor required')
    wet=dry.replace('waterlogged=false','waterlogged=true');r=c.checked('scan',min=target,max=target,details=True,include_predictions=True)
    if not coherent(r,c.world,target,target)or len(r['blocks'])!=1 or r['blocks'][0]['state']!=wet:raise RuntimeError('Only the wrong water bit may be removed; no shape or material correction')
    bucket=next((v for v in s.get('inventory',[])if v.get('slot',99)<36 and v.get('item')=='minecraft:bucket'and v.get('count')==1),None)
    if bucket is None:raise RuntimeError('Prepare a singleton empty bucket before draining')
    c.checked('select_item',item='minecraft:bucket',slot=bucket['slot']);stock=inventory_counts(c.status());write_json(out/'before.json',r)
    _request(c,out,book,target,'bucket_fill','projected_waterlog_drain',dry,pos=target,expected_state=wet,expected_hand='minecraft:bucket',projected_waterlog_drain=True,expected_dry_state=dry,placement_key=key)
    return _observe(c,out,book,target,dry,stock,True,target,target)
