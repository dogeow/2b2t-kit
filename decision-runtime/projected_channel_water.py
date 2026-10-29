"""One native source use plus independent downstream observations; never retry a use."""
import time
from pathlib import Path

from kit_runtime.journal import write_json
from material_plan import inventory_counts


def flow_frame(reply, source, world):
    low=[source[0]-7,source[1],source[2]]
    if (reply.get('world_session')!=world or reply.get('phase')!='done'
            or reply.get('scan_cells_read')!=8 or reply.get('scan_total_cells')!=8
            or reply.get('scan_coherent')is not True or reply.get('unloaded_chunks')):
        return False
    rows=reply.get('blocks')
    if not isinstance(rows,list) or len(rows)!=8:return False
    seen=set()
    for row in rows:
        p=row.get('pos')
        if (not isinstance(p,list)or len(p)!=3 or any(type(n)is not int for n in p)
                or p[1:]!=source[1:]or not low[0]<=p[0]<=source[0]or tuple(p)in seen
                or row.get('state')!=f'Block{{minecraft:water}}[level={source[0]-p[0]}]'):
            return False
        seen.add(tuple(p))
    return True


def source_receipt(reply, request_id, world, source, *, service_ceiling=None):
    ack=reply.get('bucket_water')or{}
    return (reply.get('id')==request_id and reply.get('world_session')==world
            and reply.get('phase')=='done'and ack.get('request_id')==request_id
            and ack.get('world_session')==world and ack.get('pos')==source
            and ack.get('projected_water_channel')is True and ack.get('confirmed')is True
            and ack.get('unknown_outcome')is False and ack.get('use_count')==1
            and ack.get('server_block_confirmed')is True and ack.get('server_inventory_confirmed')is True
            and ack.get('server_observed_state')=='Block{minecraft:water}[level=0]'
            and ack.get('channel_direction')=='west'and ack.get('channel_length')==8
            and (service_ceiling is None or ack.get('channel_service_ceiling')==service_ceiling))


def place(c,source,placement_key,out,*,service_ceiling=None):
    if (not isinstance(source,list)or len(source)!=3 or any(type(n)is not int for n in source)
            or any(abs(n)>30000000 for n in source)or not isinstance(placement_key,str)or not placement_key):
        raise ValueError('Exact source coordinates and locked placement required')
    if service_ceiling is not None and (
            not isinstance(service_ceiling,list)or len(service_ceiling)!=3
            or any(type(n)is not int for n in service_ceiling)
            or service_ceiling not in ([source[0],source[1]+1,source[2]],[source[0]-1,source[1]+1,source[2]])):
        raise ValueError('Only the source or immediate west ceiling may be explicitly declared')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    initial=c.status()
    if (initial.get('projected_water_channel_protocol')!=1 or initial.get('health')!=20
            or initial.get('screen')or initial.get('manual_movement')
            or initial.get('projection_selection',{}).get('key')!=placement_key):
        raise RuntimeError('Current healthy projected-channel owner required')
    if service_ceiling is not None and initial.get('projected_channel_service_ceiling_protocol')!=1:
        raise RuntimeError('Native explicit channel service ceiling protocol required before any input')
    c.checked('select_item',item='minecraft:water_bucket')
    before=c.status();stock=inventory_counts(before)
    if (before.get('hand',{}).get('item')!='minecraft:water_bucket'
            or before.get('hand',{}).get('count')!=1 or stock.get('minecraft:water_bucket',0)<1):
        raise RuntimeError('Selected singleton water bucket required')
    book={'source':source,'placement_key':placement_key,'world_session':c.world,
          'pending':'single_bucket_use','source_confirmed':False,'flow_confirmed':False,
          'complete':False,'automatic_retry_allowed':False,'service_ceiling':service_ceiling}
    write_json(out/'progress.json',book)
    try:
        reply=c.request('bucket_place',pos=source,expected_state='Block{minecraft:air}',
            expected_hand='minecraft:water_bucket',support=[source[0],source[1]-1,source[2]],
            face='up',expected_support_state='Block{minecraft:cobblestone}',
            projected_water_channel=True,placement_key=placement_key,channel_direction='west',channel_length=8,
            **({'channel_service_ceiling':service_ceiling}if service_ceiling is not None else{}))
    finally:
        book['request_id']=c.last;write_json(out/'progress.json',book)
    write_json(out/'native-source-reply.json',reply)
    if not source_receipt(reply,c.last,c.world,source,service_ceiling=service_ceiling):
        raise RuntimeError('Original source use unconfirmed; preserve identity and never repeat')
    book.update(pending=None,source_confirmed=True);write_json(out/'progress.json',book)
    stamps=[];started=time.monotonic();pause_before=getattr(c,'native_recovery_pause_seconds',0.)
    while len(stamps)<2:
        frame=c.checked('scan',min=[source[0]-7,source[1],source[2]],max=source,details=True)
        state=c.status();counts=inventory_counts(state)
        if (state.get('world_session')!=c.world or state.get('health')!=20
                or state.get('manual_movement')or state.get('screen')
                or state.get('projection_selection',{}).get('key')!=placement_key):
            raise RuntimeError('Control changed after confirmed source; no water retry')
        good=(flow_frame(frame,source,c.world)
              and counts.get('minecraft:water_bucket',0)==stock.get('minecraft:water_bucket',0)-1
              and counts.get('minecraft:bucket',0)==stock.get('minecraft:bucket',0)+1)
        stamp=frame.get('scan_ended_at',frame.get('time'))
        if good and type(stamp)is int and (not stamps or stamp>stamps[-1]):
            stamps.append(stamp);write_json(out/f'flow-frame-{len(stamps)}.json',frame)
        elif not good:stamps=[]
        paused=max(0.,getattr(c,'native_recovery_pause_seconds',0.)-pause_before)
        if time.monotonic()-started-paused>10:raise RuntimeError('Source confirmed but downstream incomplete; never replace the source')
        time.sleep(.2)
    book.update(flow_confirmed=True,complete=True,flow_observations=stamps)
    write_json(out/'progress.json',book)
    return book
