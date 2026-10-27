"""One normal walk into an observed portal; preserve receipts across dimension change."""
import math
import time
from pathlib import Path
from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from safety_interlock import require_unlocked
from material_client import Handoff
from projection_completion import block_state


def shape(rows,root,axis):
    if axis not in('x','z')or len(root)!=3 or any(type(v)is not int for v in root):
        raise ValueError('Integer lower portal cell and real horizontal axis required')
    cells={tuple(r['pos']):r for r in rows};dx,dz=(1,0)if axis=='x'else(0,1)
    core=[[root[0]+u*dx,root[1]+v,root[2]+u*dz]for u in(0,1)for v in(0,1,2)]
    for p in core:
        r=cells.get(tuple(p),{});name,props=block_state(r.get('state','Block{minecraft:air}'))
        if name!='minecraft:nether_portal'or props!={'axis':axis}or r.get('fluid')is not False:
            raise RuntimeError('Present complete ordinary portal required')
    supports=[[root[0]+u*dx,root[1]-1,root[2]+u*dz]for u in(0,1)]
    if any(cells.get(tuple(p),{}).get('state')!='Block{minecraft:obsidian}'for p in supports):
        raise RuntimeError('Actual obsidian footing required before entering')
    return {'core':core,'supports':supports,'entry':[root[0]+.5,root[1]+.02,root[2]+.5]}


def enter(client,root,axis,destination,out,checkpoint,*,timeout=45):
    """No reconnect, synthetic world state, old-world replay, or health-hold clearing."""
    if destination not in('minecraft:overworld','minecraft:the_nether')or not 5<=timeout<=60:
        raise ValueError('Bounded normal portal destination required')
    out=Path(out);out.mkdir(parents=True,exist_ok=False);q=checkpoint()
    if q['dimension']==destination or q['health']!=20 or q.get('screen')or q.get('manual_movement'):
        raise RuntimeError('Healthy actual source dimension required')
    if math.dist(q['pos'],[v+.5 for v in root])>5:raise RuntimeError('Approach the present portal before its one entry action')
    low=[root[0]-1,root[1]-1,root[2]-1];high=[root[0]+2,root[1]+3,root[2]+2]
    scan=client.request('scan',min=low,max=high,details=True)
    if scan.get('phase')!='done'or scan.get('world_session')!=client.world:raise RuntimeError('Portal observation unconfirmed')
    plan=shape(scan['blocks'],root,axis);world=client.world
    book={'source_world':world,'source_dimension':q['dimension'],'destination_dimension':destination,
          'portal':plan,'pending':'one_ordinary_walk_into_portal','walk_request':None,'release_request':None,
          'automatic_reconnect':False,'old_action_replayed':False,'complete':False};path=out/'portal-transit.json';write_json(path,book)
    previous=client.last
    try:
        try:reply=client.request('walk',target=plan['entry'],arrival=.15,restore_flight=True,seconds=15)
        finally:
            book['walk_request']=client.last if client.last!=previous else None;write_json(path,book)
        write_json(out/'native-entry-walk.json',reply)
        if reply.get('phase')!='done':raise RuntimeError('Original portal entry walk not completed; no repeat')
        # Release the old owner while standing in the portal; finishing a ground
        # material lease would instead invoke its ordinary safe-logout policy.
        previous=client.last
        try:reply=client.request('material_job_pause',release=True)
        finally:
            book['release_request']=client.last if client.last!=previous else None;write_json(path,book)
        write_json(out/'native-source-release.json',reply)
        if reply.get('phase')!='done':raise RuntimeError('Source lease release unconfirmed; no replay')
    except Handoff:
        current=read_fresh(client.root);require_unlocked(client.root,current)
        if not current.get('connected')or current.get('world_session')==world or current.get('dimension')!=destination:
            raise
        book['entry_reply_interrupted_by_actual_dimension_change']=True
    finally:
        write_json(path,book)
    end=time.monotonic()+timeout;accepted=[]
    while True:
        current=read_fresh(client.root);require_unlocked(client.root,current)
        if not current.get('connected'):raise Handoff('Portal trip disconnected; no automatic reconnect')
        if current.get('health',0)<19 or current.get('manual_movement'):
            raise Handoff('Portal health or human control changed; do not continue')
        changed=current['world_session']!=world
        if changed and current['dimension']!=destination:raise Handoff('Unplanned dimension change')
        if changed and not current.get('screen')and not current.get('supervision_lease'):
            if not accepted or current['time']!=accepted[-1]['time']:accepted.append(current)
            if len(accepted)>=2:break
        else:accepted=[]
        if time.monotonic()>=end:raise RuntimeError('Original portal transition remains unconfirmed; do not repeat entry')
        time.sleep(.1)
    if client.heartbeat:client.heartbeat.close()
    if getattr(client,'foreground_token',None):client.foreground_token.close()
    book.update(complete=True,pending=None,destination_world=current['world_session'],destination_pos=current['pos'],
                actual_dimension=current['dimension'],health=current['health'],healthy_world_observations=[v['time']for v in accepted])
    write_json(out/'healthy-destination-state.json',current);write_json(path,book);return current
