"""Read-only evidence for a pinned planter rejection before its first world input."""
from copy import deepcopy
from material_plan import inventory_counts

HOST_CLASS_SHA256='adac3c408825848fe758f0e44cb1ebf3a39099bfb7f9c763c6f451d74e61c2f9'
REASON='Each scoped wheat cell must currently be loaded mature farmland'

def prove(book,reply,event,frames,host_class_sha256):
    pending=book.get('pending')or{};cells=book.get('cells');world=book.get('world_session')
    if(host_class_sha256!=HOST_CLASS_SHA256 or not world or book.get('complete')is not False
            or book.get('inventory_credit')!=0 or pending.get('operation')!='planter_wheat_batch'
            or not cells or pending.get('soils')!=cells or len(frames)!=2
            or reply.get('phase')!='error' or reply.get('detail')!=REASON or reply.get('world_session')!=world
            or event.get('request_id')!=reply.get('id') or event.get('world_session')!=world
            or event.get('op')!='planter_wheat_batch' or event.get('phase')!='error' or event.get('detail')!=REASON
            or(event.get('params')or{}).get('soils')!=cells or event.get('inventory_delta')!={}
            or event.get('position_before')!=event.get('position_after')
            or event.get('health_before')!=20 or event.get('health_after')!=20):
        raise RuntimeError('Exact pinned native wheat preflight rejection is unproved')
    last=reply.get('time');observed=[]
    for frame in frames:
        rows={tuple(v['pos']):v for v in frame.get('blocks',[])}
        if(type(last)is not int or type(frame.get('time'))is not int or frame['time']<=last
                or frame.get('connected')is not True or frame.get('world_session')!=world
                or frame.get('phase')!='done' or frame.get('health')!=20
                or frame.get('manual_movement')is not False or frame.get('planter_active')is not False
                or frame.get('planter_material_batch')!={} or frame.get('navigating')is not False
                or frame.get('guard_busy')is not False or frame.get('control_revision')!=event.get('revision_after')
                or frame.get('scan_cells_read')!=frame.get('scan_total_cells') or frame.get('unloaded_chunks',0)
                or dict(inventory_counts(frame))!=book.get('inventory_before')
                or any(not rows.get(tuple(p),{}).get('state','').startswith('Block{minecraft:farmland}')
                    or rows.get((p[0],p[1]+1,p[2]),{}).get('state')!='Block{minecraft:wheat}[age=7]'for p in cells)):
            raise RuntimeError('Later complete field and unchanged inventory observations do not prove no start')
        last=frame['time'];observed.append(last)
    return {'schema':1,'classification':'pinned_host_preflight_rejected_before_start',
        'request_id':reply['id'],'world_session':world,'host_class_sha256':host_class_sha256,
        'original_pending':deepcopy(pending),'observed_times':observed,'harvest_credit':0,'plant_credit':0,
        'original_request_replayed':False,'original_goal_completed':False}

def record(book,proof):
    if proof.get('schema')!=1 or proof.get('host_class_sha256')!=HOST_CLASS_SHA256 or proof.get('original_pending')!=book.get('pending'):
        raise RuntimeError('Original rejection journal differs; no state changed')
    updated=deepcopy(book);updated['preflight_rejection_proof']=deepcopy(proof)
    updated['known_preflight_not_started']=True;updated['pending']=None
    # The historical batch remains incomplete, with no fabricated harvest or seed debit.
    return updated
