"""Collect a newly mined block by its live drop identity, never a guessed voxel."""
import math,time
from pathlib import Path
from material_plan import inventory_counts

def new_drop(state,item,old_ids,target):
    rows=[]
    for entity in state.get('entities',[]):
        position=entity.get('pos');stack=entity.get('stack')or{}
        if(entity.get('type')=='minecraft:item' and isinstance(entity.get('uuid'),str)and entity['uuid']
           and entity['uuid']not in old_ids and stack.get('item')==item
           and type(stack.get('count'))is int and stack['count']==1
           and isinstance(position,list) and len(position)==3
           and all(type(v)in(int,float)and math.isfinite(v)for v in position)
           and math.dist(position,[target[0]+.5,target[1]+.5,target[2]+.5])<=4):
            rows.append(entity)
    return rows[0]if len(rows)==1 else None

def pickup(builder,item,before,old_ids,target,*,timeout=3):
    deadline=time.monotonic()+timeout;drop=None
    while drop is None:
        state=builder.check();held=inventory_counts(state)[item]
        if held==before+1:return None
        if held!=before:raise RuntimeError('Block recovery stock changed; no collector input')
        drop=new_drop(state,item,old_ids,target)
        if drop is not None:break
        if time.monotonic()>=deadline:raise RuntimeError('No exact new single block drop; retain the mined result')
        time.sleep(.1)
    record=dict(item=item,before=before,drop=drop,pending=True,replayed=False)
    builder.book['pending_block_pickup']=record;builder.save()
    # One existing native collision-aware collector; never retry uncertain use.
    try:
        reply=builder.n('collect_item',expected_uuid=drop['uuid'],expected_item=item,expected_count=1,seconds=20)
    except RuntimeError as error:
        missing='Original village action did not complete: Drop is no longer loaded; observe again'
        settled='Original village action did not complete: Drop pickup not confirmed at the reached position'
        no_route='Original village action did not complete: No loaded collision-free route to this depot; no ceiling is broken'
        if str(error)not in (missing,settled,no_route):raise
        deadline=time.monotonic()+5
        while True:
            state=builder.check()
            if(inventory_counts(state)[item]==before+1
               and not any(e.get('uuid')==drop['uuid']for e in state.get('entities',[]))):break
            if str(error)==missing or time.monotonic()>=deadline:raise
            time.sleep(.1)
        # The drop can enter the player between the observation and dispatch.
        # Existing SDK proof admits only a snapshot after this exact refusal.
        original=state['last_request']
        observation=(builder.q.observe_missing_drop()if str(error)==missing
                     else builder.q.observe_refused_collection_path()if str(error)==no_route
                     else builder.q.observe_unconfirmed_pickup_terminal())
        reply=None;record.update(request_id=original,observation_id=observation['id'],
                                 completion=('natural_pickup_before_collector'if str(error)==missing
                                             else'late_natural_pickup_after_route_refusal'if str(error)==no_route
                                             else'late_natural_pickup_after_settled_collector'),collector_replayed=False)
    if reply is not None and reply.get('phase')!='done':raise RuntimeError('Original block collector did not complete')
    frames=[];deadline=time.monotonic()+5
    while len(frames)<2:
        state=builder.check()
        if(inventory_counts(state)[item]==before+1
           and not any(e.get('uuid')==drop['uuid']for e in state.get('entities',[]))):
            if not frames or state['time']>frames[-1]:frames.append(state['time'])
        else:frames=[]
        if time.monotonic()>=deadline:raise RuntimeError('Original block pickup lacks exact later stock and disappearance')
        time.sleep(.1)
    record.update(pending=False,confirmed_frames=frames)
    if reply is not None:record['request_id']=reply['id']
    else:builder.book['pending']=None
    builder.save();return record

def return_to_origin(builder,origin,identity):
    if math.dist(builder.check()['pos'],origin)<=.15:return None
    from queued_village_owner import QueuedVillageOwner
    from material_jobs.local_air_path import move
    # The grid planner admits at most .2 feet margin, even when the original
    # legal pose stood on a bed or farmland. Restore that exact pose only at
    # the final native collision-checked waypoint.
    margin=min(.1,origin[1]%1)
    return move(QueuedVillageOwner(builder),origin,Path(builder.out)/('block-recovery-return-'+identity),
                foot_offset=margin,exact_target=True)
