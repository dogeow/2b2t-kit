"""Finish carried full-cube gaps with the existing single-use Meteor AirPlace API."""
import math,time
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from material_jobs.acquisition import _scan,_safe,_travel
from material_jobs.local_air_path import move
from material_jobs.navigation import settled_state,lift_for_travel
from projection_completion import block_state
from projection_flat_plan import full_block


def candidates(audit,state,limit,*,allow_volume=False):
    if type(allow_volume)is not bool:raise ValueError("Volume air finish must be explicitly boolean")
    if type(limit)is not int or not 0<=limit<=256:raise ValueError('Air finish cap must be0..256')
    selected=state.get('projection_selection')or{};low=selected.get('min');high=selected.get('max')
    if (state.get('projection_air_seed_axis_protocol')!=1 or audit.get('placement_key')!=selected.get('key')
            or not isinstance(low,list)or not isinstance(high,list)or len(low)!=3 or len(high)!=3 or(not allow_volume and low[1]!=high[1])):return []
    held=inventory_counts(state);result=[];seen=set()
    for row in audit.get('mismatches',[]):
        pos=row.get('pos');expected=row.get('expected')
        if (not isinstance(pos,list)or len(pos)!=3 or any(type(n)is not int for n in pos)
                or tuple(pos)in seen or not all(a<=v<=b for a,v,b in zip(low,pos,high))
                or row.get('kind')!='missing'or row.get('actual')!='Block{minecraft:air}'
                or row.get('fluid')is not False or row.get('block_entity')is not False):continue
        try:item,props=block_state(expected)
        except (ValueError,TypeError):continue
        if props or not(full_block(expected,item)or allow_volume and item=='minecraft:glass')or held.get(item,0)<1:continue
        if len(result)>=limit:break
        result.append(row);seen.add(tuple(pos));held[item]-=1
    return result


def run_one(c,row,out,checkpoint,*,allow_volume=False):
    """One normal interaction, exact server ACK and two independent stock/cell reads."""
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    initial=checkpoint();key=initial['projection_selection']['key']
    if candidates({'placement_key':key,'mismatches':[row]},initial,1,allow_volume=allow_volume)!=[row]:
        raise RuntimeError('Exact carried full-block air target is unavailable')
    pos=row['pos'];item=block_state(row['expected'])[0];world=c.world
    def state():
        checkpoint();q=c.status();_safe(q)
        if q.get('world_session')!=world or(q.get('projection_selection')or{}).get('key')!=key:
            raise RuntimeError('Projection changed during air finish')
        if(q.get('build_job')or{}).get('active')or(q.get('professional_printer')or{}).get('owned'):
            raise RuntimeError('Ordinary printer still owns placement; do not overlap AirPlace')
        return q
    pose=[pos[0]+.5,pos[1]+2.2,pos[2]+.5]
    q=state()
    if math.hypot(q['pos'][0]-pose[0],q['pos'][2]-pose[2])>24 or abs(q['pos'][1]-pose[1])>64:
        lift_for_travel(c);q=state()
        _travel(c,[pose[0],max(pose[1],q['pos'][1]),pose[2]],state,[],keep_cruise=True)
    move(c,pose,out/'normal-access',foot_offset=.2,max_horizontal=24)
    settled_state(c,pose,.45);c.checked('select_item',item=item)
    before=inventory_counts(state()).get(item,0)
    if before<1 or(state().get('hand')or{}).get('item')!=item:
        raise RuntimeError('Exact air-finish material did not reach the held hand')
    for _ in range(2):
        if _scan(c,pos,pos,state)or inventory_counts(state()).get(item,0)!=before:
            raise RuntimeError('Air target or carried material changed before interaction')
        time.sleep(.15)
    book={'world_session':world,'placement_key':key,'target':pos,'item':item,'inventory_before':before,
          'pending':'projection_air_seed','complete':False}
    write_json(out/'progress.json',book)
    try:reply=c.request('projection_air_seed',placement_key=key,target=pos,expected_item=item,expected_state=row['expected'])
    finally:book['request_id']=c.last;write_json(out/'progress.json',book)
    write_json(out/'native-air-seed.json',reply);ack=reply.get('projection_air_seed')or{}
    if (reply.get('id')!=c.last or reply.get('phase')!='done'or reply.get('world_session')!=world
            or ack.get('request_id')!=c.last or ack.get('world_session')!=world or ack.get('placement_key')!=key
            or ack.get('target')!=pos or ack.get('item')!=item or ack.get('server_confirmed')is not True
            or ack.get('use_count')!=1 or ack.get('projection_matches')is not True or ack.get('requires_stripping')is not False
            or ack.get('expected_state')!=row['expected']or ack.get('projected_state')!=row['expected']
            or ack.get('inventory_before')!=before or ack.get('inventory_after')!=before-1
            or ack.get('confirmation_scope')!='matched_server_block_update_after_native_send'
            or ack.get('module_settings_changed')is not False or ack.get('automatic_retry_allowed')is not False):
        raise RuntimeError('Original air placement unconfirmed; retain its journal and never replay')
    stamps=[];until=time.monotonic()+5
    while len(stamps)<2:
        rows=_scan(c,pos,pos,state);q=state()
        good=(len(rows)==1 and rows[0]['pos']==pos and rows[0]['state']==row['expected']
                and inventory_counts(q).get(item,0)==before-1)
        if good and q['time']not in stamps:stamps.append(q['time'])
        elif not good:stamps=[]
        if time.monotonic()>=until:raise RuntimeError('Air placement physical/stock confirmation unsettled; no replay')
        time.sleep(.15)
    book.update(pending=None,complete=True,inventory_after=before-1,server_confirmed=True,physical_observations=stamps)
    write_json(out/'progress.json',book);return book


def finish_carried(c,audit,out,checkpoint,limit=8):
    completed=[]
    for index,row in enumerate(candidates(audit,checkpoint(),limit)):
        completed.append(run_one(c,row,Path(out)/('cell-%03d'%index),checkpoint))
    return completed
