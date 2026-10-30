"""One native, projection-locked observer placement, with independent settled state and inventory proof."""
from pathlib import Path
import time
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projected_source_column import coherent,AIR
from projection_completion import block_state

def place(c,target,support,face,key,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);s=c.status();lease=s.get('supervision_lease')or{}
    if s.get('projected_observer_place_protocol')!=1 or s.get('health')!=20 or s.get('guard_busy')or not s.get('guard_armed')or s.get('screen')or s.get('manual_movement')or lease.get('job_session')!=c.task:
        raise RuntimeError('Native oriented observer protocol and healthy guarded owner required')
    if any(not isinstance(p,list)or len(p)!=3 or any(type(v)is not int for v in p)for p in [target,support]):raise ValueError('Integer target/support required')
    directions={'east':[1,0,0],'west':[-1,0,0],'up':[0,1,0],'down':[0,-1,0],'north':[0,0,-1],'south':[0,0,1]}
    if face not in directions or [support[i]+directions[face][i]for i in range(3)]!=target:raise ValueError('Adjacent normal support face required')
    model=c.request('projection_model')['projection_model'];goal=next((r['state']for r in model['expected']if r['pos']==target),None)
    if model.get('placement_key')!=key or goal is None or block_state(goal)[0]!='minecraft:observer':raise RuntimeError('Original locked observer goal required')
    wanted=block_state(goal)[1]['facing'];lo=[min(target[i],support[i])for i in range(3)];hi=[max(target[i],support[i])for i in range(3)];frame=c.checked('scan',min=lo,max=hi,details=True,include_predictions=True)
    if not coherent(frame,c.world,lo,hi):raise RuntimeError('Coherent current empty cell and support required')
    rows={tuple(v['pos']):v['state']for v in frame['blocks']}
    if rows.get(tuple(target),AIR)!=AIR:raise RuntimeError('Existing observer or obstruction must be observed, never placed over')
    expected_support=rows.get(tuple(support))
    if not expected_support:raise RuntimeError('Real visible support required')
    c.checked('select_item',item='minecraft:observer');before=inventory_counts(c.status()).get('minecraft:observer',0)
    if before<1:raise RuntimeError('No carried observer')
    book={'pending':'one_normal_observer_use','complete':False,'world_session':c.world,'target':target,'facing':wanted,'automatic_retry_allowed':False};write_json(out/'progress.json',book)
    try:reply=c.request('interact',pos=support,face=face,expected_state=expected_support,expected_hand='minecraft:observer',projected_observer_place=True,place_pos=target,placement_key=key)
    finally:book['request_id']=c.last;write_json(out/'progress.json',book)
    write_json(out/'native-reply.json',reply)
    if reply.get('id')!=c.last or reply.get('world_session')!=c.world or reply.get('phase')!='done':raise RuntimeError('Original observer use unresolved; preserve identity without replay')
    end=time.monotonic()+12;frames=[]
    while len(frames)<3:
        frame=c.checked('scan',min=target,max=target,details=True,include_predictions=True);write_json(out/'latest-frame.json',frame);s=c.status()
        if s.get('world_session')!=c.world or s.get('screen')or s.get('manual_movement'):raise RuntimeError('Control changed after the original use; no replay')
        rows=frame.get('blocks',[]);actual=rows[0]['state']if len(rows)==1 and rows[0]['pos']==target else AIR
        block,props=block_state(actual)
        if coherent(frame,c.world,target,target)and block=='minecraft:observer'and props.get('facing')==wanted and inventory_counts(s).get('minecraft:observer',0)==before-1:
            stamp=frame['time']
            if not frames or stamp>frames[-1]:frames.append(stamp);write_json(out/('verified-frame-'+str(len(frames))+'.json'),frame)
        else:frames=[]
        if time.monotonic()>end:raise RuntimeError('Observer use dispatched but requested settled state not proven; no replay')
        time.sleep(.2)
    book.update(pending=None,complete=True,observations=frames,confirmation_scope='three_current_loaded_prediction_free_frames_and_exact_carried_observer_delta;powered_is_dynamic');write_json(out/'progress.json',book);return book
