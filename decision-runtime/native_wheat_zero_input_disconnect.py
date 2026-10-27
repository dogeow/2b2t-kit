"""Prove a retained, stopped wheat batch never reached its first world input.

The pinned host increments harvest_sent BEFORE startDestroyBlock and never
resets that batch on stop. An exact retained last_request, immutable crop set,
zero monotonic counters and unchanged inventory bind this across reconnection.
This never credits a harvest or marks the old job complete.
"""
from copy import deepcopy
from material_plan import inventory_counts

HOST_HASHES={
 'jar':'d51d980dd68ea9f76e0d00c531d2b903657e3879d5ac5b91ff3a47d39ad9653a',
 'auto_planter':'adac3c408825848fe758f0e44cb1ebf3a39099bfb7f9c763c6f451d74e61c2f9',
 'material_batch':'7c3e5fee92e7d907c37d65e054b5347d9932f7605f269727bb6f3b066fcbcfe5'}

def prove(book,unknown,mailbox,identity,frames,hashes):
    cells=book.get('cells');old=book.get('world_session');pending=book.get('pending')or{}
    if(hashes!=HOST_HASHES or not old or book.get('complete')is not False or book.get('inventory_credit')!=0
            or not isinstance(cells,list)or not 1<=len(cells)<=16 or len({tuple(p)for p in cells})!=len(cells)
            or pending.get('operation')!='planter_wheat_batch'or pending.get('soils')!=cells
            or unknown.get('op')!='planter_wheat_batch'or(unknown.get('params')or{}).get('soils')!=cells
            or unknown.get('world_session')!=old or unknown.get('original_request_replayed')is not False
            or mailbox.get('id')!=unknown.get('request_id')or mailbox.get('op')!='planter_wheat_batch'
            or mailbox.get('soils')!=cells or mailbox.get('world_session')!=old
            or mailbox.get('task_session')!=unknown.get('task_session')or identity.get('world_session')!=old
            or identity.get('server')!=mailbox.get('server')or identity.get('dimension')!=mailbox.get('dimension')
            or len(frames)!=2):raise RuntimeError('Pinned original wheat identity or never-sent scope is unproved')
    last=mailbox.get('expires_at');current=None;times=[]
    for f in frames:
        batch=f.get('planter_material_batch')or{};world=f.get('world_session')
        if(type(last)is not int or type(f.get('time'))is not int or f['time']<=last
                or not world or world==old or current is not None and world!=current
                or f.get('connected')is not True or f.get('health')!=20 or f.get('manual_movement')is not False
                or f.get('screen')!=''or f.get('supervision_lease')is not None
                or f.get('planter_active')is not False or f.get('navigating')is not False
                or f.get('planter_status')!='已停止：离开世界'or f.get('last_request')!=unknown['request_id']
                or f.get('server')!=mailbox['server']or f.get('dimension')!=mailbox['dimension']
                or f.get('player_uuid')!=identity.get('player_uuid')or not identity.get('player_uuid')
                or f.get('kit_version')!='2026.10.17.5'or(f.get('safety_hold')or{}).get('active')
                or f.get('health_recovery_hold')or f.get('menu',{}).get('cursor',{}).get('count')!=0
                or dict(inventory_counts(f))!=book.get('inventory_before')
                or batch.get('protocol')!=1 or batch.get('total')!=len(cells)
                or batch.get('grain_before')!=book['inventory_before'].get('minecraft:wheat',0)
                or batch.get('cells_server_confirmed')is not False
                or any(type(batch.get(k))is not int or batch[k]!=0 for k in('harvest_sent','removed_confirmed','plant_sent','replanted_confirmed'))
                or len(batch.get('crop_positions',[]))!=len(cells)
                or {tuple(p)for p in batch.get('crop_positions',[])}!={(p[0],p[1]+1,p[2])for p in cells}):
            raise RuntimeError('Exact retained zero-input batch and current untouched inventory are unproved')
        current=world;last=f['time'];times.append(last)
    return {'schema':1,'classification':'disconnected_before_any_scoped_world_input','request_id':unknown['request_id'],
            'source_world':old,'observed_world':current,'host_hashes':deepcopy(hashes),'original_pending':deepcopy(pending),
            'observed_times':times,'retained_batch':deepcopy(frames[-1]['planter_material_batch']),
            'harvest_credit':0,'plant_credit':0,'old_job_complete':False,'original_request_replayed':False}

def record(book,proof):
    if(proof.get('classification')!='disconnected_before_any_scoped_world_input'or proof.get('host_hashes')!=HOST_HASHES
            or proof.get('original_pending')!=book.get('pending')or proof.get('source_world')!=book.get('world_session')):
        raise RuntimeError('Original never-sent journal changed')
    result=deepcopy(book);result.update(pending=None,known_no_world_input=True,no_world_input_disconnect_proof=deepcopy(proof));return result
